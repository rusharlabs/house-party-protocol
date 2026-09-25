"""Typed-decision records: a contract any outside decider can fill, and the ruler that measures it.

The harness calls no model, and neither does this module. A classifier, a hosted typed-decision
model, a local model or a person may answer a small question ("which of these options?") somewhere
else; this module defines what that answer must look like to be recorded (`hpp.decision/v1`) and
measures a decider against labelled cases (`hpp decide eval`).

Three rules carry the design:

- **Advisory only.** `authority` is always `advisory`. With `direction: raise-only` the effective
  value is the higher of what was declared and what was advised, on the question's own ordered
  options — advice can raise caution, never lower it (the routing floor already works this way).
- **Abstention and failure are outcomes, not errors.** `abstention` and `instrument-failure` carry
  no value, and neither ever changes a declared value. A timeout, an HTML page or a malformed
  answer is an instrument failure, never a verdict.
- **Re-derivable from disk.** A model's answer is not reproducible by asking again, so a model
  record names the pinned version that served it and the hash of the raw response kept beside it.
  The judged text itself never enters the record — only its hash — and secret-like text is refused.

Version 1 measures `choice` questions only: a label is either the expected one or not. Numeric
answers (a score, a probability of yes) need a definition of "correct" that this ruler does not
make up, so they are refused rather than reported as a vacuous 0%.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Optional

from hpp._process import MAX_TIMEOUT, run_bounded, stderr_tail, valid_timeout
from hpp.context import _SECRET_PATTERN

SCHEMA = "hpp.decision/v1"
SUITE_SCHEMA = "hpp.decision-suite/v1"
REPORT_SCHEMA = "hpp.decision-eval/v1"
KINDS = ("choice",)
METHODS = ("regex", "lexical", "human", "replay", "local-model", "external-model", "panel")
MODEL_METHODS = ("local-model", "external-model")
RULE_METHODS = ("regex", "lexical", "human")
# Why (House Session, 2.7.0): a panel's verdict is the judge's answer after a counted deliberation;
# it has no measured confidence, and its "raw response" is the sealed deliberation record.
NO_CONFIDENCE_METHODS = RULE_METHODS + ("panel",)
STATUSES = ("recommendation", "abstention", "instrument-failure")
DIRECTIONS = ("raise-only", "informational")
ABSTAIN = "abstain"
MAX_OPTIONS = 255
CURVE_FLOORS = (0.5, 0.6, 0.7, 0.8, 0.9)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
# Why: an alias ("-latest", "~vendor/...", "preview") is re-pointed by the vendor without notice;
# a record that names an alias cannot say which model answered, so it is refused.
_ALIAS = re.compile(r"latest|preview|^~", re.IGNORECASE)


class DecisionError(ValueError):
    """A decision record, question or suite does not satisfy the contract."""


def is_alias(model: str) -> bool:
    """True when a model id is a moving alias rather than a pinned version."""
    return bool(_ALIAS.search(model or ""))


def digest(text: str) -> str:
    """Hash of the judged text. Secret-like text is refused before it is hashed or sent anywhere."""
    if not isinstance(text, str):
        raise DecisionError("state must be text")
    if _SECRET_PATTERN.search(text):
        raise DecisionError("state looks like it carries a secret; it is never hashed into a record or sent to a decider")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def question_digest(question: dict[str, Any]) -> str:
    """Hash of everything that changes the answer: the options AND the wording."""
    return normalise_question(question, check_digest=False)["sha256"]


def normalise_question(question: Any, check_digest: bool = True) -> dict[str, Any]:
    if not isinstance(question, dict):
        raise DecisionError("question must be an object")
    question_id = question.get("id")
    if not isinstance(question_id, str) or not question_id:
        raise DecisionError("question needs an id")
    if question.get("kind") not in KINDS:
        raise DecisionError("question kind must be 'choice'; score and noul answers are not measurable in v1")
    options = question.get("options")
    if not isinstance(options, list) or not all(isinstance(item, str) and item for item in options):
        raise DecisionError("question options must be a list of non-empty strings")
    if len(set(options)) != len(options):
        raise DecisionError("question options must be unique")
    if ABSTAIN in options:
        raise DecisionError(f"'{ABSTAIN}' is an outcome, not an option")
    if not 2 <= len(options) <= MAX_OPTIONS:
        raise DecisionError(f"a choice question needs 2 to {MAX_OPTIONS} options")
    ladder = question.get("ladder", False)
    if not isinstance(ladder, bool):
        raise DecisionError("question ladder must be true or false")
    instructions = question.get("instructions")
    if instructions is not None and not isinstance(instructions, str):
        raise DecisionError("question instructions must be text")
    criteria = question.get("criteria")
    if criteria is not None and (not isinstance(criteria, dict) or set(criteria) - set(options)
                                 or not all(isinstance(item, str) for item in criteria.values())):
        raise DecisionError("question criteria must describe only declared options, as text")
    normalised = {"id": question_id, "kind": "choice", "options": list(options), "ladder": ladder,
                  "instructions": instructions, "criteria": criteria}
    computed = hashlib.sha256(json.dumps(normalised, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=False).encode("utf-8")).hexdigest()
    if check_digest and "sha256" in question and question["sha256"] != computed:
        raise DecisionError("question sha256 does not match its options and wording; the question was edited after hashing")
    normalised["sha256"] = computed
    return normalised


def _unit(value: Any, label: str) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
        raise DecisionError(f"{label} must be a number between 0 and 1, or null")
    return float(value)


def _hex(value: Any, label: str) -> str:
    # Why (review 2026-09-25): `$` also matches before a trailing newline, so `match` accepted a
    # 65-character value and sealed it verbatim. `fullmatch` takes the whole string or nothing.
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        raise DecisionError(f"{label} must be a 64-character lowercase sha256")
    return value


def validate(record: Any) -> dict[str, Any]:
    """Return the normalised record, or raise DecisionError naming the first broken rule."""
    if not isinstance(record, dict):
        raise DecisionError("a decision record must be an object")
    if record.get("schema") != SCHEMA:
        raise DecisionError(f"schema must be {SCHEMA}")
    question = normalise_question(record.get("question"))
    state = _hex(record.get("state_sha256"), "state_sha256")
    method = record.get("method")
    if method not in METHODS:
        raise DecisionError(f"method must be one of {', '.join(METHODS)}")
    if record.get("authority") != "advisory":
        raise DecisionError("authority must be 'advisory': a decision record never grants or approves anything")
    direction = record.get("direction")
    if direction not in DIRECTIONS:
        raise DecisionError(f"direction must be one of {', '.join(DIRECTIONS)}")
    if direction == "raise-only" and not question["ladder"]:
        raise DecisionError("raise-only needs an ordered question (ladder: true, options from low to high)")
    outcome = record.get("outcome")
    if not isinstance(outcome, dict) or outcome.get("status") not in STATUSES:
        raise DecisionError(f"outcome status must be one of {', '.join(STATUSES)}")
    status = outcome["status"]
    value = outcome.get("value")
    if status == "recommendation":
        if value not in question["options"]:
            raise DecisionError(f"value {value!r} is not one of the options")
    elif value is not None:
        raise DecisionError(f"{'abstention' if status == 'abstention' else 'an instrument failure'} carries no value")
    error = outcome.get("error")
    if status == "instrument-failure" and (not isinstance(error, str) or not error.strip()):
        raise DecisionError("an instrument failure must say what failed (outcome.error)")
    confidence = _unit(outcome.get("confidence"), "confidence")
    if confidence is not None and method in NO_CONFIDENCE_METHODS:
        raise DecisionError(f"a {method} decision has no confidence; publish null instead of inventing one")
    probabilities = outcome.get("probabilities")
    if probabilities is not None:
        if not isinstance(probabilities, dict) or set(probabilities) != set(question["options"]):
            raise DecisionError("probabilities must name every option exactly once")
        values = [_unit(item, "each probability") for item in probabilities.values()]
        if abs(sum(values) - 1.0) > 1e-3:
            raise DecisionError("probabilities must sum to 1")
    provider = record.get("provider")
    if provider is not None:
        if not isinstance(provider, dict) or not isinstance(provider.get("id"), str) or not provider["id"]:
            raise DecisionError("provider must be an object with the non-empty id the user declared")
        served = provider.get("model_served")
        if served is not None and (not isinstance(served, str) or not served or is_alias(served)):
            raise DecisionError("provider.model_served must be the pinned version that answered, never an alias")
    raw = record.get("raw_response_sha256")
    if method in MODEL_METHODS:
        if provider is None:
            raise DecisionError("a model decision needs the provider id the user declared")
        if not provider.get("model_served"):
            raise DecisionError("provider.model_served is missing: a model decision names the pinned version that answered")
        if status != "instrument-failure" or raw is not None:
            raw = _hex(raw, "raw_response_sha256")
    elif method == "panel":
        raw = _hex(raw, "raw_response_sha256 (the sealed hpp.deliberation/v1 record)")
    elif raw is not None:
        raw = _hex(raw, "raw_response_sha256")
    declared = record.get("declared")
    if declared is not None:
        if direction != "raise-only":
            raise DecisionError("declared is only meaningful with direction raise-only")
        if declared not in question["options"]:
            raise DecisionError(f"declared {declared!r} is not one of the options")
    normalised = {
        "schema": SCHEMA, "question": question, "state_sha256": state, "method": method,
        "outcome": {"status": status, "value": value, "confidence": confidence},
        "authority": "advisory", "direction": direction,
    }
    if probabilities is not None:
        normalised["outcome"]["probabilities"] = {key: float(item) for key, item in probabilities.items()}
    if status == "instrument-failure":
        normalised["outcome"]["error"] = error
    if provider is not None:
        normalised["provider"] = {"id": provider["id"], "model_served": provider.get("model_served")}
    if raw is not None:
        normalised["raw_response_sha256"] = raw
    if declared is not None:
        normalised["declared"] = declared
    usage = record.get("usage")
    if isinstance(usage, dict):
        normalised["usage"] = {key: usage[key] for key in sorted(usage)
                               if usage[key] is None or (isinstance(usage[key], (int, float)) and not isinstance(usage[key], bool))}
    return normalised


def effective(record: dict[str, Any]) -> dict[str, Any]:
    """What a consumer may act on. Advice raises a declared value; it never lowers or replaces it."""
    outcome = record["outcome"]
    declared = record.get("declared")
    advised = outcome["value"] if outcome["status"] == "recommendation" else None
    if record["direction"] == "raise-only" and declared is not None:
        options = record["question"]["options"]
        if advised is not None and options.index(advised) > options.index(declared):
            return {"value": advised, "action": "raised", "declared": declared}
        return {"value": declared, "action": "kept", "declared": declared}
    return {"value": advised, "action": "advised" if advised is not None else "none", "declared": declared}


# --------------------------------------------------------------------------- the ruler

def load_decision_suite(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        raise DecisionError(f"decision suite not found: {path}")
    raw = path.read_bytes()
    try:
        suite = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DecisionError(f"invalid decision suite JSON: {exc}") from exc
    if not isinstance(suite, dict) or suite.get("schema") != SUITE_SCHEMA:
        raise DecisionError(f"decision suite schema must be {SUITE_SCHEMA}")
    question = normalise_question(suite.get("question"))
    cases = suite.get("cases")
    if not isinstance(cases, list) or not cases:
        raise DecisionError("decision suite needs non-empty cases")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not case["id"]:
            raise DecisionError("every case needs an id")
        if case["id"] in seen:
            raise DecisionError(f"duplicate case id: {case['id']}")
        seen.add(case["id"])
        if not isinstance(case.get("state"), str):
            raise DecisionError(f"case {case['id']} needs a text state")
        expected = case.get("expected")
        if expected != ABSTAIN and expected not in question["options"]:
            raise DecisionError(f"case {case['id']} expects {expected!r}, which is neither an option nor '{ABSTAIN}'")
    floor = _unit(suite.get("confidence_floor", 0.6), "confidence_floor")
    return {**suite, "question": question, "confidence_floor": floor}, hashlib.sha256(raw).hexdigest()


def _ask(command: list[str], question: dict[str, Any], state: str, timeout: float) -> dict[str, Any]:
    # Why (Windows console, 2026-09-23): a child reading stdin in its locale codepage (cp1252) decoded
    # accented text differently, so the state it hashed was not the state the case holds and every
    # non-ASCII case became an instrument failure. ASCII-escaped JSON reads the same in any codepage.
    request = json.dumps({"question": question, "state": state}, ensure_ascii=True)
    state, exit_code, stdout, stderr = run_bounded(command, timeout=timeout, stdin=request.encode("ascii"))
    if state == "timeout":
        raise DecisionError(f"decider exceeded {timeout:g}s")
    if state == "could-not-start":
        raise DecisionError("decider could not start: check the command and that it is on PATH")
    if exit_code != 0:
        raise DecisionError(f"decider exited {exit_code}: {stderr_tail(stderr)}")
    text = stdout.decode("utf-8", errors="replace")
    if not text.strip():
        raise DecisionError("decider printed nothing")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise DecisionError(f"decider output is not JSON: {exc.msg}")


def _curve(decided: list[dict[str, Any]], total: int) -> Any:
    # Why: a single default confidence floor is not an operating point; it is somebody else's
    # guess about somebody else's task. With confidences present, publish coverage and selective
    # accuracy at each floor so the user chooses one.
    pool = [item for item in decided if item["confidence"] is not None]
    if not pool:
        return "not-measured"
    curve = []
    for floor in CURVE_FLOORS:
        kept = [item for item in pool if item["confidence"] >= floor]
        curve.append({"floor": floor, "decided": len(kept), "coverage": len(kept) / total,
                      "selective_accuracy": (sum(1 for item in kept if item["correct"]) / len(kept)) if kept else None})
    return curve


def run_decision_suite(path: Path, decider_command: Optional[list[str]] = None, timeout: float = 10.0,
                       min_selective_accuracy: float = 0.9, max_confident_errors: int = 0,
                       max_failures: int = 0) -> dict[str, Any]:
    """Measure a decider with abstention as a first-class outcome. No model is called here."""
    if not valid_timeout(timeout):
        raise DecisionError(f"timeout must be a positive, finite number of seconds, at most {MAX_TIMEOUT:g}")
    suite, suite_hash = load_decision_suite(Path(path))
    question = suite["question"]
    floor = suite["confidence_floor"]
    results: list[dict[str, Any]] = []
    for case in suite["cases"]:
        try:
            state_hash = digest(case["state"])
        except DecisionError as exc:
            raise DecisionError(f"case {case['id']}: {exc}") from exc
        entry: dict[str, Any] = {"id": case["id"], "expected": case["expected"]}
        try:
            if decider_command:
                raw_record = _ask(decider_command, question, case["state"], timeout)
            elif "record" in case:
                raw_record = case["record"]
            else:
                raise DecisionError("case has no replay record and no decider command was given")
            record = validate(raw_record)
            if record["question"]["sha256"] != question["sha256"]:
                raise DecisionError("record answered a different question")
            if record["state_sha256"] != state_hash:
                raise DecisionError("record judged a different state than the case holds")
        except DecisionError as exc:
            entry.update({"status": "instrument-failure", "value": None, "confidence": None,
                          "correct": None, "error": str(exc)})
            results.append(entry)
            continue
        outcome = record["outcome"]
        entry.update({"status": outcome["status"], "value": outcome["value"], "confidence": outcome["confidence"]})
        if outcome["status"] == "instrument-failure":
            entry.update({"correct": None, "error": outcome.get("error")})
        elif outcome["status"] == "abstention":
            entry["correct"] = case["expected"] == ABSTAIN
        else:
            entry["correct"] = outcome["value"] == case["expected"]
            if "probabilities" in outcome:
                entry["probabilities"] = outcome["probabilities"]
        results.append(entry)
    decided = [item for item in results if item["status"] == "recommendation"]
    abstained = [item for item in results if item["status"] == "abstention"]
    failed = [item for item in results if item["status"] == "instrument-failure"]
    right = [item for item in decided if item["correct"]]
    confident = [item for item in decided if not item["correct"] and item["confidence"] is not None
                 and floor is not None and item["confidence"] >= floor]
    errors: dict[str, int] = {}
    for item in decided:
        if not item["correct"]:
            errors[item["expected"]] = errors.get(item["expected"], 0) + 1
    scorable = [item for item in decided if item["expected"] != ABSTAIN]
    if scorable and all("probabilities" in item for item in scorable):
        brier: Any = sum(
            sum((item["probabilities"].get(option, 0.0) - (1.0 if option == item["expected"] else 0.0)) ** 2
                for option in question["options"])
            for item in scorable) / len(scorable)
    else:
        brier = "not-measured"
    total = len(results)
    selective = len(right) / len(decided) if decided else None
    metrics = {
        "total": total, "decided": len(decided), "abstained": len(abstained), "failed": len(failed),
        "coverage": len(decided) / total,
        "selective_accuracy": selective,
        "correct_abstentions": sum(1 for item in abstained if item["correct"]),
        "missed_abstentions": sum(1 for item in decided if item["expected"] == ABSTAIN),
        "confident_errors": len(confident),
        "errors_by_expected": dict(sorted(errors.items())),
        "brier": brier,
        "coverage_curve": _curve(decided, total),
    }
    if selective is None:
        passed = False
        reason = (f"no decision was made ({len(abstained)} abstained, {len(failed)} instrument failure(s)); "
                  "there is no accuracy to measure")
    elif len(failed) > max_failures:
        passed, reason = False, f"{len(failed)} instrument failure(s) > {max_failures}"
    elif selective < min_selective_accuracy:
        passed, reason = False, f"selective accuracy {selective:.3f} < {min_selective_accuracy:g}"
    elif len(confident) > max_confident_errors:
        passed, reason = False, f"{len(confident)} confident error(s) > {max_confident_errors}"
    else:
        passed, reason = True, "every threshold held"
    return {
        "schema": REPORT_SCHEMA,
        "suite": {"name": suite.get("name", Path(path).stem), "version": suite.get("version"), "sha256": suite_hash},
        "question": {"id": question["id"], "kind": question["kind"], "sha256": question["sha256"]},
        "decider": {"mode": "command" if decider_command else "replay", "command": list(decider_command or [])},
        "confidence_floor": floor,
        "cases": results,
        "metrics": metrics,
        "gate": {"passed": passed, "reason": reason, "min_selective_accuracy": min_selective_accuracy,
                 "max_confident_errors": max_confident_errors, "max_failures": max_failures},
    }


def exit_for(report: dict[str, Any]) -> int:
    return 0 if report["gate"]["passed"] else 1
