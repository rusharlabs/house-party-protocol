"""The Codex CLI plugin channel: `.agents/plugins/marketplace.json` plus one `.codex-plugin/plugin.json`
per module that carries skills and is supported on Codex.

Codex CLI reads a marketplace at `.agents/plugins/marketplace.json` (its own form: `name`,
`interface.displayName`, `plugins[]` with a `source` object) and, for the modules it lists, a plugin
manifest at `<module>/.codex-plugin/plugin.json`. `hpp doctor` cross-checks both against the
manifest whenever the Codex marketplace sits beside `marketplace.json`: every listed plugin is a
module that qualifies for the channel, every qualifying module is listed, versions agree, and every
Codex plugin manifest carries the EMPTY inline hooks object `{"hooks": {}}` -- the hooks are Claude
Code's, and on Codex the same capabilities stay explicit commands. Absent is not "no hooks": with no
`hooks` key the Codex plugin loader reads `hooks/hooks.json` from the plugin root, and an empty list
is dropped as if absent.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from hpp.hosts import codex_plugin_eligible
from hpp.manifest import ManifestError, load_manifest, validate_distribution

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
EMITTED = (PRODUCT_ROOT / "marketplace.json").is_file()
CODEX_MARKETPLACE = Path(".agents") / "plugins" / "marketplace.json"


def _tree(tmp_path: Path, manifest: dict) -> Path:
    """A synthetic emitted tree: the manifest, a consistent marketplace.json, one directory per module
    with its Claude plugin manifest, and the Codex channel files for the qualifying modules."""
    root = tmp_path / "emitted"
    root.mkdir()
    (root / "hpp.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    plugins = []
    codex_plugins = []
    for module in manifest["modules"]:
        module_dir = root / module["path"]
        (module_dir / ".claude-plugin").mkdir(parents=True)
        claude = {"name": module["id"], "version": module["version"], "description": f"{module['id']} module"}
        (module_dir / ".claude-plugin" / "plugin.json").write_text(json.dumps(claude), encoding="utf-8")
        plugins.append({"name": module["id"], "version": module["version"], "source": f"./{module['path']}"})
        if codex_plugin_eligible(module):
            (module_dir / ".codex-plugin").mkdir()
            codex = {"name": module["id"], "version": module["version"], "description": claude["description"],
                     "skills": "./skills/", "hooks": {"hooks": {}}}
            (module_dir / ".codex-plugin" / "plugin.json").write_text(json.dumps(codex), encoding="utf-8")
            codex_plugins.append({"name": module["id"], "source": {"source": "local", "path": f"./{module['path']}"},
                                  "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                                  "category": "Developer Tools"})
    (root / "marketplace.json").write_text(json.dumps({"name": manifest["name"], "version": manifest["product_version"],
                                                       "plugins": plugins}), encoding="utf-8")
    codex_path = root / CODEX_MARKETPLACE
    codex_path.parent.mkdir(parents=True)
    codex_path.write_text(json.dumps({"name": manifest["name"], "interface": {"displayName": "House Party Protocol"},
                                      "plugins": codex_plugins}), encoding="utf-8")
    return root


@pytest.fixture()
def manifest():
    data, _ = load_manifest()
    return data


def _codex(root: Path) -> dict:
    return json.loads((root / CODEX_MARKETPLACE).read_text(encoding="utf-8"))


def _write_codex(root: Path, document: dict) -> None:
    (root / CODEX_MARKETPLACE).write_text(json.dumps(document), encoding="utf-8")


def test_a_consistent_codex_channel_is_checked_and_counted(manifest, tmp_path):
    root = _tree(tmp_path, manifest)
    report = validate_distribution(manifest, root)
    eligible = [module for module in manifest["modules"] if codex_plugin_eligible(module)]
    assert report["status"] == "ok"
    assert report["codex_marketplace"] == {"checked": True, "plugins": len(eligible)}
    assert len(eligible) >= 1


def test_CONTROLE_without_a_codex_marketplace_the_distribution_still_checks_and_says_so(manifest, tmp_path):
    root = _tree(tmp_path, manifest)
    (root / CODEX_MARKETPLACE).unlink()
    report = validate_distribution(manifest, root)
    assert report["status"] == "ok" and report["codex_marketplace"] == {"checked": False}


def test_a_listed_module_that_does_not_qualify_is_refused(manifest, tmp_path):
    root = _tree(tmp_path, manifest)
    document = _codex(root)
    unsupported = next(module for module in manifest["modules"] if not codex_plugin_eligible(module))
    document["plugins"].append({"name": unsupported["id"],
                                "source": {"source": "local", "path": f"./{unsupported['path']}"},
                                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                                "category": "Developer Tools"})
    _write_codex(root, document)
    with pytest.raises(ManifestError, match=unsupported["id"]):
        validate_distribution(manifest, root)


def test_a_qualifying_module_missing_from_the_codex_marketplace_is_refused(manifest, tmp_path):
    root = _tree(tmp_path, manifest)
    document = _codex(root)
    dropped = document["plugins"].pop()
    _write_codex(root, document)
    with pytest.raises(ManifestError, match=dropped["name"]):
        validate_distribution(manifest, root)


def test_a_version_drift_in_the_codex_plugin_manifest_is_refused(manifest, tmp_path):
    root = _tree(tmp_path, manifest)
    module = next(module for module in manifest["modules"] if codex_plugin_eligible(module))
    path = root / module["path"] / ".codex-plugin" / "plugin.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["version"] = "0.0.1"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ManifestError, match=module["id"]):
        validate_distribution(manifest, root)


def test_a_missing_codex_plugin_manifest_is_refused(manifest, tmp_path):
    root = _tree(tmp_path, manifest)
    module = next(module for module in manifest["modules"] if codex_plugin_eligible(module))
    (root / module["path"] / ".codex-plugin" / "plugin.json").unlink()
    with pytest.raises(ManifestError, match=module["id"]):
        validate_distribution(manifest, root)


@pytest.mark.parametrize("hooks", [
    "./hooks/hooks.json",
    ["./hooks/hooks.json"],
    {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "true"}]}]}},
    [],   # the Codex loader drops an empty list as if the key were absent, and reads hooks/hooks.json
    {},   # registers nothing on Codex today, but is not the form the channel renders
])
def test_a_codex_plugin_manifest_that_declares_hooks_is_refused(manifest, tmp_path, hooks):
    root = _tree(tmp_path, manifest)
    module = next(module for module in manifest["modules"] if codex_plugin_eligible(module))
    path = root / module["path"] / ".codex-plugin" / "plugin.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["hooks"] = hooks
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ManifestError, match=rf"{module['id']}\b.*hooks"):
        validate_distribution(manifest, root)


def test_a_codex_plugin_manifest_without_the_empty_hooks_override_is_refused(manifest, tmp_path):
    """Omitting `hooks` exposes them: Codex then loads the module's hooks/hooks.json by default."""
    root = _tree(tmp_path, manifest)
    module = next(module for module in manifest["modules"] if codex_plugin_eligible(module))
    path = root / module["path"] / ".codex-plugin" / "plugin.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    del document["hooks"]
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ManifestError, match=rf"{module['id']}\b.*hooks/hooks\.json"):
        validate_distribution(manifest, root)


@pytest.mark.parametrize("edit, fragment", [
    (lambda doc: doc.update(name="another-marketplace"), "name"),
    (lambda doc: doc["plugins"][0].update(source="./frameworks/x"), "source"),
    (lambda doc: doc["plugins"][0]["source"].update(path="./elsewhere"), "source"),
    (lambda doc: doc.update(plugins={}), "plugins"),
])
def test_a_codex_marketplace_off_the_documented_shape_is_refused(manifest, tmp_path, edit, fragment):
    root = _tree(tmp_path, manifest)
    document = _codex(root)
    edit(document)
    _write_codex(root, document)
    with pytest.raises(ManifestError, match=fragment):
        validate_distribution(manifest, root)


def test_CONTROLE_the_synthetic_tree_discriminates_a_claude_side_drift_too(manifest, tmp_path):
    """Control: the fixture is a real distribution for `validate_distribution`, not a tree where
    everything passes -- the pre-existing Claude-side checks still fire in it."""
    root = _tree(tmp_path, manifest)
    changed = copy.deepcopy(manifest)
    changed["modules"][0]["version"] = "0.0.1"
    with pytest.raises(ManifestError, match="diverges"):
        validate_distribution(changed, root)


@pytest.mark.skipif(not EMITTED, reason="source tree: the Codex marketplace is written by the emission")
def test_the_emitted_product_carries_the_codex_marketplace_and_doctor_checks_it():
    assert (PRODUCT_ROOT / CODEX_MARKETPLACE).is_file()
    result = subprocess.run([sys.executable, "-m", "hpp", "doctor", "--json"], cwd=PRODUCT_ROOT,
                            capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stderr
    distribution = json.loads(result.stdout)["distribution"]
    assert distribution["codex_marketplace"]["checked"] is True
    assert distribution["codex_marketplace"]["plugins"] >= 1
