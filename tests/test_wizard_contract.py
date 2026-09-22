"""Installer contract applied to `hpp init`: six stages in fixed order, a
blockage skips the following stages instead of pretending they ran,
`wire-suggest` does not execute A SINGLE write operation (guard on
`open`/`write_text`/`mkdir`), the block to paste distinguishes native host
from explicit command, and `--help` exposes all the flags.

The control proves that the anti-write guard catches a real write: applied to
the `profile` stage in --apply mode, it raises.
"""
from __future__ import annotations

import builtins
import json
import pathlib
import subprocess
import sys
from pathlib import Path

import pytest

from hpp import cli, wizard
from hpp.manifest import load_manifest

PRODUCT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def target(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    return workspace


@pytest.fixture()
def loaded():
    return load_manifest()


def _options(target: Path, **overrides) -> wizard.InitOptions:
    base = dict(target=target, target_label=str(target), benchmark_k=0)
    base.update(overrides)
    return wizard.InitOptions(**base)


def _context(target: Path, loaded, **overrides) -> wizard._Context:
    manifest, manifest_path = loaded
    return wizard._Context(options=_options(target, **overrides), manifest=manifest, manifest_path=manifest_path)


class _WriteGuard:
    """Makes any disk write raise while active."""

    def __init__(self, monkeypatch):
        real_open = builtins.open

        def guarded_open(file, mode="r", *args, **kwargs):
            if any(flag in mode for flag in "wax+"):
                raise AssertionError(f"write attempted: open({file!r}, {mode!r})")
            return real_open(file, mode, *args, **kwargs)

        def forbidden(*args, **kwargs):
            raise AssertionError(f"write attempted: {args!r}")

        monkeypatch.setattr(builtins, "open", guarded_open)
        monkeypatch.setattr(pathlib.Path, "write_text", forbidden)
        monkeypatch.setattr(pathlib.Path, "write_bytes", forbidden)
        monkeypatch.setattr(pathlib.Path, "mkdir", forbidden)
        monkeypatch.setattr(pathlib.Path, "touch", forbidden)


def test_the_six_stages_run_in_this_order_and_only_this_order(target, loaded, capsys):
    manifest, manifest_path = loaded
    report = wizard.run_init(_options(target), manifest, manifest_path)
    assert wizard.STAGES == ("detect", "prereqs", "profile", "configure", "wire-suggest", "smoke")
    assert [stage["stage"] for stage in report["stages"]] == list(wizard.STAGES)
    assert set(wizard.STAGE_FUNCTIONS) == set(wizard.STAGES)
    assert set(wizard.BOOT_LINES) == set(wizard.STAGES)


def test_boot_callbacks_fire_one_begin_and_one_end_per_stage_in_order(target, loaded):
    manifest, manifest_path = loaded
    trace: list[tuple[str, str]] = []
    wizard.run_init(_options(target), manifest, manifest_path,
                    on_begin=lambda name: trace.append(("begin", name)),
                    on_end=lambda result: trace.append(("end", result["stage"])))
    expected = [item for name in wizard.STAGES for item in (("begin", name), ("end", name))]
    assert trace == expected


def test_a_blockage_stops_the_sequence_and_the_following_stages_are_skipped(target, loaded):
    manifest, manifest_path = loaded
    unsupported = next(module["id"] for module in manifest["modules"] if module["hosts"].get("codex") == "unsupported")
    options = _options(target, answers={"host": "codex", "modules": [unsupported]}, sources={"host": "flag", "modules": "flag"})
    ran: list[str] = []
    report = wizard.run_init(options, manifest, manifest_path, on_begin=ran.append)
    assert ran == ["detect", "prereqs", "profile", "configure"]
    assert [stage["status"] for stage in report["stages"]] == ["ok", "ok", "ok", "fail", "skipped", "skipped"]
    assert report["status"] == "halted" and report["exit_code"] == 2
    assert all("configure failed" in stage["summary"] for stage in report["stages"][4:])


def test_wire_suggest_executes_no_write_at_all(target, loaded, monkeypatch):
    ctx = _context(target, loaded)
    wizard.stage_detect(ctx)
    wizard.stage_prereqs(ctx)
    wizard.stage_profile(ctx)
    wizard.stage_configure(ctx)
    _WriteGuard(monkeypatch)
    result = wizard.stage_wire_suggest(ctx)
    assert result["status"] == "ok"
    assert result["detail"]["writes"] == 0
    assert result["detail"]["settings_path"] == ".claude/settings.local.json"
    assert "hooks" in result["detail"]["manual_gates"]


def test_claude_code_block_installs_natives_and_sends_the_installer_for_the_explicit_ones(target, loaded):
    manifest, _ = loaded
    ctx = _context(target, loaded, answers={"host": "claude-code"}, sources={"host": "flag"})
    for stage in (wizard.stage_detect, wizard.stage_prereqs, wizard.stage_profile, wizard.stage_configure):
        stage(ctx)
    lines = wizard.stage_wire_suggest(ctx)["detail"]["lines"]
    bundle = manifest["bundles"]["reliable-coding"]["modules"]
    by_id = {module["id"]: module for module in manifest["modules"]}
    native = [module_id for module_id in bundle if by_id[module_id]["hosts"]["claude-code"] == "native"]
    explicit = [module_id for module_id in bundle if by_id[module_id]["hosts"]["claude-code"] != "native"]
    assert f"/plugin marketplace add {wizard.DEFAULT_MARKETPLACE}" in lines
    for module_id in native:
        assert f"/plugin install {module_id}@{manifest['name']}" in lines
    for module_id in explicit:
        assert not any(line == f"/plugin install {module_id}@{manifest['name']}" for line in lines)
        assert any(by_id[module_id]["path"] in line and "--host claude-code" in line for line in lines)
    assert any(line.startswith("# .claude/settings.local.json") and "wrote nothing" in line for line in lines)


def test_codex_block_has_one_installer_line_per_module_and_hooks_off(target, loaded):
    manifest, _ = loaded
    ctx = _context(target, loaded, answers={"host": "codex"}, sources={"host": "flag"})
    for stage in (wizard.stage_detect, wizard.stage_prereqs, wizard.stage_profile, wizard.stage_configure):
        stage(ctx)
    lines = wizard.stage_wire_suggest(ctx)["detail"]["lines"]
    installer = manifest["installer"]["path"]
    commands = [line for line in lines if line.startswith(f"python {installer} install")]
    assert len(commands) == len(manifest["bundles"]["reliable-coding"]["modules"])
    assert all("--host codex" in line and "--apply" in line for line in commands)
    assert any(".agents/skills" in line and ".agents/hpp" in line for line in lines)
    assert any("hooks stay off" in line for line in lines)
    assert not any(line.startswith("/plugin") for line in lines)


def test_marketplace_is_replaceable_by_flag(target, capsys):
    code = cli.main(["init", "--target", str(target), "--no-benchmark", "--marketplace", "me/fork", "--json"])
    report = json.loads(capsys.readouterr().out)
    assert code == 0
    lines = next(stage for stage in report["stages"] if stage["stage"] == "wire-suggest")["detail"]["lines"]
    assert "/plugin marketplace add me/fork" in lines


def test_json_mode_is_parseable_and_has_no_ansi(target):
    result = subprocess.run([sys.executable, "-m", "hpp", "init", "--target", str(target), "--no-benchmark", "--json"],
                            cwd=PRODUCT_ROOT, capture_output=True, timeout=60)
    assert result.returncode == 0
    assert b"\x1b" not in result.stdout
    report = json.loads(result.stdout.decode("ascii"))
    assert report["schema"] == wizard.REPORT_SCHEMA
    assert report["mode"] == "plan" and report["writes"] == 0


def test_help_exposes_all_the_contract_flags():
    result = subprocess.run([sys.executable, "-m", "hpp", "init", "--help"], cwd=PRODUCT_ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0
    for flag in ("--apply", "--yes", "--profile", "--modules", "--non-interactive", "--no-animation", "--json", "--target", "--host", "--bundle"):
        assert flag in result.stdout
    assert "detect, prereqs, profile, configure, wire-suggest, smoke" in result.stdout


def test_CONTROLE_the_anti_write_guard_catches_the_profile_stage_in_apply(target, loaded, monkeypatch):
    """Control: the same guard used to prove that wire-suggest does not write RAISES
    when the profile stage tries to write in --apply -- so it does catch a real write."""
    ctx = _context(target, loaded, apply=True)
    wizard.stage_detect(ctx)
    wizard.stage_prereqs(ctx)
    _WriteGuard(monkeypatch)
    with pytest.raises(AssertionError, match="write attempted"):
        wizard.stage_profile(ctx)
