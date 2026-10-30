"""The optional Orca launcher resolves the documented CLI and uses the host shell.

All Orca calls use an argv recorder; no installed app or agent is invoked.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.fixture
def dash(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    kits = list((root / "multi-session").glob("lane-kit-*/scripts/lane_dashboard.py"))
    script = kits[0] if kits else root.parents[2] / "staging/lane-kit/scripts/lane_dashboard.py"
    spec = importlib.util.spec_from_file_location("orca_dashboard_under_test", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.delenv("ORCA_CLI_COMMAND", raising=False)
    return module


def which(*names):
    return lambda name: name if name in names else None


def recorder(*, truncated=False, code=0, payload=None, stderr=""):
    calls = []

    def run(argv, *_args, **_kwargs):
        calls.append(argv)
        result = {"worktrees": [], "truncated": truncated} if argv[1] == "worktree" else {"repos": []}
        body = payload if payload is not None else {"ok": True, "result": result}
        return subprocess.CompletedProcess(argv, code, json.dumps(body), stderr)

    run.calls = calls
    return run


def test_linux_screen_reader_is_never_called(dash, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    run = recorder()
    projects = dash.Projects([tmp_path], run=run, which=which("orca"))
    projects.list()
    # Exercise discovery again, as the dashboard does while serving the page.
    projects._next_build = projects._next_ask = 0
    projects.list()
    row = next(row for row in dash.launchers_snapshot(tmp_path, which("orca"), {}, "linux") if row["id"] == "orca")
    assert run.calls == [], f"GNOME screen reader called: {run.calls}"
    assert row["available"] is False


@pytest.mark.parametrize("system,env,names,expected", [
    ("linux", {}, ("orca-ide", "orca"), "orca-ide"),
    ("linux", {"ORCA_CLI_COMMAND": "custom-orca"}, ("custom-orca", "orca-ide", "orca"), "custom-orca"),
    ("darwin", {"ORCA_CLI_COMMAND": "custom-orca"}, ("custom-orca", "orca"), "custom-orca"),
    ("win32", {"ORCA_CLI_COMMAND": "custom-orca"}, ("custom-orca", "orca"), "custom-orca"),
    ("darwin", {}, ("orca",), "orca"),
    ("win32", {}, ("orca",), "orca"),
])
def test_discovery_and_availability_use_the_same_cli(dash, tmp_path, monkeypatch, system, env, names, expected):
    monkeypatch.setattr(sys, "platform", system)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    run = recorder()
    assert dash.orca_worktrees(run, which(*names)) == []
    assert len(run.calls) == 2 and {call[0] for call in run.calls} == {expected}, run.calls
    row = next(row for row in dash.launchers_snapshot(tmp_path, which(*names), env, system) if row["id"] == "orca")
    assert row["available"]


def test_a_missing_override_does_not_silently_run_a_different_cli(dash, monkeypatch):
    monkeypatch.setenv("ORCA_CLI_COMMAND", "missing-orca")
    run = recorder()
    dash.orca_worktrees(run, which("orca", "orca-ide"))
    assert run.calls == []


def test_truncated_worktree_discovery_is_visible_in_snapshot_and_page(dash, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    projects = dash.Projects([], run=recorder(truncated=True), which=which("orca-ide"))
    snapshot = dash.collect_view(projects, which=which())
    assert snapshot.get("orca_truncated") is True, snapshot
    page = dash.SCRIPT.with_suffix(".html").read_text(encoding="utf-8")
    assert "all.orca_truncated" in page and "Orca worktree list was truncated" in page
    projects._run = recorder(truncated=False)
    projects._next_build = projects._next_ask = 0
    assert dash.collect_view(projects, which=which())["orca_truncated"] is False


def profile():
    return {"id": "claude", "label": "Claude", "command": "claude", "available": True,
            "model": "claude", "interactive": ["claude", "{prompt}"]}


@pytest.mark.parametrize("system,expected", [("win32", "custom-orca"), ("darwin", "custom-orca"), ("linux", "orca-ide")])
def test_session_argv_uses_the_resolved_cli_and_correct_shell(dash, tmp_path, system, expected):
    run = recorder(payload={"ok": True, "result": {"terminal": {"handle": "term_1"}}})
    env = {"ORCA_CLI_COMMAND": expected} if expected == "custom-orca" else {}
    info = dash.start_session(tmp_path, "orca", profile(), "planner", "test-lane", "title", "hello",
                              which=which("claude", expected, "orca"), run=run, env=env, system=system)
    assert info["session"] == "term_1"
    argv = run.calls[0]
    assert argv[0] == expected
    command = argv[argv.index("--command") + 1]
    if system == "win32":
        assert argv[argv.index("--shell") + 1] == "powershell", argv
        assert "Set-Location -LiteralPath" in command and "-Encoding UTF8" in command
        assert "$env:CLAUDE_LANE_ID=" in command and "&&" not in command and "env " not in command
    else:
        assert "--shell" not in argv and "&& env " in command and "$(cat " in command


@pytest.mark.parametrize("payload,stderr", [
    ({"ok": False, "error": {"code": "incompatible_runtime", "message": "shell unsupported"}}, ""),
    ({}, "unknown option '--shell'"),
])
def test_old_orca_shell_refusal_is_actionable_and_not_retried(dash, tmp_path, payload, stderr):
    run = recorder(code=1, payload=payload, stderr=stderr)
    with pytest.raises(dash.LaunchError, match="(?i)update Orca.*--launcher terminal"):
        dash.start_session(tmp_path, "orca", profile(), "planner", "old-orca", "t", "hello",
                           which=which("orca", "claude"), run=run, env={}, system="win32")
    assert len(run.calls) == 1, run.calls


def test_page_opener_uses_linux_cli(dash, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("TERM_PROGRAM", "Orca")
    monkeypatch.setattr(dash.shutil, "which", which("orca", "orca-ide"))
    run = recorder()
    monkeypatch.setattr(dash, "_run", run)
    monkeypatch.setattr(dash.webbrowser, "open", lambda _url: False)
    assert dash.open_page("http://localhost:8765", tmp_path) == "opened in Orca's browser"
    assert run.calls[0][0] == "orca-ide"


def test_orca_guide_documents_only_supported_dashboard_commands(dash):
    kit = dash.SCRIPT.parents[1]
    commands = [
        ["serve", "--project-dir", ".", "--open"],
        ["snapshot", "--project-dir", "."],
        ["serve", "--project-dir", ".", "--no-orca"],
        ["review", "launch", "ITEM", "--agent", "codex", "--launcher", "terminal"],
    ]
    for suffix in ("", ".pt-BR"):
        text = (kit / f"README{suffix}.md").read_text(encoding="utf-8")
        assert ("## HPP inside Orca" if not suffix else "## HPP dentro do Orca") in text
        assert "--scope project" in text and "ORCA_CLI_COMMAND" in text
        for command in commands:
            assert "lane_dashboard.py " + " ".join(command) in text
            dash.build_cli_parser().parse_args(command)
