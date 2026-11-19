"""An attestation explains which measured paths made its snapshot stale."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from hpp import cli


@pytest.fixture
def repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)
    for key in tuple(os.environ):
        if key.upper().startswith("GIT_"):
            monkeypatch.delenv(key, raising=False)
    config = tmp_path / "gitconfig"
    config.write_bytes(b"")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    _git("init", "-q")
    Path("SPEC.md").write_text("Change scope\n", encoding="utf-8")
    Path("app.py").write_text("VALUE = 1\n", encoding="utf-8")
    Path("old.py").write_text("VALUE = 0\n", encoding="utf-8")
    message = tmp_path / "commit-message"
    message.write_text("Seed the test repository\n", encoding="utf-8")
    _git("add", "--", "SPEC.md", "app.py", "old.py")
    _git("-c", "user.name=HPP Test", "-c", "user.email=hpp@example.invalid",
         "commit", "-q", "-F", str(message))
    return repo


def _git(*args):
    subprocess.run(["git", *args], check=True, capture_output=True)


def _run(capsys, *args, exit_code=0):
    assert cli.main(list(args)) == exit_code
    result = capsys.readouterr()
    return json.loads(result.out), result.err


def _create(capsys, output):
    return _run(capsys, "attest", "create", "--spec", "SPEC.md", "--output", output,
                "--maker", "maker", "--checker", "checker", "--session", "review-69",
                "--verdict", "approved")


def _changed(capsys, output):
    report, stderr = _run(capsys, "attest", "verify", output, exit_code=2)
    assert not stderr
    assert report["status"] == "blocked"
    assert report["mismatches"] == ["snapshot_digest"]
    return report["changed_paths"]


def test_runtime_files_warn_and_explain_snapshot_drift(repo, capsys):
    _run(capsys, "event", "append", "--type", "work_started")
    output = ".hpp/attestation.json"
    approval, stderr = _create(capsys, output)
    assert ".hpp/events.jsonl" in stderr and ".gitignore" in stderr and "'.hpp/'" in stderr
    assert output not in stderr
    entries = approval["snapshot"]["entries"]
    assert [entry["path"] for entry in entries] == [".hpp/events.jsonl", "SPEC.md", "app.py", "old.py"]
    valid, stderr = _run(capsys, "attest", "verify", output)
    assert not stderr and valid["status"] == "valid" and "changed_paths" not in valid

    _run(capsys, "event", "append", "--type", "evidence_recorded")
    assert _changed(capsys, output) == {".hpp/events.jsonl": "modified"}

    archive = Path(".hpp/archive/events.jsonl")
    archive.parent.mkdir()
    archive.write_bytes(Path(".hpp/events.jsonl").read_bytes())
    second, stderr = _create(capsys, ".hpp/second.json")
    assert all(name in stderr for name in (archive.as_posix(), output, ".hpp/events.jsonl"))
    assert ".hpp/second.json" not in stderr
    assert second["snapshot"]["file_count"] == 6
    assert _changed(capsys, output) == {
        archive.as_posix(): "added", ".hpp/events.jsonl": "modified", ".hpp/second.json": "added",
    }

    Path(".gitignore").write_text(".hpp/\n", encoding="utf-8")
    _git("check-ignore", "-q", "--", ".hpp/events.jsonl")
    approval, stderr = _create(capsys, output)
    assert not stderr
    assert all(not entry["path"].startswith(".hpp/") for entry in approval["snapshot"]["entries"])
    _run(capsys, "event", "append", "--type", "check_passed")
    valid, stderr = _run(capsys, "attest", "verify", output)
    assert not stderr and valid["status"] == "valid"

    Path("app.py").write_text("VALUE = 2\n", encoding="utf-8")
    Path("new file.py").write_text("VALUE = 3\n", encoding="utf-8")
    Path("old.py").unlink()
    assert _changed(capsys, output) == {"app.py": "modified", "new file.py": "added", "old.py": "deleted"}


def test_doctor_and_apply_warn_on_files_git_would_include(repo, capsys):
    _, stderr = _run(capsys, "doctor", "--json")
    assert not stderr
    init = ("init", "--target", ".", "--non-interactive", "--host", "codex",
            "--bundle", "reliable-coding", "--json")
    _, stderr = _run(capsys, *init)
    assert not stderr and not Path(".hpp").exists()

    report, stderr = _run(capsys, *init, "--apply")
    assert report["writes"] == 1 and ".hpp/profile.json" in stderr and ".gitignore" in stderr
    assert not Path(".gitignore").exists()
    _, stderr = _run(capsys, "doctor", "--json")
    assert ".hpp/profile.json" in stderr

    Path(".gitignore").write_text(".hpp/\n", encoding="utf-8")
    _, stderr = _run(capsys, *init, "--apply")
    assert not stderr
    _, stderr = _run(capsys, "doctor", "--json")
    assert not stderr

    _git("add", "-f", "--", ".hpp/profile.json")
    _, stderr = _run(capsys, "doctor", "--json")
    assert ".hpp/profile.json" in stderr and "tracked" in stderr


@pytest.mark.parametrize("variable", [
    "GIT_LITERAL_PATHSPECS", "GIT_NOGLOB_PATHSPECS", "GIT_GLOB_PATHSPECS", "GIT_ICASE_PATHSPECS",
])
def test_advisory_matches_snapshot_under_ambient_pathspec_modes(repo, capsys, monkeypatch, variable):
    monkeypatch.setenv(variable, "1")
    _run(capsys, "event", "append", "--type", "work_started")
    uppercase = Path("nested/.HPP/ordinary.txt")
    uppercase.parent.mkdir(parents=True)
    uppercase.write_text("Ordinary tracked or untracked project file\n", encoding="utf-8")
    approval, create_stderr = _create(capsys, ".hpp/attestation.json")
    assert {entry["path"] for entry in approval["snapshot"]["entries"]} >= {
        ".hpp/events.jsonl", uppercase.as_posix(),
    }
    assert ".hpp/events.jsonl" in create_stderr and uppercase.as_posix() not in create_stderr

    _, doctor_stderr = _run(capsys, "doctor", "--json")
    assert ".hpp/events.jsonl" in doctor_stderr and uppercase.as_posix() not in doctor_stderr
    assert os.environ[variable] == "1"


def test_untrustworthy_snapshot_entries_keep_the_existing_block(repo, capsys):
    output = ".hpp/attestation.json"
    approval, stderr = _create(capsys, output)
    assert not stderr
    approval["snapshot"]["entries"] = [None]
    Path(output).write_text(json.dumps(approval), encoding="utf-8")
    Path("app.py").write_text("VALUE = 2\n", encoding="utf-8")
    report, stderr = _run(capsys, "attest", "verify", output, exit_code=2)
    assert not stderr and report["mismatches"] == ["snapshot_digest"]
    assert "changed_paths" not in report
