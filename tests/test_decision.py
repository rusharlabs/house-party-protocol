"""Typed-decision records (`hpp.decision/v1`) and the ruler that measures a decider.

The harness still calls no model. What this file pins down is the contract a decision made
OUTSIDE the harness must satisfy to be recorded, and the evaluation that decides whether a decider
earns trust: abstention is a first-class outcome, a transport failure is never a verdict, and an
advisory decision may raise caution but never lower it.

Every refusal below is a case the contract exists to stop, written as a test that fails if the
record is accepted. The CONTROLE tests prove the validator is not refusing everything.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from hpp import cli
from hpp.decision import (
    DecisionError,
    digest,
    effective,
    question_digest,
    run_decision_suite,
    validate,
)
from hpp.policy import assess

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = PRODUCT_ROOT / "examples" / "typed-decisions"

QUESTION = {"id": "route.risk", "kind": "choice", "options": ["low", "medium", "high"], "ladder": True,
            "instructions": "How risky is this change?"}
STATE = "rename a local variable inside one test file"


def _record(**overrides):
    record = {
        "schema": "hpp.decision/v1",
        "question": dict(QUESTION),
        "state_sha256": digest(STATE),
        "method": "external-model",
        "provider": {"id": "declared-advisor", "model_served": "jev-1.13.0"},
        "outcome": {"status": "recommendation", "value": "medium",
                    "probabilities": {"low": 0.1, "medium": 0.8, "high": 0.1}, "confidence": 0.7},
        "authority": "advisory",
        "direction": "raise-only",
        "declared": "low",
        "raw_response_sha256": hashlib.sha256(b"{}").hexdigest(),
    }
    for key, value in overrides.items():
        if value is None:
            record.pop(key, None)
        else:
            record[key] = value
    return record


# --------------------------------------------------------------------------- the contract

def test_CONTROLE_a_complete_advisory_record_is_valid():
    normalised = validate(_record())
    assert normalised["question"]["sha256"] == question_digest(QUESTION)
    assert effective(normalised) == {"value": "medium", "action": "raised", "declared": "low"}


def test_raise_only_never_lowers_the_declared_value():
    result = effective(validate(_record(declared="high")))
    assert result == {"value": "high", "action": "kept", "declared": "high"}


def test_abstention_and_failure_never_change_the_declared_value():
    abstained = _record(outcome={"status": "abstention", "value": None, "confidence": 0.2})
    failed = _record(outcome={"status": "instrument-failure", "value": None, "error": "HTTP 403 (text/html)"},
                     raw_response_sha256=None)
    assert effective(validate(abstained))["value"] == "low"
    assert effective(validate(failed)) == {"value": "low", "action": "kept", "declared": "low"}


@pytest.mark.parametrize("mutation, fragment", [
    ({"authority": "binding"}, "authority must be 'advisory'"),
    ({"outcome": {"status": "recommendation", "value": "critical", "confidence": 0.9}}, "not one of the options"),
    ({"outcome": {"status": "abstention", "value": "high"}}, "abstention carries no value"),
    ({"outcome": {"status": "instrument-failure", "value": None}}, "must say what failed"),
    ({"outcome": {"status": "approved", "value": "high"}}, "outcome status must be one of"),
    ({"provider": {"id": "declared-advisor", "model_served": "jev-latest"}}, "pinned"),
    ({"provider": {"id": "declared-advisor", "model_served": "~typesafe/jev-latest"}}, "pinned"),
    ({"provider": None}, "provider id the user declared"),
    ({"raw_response_sha256": None}, "raw_response_sha256"),
    ({"state_sha256": "not-a-hash"}, "state_sha256"),
    ({"schema": "hpp.decision/v0"}, "schema must be"),
    ({"declared": "critical"}, "declared 'critical' is not one of the options"),
    ({"outcome": {"status": "recommendation", "value": "high",
                  "probabilities": {"low": 0.5, "medium": 0.5, "high": 0.5}, "confidence": 0.5}}, "sum to 1"),
    ({"method": "replay", "provider": "x", "raw_response_sha256": None}, "provider must be an object"),
    ({"method": "replay", "provider": {}, "raw_response_sha256": None}, "provider must be an object"),
])
def test_the_contract_refuses_each_malformed_record(mutation, fragment):
    with pytest.raises(DecisionError) as info:
        validate(_record(**mutation))
    assert fragment in str(info.value)


@pytest.mark.parametrize("kind", ["score", "noul"])
def test_numeric_question_kinds_are_refused_instead_of_measured_as_zero(kind):
    with pytest.raises(DecisionError, match="not measurable"):
        validate(_record(question=dict(QUESTION, kind=kind)))


def test_a_rule_based_method_cannot_claim_a_confidence():
    record = _record(method="regex", provider=None, raw_response_sha256=None)
    with pytest.raises(DecisionError, match="confidence"):
        validate(record)
    record["outcome"]["confidence"] = None
    assert validate(record)["method"] == "regex"


def test_raise_only_needs_an_ordered_question():
    with pytest.raises(DecisionError, match="ordered"):
        validate(_record(question=dict(QUESTION, ladder=False)))


def test_a_question_whose_hash_was_edited_is_refused():
    with pytest.raises(DecisionError, match="question sha256"):
        validate(_record(question=dict(QUESTION, sha256="0" * 64)))


def test_secret_like_state_is_never_hashed():
    with pytest.raises(DecisionError, match="secret"):
        digest("export OPENROUTER_API_KEY=sk-live-abcdefghijk")


def test_running_the_example_adapter_is_a_manual_gate_and_the_baseline_is_not():
    assert assess("python examples/typed-decisions/decide.py --provider typesafe --model jev-1.13.0")["action"] == "MANUAL"
    evaluation = ("python -m hpp decide eval s.json --decider-command "
                  "'[\"python\", \"examples/typed-decisions/decide.py\"]'")
    assert assess(evaluation)["rule"] == "decision-advisor"
    assert assess("python examples/typed-decisions/baseline_decider.py")["action"] == "ALLOW"


# --------------------------------------------------------------------------- the ruler

def _suite(tmp_path: Path, cases: list[dict]) -> Path:
    path = tmp_path / "suite.json"
    path.write_text(json.dumps({"schema": "hpp.decision-suite/v1", "name": "t", "version": "1",
                                "question": QUESTION, "confidence_floor": 0.6, "cases": cases}), encoding="utf-8")
    return path


def _case(case_id: str, state: str, expected: str, status: str, value, confidence=None, probabilities=None):
    outcome = {"status": status, "value": value, "confidence": confidence}
    if probabilities:
        outcome["probabilities"] = probabilities
    if status == "instrument-failure":
        outcome["error"] = "timeout"
    record = {"schema": "hpp.decision/v1", "question": QUESTION, "state_sha256": digest(state),
              "method": "replay", "outcome": outcome, "authority": "advisory", "direction": "informational"}
    return {"id": case_id, "state": state, "expected": expected, "record": record}


def test_selective_metrics_separate_coverage_accuracy_abstention_and_failure(tmp_path):
    suite = _suite(tmp_path, [
        _case("a", "drop the production table", "high", "recommendation", "high", 0.9),
        _case("b", "fix a typo in a comment", "low", "recommendation", "low", 0.8),
        _case("c", "refactor the auth module", "medium", "recommendation", "low", 0.95),   # confident error
        _case("d", "?", "abstain", "abstention", None, 0.3),                                # correct abstention
        _case("e", "bump a pinned dependency", "medium", "instrument-failure", None),
    ])
    report = run_decision_suite(suite)
    metrics = report["metrics"]
    assert (metrics["total"], metrics["decided"], metrics["abstained"], metrics["failed"]) == (5, 3, 1, 1)
    assert metrics["coverage"] == pytest.approx(3 / 5)
    assert metrics["selective_accuracy"] == pytest.approx(2 / 3)
    assert metrics["correct_abstentions"] == 1
    assert metrics["confident_errors"] == 1
    assert metrics["errors_by_expected"] == {"medium": 1}
    assert report["gate"]["passed"] is False


def test_no_decision_is_no_sample_never_a_percentage(tmp_path):
    report = run_decision_suite(_suite(tmp_path, [_case("a", "x", "high", "abstention", None, 0.1)]))
    assert report["metrics"]["selective_accuracy"] is None
    assert report["gate"]["passed"] is False
    assert "no decision was made (1 abstained, 0 instrument failure(s))" in report["gate"]["reason"]


def test_a_decider_that_never_ran_is_not_reported_as_abstaining(tmp_path):
    suite = _suite(tmp_path, [_case("a", "x", "high", "recommendation", "high", 0.9)])
    report = run_decision_suite(suite, decider_command=[sys.executable, str(tmp_path / "missing.py")])
    assert report["metrics"]["failed"] == 1 and report["metrics"]["abstained"] == 0
    assert "0 abstained, 1 instrument failure(s)" in report["gate"]["reason"]


def test_a_record_about_a_different_state_is_an_instrument_failure(tmp_path):
    case = _case("a", "the state the suite holds", "high", "recommendation", "high", 0.9)
    case["record"]["state_sha256"] = digest("some other text")
    report = run_decision_suite(_suite(tmp_path, [case]))
    assert report["cases"][0]["status"] == "instrument-failure"
    assert "different state" in report["cases"][0]["error"]


def test_a_secret_like_case_is_refused_and_named(tmp_path):
    suite = _suite(tmp_path, [_case("ok", "x", "high", "recommendation", "high", 0.9),
                              {"id": "leaky", "state": "password: hunter2", "expected": "high"}])
    with pytest.raises(DecisionError, match="case leaky"):
        run_decision_suite(suite)


def test_brier_is_not_measured_without_probabilities(tmp_path):
    suite = _suite(tmp_path, [_case("a", "x", "high", "recommendation", "high", 0.9)])
    assert run_decision_suite(suite)["metrics"]["brier"] == "not-measured"


def test_CONTROLE_a_perfect_replay_passes_the_gate(tmp_path):
    suite = _suite(tmp_path, [
        _case("a", "drop the production table", "high", "recommendation", "high", 0.9,
              {"low": 0.0, "medium": 0.1, "high": 0.9}),
        _case("b", "?", "abstain", "abstention", None, 0.2),
    ])
    report = run_decision_suite(suite)
    assert report["gate"]["passed"] is True
    # multi-class Brier over the decided case: (0-0)^2 + (0.1-0)^2 + (0.9-1)^2 = 0.02
    assert report["metrics"]["brier"] == pytest.approx(0.02)


# Why: one default confidence floor is a guess about someone else's task. The ruler publishes the
# whole curve so the operating point is chosen, not inherited.
def test_the_report_publishes_coverage_and_accuracy_at_every_floor(tmp_path):
    suite = _suite(tmp_path, [
        _case("a", "s1", "high", "recommendation", "high", 0.95),
        _case("b", "s2", "low", "recommendation", "low", 0.75),
        _case("c", "s3", "medium", "recommendation", "low", 0.65),
        _case("d", "s4", "high", "recommendation", "medium", 0.55),
    ])
    curve = {point["floor"]: point for point in run_decision_suite(suite)["metrics"]["coverage_curve"]}
    assert curve[0.5]["decided"] == 4 and curve[0.5]["selective_accuracy"] == pytest.approx(0.5)
    assert curve[0.7]["decided"] == 2 and curve[0.7]["selective_accuracy"] == pytest.approx(1.0)
    assert curve[0.9]["coverage"] == pytest.approx(0.25)


def test_CONTROLE_no_confidence_means_no_curve(tmp_path):
    suite = _suite(tmp_path, [_case("a", "s1", "high", "recommendation", "high", None)])
    assert run_decision_suite(suite)["metrics"]["coverage_curve"] == "not-measured"


def test_the_shipped_lexical_baseline_runs_through_the_command_runner(monkeypatch):
    monkeypatch.delenv("PYTHONPATH", raising=False)
    command = [sys.executable, str(EXAMPLE / "baseline_decider.py")]
    report = run_decision_suite(EXAMPLE / "gotcha-family-suite.json", decider_command=command, timeout=20)
    metrics = report["metrics"]
    assert metrics["total"] >= 12
    assert metrics["failed"] == 0, [case for case in report["cases"] if case["status"] == "instrument-failure"]
    assert metrics["decided"] >= 1 and metrics["abstained"] >= 1


def _run_example(script: str, env_path: str | None = None) -> subprocess.CompletedProcess:
    # Why: `-S` keeps site-packages out, so an installed or editable hpp cannot make this pass.
    env = {key: value for key, value in __import__("os").environ.items() if key != "PYTHONPATH"}
    if env_path:
        env["PYTHONPATH"] = env_path
    argv = [sys.executable, "-S", str(EXAMPLE / script)] + (["--help"] if script == "decide.py" else [])
    return subprocess.run(argv, input=json.dumps({"question": QUESTION, "state": STATE}), capture_output=True,
                          text=True, timeout=30, cwd=str(PRODUCT_ROOT.parent), env=env)


@pytest.mark.parametrize("script", ["baseline_decider.py", "decide.py"])
def test_the_example_scripts_import_hpp_from_a_checkout_without_pythonpath(script):
    # Why (docs audit, 2026-09-23): the documented commands run `python examples/typed-decisions/<x>.py`
    # from a clone, where the script's own directory is on sys.path and the checkout root is not;
    # every case became `No module named 'hpp'`.
    result = _run_example(script)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("script", ["baseline_decider.py", "decide.py"])
def test_an_older_installed_hpp_without_decisions_does_not_win(tmp_path, script):
    # Why (review round 3): the published 2.5.8 has no hpp.decision; probing `import hpp` found it
    # and skipped the checkout, so the script failed on `No module named 'hpp.decision'`.
    (tmp_path / "hpp").mkdir()
    (tmp_path / "hpp" / "__init__.py").write_text("__version__ = '2.5.8'\n", encoding="utf-8")
    result = _run_example(script, env_path=str(tmp_path))
    assert result.returncode == 0, result.stderr


def test_cli_decide_validate_and_eval_follow_the_exit_contract(tmp_path, capsys):
    good = tmp_path / "good.json"
    good.write_text(json.dumps(_record()), encoding="utf-8")
    assert cli.main(["decide", "validate", str(good)]) == 0
    assert json.loads(capsys.readouterr().out)["effective"]["action"] == "raised"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(_record(authority="binding")), encoding="utf-8")
    assert cli.main(["decide", "validate", str(bad)]) == 2
    failing = _suite(tmp_path, [_case("a", "x", "high", "recommendation", "low", 0.9)])
    assert cli.main(["decide", "eval", str(failing)]) == 1


# --------------------------------------------------------------------------- the example HTTP adapter
# Fake servers on 127.0.0.1 stand in for the provider: the suite stays offline, and every way the
# call can go wrong is produced on purpose instead of hoped for.

def _adapter():
    spec = importlib.util.spec_from_file_location("hpp_example_decide", EXAMPLE / "decide.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Fake:
    def __init__(self):
        self.status, self.body, self.content_type, self.delay = 200, None, "application/json", 0.0
        self.location = None
        self.requests: list[dict] = []


def _serve(fake: _Fake):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - stdlib handler name
            length = int(self.headers.get("Content-Length", "0"))
            fake.requests.append({"auth": self.headers.get("Authorization"),
                                  "body": json.loads(self.rfile.read(length) or b"{}")})
            time.sleep(fake.delay)
            payload = fake.body if isinstance(fake.body, bytes) else json.dumps(fake.body).encode("utf-8")
            self.send_response(fake.status)
            self.send_header("Content-Type", fake.content_type)
            if fake.location:
                self.send_header("Location", fake.location)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        do_GET = do_POST  # noqa: N815 - a followed redirect would arrive here as a GET

        def log_message(self, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    fake.url = f"http://127.0.0.1:{server.server_address[1]}/v1/systemone"
    return server


@pytest.fixture
def fake_server():
    fake = _Fake()
    server = _serve(fake)
    yield fake
    server.shutdown()
    server.server_close()


RISK = {"id": "route.risk", "kind": "choice", "options": ["low", "medium", "high"], "ladder": True}
KEY = "test-key-value-not-a-secret"


def _answer(choice="high", confidence=0.9, model="jev-1.13.0"):
    return {"model": model, "usage": {"input_tokens": 42, "output_tokens": 3},
            "answers": {"route.risk": {"choice": choice, "confidence": confidence,
                                       "probabilities": {"low": 0.05, "medium": 0.05, "high": 0.9}}}}


def test_adapter_records_a_confident_answer_with_raw_hash_and_sends_the_key_only_in_the_header(fake_server, tmp_path):
    fake_server.body = _answer()
    record = _adapter().ask(RISK, STATE, provider="compatible", model="jev-1.13.0", endpoint=fake_server.url,
                            key_env="HPP_TEST_KEY", env={"HPP_TEST_KEY": KEY}, raw_dir=tmp_path)
    assert validate(record)["outcome"]["value"] == "high"
    assert record["provider"]["model_served"] == "jev-1.13.0"
    assert (tmp_path / f"{record['raw_response_sha256']}.json").is_file()
    assert fake_server.requests[0]["auth"] == f"Bearer {KEY}"
    assert KEY not in json.dumps(record)
    assert fake_server.requests[0]["body"]["questions"]["route.risk"]["type"] == "choice"


def test_adapter_declared_value_makes_the_record_raise_only(fake_server):
    fake_server.body = _answer(choice="high")
    record = _adapter().ask(RISK, STATE, provider="compatible", model="jev-1.13.0", endpoint=fake_server.url,
                            declared="low")
    assert effective(validate(record)) == {"value": "high", "action": "raised", "declared": "low"}


def test_adapter_turns_low_confidence_into_abstention(fake_server):
    fake_server.body = _answer(confidence=0.3)
    record = _adapter().ask(RISK, STATE, provider="compatible", model="jev-1.13.0", endpoint=fake_server.url)
    assert record["outcome"]["status"] == "abstention" and record["outcome"]["value"] is None


@pytest.mark.parametrize("status, body, content_type, fragment", [
    (403, b"<html>blocked</html>", "text/html", "HTTP 403"),
    (200, b"<html>not json</html>", "text/html", "expected JSON"),
    (200, {"model": "jev-1.13.0", "answers": {}}, "application/json", "answer missing"),
    (200, {"model": "jev-1.13.0", "answers": {"route.risk": "high"}}, "application/json", "not an object"),
    (200, _answer(choice="critical"), "application/json", "broke the contract"),
    (200, _answer(model="jev-latest"), "application/json", "alias 'jev-latest'"),
    (200, b"x" * ((1 << 20) + 10), "application/json", "larger than"),
], ids=["http-403-html", "html-200", "no-answer", "answer-not-object", "outside-options", "served-alias", "oversized"])
def test_adapter_maps_every_transport_and_shape_failure_to_a_valid_instrument_failure(fake_server, status, body, content_type, fragment):
    fake_server.status, fake_server.body, fake_server.content_type = status, body, content_type
    record = _adapter().ask(RISK, STATE, provider="compatible", model="jev-1.13.0", endpoint=fake_server.url)
    assert record["outcome"]["status"] == "instrument-failure"
    assert fragment in record["outcome"]["error"]
    validate(record)


def test_adapter_refuses_a_redirect_and_the_key_never_reaches_the_second_host(fake_server):
    second = _Fake()
    second.body = _answer()
    server = _serve(second)
    try:
        fake_server.status, fake_server.body, fake_server.location = 302, b"", second.url
        record = _adapter().ask(RISK, STATE, provider="compatible", model="jev-1.13.0", endpoint=fake_server.url,
                                key_env="HPP_TEST_KEY", env={"HPP_TEST_KEY": KEY})
    finally:
        server.shutdown()
        server.server_close()
    assert record["outcome"]["status"] == "instrument-failure" and "HTTP 302" in record["outcome"]["error"]
    assert "redirect refused" in record["outcome"]["error"]
    assert second.requests == []


def test_adapter_timeout_is_an_instrument_failure_not_a_hang(fake_server):
    fake_server.body, fake_server.delay = _answer(), 2.0
    started = time.monotonic()
    record = _adapter().ask(RISK, STATE, provider="compatible", model="jev-1.13.0", endpoint=fake_server.url, timeout=0.5)
    assert record["outcome"]["status"] == "instrument-failure"
    assert time.monotonic() - started < 2.0


@pytest.mark.parametrize("kwargs, fragment", [
    ({"provider": "compatible", "model": "jev-latest"}, "alias"),
    ({"provider": "typesafe", "model": "jev-1.13.0", "env": {}}, "TYPESAFE_API_KEY"),
    ({"provider": "compatible", "model": "jev-1.13.0", "declared": "urgent"}, "not one of the options"),
])
def test_adapter_refuses_before_any_request(fake_server, kwargs, fragment):
    kwargs.setdefault("endpoint", fake_server.url)
    with pytest.raises(DecisionError, match=fragment):
        _adapter().ask(RISK, STATE, **kwargs)
    assert fake_server.requests == []


def test_adapter_sends_a_key_only_over_https_or_to_loopback():
    with pytest.raises(DecisionError, match="only sent over https"):
        _adapter().ask(RISK, STATE, provider="typesafe", model="jev-1.13.0", endpoint="http://example.invalid/v1",
                       env={"TYPESAFE_API_KEY": KEY})


def test_adapter_never_sends_secret_like_state(fake_server):
    with pytest.raises(DecisionError, match="secret"):
        _adapter().ask(RISK, "password: hunter2", provider="compatible", model="jev-1.13.0", endpoint=fake_server.url)
    assert fake_server.requests == []


def test_the_documented_command_line_runs_through_the_ruler(fake_server, tmp_path, monkeypatch):
    monkeypatch.delenv("PYTHONPATH", raising=False)
    fake_server.body = _answer(choice="high")
    suite = _suite(tmp_path, [{"id": "a", "state": STATE, "expected": "high"}])
    command = [sys.executable, str(EXAMPLE / "decide.py"), "--provider", "compatible", "--model", "jev-1.13.0",
               "--endpoint", fake_server.url, "--raw-dir", str(tmp_path / "raw")]
    report = run_decision_suite(suite, decider_command=command, timeout=20)
    assert report["metrics"]["failed"] == 0, report["cases"]
    assert report["cases"][0]["value"] == "high"
    assert len(list((tmp_path / "raw").iterdir())) == 1


# --------------------------------------------------------------------------- second review

@pytest.mark.parametrize("timeout", [0, -1, float("inf"), 1e300])
def test_a_timeout_that_cannot_be_waited_on_is_refused(tmp_path, timeout):
    suite = _suite(tmp_path, [_case("a", STATE, "high", "recommendation", "high", 0.9)])
    with pytest.raises(DecisionError, match="timeout"):
        run_decision_suite(suite, decider_command=[sys.executable, "-c", "pass"], timeout=timeout)


def test_a_decider_that_hangs_with_a_helper_is_bounded_by_the_timeout(tmp_path):
    helper = "import time; time.sleep(20)"
    code = ("import subprocess, sys, time\n"
            f"subprocess.Popen([sys.executable, '-c', {helper!r}])\n"
            "time.sleep(20)\n")
    suite = _suite(tmp_path, [_case("a", STATE, "high", "recommendation", "high", 0.9)])
    started = time.monotonic()
    report = run_decision_suite(suite, decider_command=[sys.executable, "-c", code], timeout=1.0)
    assert report["metrics"]["failed"] == 1
    assert time.monotonic() - started < 12
