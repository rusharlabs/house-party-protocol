"""Evidence bundles: a criterion command's exit code plus the hashes of the artifacts it produced.

A browser test, a screenshot or a trace is only proof when the command that made it can be named,
its exit code was measured outside the model, and the files can be re-hashed later. These tests pin
that contract; the CONTROLE tests prove the checks are not refusing everything.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

from hpp import cli
from hpp.evidence import EvidenceError, _canonical, _sha256, exit_for_run, run_evidence, verify_evidence
from hpp.manifest import load_manifest
from hpp.state import event_path, project, read_events

WRITE_TWO = ("import pathlib; p = pathlib.Path('out'); p.mkdir(exist_ok=True); "
             "(p / 'shot.png').write_bytes(b'png'); (p / 'trace.zip').write_bytes(b'zip')")
DEMO = Path(__file__).resolve().parent.parent / "examples" / "evidence" / "smoke_page.py"


def _py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def _start_loop(root: Path) -> Path:
    log = event_path(root)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(json.dumps({"seq": 1, "id": "event:1", "type": "work_started", "data": {}}) + "\n",
                   encoding="utf-8")
    return log


# --------------------------------------------------------------------------- run

def test_CONTROLE_a_passing_command_with_its_artifacts_is_evidence(tmp_path):
    record = run_evidence("e2e-login", _py(WRITE_TWO), ["out/*.png", "out/trace.zip"], root=tmp_path)
    assert record["verdict"] == "passed" and record["exit_code"] == 0
    files = {item["path"] for group in record["artifacts"] for item in group["files"]}
    assert files == {"out/shot.png", "out/trace.zip"}
    assert Path(tmp_path / record["record_path"]).is_file()


def test_a_failing_command_is_not_evidence_even_with_artifacts(tmp_path):
    record = run_evidence("e2e-login", _py(WRITE_TWO + "; raise SystemExit(3)"), ["out/*.png"], root=tmp_path)
    assert record["verdict"] == "failed" and record["exit_code"] == 3


def test_a_declared_artifact_that_was_never_written_fails_the_bundle(tmp_path):
    record = run_evidence("e2e-login", _py("pass"), ["out/trace.zip"], root=tmp_path)
    assert record["verdict"] == "missing-artifacts"
    assert record["missing"] == ["out/trace.zip"]


def test_a_pattern_that_only_matches_directories_is_missing(tmp_path):
    record = run_evidence("e2e", _py("import os; os.makedirs('out/sub')"), ["out/*"], root=tmp_path)
    assert record["verdict"] == "missing-artifacts"


def test_a_trailing_double_star_matches_files_on_every_supported_python(tmp_path):
    code = ("import pathlib; p = pathlib.Path('test-results/a/b'); p.mkdir(parents=True); "
            "(p / 'trace.zip').write_bytes(b'z')")
    record = run_evidence("e2e", _py(code), ["test-results/**"], root=tmp_path)
    assert record["verdict"] == "passed"
    assert [item["path"] for item in record["artifacts"][0]["files"]] == ["test-results/a/b/trace.zip"]


def test_a_command_that_outlives_its_timeout_is_a_timeout_not_a_pass(tmp_path):
    record = run_evidence("slow", _py("import time; time.sleep(5)"), [], root=tmp_path, timeout=0.5)
    assert record["verdict"] == "timeout" and record["exit_code"] is None


# The grandchild stops on its own after 40 s, so a regression fails this test instead of leaving
# a process running after the suite.
GRANDCHILD = (
    "import subprocess, sys, time\n"
    "child = 'import time, pathlib\\np = pathlib.Path(\"beat.txt\")\\nend = time.time() + 40\\n"
    "while time.time() < end:\\n    p.write_text(str(time.time()))\\n    time.sleep(0.1)\\n'\n"
    "subprocess.Popen([sys.executable, '-c', child])\n"
    "time.sleep(40)\n"
)


def test_a_timeout_stops_the_whole_process_tree_and_returns(tmp_path):
    started = time.monotonic()
    record = run_evidence("tree", _py(GRANDCHILD), [], root=tmp_path, timeout=2.0)
    assert record["verdict"] == "timeout" and time.monotonic() - started < 20
    beat = tmp_path / "beat.txt"
    time.sleep(0.6)
    first = beat.read_text() if beat.exists() else ""
    time.sleep(0.8)
    assert (beat.read_text() if beat.exists() else "") == first, "a grandchild is still running after the timeout"


def test_a_command_that_cannot_start_is_recorded_as_such(tmp_path):
    record = run_evidence("ghost", [str(tmp_path / "no-such-binary")], [], root=tmp_path)
    assert record["verdict"] == "could-not-start"


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_the_timeout_must_be_a_positive_finite_number(tmp_path, timeout):
    with pytest.raises(EvidenceError, match="timeout"):
        run_evidence("x", _py("pass"), [], root=tmp_path, timeout=timeout)


# --------------------------------------------------------------------------- refusals before running

@pytest.mark.parametrize("pattern", ["../outside.txt", "/etc/passwd", "C:/Windows/win.ini", "out/../../x"])
def test_an_artifact_pattern_cannot_leave_the_workspace(tmp_path, pattern):
    with pytest.raises(EvidenceError, match="inside the workspace"):
        run_evidence("x", _py("pass"), [pattern], root=tmp_path)


def test_the_record_directory_cannot_leave_the_workspace_and_is_checked_before_running(tmp_path):
    marker = tmp_path / "ran"
    for out in ("../outside", "C:/elsewhere", "/abs"):
        with pytest.raises(EvidenceError, match="inside the workspace"):
            run_evidence("x", _py(f"open(r'{marker}', 'w')"), [], root=tmp_path, out_dir=Path(out))
    assert not marker.exists()


# Split so this file holds no token-shaped literal for a secret scanner to flag.
FAKE_GITHUB_TOKEN = "ghp_" + "abcdefghijklmnopqrstuvwxyz0123"


@pytest.mark.parametrize("extra", [
    ["--token=sk-live-abcdefghijk"], ["--password", "hunter2"], ["--token", "abc123"], ["--api-key=abc123"],
    ["TOKEN=abc123"], ["Authorization: Bearer abcdefghijklmnop"], [FAKE_GITHUB_TOKEN],
])
def test_a_secret_like_command_line_is_refused_before_it_runs(tmp_path, extra):
    marker = tmp_path / "ran"
    with pytest.raises(EvidenceError, match="secret"):
        run_evidence("x", _py(f"open(r'{marker}', 'w')") + extra, [], root=tmp_path)
    assert not marker.exists()


def test_CONTROLE_ordinary_flags_are_not_mistaken_for_secrets(tmp_path):
    record = run_evidence("x", _py("pass") + ["-p", "no:cacheprovider", "--tb=short", "--api-docs"], [],
                          root=tmp_path)
    assert record["verdict"] == "passed"


@pytest.mark.parametrize("bad_id", ["", "has space", "../up", "a/b"])
def test_the_id_is_a_plain_name(tmp_path, bad_id):
    with pytest.raises(EvidenceError, match="id"):
        run_evidence(bad_id, _py("pass"), [], root=tmp_path)


def test_the_record_holds_no_output_text_and_only_relative_paths_of_its_own(tmp_path):
    # The command is recorded as passed (it is what ran); the text it printed is not. The
    # concatenation keeps the printed line out of the command itself.
    record = run_evidence("e2e", _py("print('SENSITIVE-' + 'OUTPUT-LINE')"), [], root=tmp_path)
    text = (tmp_path / record["record_path"]).read_text(encoding="utf-8")
    assert "SENSITIVE-OUTPUT-LINE" not in text
    own_paths = [record["record_path"]] + [item["path"] for group in record["artifacts"] for item in group["files"]]
    assert all(not Path(path).is_absolute() and ".." not in Path(path).parts for path in own_paths)
    assert record["stdout"]["bytes"] > 0 and len(record["stdout"]["sha256"]) == 64


# --------------------------------------------------------------------------- verify

def test_verify_accepts_the_untouched_bundle_and_blocks_a_changed_artifact(tmp_path):
    record = run_evidence("e2e-login", _py(WRITE_TWO), ["out/*"], root=tmp_path)
    path = tmp_path / record["record_path"]
    assert verify_evidence(path, root=tmp_path)["status"] == "valid"
    (tmp_path / "out" / "shot.png").write_bytes(b"edited after the run")
    report = verify_evidence(path, root=tmp_path)
    assert report["status"] == "blocked" and report["changed"] == ["out/shot.png"]
    (tmp_path / "out" / "trace.zip").unlink()
    assert verify_evidence(path, root=tmp_path)["missing"] == ["out/trace.zip"]


def test_verify_refuses_a_record_whose_own_bytes_were_edited(tmp_path):
    record = run_evidence("e2e-login", _py(WRITE_TWO), ["out/*"], root=tmp_path)
    path = tmp_path / record["record_path"]
    data = json.loads(path.read_text(encoding="utf-8"))
    data["command"] = ["something", "else"]
    path.write_text(json.dumps(data), encoding="utf-8")
    assert verify_evidence(path, root=tmp_path)["status"] == "blocked"


def test_a_tampered_record_is_blocked_without_reading_the_paths_it_names(tmp_path):
    record = run_evidence("e2e", _py(WRITE_TWO), ["out/*"], root=tmp_path)
    path = tmp_path / record["record_path"]
    data = json.loads(path.read_text(encoding="utf-8"))
    data["artifacts"][0]["files"][0]["path"] = "../../outside.txt"
    path.write_text(json.dumps(data), encoding="utf-8")
    report = verify_evidence(path, root=tmp_path)
    assert report["status"] == "blocked" and report["changed"] == [] and report["missing"] == []


def test_a_rehashed_record_whose_verdict_contradicts_its_exit_code_is_blocked(tmp_path):
    record = run_evidence("bad", _py("raise SystemExit(1)"), [], root=tmp_path)
    path = tmp_path / record["record_path"]
    data = json.loads(path.read_text(encoding="utf-8"))
    data["verdict"] = "passed"
    data["record_sha256"] = _sha256(_canonical(data))
    path.write_text(json.dumps(data), encoding="utf-8")
    report = verify_evidence(path, root=tmp_path)
    assert report["status"] == "blocked" and any("exit" in problem for problem in report["problems"])


def test_verify_never_exits_zero_on_a_bundle_that_did_not_pass(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    cli.main(["evidence", "run", "--id", "bad", "--", *_py("raise SystemExit(1)")])
    record = json.loads(capsys.readouterr().out)
    assert cli.main(["evidence", "verify", record["record_path"]]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "not-evidence"


# --------------------------------------------------------------------------- the loop

def test_record_event_appends_evidence_only_for_a_passing_bundle(tmp_path):
    manifest, _ = load_manifest()
    log = _start_loop(tmp_path)
    failed = run_evidence("e2e", _py("raise SystemExit(1)"), ["out/*"], root=tmp_path, manifest=manifest)
    assert failed["event"] is None
    assert project(read_events(log), manifest)["evidence_count"] == 0
    passed = run_evidence("e2e", _py(WRITE_TWO), ["out/*"], root=tmp_path, manifest=manifest)
    assert passed["event"]["type"] == "evidence_recorded"
    state = project(read_events(log), manifest)
    assert state["evidence_count"] == 1 and state["state"] == "evidenced"
    assert read_events(log)[-1]["data"]["evidence_sha256"] == passed["record_sha256"]


def test_record_event_needs_at_least_one_artifact(tmp_path):
    manifest, _ = load_manifest()
    with pytest.raises(EvidenceError, match="artifact"):
        run_evidence("e2e", _py("pass"), [], root=tmp_path, manifest=manifest)


def test_record_event_from_the_wrong_state_leaves_the_log_untouched(tmp_path):
    manifest, _ = load_manifest()
    log = event_path(tmp_path)
    record = run_evidence("e2e", _py(WRITE_TWO), ["out/*"], root=tmp_path, manifest=manifest)
    assert record["event"] is None and "invalid transition" in record["event_error"]
    assert not log.exists() or read_events(log) == []


# --------------------------------------------------------------------------- CLI

def test_cli_evidence_run_and_verify_follow_the_exit_contract(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["evidence", "run", "--id", "ok", "--artifact", "out/*", "--", *_py(WRITE_TWO)]) == 0
    record = json.loads(capsys.readouterr().out)
    assert cli.main(["evidence", "verify", record["record_path"]]) == 0
    capsys.readouterr()
    assert cli.main(["evidence", "run", "--id", "bad", "--", *_py("raise SystemExit(2)")]) == 1
    capsys.readouterr()
    assert cli.main(["evidence", "run", "--id", "../x", "--", *_py("pass")]) == 2


def test_cli_without_a_command_is_a_usage_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["evidence", "run", "--id", "x"]) == 2
    assert cli.main(["evidence", "run", "--id", "x", "--"]) == 2


def test_the_printed_record_verifies_like_the_written_one(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _start_loop(tmp_path)
    cli.main(["evidence", "run", "--id", "ok", "--artifact", "out/*", "--record-event", "--", *_py(WRITE_TWO)])
    printed = json.loads(capsys.readouterr().out)
    assert printed["event"]["type"] == "evidence_recorded"
    copy = tmp_path / "printed.json"
    copy.write_text(json.dumps(printed), encoding="utf-8")
    assert verify_evidence(copy, root=tmp_path)["status"] == "valid"


def test_the_documented_demo_passes_and_its_broken_twin_does_not(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    args = ["evidence", "run", "--id", "smoke-page", "--artifact", "out/report.html", "--artifact", "out/smoke.log",
            "--", sys.executable, str(DEMO)]
    assert cli.main(args) == 0
    record = json.loads(capsys.readouterr().out)
    assert record["verdict"] == "passed"
    assert cli.main(["evidence", "verify", record["record_path"]]) == 0
    capsys.readouterr()
    assert cli.main(args + ["--break"]) == 1
    assert json.loads(capsys.readouterr().out)["verdict"] == "failed"


# --------------------------------------------------------------------------- second review

def test_an_event_log_that_cannot_be_written_is_reported_not_raised(tmp_path):
    manifest, _ = load_manifest()
    event_path(tmp_path).mkdir(parents=True)  # a directory where the log file should be
    record = run_evidence("e2e", _py(WRITE_TWO), ["out/*"], root=tmp_path, manifest=manifest)
    assert record["event"] is None and record["event_error"]
    assert (tmp_path / record["record_path"]).is_file()
    assert exit_for_run(record) == 2


def test_a_file_left_from_an_earlier_run_is_not_evidence_of_this_one(tmp_path):
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "old.png").write_bytes(b"yesterday")
    record = run_evidence("e2e", _py("pass"), ["out/*.png"], root=tmp_path)
    assert record["verdict"] == "missing-artifacts"
    assert record["artifacts"][0]["files"] == [] and record["artifacts"][0]["unchanged"] == ["out/old.png"]


def test_CONTROLE_a_file_the_run_rewrote_counts_even_if_it_existed(tmp_path):
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "old.png").write_bytes(b"yesterday")
    record = run_evidence("e2e", _py("open('out/old.png', 'wb').write(b'today, longer')"), ["out/*.png"],
                          root=tmp_path)
    assert record["verdict"] == "passed"
    assert [item["path"] for item in record["artifacts"][0]["files"]] == ["out/old.png"]


def _rehash(path: Path, change) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    data["record_sha256"] = _sha256(_canonical(data))
    path.write_text(json.dumps(data), encoding="utf-8")


def test_a_rehashed_record_with_a_malformed_group_is_blocked_not_a_crash(tmp_path):
    record = run_evidence("e2e", _py("pass"), ["out/x.png", "out/y.png"], root=tmp_path)
    path = tmp_path / record["record_path"]
    _rehash(path, lambda data: data["artifacts"][0].pop("pattern"))  # two groups: None sorts against a str
    assert verify_evidence(path, root=tmp_path)["status"] == "blocked"


def test_a_boolean_exit_code_is_not_a_zero(tmp_path):
    record = run_evidence("e2e", _py("pass"), [], root=tmp_path)
    path = tmp_path / record["record_path"]
    _rehash(path, lambda data: data.update(exit_code=False))
    assert verify_evidence(path, root=tmp_path)["status"] == "blocked"


@pytest.mark.parametrize("extra", [
    ["TOKENIZERS_PARALLELISM=false"], ["SECRET_KEY_FILE=/run/secrets/k"], ["GITHUB_TOKEN_PATH=tok.txt"],
    ["USE_TOKEN=false"],
])
def test_CONTROLE_environment_style_settings_are_not_secrets(tmp_path, extra):
    record = run_evidence("x", _py("pass") + extra, [], root=tmp_path)
    assert record["verdict"] == "passed"


def test_an_environment_style_secret_is_still_refused(tmp_path):
    with pytest.raises(EvidenceError, match="secret"):
        run_evidence("x", _py("pass") + ["GITHUB_TOKEN=abc123def"], [], root=tmp_path)


@pytest.mark.skipif(sys.platform != "win32", reason="batch launchers are a Windows concern")
def test_a_bare_command_name_resolves_to_its_windows_launcher(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "fake-runner.cmd").write_text("@exit /b 0\r\n", encoding="ascii")
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))
    record = run_evidence("x", ["fake-runner"], [], root=tmp_path)
    assert record["verdict"] == "passed" and record["command"] == ["fake-runner"]
