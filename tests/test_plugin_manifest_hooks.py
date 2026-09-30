"""A Claude Code plugin manifest never lists the standard `hooks/hooks.json`.

Why (2.11.1, reported by a user whose four plugins would not load): Claude Code loads
`<plugin>/hooks/hooks.json` on its own. Six modules also listed it in `.claude-plugin/plugin.json`
(`"hooks": "./hooks/hooks.json"`), so the same file was named twice. Earlier Claude Code versions
refuse such a plugin ("Duplicate hooks file detected"); 2.1.x loads it once and prints a notice.
`manifest.hooks` is for additional hook files, never for the standard one.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _file_entries(value) -> list[str]:
    """The hook-file paths a manifest's `hooks` value names (an inline object names none)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def standard_duplicates(root: Path) -> list[str]:
    """Every manifest under `<root>/<area>/<module>/` whose `hooks` names that module's hooks/hooks.json."""
    found = []
    for manifest in sorted(root.glob("*/*/.claude-plugin/plugin.json")):
        plugin = manifest.parent.parent
        standard = (plugin / "hooks" / "hooks.json").resolve()
        for entry in _file_entries(json.loads(manifest.read_text(encoding="utf-8")).get("hooks")):
            if (plugin / entry).resolve() == standard:
                found.append(f"{manifest.relative_to(root).as_posix()}: {entry}")
    return found


def _module(root: Path, hooks=None) -> Path:
    plugin = root / "frameworks" / "sample-kit-1.0.0"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / "hooks").mkdir()
    (plugin / "hooks" / "hooks.json").write_text('{"hooks": {}}', encoding="utf-8")
    manifest = {"name": "sample-kit", "version": "1.0.0"}
    if hooks is not None:
        manifest["hooks"] = hooks
    (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    return plugin


def test_the_check_catches_a_manifest_that_lists_the_standard_file(tmp_path: Path) -> None:
    _module(tmp_path, "./hooks/hooks.json")
    assert standard_duplicates(tmp_path) == ["frameworks/sample-kit-1.0.0/.claude-plugin/plugin.json: ./hooks/hooks.json"]


@pytest.mark.parametrize("hooks", [None, "./hooks/extra.json", {"hooks": {}}])
def test_CONTROL_a_manifest_without_the_standard_file_passes(tmp_path: Path, hooks) -> None:
    _module(tmp_path, hooks)
    assert standard_duplicates(tmp_path) == []


def test_no_distributed_plugin_manifest_lists_the_standard_hooks_file() -> None:
    if not (ROOT / "marketplace.json").is_file():
        pytest.skip("no marketplace.json at <product-root> (source tree): the modules are emitted elsewhere")
    assert len(list(ROOT.glob("*/*/.claude-plugin/plugin.json"))) >= 5, "the scan found no plugin manifests"
    duplicates = standard_duplicates(ROOT)
    assert not duplicates, (
        "manifest.hooks names the standard hooks/hooks.json, which Claude Code already loads; "
        "remove the entry:\n" + "\n".join(duplicates)
    )
