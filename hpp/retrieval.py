"""Retrieval ruler: measure a retriever the user declares, apart from any generation step.

The harness runs no index and calls no model, and neither does this module. A retriever is whatever
command the user names: it reads `{"query": ..., "k": ...}` on stdin and prints ranked ids. This
module scores the top k of each answer against the ids a suite marks relevant
(`hpp.retrieval-suite/v1`) and writes a report (`hpp.retrieval-eval/v1`). Whether a good answer can
be generated from what was retrieved is a separate question, and it is not asked here.

Three rules carry the design:

- **A measured zero is not a failure.** A retriever that answers and finds nothing relevant scores
  0 on that case. A timeout, a crash, an HTML page or a malformed answer is an `instrument-failure`:
  it is counted apart and never scored.
- **Means over measured cases only.** With no measured case the metrics are `None` and the gate
  says why, never 0%.
- **The ranking is the order the retriever printed.** A `score` is checked, never used to re-sort:
  some retrievers print similarities (higher is better), others distances (lower is better).

Relevance is binary and labelled per id. The id a retriever returns must be the unit the suite
labels (a document, a chunk, a passage): a duplicate id in one answer is refused, because counting
it twice would inflate precision and nDCG.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from hpp._process import MAX_TIMEOUT, run_bounded, stderr_tail, valid_timeout
from hpp.context import _SECRET_PATTERN

SUITE_SCHEMA = "hpp.retrieval-suite/v1"
REPORT_SCHEMA = "hpp.retrieval-eval/v1"
DEFAULT_K = 5
MEASURED = "measured"
FAILURE = "instrument-failure"


class RetrievalError(ValueError):
    """A retrieval suite, an argument or a retriever's answer does not satisfy the contract."""


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RetrievalError(f"{label} must be an integer >= 1")
    return value


def load_retrieval_suite(path: Path) -> tuple[dict[str, Any], str]:
    """Return the validated suite and the sha256 of its bytes, or raise naming the first broken rule."""
    path = Path(path)
    if not path.is_file():
        raise RetrievalError(f"retrieval suite not found: {path}")
    raw = path.read_bytes()
    try:
        suite = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RetrievalError(f"invalid retrieval suite JSON: {exc}") from exc
    if not isinstance(suite, dict) or suite.get("schema") != SUITE_SCHEMA:
        raise RetrievalError(f"retrieval suite schema must be {SUITE_SCHEMA}")
    if not isinstance(suite.get("version"), str) or not suite["version"]:
        raise RetrievalError("retrieval suite needs a string version")
    name = suite.get("name", path.stem)
    if not isinstance(name, str) or not name:
        raise RetrievalError("retrieval suite name must be text")
    k = _positive_int(suite.get("k", DEFAULT_K), "k")
    cases = suite.get("cases")
    if not isinstance(cases, list) or not cases:
        raise RetrievalError("retrieval suite needs non-empty cases")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not case["id"]:
            raise RetrievalError("every case needs an id")
        case_id = case["id"]
        if case_id in seen:
            raise RetrievalError(f"duplicate case id: {case_id}")
        seen.add(case_id)
        query = case.get("query")
        if not isinstance(query, str) or not query.strip():
            raise RetrievalError(f"case {case_id} needs a non-empty text query")
        if _SECRET_PATTERN.search(query):
            raise RetrievalError(f"case {case_id}: the query looks like it carries a secret; "
                                 "it is never sent to a retriever")
        relevant = case.get("relevant")
        if not isinstance(relevant, list) or not relevant:
            raise RetrievalError(f"case {case_id} needs a non-empty list of relevant ids")
        if not all(isinstance(item, str) and item for item in relevant):
            raise RetrievalError(f"case {case_id}: relevant ids must be non-empty strings")
        if len(set(relevant)) != len(relevant):
            raise RetrievalError(f"case {case_id}: relevant ids must be unique")
    return {**suite, "name": name, "k": k}, hashlib.sha256(raw).hexdigest()


def _finite(value: float) -> bool:
    try:
        return math.isfinite(value)
    except OverflowError:  # an int too large for a float
        return False


def ranked_ids(answer: Any) -> list[str]:
    """The ids a retriever returned, in its order: a list of ids, or `{"results": [{"id", "score"}, ...]}`."""
    if isinstance(answer, dict):
        if "results" not in answer:
            raise RetrievalError("answer is an object without a 'results' list")
        answer = answer["results"]
    if not isinstance(answer, list):
        raise RetrievalError("results must be a list of ids or of {id, score} objects")
    ids: list[str] = []
    for position, item in enumerate(answer, 1):
        if isinstance(item, dict):
            score = item.get("score")
            if score is not None and (isinstance(score, bool) or not isinstance(score, (int, float))
                                      or not _finite(score)):
                raise RetrievalError(f"result {position} has a score that is not a finite number")
            item = item.get("id")
        if not isinstance(item, str) or not item:
            raise RetrievalError(f"result {position} has no non-empty string id")
        ids.append(item)
    repeated = sorted(item for item, count in Counter(ids).items() if count > 1)
    if repeated:
        raise RetrievalError(f"duplicate id {repeated[0]!r} in results: return each labelled unit once")
    return ids


def case_metrics(ranked: list[str], relevant: list[str], k: int) -> dict[str, float]:
    """hit, recall, precision, reciprocal rank and binary nDCG over the top k of one ranking."""
    wanted = set(relevant)
    ranks = [rank for rank, item in enumerate(ranked[:k], 1) if item in wanted]
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(k, len(wanted)) + 1))
    return {
        "hit_at_k": 1.0 if ranks else 0.0,
        "recall_at_k": len(ranks) / len(wanted),
        # Why: precision divides by k, not by what came back. One lucky id in a short answer is not
        # 100% precise, and an empty answer then has a defined precision of 0 instead of 0/0.
        "precision_at_k": len(ranks) / k,
        "reciprocal_rank": 1 / ranks[0] if ranks else 0.0,
        "ndcg_at_k": sum(1 / math.log2(rank + 1) for rank in ranks) / ideal,
    }


def _ask(command: list[str], query: str, k: int, timeout: float) -> Any:
    # Why (Windows console, 2026-09-23, same lesson as hpp decide eval): a child reading stdin in its
    # locale codepage (cp1252) decoded accented text differently. ASCII-escaped JSON reads the same in
    # any codepage. The case id is not sent: a retriever keyed on it could replay answers.
    request = json.dumps({"query": query, "k": k}, ensure_ascii=True)
    state, exit_code, stdout, stderr = run_bounded(command, timeout=timeout, stdin=request.encode("ascii"))
    if state == "timeout":
        raise RetrievalError(f"retriever exceeded {timeout:g}s")
    if state == "could-not-start":
        raise RetrievalError("retriever could not start: check the command and that it is on PATH")
    if exit_code != 0:
        raise RetrievalError(f"retriever exited {exit_code}: {stderr_tail(stderr)}")
    text = stdout.decode("utf-8", errors="replace")
    if not text.strip():
        raise RetrievalError("retriever printed nothing")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RetrievalError(f"retriever output is not JSON: {exc.msg}") from None


def _check_arguments(retriever_command: Any, k: Any, timeout: Any, min_recall: Any, max_failures: Any) -> None:
    if retriever_command is not None and (not isinstance(retriever_command, list) or not retriever_command
                                          or not all(isinstance(item, str) and item for item in retriever_command)):
        raise RetrievalError("retriever command must be a non-empty argv list of strings")
    if k is not None:
        _positive_int(k, "k")
    if not valid_timeout(timeout):
        raise RetrievalError(f"timeout must be a positive, finite number of seconds, at most {MAX_TIMEOUT:g}")
    if isinstance(min_recall, bool) or not isinstance(min_recall, (int, float)) or not 0.0 <= min_recall <= 1.0:
        raise RetrievalError("min_recall must be a number between 0 and 1")
    if isinstance(max_failures, bool) or not isinstance(max_failures, int) or max_failures < 0:
        raise RetrievalError("max_failures must be an integer >= 0")


def run_retrieval_suite(path: Path, retriever_command: Optional[list[str]] = None, k: Optional[int] = None,
                        timeout: float = 10.0, min_recall: float = 0.8, max_failures: int = 0) -> dict[str, Any]:
    """Measure a retriever (a command, or the suite's recorded results) against labelled relevant ids."""
    _check_arguments(retriever_command, k, timeout, min_recall, max_failures)
    suite, suite_hash = load_retrieval_suite(Path(path))
    cut = k if k is not None else suite["k"]
    results: list[dict[str, Any]] = []
    for case in suite["cases"]:
        entry: dict[str, Any] = {"id": case["id"]}
        try:
            if retriever_command is not None:
                answer = _ask(retriever_command, case["query"], cut, timeout)
            elif "results" in case:
                answer = case["results"]
            else:
                raise RetrievalError("case has no replay results and no retriever command was given")
            ranked = ranked_ids(answer)
        except RetrievalError as exc:
            entry.update({"status": FAILURE, "error": str(exc), "metrics": None})
            results.append(entry)
            continue
        top = ranked[:cut]
        wanted = set(case["relevant"])
        entry.update({"status": MEASURED, "returned": top, "relevant_hits": [item for item in top if item in wanted],
                      "metrics": case_metrics(ranked, case["relevant"], cut)})
        results.append(entry)
    measured = [entry["metrics"] for entry in results if entry["status"] == MEASURED]
    failed = len(results) - len(measured)

    def mean(key: str) -> Optional[float]:
        return sum(item[key] for item in measured) / len(measured) if measured else None

    metrics = {
        "total": len(results), "measured": len(measured), "failed": failed,
        "hit_at_k": mean("hit_at_k"), "recall_at_k": mean("recall_at_k"), "precision_at_k": mean("precision_at_k"),
        "mrr": mean("reciprocal_rank"), "ndcg_at_k": mean("ndcg_at_k"),
    }
    recall = metrics["recall_at_k"]
    if recall is None:
        passed = False
        reason = (f"no case was measured ({failed} instrument failure{'' if failed == 1 else 's'}); "
                  "there is no recall to measure")
    elif failed > max_failures:
        passed, reason = False, f"{failed} instrument failure(s) > {max_failures}"
    elif recall < min_recall:
        passed, reason = False, f"mean recall@k {recall:.3f} < {min_recall:g}"
    else:
        passed, reason = True, "every threshold held"
    return {
        "schema": REPORT_SCHEMA,
        "suite": {"name": suite["name"], "version": suite["version"], "sha256": suite_hash, "k": suite["k"]},
        "retriever": {"mode": "command" if retriever_command is not None else "replay",
                      "command": list(retriever_command or [])},
        "k": cut,
        "cases": results,
        "metrics": metrics,
        "gate": {"passed": passed, "reason": reason,
                 "thresholds": {"min_recall": float(min_recall), "max_failures": max_failures}},
    }


def exit_for(report: dict[str, Any]) -> int:
    return 0 if report["gate"]["passed"] else 1
