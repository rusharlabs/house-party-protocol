"""A4 — every hook the product installs declares what it is CAPABLE of.

`hpp init` told you which hooks to paste. It did not tell you what each one can do: write
files in your project, control the process, send transcript-derived text to a model, touch
the network, deny a tool call, or keep records. Consent without capability is a signature on
a blank page.

The contract this file pins:
  · a closed vocabulary of six capability groups, declared once in the manifest;
  · one declaration per hook, with `module`, `script`, `events`, `capabilities`, `exit_policy`;
  · `hpp doctor` FAILS on a hook without a declaration and on a module that declares the
    `hooks` component with nothing declared for it — absent is never read as empty, which is
    the `penless` lesson (a missing `tools:` meant *all* tools, and a gate that looked for the
    word `Write` passed all seven violators);
  · `hpp init` prints the capability table BEFORE the commands to paste.

Vocabulary adapted from ECC (MIT). No code copied.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from hpp.manifest import ManifestError, load_manifest, validate_manifest

PRODUCT_ROOT = Path(__file__).resolve().parent.parent

VOCABULARY = {
    "automatic-source-writes",
    "command-rewrite-and-process-control",
    "transcript-derived-llm-egress",
    "mcp-network-and-process-activity",
    "automatic-permission-gates",
    "session-observation-and-cost-records",
}


@pytest.fixture()
def manifest():
    data, _ = load_manifest()
    return data


def _run(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "hpp", *argv], cwd=PRODUCT_ROOT,
                          capture_output=True, text=True, encoding="utf-8", timeout=120)


# ---------------------------------------------------------------------------
# The declaration itself
# ---------------------------------------------------------------------------

def test_the_manifest_declares_the_closed_vocabulary(manifest):
    assert set(manifest["hook_capabilities"]) == VOCABULARY
    assert len(manifest["hook_capabilities"]) == len(set(manifest["hook_capabilities"]))


def test_every_hook_declares_module_events_capabilities_and_exit_policy(manifest):
    hooks = manifest["hooks"]
    assert len(hooks) >= 15, len(hooks)
    module_ids = {module["id"] for module in manifest["modules"]}
    seen = set()
    for hook in hooks:
        assert hook["id"] not in seen, hook["id"]
        seen.add(hook["id"])
        assert hook["module"] in module_ids, hook
        assert hook["script"] and not hook["script"].startswith(("/", "..")), hook
        assert hook["events"] and all(isinstance(event, str) and event for event in hook["events"]), hook
        assert hook["capabilities"], hook
        assert set(hook["capabilities"]) <= VOCABULARY, hook
        assert hook["exit_policy"] in {"observe", "warn", "block"}, hook


def test_every_module_that_declares_the_hooks_component_has_hooks(manifest):
    declared = {hook["module"] for hook in manifest["hooks"]}
    missing = [module["id"] for module in manifest["modules"]
               if "hooks" in module["components"] and module["id"] not in declared]
    assert not missing, missing


def test_no_hook_sends_transcript_derived_text_to_a_model(manifest):
    """The product's refusal, stated as a measurement instead of a promise."""
    egress = [hook["id"] for hook in manifest["hooks"]
              if "transcript-derived-llm-egress" in hook["capabilities"]]
    assert egress == [], egress


# ---------------------------------------------------------------------------
# CONTROLE — the validator must refuse what it exists to refuse
# ---------------------------------------------------------------------------

def test_CONTROLE_a_hook_without_capabilities_is_refused(manifest):
    broken = json.loads(json.dumps(manifest))
    broken["hooks"][0].pop("capabilities")
    with pytest.raises(ManifestError, match="capabilities"):
        validate_manifest(broken)


def test_CONTROLE_an_empty_capabilities_list_is_refused_not_read_as_none(manifest):
    """The `penless` lesson: absent must never be read as empty."""
    broken = json.loads(json.dumps(manifest))
    broken["hooks"][0]["capabilities"] = []
    with pytest.raises(ManifestError, match="capabilities"):
        validate_manifest(broken)


def test_CONTROLE_a_capability_outside_the_vocabulary_is_refused(manifest):
    broken = json.loads(json.dumps(manifest))
    broken["hooks"][0]["capabilities"] = ["does-whatever-it-likes"]
    with pytest.raises(ManifestError, match="does-whatever-it-likes"):
        validate_manifest(broken)


def test_CONTROLE_an_unknown_exit_policy_is_refused(manifest):
    broken = json.loads(json.dumps(manifest))
    broken["hooks"][0]["exit_policy"] = "maybe"
    with pytest.raises(ManifestError, match="exit_policy"):
        validate_manifest(broken)


def test_CONTROLE_a_hook_module_that_is_not_a_module_is_refused(manifest):
    broken = json.loads(json.dumps(manifest))
    broken["hooks"][0]["module"] = "ghost-kit"
    with pytest.raises(ManifestError, match="ghost-kit"):
        validate_manifest(broken)


def test_CONTROLE_a_hooks_module_with_no_declaration_is_refused(manifest):
    broken = json.loads(json.dumps(manifest))
    victim = next(module["id"] for module in broken["modules"] if "hooks" in module["components"])
    broken["hooks"] = [hook for hook in broken["hooks"] if hook["module"] != victim]
    with pytest.raises(ManifestError, match=victim):
        validate_manifest(broken)


def test_CONTROLE_the_manifest_as_shipped_still_validates(manifest):
    validate_manifest(json.loads(json.dumps(manifest)))


# ---------------------------------------------------------------------------
# The two surfaces: doctor refuses, init prints
# ---------------------------------------------------------------------------

def test_doctor_reports_the_hook_capability_census(manifest):
    result = _run("doctor", "--json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["hooks"]["declared"] == len(manifest["hooks"])
    assert set(report["hooks"]["by_capability"]) == VOCABULARY
    assert report["hooks"]["by_capability"]["transcript-derived-llm-egress"] == 0


def test_doctor_fails_on_a_hook_without_a_declaration(tmp_path: Path, manifest):
    broken = json.loads(json.dumps(manifest))
    broken["hooks"][0].pop("capabilities")
    target = tmp_path / "hpp.manifest.json"
    target.write_text(json.dumps(broken), encoding="utf-8")
    result = _run("doctor", "--manifest", str(target), "--json")
    assert result.returncode == 2, result.stdout
    assert "capabilities" in result.stderr


def _emitted_root() -> Path | None:
    """The emitted product beside its marketplace, when this suite runs there; None in the source tree."""
    return PRODUCT_ROOT if (PRODUCT_ROOT / "marketplace.json").is_file() else None


def test_doctor_fails_on_a_hook_that_is_wired_but_not_declared(tmp_path: Path, manifest):
    """🔴 CORRIGIDO 2026-09-22 (cross-model review, MÉDIA): the table was only checked against
    itself. A module that wired three scripts in `hooks/hooks.json` and declared one passed doctor,
    because doctor never opened the file the host reads. The coverage lived in a source-tree test
    that does not ship. Now `validate_distribution` reads every module's `hooks.json` and refuses a
    wired script with no declaration — in the emitted tree, which is where a user runs doctor.
    """
    root = _emitted_root()
    if root is None:
        pytest.skip("wired-vs-declared needs the emitted tree (marketplace.json beside the manifest)")
    modules_with_hooks = [h["module"] for h in manifest["hooks"]]
    assert modules_with_hooks, "vacuity: no module declares hooks"
    victim = next(h for h in manifest["hooks"] if (root / next(m["path"] for m in manifest["modules"] if m["id"] == h["module"]) / "hooks" / "hooks.json").is_file())
    broken = json.loads(json.dumps(manifest))
    broken["hooks"] = [h for h in broken["hooks"] if h["id"] != victim["id"]]
    # the copy must sit beside marketplace.json, or validate_distribution never runs (source-contract)
    target = root / "hpp.manifest.WIRED-NOT-DECLARED.json"
    target.write_text(json.dumps(broken), encoding="utf-8")
    try:
        result = _run("doctor", "--manifest", str(target))
    finally:
        target.unlink()
    assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
    assert victim["script"] in result.stderr and "no capability declaration" in result.stderr, result.stderr


def test_CONTROLE_the_shipped_tree_wires_nothing_it_does_not_declare(manifest):
    """The positive side of the gate above: on the real manifest doctor passes — so the assertion
    in the previous test is about the planted gap, not about a pre-existing red."""
    if _emitted_root() is None:
        pytest.skip("needs the emitted tree")
    result = _run("doctor")
    assert result.returncode == 0, result.stderr


def test_init_prints_the_capability_table_before_the_commands_to_paste(tmp_path: Path):
    result = _run("init", "--target", str(tmp_path), "--non-interactive", "--no-animation",
                  "--no-benchmark")
    assert result.returncode in (0, 1), result.stderr
    out = result.stdout
    assert "HOOK CAPABILITIES" in out, out[-2000:]
    assert out.index("HOOK CAPABILITIES") < out.index("WIRE"), "the table must come before the paste block"
    assert "automatic-permission-gates" in out


def test_init_json_carries_the_same_table(tmp_path: Path):
    result = _run("init", "--target", str(tmp_path), "--non-interactive", "--no-benchmark", "--json")
    assert result.returncode in (0, 1), result.stderr
    report = json.loads(result.stdout)
    stage = next(item for item in report["stages"] if item["stage"] == "wire-suggest")
    rows = stage["detail"]["hook_capabilities"]
    assert rows, stage["detail"]
    for row in rows:
        assert row["capabilities"] and set(row["capabilities"]) <= VOCABULARY, row
        assert row["exit_policy"] in {"observe", "warn", "block"}


def test_CONTROLE_a_module_with_no_hooks_shows_an_empty_table(tmp_path: Path):
    """Vacuity check: the table must be derived from the chosen modules, not printed blindly."""
    result = _run("init", "--target", str(tmp_path), "--non-interactive", "--no-benchmark",
                  "--modules", "supabase-pack", "--json")
    assert result.returncode in (0, 1), result.stderr
    report = json.loads(result.stdout)
    stage = next(item for item in report["stages"] if item["stage"] == "wire-suggest")
    assert stage["detail"]["hook_capabilities"] == []
