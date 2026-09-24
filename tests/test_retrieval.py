"""The retrieval ruler (`hpp.retrieval-eval/v1`): a retriever the user declares, measured apart from generation.

The harness still calls no model and runs no index of its own. It sends each labelled query to the
command the user names, reads back ranked ids, and scores the top k against the ids the suite marks
relevant. Three rules carry the file:

- a measured zero (the retriever answered, and found nothing relevant) and an instrument failure
  (it timed out, crashed, printed HTML) are different outcomes, and only the first is scored;
- aggregates are means over MEASURED cases, and no measured case is no sample, never 0%;
- a query that looks like it carries a secret is refused before anything runs.

The CONTROLE tests prove the ruler can pass: without them, a runner that fails everything would
satisfy every refusal below.
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import pytest

from hpp.retrieval import RetrievalError, exit_for, load_retrieval_suite, ranked_ids, run_retrieval_suite

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = PRODUCT_ROOT / "examples" / "retrieval"


def _body(cases=None, k=5) -> dict:
    return {"schema": "hpp.retrieval-suite/v1", "name": "t", "version": "1", "k": k,
            "cases": cases if cases is not None else [{"id": "a", "query": "how do I rotate the logs",
                                                      "relevant": ["d1"], "results": ["d1"]}]}


def _suite(tmp_path: Path, cases=None, k=5) -> Path:
    path = tmp_path / "suite.json"
    path.write_text(json.dumps(_body(cases, k)), encoding="utf-8")
    return path


def _printer(tmp_path: Path, stdout, exit_code: int = 0, stderr: str = "", name: str = "retriever.py") -> list[str]:
    """A stand-in retriever that reads the request and prints exactly `stdout` (text or raw bytes)."""
    write = f"sys.stdout.buffer.write({stdout!r})" if isinstance(stdout, bytes) else f"sys.stdout.write({stdout!r})"
    script = tmp_path / name
    script.write_text(f"import sys\nsys.stdin.read()\n{write}\nsys.stdout.flush()\n"
                      f"sys.stderr.write({stderr!r})\nsys.exit({exit_code})\n", encoding="utf-8")
    return [sys.executable, "-S", str(script)]


# --------------------------------------------------------------------------- the metrics

def test_metrics_on_a_hand_computed_case(tmp_path):
    # relevant = {d1, d3, d9}, k = 4, the retriever ranked d2 d1 d5 d3 | d9 (d9 is fifth: outside the cut)
    # hits in the top 4: d1 at rank 2, d3 at rank 4
    # hit@4 = 1 · recall@4 = 2/3 · precision@4 = 2/4 · reciprocal rank = 1/2
    # DCG@4  = 1/log2(2+1) + 1/log2(4+1)               = 0.63093 + 0.43068      = 1.06161
    # IDCG@4 = 1/log2(1+1) + 1/log2(2+1) + 1/log2(3+1) = 1 + 0.63093 + 0.5      = 2.13093
    #          (min(k=4, 3 relevant) = 3 ideal positions)
    # nDCG@4 = 1.06161 / 2.13093                                                 = 0.49819
    suite = _suite(tmp_path, [{"id": "q1", "query": "where are backups kept", "relevant": ["d1", "d3", "d9"],
                               "results": ["d2", "d1", "d5", "d3", "d9"]}], k=4)
    case = run_retrieval_suite(suite)["cases"][0]
    assert case["status"] == "measured"
    assert case["returned"] == ["d2", "d1", "d5", "d3"]
    assert case["relevant_hits"] == ["d1", "d3"]
    metrics = case["metrics"]
    assert metrics["hit_at_k"] == 1.0
    assert metrics["recall_at_k"] == pytest.approx(2 / 3)
    assert metrics["precision_at_k"] == pytest.approx(0.5)
    assert metrics["reciprocal_rank"] == pytest.approx(0.5)
    ideal = 1 / math.log2(2) + 1 / math.log2(3) + 1 / math.log2(4)
    assert metrics["ndcg_at_k"] == pytest.approx((1 / math.log2(3) + 1 / math.log2(5)) / ideal)
    assert metrics["ndcg_at_k"] == pytest.approx(0.49819, abs=1e-5)


def test_nothing_relevant_in_the_top_k_is_a_measured_zero(tmp_path):
    suite = _suite(tmp_path, [{"id": "a", "query": "q", "relevant": ["d9"], "results": ["d1", "d2"]}], k=2)
    case = run_retrieval_suite(suite)["cases"][0]
    assert case["status"] == "measured"
    assert case["metrics"] == {"hit_at_k": 0.0, "recall_at_k": 0.0, "precision_at_k": 0.0,
                               "reciprocal_rank": 0.0, "ndcg_at_k": 0.0}


def test_results_beyond_k_are_not_scored_and_k_can_be_overridden(tmp_path):
    suite = _suite(tmp_path, [{"id": "a", "query": "q", "relevant": ["d2"], "results": ["d1", "d2"]}], k=5)
    wide = run_retrieval_suite(suite)
    assert wide["k"] == 5 and wide["cases"][0]["metrics"]["recall_at_k"] == 1.0
    narrow = run_retrieval_suite(suite, k=1)
    assert narrow["k"] == 1 and narrow["suite"]["k"] == 5
    assert narrow["cases"][0]["returned"] == ["d1"]
    assert narrow["cases"][0]["metrics"]["recall_at_k"] == 0.0


def test_aggregates_are_means_over_measured_cases_only(tmp_path):
    suite = _suite(tmp_path, [
        {"id": "a", "query": "q", "relevant": ["x"], "results": ["x"]},   # recall 1, rr 1, precision 1/3
        {"id": "b", "query": "q", "relevant": ["y"], "results": []},      # answered nothing: a measured 0
        {"id": "c", "query": "q", "relevant": ["z"]},                     # nothing to replay: not measured
    ], k=3)
    report = run_retrieval_suite(suite, max_failures=1)
    metrics = report["metrics"]
    assert (metrics["total"], metrics["measured"], metrics["failed"]) == (3, 2, 1)
    assert metrics["recall_at_k"] == pytest.approx(0.5)          # (1 + 0) / 2 measured, never / 3
    assert metrics["mrr"] == pytest.approx(0.5)
    assert metrics["precision_at_k"] == pytest.approx((1 / 3) / 2)
    assert report["cases"][1]["status"] == "measured" and report["cases"][1]["metrics"]["recall_at_k"] == 0.0
    failed = report["cases"][2]
    assert failed["status"] == "instrument-failure" and failed["metrics"] is None
    assert "no replay results" in failed["error"]
    assert report["gate"]["passed"] is False and "recall@k 0.500 < 0.8" in report["gate"]["reason"]


def test_no_case_measured_is_no_sample_never_zero(tmp_path):
    suite = _suite(tmp_path, [{"id": "a", "query": "q", "relevant": ["x"]},
                              {"id": "b", "query": "q", "relevant": ["y"], "results": "d1"}])
    report = run_retrieval_suite(suite, max_failures=5)
    metrics = report["metrics"]
    assert (metrics["measured"], metrics["failed"]) == (0, 2)
    for key in ("hit_at_k", "recall_at_k", "precision_at_k", "mrr", "ndcg_at_k"):
        assert metrics[key] is None, key
    assert report["gate"]["passed"] is False
    assert "no case was measured (2 instrument failures)" in report["gate"]["reason"]
    assert exit_for(report) == 1


# --------------------------------------------------------------------------- the gate

def test_CONTROLE_a_perfect_replay_passes_the_gate(tmp_path):
    suite = _suite(tmp_path, [
        {"id": "a", "query": "q1", "relevant": ["d1"], "results": ["d1"]},
        {"id": "b", "query": "q2", "relevant": ["d2", "d3"], "results": [{"id": "d3", "score": 0.9}, {"id": "d2", "score": 0.4}]},
    ], k=2)
    report = run_retrieval_suite(suite)
    assert report["schema"] == "hpp.retrieval-eval/v1"
    assert report["retriever"] == {"mode": "replay", "command": []}
    assert report["suite"]["sha256"] == hashlib.sha256(suite.read_bytes()).hexdigest()
    assert report["suite"]["name"] == "t" and report["suite"]["version"] == "1"
    assert report["metrics"]["failed"] == 0 and report["metrics"]["measured"] == 2
    assert report["metrics"]["recall_at_k"] == 1.0 and report["metrics"]["ndcg_at_k"] == pytest.approx(1.0)
    assert report["gate"] == {"passed": True, "reason": "every threshold held",
                              "thresholds": {"min_recall": 0.8, "max_failures": 0}}
    assert exit_for(report) == 0


def test_one_instrument_failure_fails_the_default_gate_even_with_perfect_recall(tmp_path):
    suite = _suite(tmp_path, [{"id": "a", "query": "q", "relevant": ["d1"], "results": ["d1"]},
                              {"id": "b", "query": "q", "relevant": ["d2"]}])
    report = run_retrieval_suite(suite)
    assert report["metrics"]["recall_at_k"] == 1.0
    assert report["gate"]["passed"] is False and "1 instrument failure(s) > 0" in report["gate"]["reason"]
    assert run_retrieval_suite(suite, max_failures=1)["gate"]["passed"] is True


# --------------------------------------------------------------------------- command mode

def test_the_retriever_receives_only_the_query_and_k_as_ascii_json(tmp_path):
    # Why: the cp1252 lesson from hpp decide eval — a child reading stdin in its locale codepage must
    # see the same query the suite holds. ASCII-escaped JSON reads the same in any codepage.
    seen = tmp_path / "seen.bin"
    script = tmp_path / "recorder.py"
    script.write_text("import sys\nraw = sys.stdin.buffer.read()\nopen(sys.argv[1], 'wb').write(raw)\n"
                      "sys.stdout.write('[\"d1\"]')\n", encoding="utf-8")
    suite = _suite(tmp_path, [{"id": "acentos", "query": "coração do índice", "relevant": ["d1"]}], k=2)
    report = run_retrieval_suite(suite, retriever_command=[sys.executable, "-S", str(script), str(seen)], timeout=20)
    assert report["metrics"]["measured"] == 1, report["cases"]
    raw = seen.read_bytes()
    assert raw.isascii()
    assert json.loads(raw.decode("ascii")) == {"query": "coração do índice", "k": 2}
    assert report["retriever"]["mode"] == "command"


def test_CONTROLE_both_answer_shapes_are_measured(tmp_path):
    suite = _suite(tmp_path, [{"id": "a", "query": "q", "relevant": ["x"]}], k=3)
    ids_only = _printer(tmp_path, '["x", "y"]', name="ids.py")
    objects = _printer(tmp_path, json.dumps({"results": [{"id": "x", "score": 0.9},
                                                         {"id": "y", "score": None, "text": "extra keys are ignored"}]}),
                       name="objects.py")
    for command in (ids_only, objects):
        report = run_retrieval_suite(suite, retriever_command=command, timeout=20)
        assert report["metrics"]["failed"] == 0, report["cases"]
        assert report["cases"][0]["returned"] == ["x", "y"]


@pytest.mark.parametrize("stdout, exit_code, stderr, fragment", [
    ("", 3, "index offline\n", "exited 3: index offline"),
    ("<html>502 Bad Gateway</html>", 0, "", "not JSON"),
    ("", 0, "", "printed nothing"),
    (b"\xff\xfe[1]", 0, "", "not JSON"),
    ('["d1", "d1"]', 0, "", "duplicate id 'd1'"),
    ("[1, 2]", 0, "", "string id"),
    ('["", "d1"]', 0, "", "string id"),
    ('{"hits": ["d1"]}', 0, "", "'results'"),
    ('{"results": "d1"}', 0, "", "list"),
    ('{"results": [{"id": "d1", "score": "high"}]}', 0, "", "score"),
    ('{"results": [{"id": "d1", "score": NaN}]}', 0, "", "score"),
    ('{"results": [{"id": "d1", "score": true}]}', 0, "", "score"),
], ids=["nonzero-exit", "html", "printed-nothing", "not-utf8", "duplicate-ids", "numeric-ids", "empty-id",
        "object-without-results", "results-not-a-list", "score-text", "score-nan", "score-bool"])
def test_every_broken_answer_is_an_instrument_failure_never_a_zero(tmp_path, stdout, exit_code, stderr, fragment):
    suite = _suite(tmp_path, [{"id": "a", "query": "q", "relevant": ["d1"], "results": ["d1"]}])
    report = run_retrieval_suite(suite, retriever_command=_printer(tmp_path, stdout, exit_code, stderr), timeout=20)
    case = report["cases"][0]
    assert case["status"] == "instrument-failure" and case["metrics"] is None
    assert fragment in case["error"], case["error"]
    assert (report["metrics"]["measured"], report["metrics"]["failed"]) == (0, 1)
    assert report["metrics"]["recall_at_k"] is None


def test_a_retriever_that_cannot_start_is_an_instrument_failure(tmp_path):
    suite = _suite(tmp_path)
    report = run_retrieval_suite(suite, retriever_command=["hpp-no-such-retriever-7f3a"], timeout=20)
    assert report["cases"][0]["status"] == "instrument-failure"
    assert "could not start" in report["cases"][0]["error"]
    assert "no case was measured (1 instrument failure)" in report["gate"]["reason"]


def test_a_timeout_is_an_instrument_failure_not_a_hang(tmp_path):
    script = tmp_path / "slow.py"
    script.write_text("import sys, time\nsys.stdin.read()\ntime.sleep(10)\n", encoding="utf-8")
    started = time.monotonic()
    report = run_retrieval_suite(_suite(tmp_path), retriever_command=[sys.executable, "-S", str(script)], timeout=0.5)
    assert time.monotonic() - started < 8
    assert report["cases"][0]["status"] == "instrument-failure"
    assert "exceeded 0.5s" in report["cases"][0]["error"]


def test_a_malformed_replay_is_an_instrument_failure_too(tmp_path):
    suite = _suite(tmp_path, [{"id": "a", "query": "q", "relevant": ["d1"], "results": ["d1", "d1"]}])
    case = run_retrieval_suite(suite)["cases"][0]
    assert case["status"] == "instrument-failure" and "duplicate id 'd1'" in case["error"]


# --------------------------------------------------------------------------- refusals

def test_a_secret_like_query_is_refused_named_and_never_sent(tmp_path):
    marker = tmp_path / "ran.txt"
    script = tmp_path / "spy.py"
    script.write_text("import sys\nsys.stdin.read()\nopen(sys.argv[1], 'w').write('ran')\nsys.stdout.write('[]')\n",
                      encoding="utf-8")
    suite = _suite(tmp_path, [{"id": "ok", "query": "where are backups kept", "relevant": ["d1"]},
                              {"id": "leaky", "query": "password: hunter2", "relevant": ["d2"]}])
    with pytest.raises(RetrievalError, match="case leaky"):
        run_retrieval_suite(suite, retriever_command=[sys.executable, "-S", str(script), str(marker)], timeout=20)
    assert not marker.exists()


def _mutated(mutation):
    body = _body()
    mutation(body)
    return body


@pytest.mark.parametrize("mutation, fragment", [
    (lambda s: s.update(schema="hpp.retrieval-suite/v0"), "schema must be hpp.retrieval-suite/v1"),
    (lambda s: s.pop("version"), "string version"),
    (lambda s: s.update(name=5), "name must be text"),
    (lambda s: s.update(k=0), "k must be an integer >= 1"),
    (lambda s: s.update(k=True), "k must be an integer >= 1"),
    (lambda s: s.update(k=2.5), "k must be an integer >= 1"),
    (lambda s: s.update(cases=[]), "non-empty cases"),
    (lambda s: s["cases"].append(dict(s["cases"][0])), "duplicate case id: a"),
    (lambda s: s["cases"][0].pop("id"), "every case needs an id"),
    (lambda s: s["cases"][0].update(query=""), "case a needs a non-empty text query"),
    (lambda s: s["cases"][0].update(query=["q"]), "case a needs a non-empty text query"),
    (lambda s: s["cases"][0].update(relevant=[]), "case a needs a non-empty list of relevant ids"),
    (lambda s: s["cases"][0].update(relevant="d1"), "case a needs a non-empty list of relevant ids"),
    (lambda s: s["cases"][0].update(relevant=["d1", 7]), "case a: relevant ids must be non-empty strings"),
    (lambda s: s["cases"][0].update(relevant=["d1", "d1"]), "case a: relevant ids must be unique"),
], ids=["schema", "version", "name", "k-zero", "k-bool", "k-float", "no-cases", "duplicate-case", "no-id",
        "empty-query", "query-not-text", "no-relevant", "relevant-not-list", "relevant-not-text", "relevant-duplicate"])
def test_the_suite_refuses_each_malformed_shape(tmp_path, mutation, fragment):
    path = tmp_path / "suite.json"
    path.write_text(json.dumps(_mutated(mutation)), encoding="utf-8")
    with pytest.raises(RetrievalError) as info:
        load_retrieval_suite(path)
    assert fragment in str(info.value)


def test_a_missing_or_unreadable_suite_is_refused(tmp_path):
    with pytest.raises(RetrievalError, match="not found"):
        run_retrieval_suite(tmp_path / "absent.json")
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(RetrievalError, match="invalid retrieval suite JSON"):
        run_retrieval_suite(broken)


@pytest.mark.parametrize("kwargs, fragment", [
    ({"k": 0}, "k must be an integer >= 1"),
    ({"k": True}, "k must be an integer >= 1"),
    ({"min_recall": 1.5}, "min_recall"),
    ({"min_recall": True}, "min_recall"),
    ({"max_failures": -1}, "max_failures"),
    ({"timeout": 0}, "timeout"),
    ({"retriever_command": []}, "retriever command"),
    ({"retriever_command": ["python", 3]}, "retriever command"),
])
def test_the_runner_refuses_bad_arguments(tmp_path, kwargs, fragment):
    with pytest.raises(RetrievalError, match=fragment):
        run_retrieval_suite(_suite(tmp_path), **kwargs)


# --------------------------------------------------------------------------- the shipped example

def _toy() -> list[str]:
    # Why: `-S` keeps site-packages out, so nothing installed can make the example pass.
    return [sys.executable, "-S", str(EXAMPLE / "keyword_retriever.py")]


def test_the_example_retriever_runs_from_a_checkout_without_pythonpath(monkeypatch, tmp_path):
    monkeypatch.delenv("PYTHONPATH", raising=False)
    monkeypatch.chdir(tmp_path)   # the corpus is found beside the script, not in the working directory
    report = run_retrieval_suite(EXAMPLE / "suite.json", retriever_command=_toy(), timeout=20)
    metrics = report["metrics"]
    assert metrics["failed"] == 0, [case for case in report["cases"] if case["status"] != "measured"]
    assert metrics["measured"] == metrics["total"] == 7
    # The README quotes this: the keyword baseline misses the paraphrase (0) and half of the disk case
    # (0.5), so mean recall@3 = (5 * 1 + 0.5 + 0) / 7 = 0.786 and the default 0.8 floor fails.
    assert metrics["recall_at_k"] == pytest.approx(5.5 / 7)
    assert report["gate"]["passed"] is False and "mean recall@k 0.786 < 0.8" in report["gate"]["reason"]


def test_the_recorded_replay_is_what_the_example_retriever_returns_today(monkeypatch):
    monkeypatch.delenv("PYTHONPATH", raising=False)
    live = run_retrieval_suite(EXAMPLE / "suite.json", retriever_command=_toy(), timeout=20)
    replayed = run_retrieval_suite(EXAMPLE / "suite.json")
    assert replayed["retriever"]["mode"] == "replay"
    assert [case["returned"] for case in replayed["cases"]] == [case["returned"] for case in live["cases"]]
    assert replayed["metrics"] == live["metrics"]


def test_the_example_retriever_honours_k_and_answers_in_the_declared_shape():
    request = json.dumps({"query": "how do I restore a backup", "k": 2})
    result = subprocess.run(_toy(), input=request, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    answer = json.loads(result.stdout)
    assert 1 <= len(answer["results"]) <= 2
    assert all(isinstance(item["id"], str) and isinstance(item["score"], (int, float)) for item in answer["results"])


# --------------------------------------------------------------------------- CLI

def test_cli_retrieval_eval_follows_the_exit_contract(tmp_path, capsys):
    from hpp import cli

    suite = Path(__file__).resolve().parent.parent / "examples" / "retrieval" / "suite.json"
    retriever = str(suite.parent / "keyword_retriever.py")
    assert cli.main(["retrieval", "eval", str(suite)]) == 1
    replay = json.loads(capsys.readouterr().out)
    assert cli.main(["retrieval", "eval", str(suite), "--retriever-command", json.dumps([sys.executable, retriever])]) == 1
    live = json.loads(capsys.readouterr().out)
    assert replay["metrics"] == live["metrics"] and live["retriever"]["mode"] == "command"
    assert cli.main(["retrieval", "eval", str(suite), "--min-recall", "0.5"]) == 0
    capsys.readouterr()
    assert cli.main(["retrieval", "eval", str(suite), "--retriever-command", "[]"]) == 2
    assert cli.main(["retrieval", "eval", str(tmp_path / "missing.json")]) == 2


# --------------------------------------------------------------------------- second review

def test_a_retriever_that_leaves_a_helper_running_is_still_measured(tmp_path):
    suite = tmp_path / "suite.json"
    suite.write_text(json.dumps({"schema": "hpp.retrieval-suite/v1", "version": "1", "k": 1,
                                 "cases": [{"id": "c1", "query": "q", "relevant": ["d1"]}]}), encoding="utf-8")
    helper = "import time; time.sleep(20)"
    code = ("import subprocess, sys\n"
            f"subprocess.Popen([sys.executable, '-c', {helper!r}])\n"
            "sys.stdin.read(); print('[\"d1\"]')\n")
    started = time.monotonic()
    report = run_retrieval_suite(suite, retriever_command=[sys.executable, "-c", code], timeout=10.0)
    assert report["cases"][0]["status"] == "measured" and time.monotonic() - started < 12


@pytest.mark.parametrize("timeout", [float("inf"), 1e300])
def test_a_timeout_that_cannot_be_waited_on_is_refused(tmp_path, timeout):
    suite = Path(__file__).resolve().parent.parent / "examples" / "retrieval" / "suite.json"
    with pytest.raises(RetrievalError, match="timeout"):
        run_retrieval_suite(suite, retriever_command=[sys.executable, "-c", "print('[]')"], timeout=timeout)


def test_a_score_too_large_for_a_float_is_an_instrument_failure_not_a_crash():
    with pytest.raises(RetrievalError, match="finite"):
        ranked_ids({"results": [{"id": "d1", "score": 10 ** 400}]})


def test_a_secret_like_stderr_line_is_withheld_from_the_report(tmp_path):
    suite = tmp_path / "suite.json"
    suite.write_text(json.dumps({"schema": "hpp.retrieval-suite/v1", "version": "1", "k": 1,
                                 "cases": [{"id": "c1", "query": "q", "relevant": ["d1"]}]}), encoding="utf-8")
    code = "import sys; sys.stderr.write('connect failed password=hunter2 host=db' + chr(10)); sys.exit(1)"
    report = run_retrieval_suite(suite, retriever_command=[sys.executable, "-c", code])
    error = report["cases"][0]["error"]
    assert "hunter2" not in error and "withheld" in error


def test_the_example_readmes_share_their_code_blocks():
    import re
    example = Path(__file__).resolve().parent.parent / "examples" / "retrieval"
    fences = [re.findall(r"^```.*?^```", (example / name).read_text(encoding="utf-8"), re.S | re.M)
              for name in ("README.md", "README.pt-BR.md")]
    assert fences[0] and fences[0] == fences[1]
