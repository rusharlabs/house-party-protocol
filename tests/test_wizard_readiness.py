"""Honest readiness: every item comes from a check that ran, carries the
command that reproduces it, and what was not measured is `not-verified` -- never 0 nor 100.

Both states of "distribution integrity" and "module checksums" are reached
here (emitted-product fixture assembled in tmp from the real manifest), to
prove that the `not-verified` of the source tree is not a fixed state.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hpp import cli, wizard
from hpp.manifest import load_manifest

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
STATES = {"verified", "failed", "not-verified"}


@pytest.fixture()
def target(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    return workspace


def _report(target: Path, capsys, *extra: str) -> dict:
    code = cli.main(["init", "--target", str(target), "--no-animation", "--json", *extra])
    report = json.loads(capsys.readouterr().out)
    assert report["exit_code"] == code
    return report


def _item(report: dict, item_id: str) -> dict:
    return next(item for item in report["readiness"]["items"] if item["id"] == item_id)


def _emitted_root(tmp_path: Path, *, corrupt: str | None = None) -> Path:
    """A minimal 'emitted product': real manifest + coherent marketplace + one directory per
    module with plugin.json and correct CHECKSUMS.txt (or one of them corrupted)."""
    manifest = json.loads((PRODUCT_ROOT / "hpp.manifest.json").read_text(encoding="utf-8"))
    root = tmp_path / "emitted"
    root.mkdir()
    (root / "hpp.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    plugins = []
    for module in manifest["modules"]:
        module_dir = root / module["path"]
        (module_dir / ".claude-plugin").mkdir(parents=True)
        (module_dir / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": module["id"], "version": module["version"]}), encoding="utf-8")
        payload = module_dir / "README.md"
        payload.write_text(f"# {module['id']}\n", encoding="utf-8")
        digest = hashlib.sha256(payload.read_bytes()).hexdigest()
        if corrupt == module["id"]:
            digest = "0" * 64
        (module_dir / "CHECKSUMS.txt").write_text(f"{digest}  README.md\n", encoding="utf-8")
        plugins.append({"name": module["id"], "source": "./" + module["path"], "version": module["version"]})
    (root / "marketplace.json").write_text(json.dumps({"version": manifest["product_version"], "plugins": plugins}), encoding="utf-8")
    return root


def test_every_item_has_a_valid_state_command_and_the_sum_closes(target, capsys):
    report = _report(target, capsys, "--no-benchmark")
    readiness = report["readiness"]
    assert readiness["items"]
    for item in readiness["items"]:
        assert item["status"] in STATES
        assert item["command"].strip()
        assert item["evidence"].strip()
    assert readiness["verified"] + readiness["failed"] + readiness["not_verified"] == readiness["total"] == len(readiness["items"])
    assert sum(readiness["cells"].values()) == wizard.READINESS_CELLS


def test_what_was_not_measured_is_not_verified_never_zero_nor_a_hundred(target, capsys):
    report = _report(target, capsys, "--no-benchmark")
    assert _item(report, "benchmark")["status"] == "not-verified"
    assert "skipped" in _item(report, "benchmark")["evidence"]
    assert _item(report, "profile")["status"] == "not-verified"
    assert _item(report, "wiring")["status"] == "not-verified"
    # Why: distribution and checksums depend on the TREE where the suite runs. In the source
    # there is neither marketplace.json nor a module directory, so both are unmeasured; running
    # from inside the emitted copy they EXIST and become `verified`. Fixing `not-verified` would
    # tie the test to one of the two trees and would fail the other for being complete.
    source = not (Path(wizard.__file__).resolve().parents[1] / "marketplace.json").is_file()
    esperado = "not-verified" if source else "verified"
    assert _item(report, "distribution")["status"] == esperado
    assert _item(report, "checksums")["status"] == esperado
    assert 0 < report["readiness"]["verified"] < report["readiness"]["total"]


def test_benchmark_becomes_verified_when_it_actually_runs(target, capsys):
    report = _report(target, capsys)
    item = _item(report, "benchmark")
    assert item["status"] == "verified"
    assert "pass@k=" in item["evidence"] and item["command"] == "python -m hpp benchmark -k 1"


def test_profile_becomes_verified_only_after_apply(target, capsys):
    before = _report(target, capsys, "--no-benchmark")
    assert _item(before, "profile")["status"] == "not-verified"
    after = _report(target, capsys, "--no-benchmark", "--apply", "--yes")
    assert _item(after, "profile")["status"] == "verified"
    assert after["readiness"]["verified"] == before["readiness"]["verified"] + 1


def test_distribution_and_checksums_become_verified_in_a_coherent_emitted_product(tmp_path, target, capsys):
    root = _emitted_root(tmp_path)
    report = _report(target, capsys, "--no-benchmark", "--manifest", str(root / "hpp.manifest.json"))
    assert report["exit_code"] == 0
    distribution = _item(report, "distribution")
    assert distribution["status"] == "verified" and "marketplace.json checked" in distribution["evidence"]
    checksums = _item(report, "checksums")
    assert checksums["status"] == "verified" and checksums["evidence"] == "6/6 verified"
    configure = next(stage for stage in report["stages"] if stage["stage"] == "configure")
    assert all(module["checksum"]["status"] == "verified" for module in configure["detail"]["modules"])


def test_divergent_checksum_is_failed_and_blocks_with_exit_2(tmp_path, target, capsys):
    root = _emitted_root(tmp_path, corrupt="operator-kit")
    report = _report(target, capsys, "--no-benchmark", "--manifest", str(root / "hpp.manifest.json"))
    manifest, _ = load_manifest()
    assert report["exit_code"] == manifest["exit_codes"]["block"]
    assert report["status"] == "halted"
    checksums = _item(report, "checksums")
    assert checksums["status"] == "failed" and checksums["evidence"].startswith("1/6")
    configure = next(stage for stage in report["stages"] if stage["stage"] == "configure")
    problem = configure["problems"][0]
    assert "mismatch: README.md" in problem["measured"]
    assert "re-emit" in problem["next_step"]


def test_divergent_marketplace_is_failed_in_prereqs_and_blocks(tmp_path, target, capsys):
    root = _emitted_root(tmp_path)
    marketplace = json.loads((root / "marketplace.json").read_text(encoding="utf-8"))
    marketplace["version"] = "0.0.1"
    (root / "marketplace.json").write_text(json.dumps(marketplace), encoding="utf-8")
    report = _report(target, capsys, "--no-benchmark", "--manifest", str(root / "hpp.manifest.json"))
    assert report["exit_code"] == 2
    assert _item(report, "distribution")["status"] == "failed"
    prereqs = next(stage for stage in report["stages"] if stage["stage"] == "prereqs")
    assert prereqs["status"] == "fail"
    assert any(problem["label"] == "distribution" and "hpp doctor" in problem["next_step"] for problem in prereqs["problems"])
    assert [stage["status"] for stage in report["stages"][2:]] == ["skipped"] * 4


def test_missing_git_becomes_warn_with_an_install_command_and_exit_1(target, capsys, monkeypatch):
    manifest, _ = load_manifest()
    monkeypatch.setattr(wizard.shutil, "which", lambda name: None)
    report = _report(target, capsys, "--no-benchmark")
    assert report["exit_code"] == manifest["exit_codes"]["warn"]
    prereqs = next(stage for stage in report["stages"] if stage["stage"] == "prereqs")
    assert prereqs["status"] == "warn"
    git = next(problem for problem in prereqs["problems"] if problem["label"] == "git")
    assert git["measured"] == "not on PATH"
    assert any(token in git["next_step"] for token in ("winget", "brew", "apt-get", "xcode-select"))
    detect = next(stage for stage in report["stages"] if stage["stage"] == "detect")
    assert detect["detail"]["signals"]["git_commit_count"] is None


def test_verify_checksums_distinguishes_ok_mismatch_and_missing(tmp_path):
    module_dir = tmp_path / "mod"
    module_dir.mkdir()
    (module_dir / "a.txt").write_text("alpha", encoding="utf-8")
    good = hashlib.sha256(b"alpha").hexdigest()
    checksums = module_dir / "CHECKSUMS.txt"
    checksums.write_text(f"{good}  a.txt\n", encoding="utf-8")
    assert wizard.verify_checksums(module_dir, checksums) == (True, 1, [])
    checksums.write_text(f"{'0' * 64}  a.txt\n{good}  missing.txt\nbroken-line\n", encoding="utf-8")
    ok, checked, failures = wizard.verify_checksums(module_dir, checksums)
    assert ok is False and checked == 1
    assert failures == ["mismatch: a.txt", "missing: missing.txt", "malformed line: 'broken-line'"]


def test_CONTROLE_the_three_states_are_distinguishable_in_the_same_report(target, capsys, monkeypatch):
    """Control: a report with verified, failed AND not-verified at the same time -- proves that
    the builder does not collapse states (a readiness that only knew 'verified' would pass
    several tests above)."""
    monkeypatch.setattr(wizard, "assess", lambda command: {"action": "ALLOW", "rule": "allow", "reason": "broken"})
    report = _report(target, capsys, "--no-benchmark")
    statuses = {item["status"] for item in report["readiness"]["items"]}
    assert statuses == STATES
    assert report["readiness"]["failed"] == 1
    assert _item(report, "policy")["status"] == "failed"
    assert _item(report, "graph")["status"] == "verified"
    assert _item(report, "benchmark")["status"] == "not-verified"
