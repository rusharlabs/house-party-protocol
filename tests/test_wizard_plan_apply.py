"""`hpp init`: plan does not write, --apply writes ONE file inside the target,
the second run is a no-op, conflict never overwrites, and every exit code of
the contract (0 ok - 1 warn - 2 block - 3 error) is produced by a real path.

The proof of "did not write" is a hash of the target tree before and after --
not the absence of a specific file. The control at the end shows that the
hash does change when something is written, otherwise the comparison would be vacuous.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from hpp import cli, wizard
from hpp.manifest import load_manifest

PRODUCT_ROOT = Path(__file__).resolve().parent.parent


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _init(target: Path, *extra: str) -> int:
    return cli.main(["init", "--target", str(target), "--no-benchmark", "--no-animation", *extra])


@pytest.fixture()
def exit_codes():
    manifest, _ = load_manifest()
    return manifest["exit_codes"]


@pytest.fixture()
def target(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    return workspace


def test_plan_without_apply_writes_nothing_to_the_target(target, exit_codes, capsys):
    before = _tree_hash(target)
    code = _init(target)
    out = capsys.readouterr().out
    assert code == exit_codes["ok"]
    assert _tree_hash(target) == before
    assert "PLAN" in out and "nothing was written" in out
    assert not (target / ".hpp").exists()


def test_plan_does_not_write_outside_the_target(tmp_path, target, capsys):
    outside = tmp_path / "sibling"
    outside.mkdir()
    (outside / "keep.txt").write_text("untouched", encoding="utf-8")
    registry = Path.home() / ".claude-kits" / "registry.json"
    registry_state = (registry.exists(), registry.stat().st_mtime_ns if registry.exists() else None)
    before = _tree_hash(outside)
    _init(target, "--apply", "--yes")
    capsys.readouterr()
    assert _tree_hash(outside) == before
    assert (registry.exists(), registry.stat().st_mtime_ns if registry.exists() else None) == registry_state


def test_apply_writes_exactly_the_profile_inside_the_target(target, exit_codes, capsys):
    code = _init(target, "--apply", "--non-interactive")
    out = capsys.readouterr().out
    assert code == exit_codes["ok"]
    written = sorted(path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file())
    assert written == [".hpp/profile.json"]
    profile = json.loads((target / ".hpp" / "profile.json").read_text(encoding="utf-8"))
    manifest, _ = load_manifest()
    assert profile["schema"] == wizard.PROFILE_SCHEMA
    assert profile["host"] in manifest["hosts"]
    assert profile["modules"] == manifest["bundles"][profile["bundle"]]["modules"]
    assert "APPLIED" in out and "1 file(s) written" in out


def test_second_apply_is_a_no_op_and_does_not_change_a_byte(target, exit_codes, capsys):
    _init(target, "--apply", "--yes")
    capsys.readouterr()
    after_first = _tree_hash(target)
    code = _init(target, "--apply", "--yes", "--json")
    report = json.loads(capsys.readouterr().out)
    assert code == exit_codes["ok"]
    assert report["mode"] == "no-op"
    assert report["status"] == "no-op"
    assert report["writes"] == 0
    assert _tree_hash(target) == after_first
    detect = next(stage for stage in report["stages"] if stage["stage"] == "detect")
    assert detect["detail"]["classification"] == "re-run"
    assert any("nothing to do" in step for step in report["next"])


def test_conflict_with_existing_profile_is_warn_and_never_overwrites(target, exit_codes, capsys):
    _init(target, "--apply", "--yes", "--host", "claude-code")
    capsys.readouterr()
    profile_path = target / ".hpp" / "profile.json"
    original = profile_path.read_bytes()
    code = _init(target, "--apply", "--yes", "--host", "codex", "--json")
    report = json.loads(capsys.readouterr().out)
    assert code == exit_codes["warn"]
    assert report["status"] == "warn"
    assert profile_path.read_bytes() == original
    profile = next(stage for stage in report["stages"] if stage["stage"] == "profile")
    assert profile["detail"]["action"] == "conflict"
    assert profile["problems"] and "host" in profile["problems"][0]["measured"]


def test_apply_does_not_touch_existing_claude_settings_or_agents_md(target, capsys):
    claude_dir = target / ".claude"
    claude_dir.mkdir()
    settings = claude_dir / "settings.local.json"
    settings.write_text(json.dumps({"hooks": {"Stop": []}}), encoding="utf-8")
    agents = target / "AGENTS.md"
    agents.write_text("# mine\n", encoding="utf-8")
    settings_bytes, agents_bytes = settings.read_bytes(), agents.read_bytes()
    code = _init(target, "--apply", "--yes", "--json")
    report = json.loads(capsys.readouterr().out)
    assert code == 0
    assert settings.read_bytes() == settings_bytes
    assert agents.read_bytes() == agents_bytes
    wire = next(stage for stage in report["stages"] if stage["stage"] == "wire-suggest")
    assert wire["detail"]["writes"] == 0
    detect = next(stage for stage in report["stages"] if stage["stage"] == "detect")
    assert detect["detail"]["classification"] == "in-progress"
    assert any("settings.local.json" in item for item in detect["detail"]["existing_config"])


# ---------------------------------------------------------------------------
# Exit codes: each one through a real wizard path.
# ---------------------------------------------------------------------------


def test_exit_0_on_a_clean_plan(target, exit_codes, capsys):
    assert _init(target) == exit_codes["ok"]


def test_exit_1_when_smoke_fails(target, exit_codes, capsys, monkeypatch):
    """A policy classifier that lets `rm -rf` through is exactly what smoke
    exists to catch: the stage fails, the sequence does not stop (it is the
    last one), and the installer contract mandates exit 1 for a failed smoke."""
    monkeypatch.setattr(wizard, "assess", lambda command: {"action": "ALLOW", "rule": "allow", "reason": "broken"})
    code = _init(target, "--json")
    report = json.loads(capsys.readouterr().out)
    assert code == exit_codes["warn"]
    smoke = report["stages"][-1]
    assert smoke["stage"] == "smoke" and smoke["status"] == "fail"
    assert smoke["problems"][0]["next_step"].startswith("python -m hpp policy check")
    policy_item = next(item for item in report["readiness"]["items"] if item["id"] == "policy")
    assert policy_item["status"] == "failed"


def test_exit_2_when_a_module_is_not_supported_on_the_host(target, exit_codes, capsys):
    manifest, _ = load_manifest()
    unsupported = next(module["id"] for module in manifest["modules"] if module["hosts"].get("codex") == "unsupported")
    code = _init(target, "--host", "codex", "--modules", unsupported, "--json")
    report = json.loads(capsys.readouterr().out)
    assert code == exit_codes["block"]
    assert report["status"] == "halted"
    names = [(stage["stage"], stage["status"]) for stage in report["stages"]]
    assert names[3] == ("configure", "fail")
    assert names[4] == ("wire-suggest", "skipped") and names[5] == ("smoke", "skipped")
    assert report["writes"] == 0


def test_exit_2_for_an_unknown_bundle_via_main(target, exit_codes, capsys):
    code = _init(target, "--bundle", "does-not-exist")
    assert code == exit_codes["block"]
    assert "unknown bundle" in capsys.readouterr().err


def test_exit_3_when_the_target_is_not_a_directory(tmp_path, exit_codes, capsys):
    code = cli.main(["init", "--target", str(tmp_path / "missing"), "--no-benchmark"])
    assert code == exit_codes["error"]
    assert "not a directory" in capsys.readouterr().err


def test_exit_3_when_the_profile_file_is_not_json(target, exit_codes, capsys):
    answers = target.parent / "answers.json"
    answers.write_text("{not json", encoding="utf-8")
    code = _init(target, "--profile", str(answers))
    assert code == exit_codes["error"]
    assert "not valid JSON" in capsys.readouterr().err


def test_CONTROLE_tree_hash_detects_a_write(target):
    """Control: the hash used above changes when a file appears -- without this,
    'plan does not write' could pass with a hash that ignores the content."""
    before = _tree_hash(target)
    (target / "novo.txt").write_text("x", encoding="utf-8")
    assert _tree_hash(target) != before


def test_CONTROLE_different_profile_is_detected_as_a_conflict_by_the_stage_itself(target, capsys):
    """Symmetric control: the profile stage distinguishes 'same' from 'different' --
    proves that the no-op above is not a stage that always says unchanged."""
    _init(target, "--apply", "--yes")
    capsys.readouterr()
    path = target / ".hpp" / "profile.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["policy_mode"] = "enforce" if data["policy_mode"] == "audit" else "audit"
    path.write_text(json.dumps(data), encoding="utf-8")
    _init(target, "--apply", "--yes", "--json")
    report = json.loads(capsys.readouterr().out)
    assert next(stage for stage in report["stages"] if stage["stage"] == "profile")["detail"]["action"] == "conflict"
    assert os.path.getsize(path) == len(json.dumps(data).encode("utf-8"))
