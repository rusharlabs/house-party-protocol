"""The host x module x channel matrix is rendered from the manifest, and the documents carry that render.

Coverage used to live in prose ("six modules native, four explicit-command") in four documents, with
nothing tying the sentences to `hpp.manifest.json`. `hpp/hosts.py` derives one row per module --
integration level and installation channels per host -- and `docs/ARCHITECTURE.md` (and its pt-BR
pair) must contain exactly that render: a manifest edit that is not re-rendered fails here.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from hpp import cli
from hpp.hosts import codex_plugin_eligible, host_matrix, render_host_matrix
from hpp.manifest import load_manifest

DOCS = Path(__file__).resolve().parent.parent / "docs"


@pytest.fixture()
def manifest():
    data, _ = load_manifest()
    return data


def test_one_row_per_module_with_the_integration_the_manifest_declares(manifest):
    rows = host_matrix(manifest)
    assert [row["id"] for row in rows] == [module["id"] for module in manifest["modules"]]
    for row, module in zip(rows, manifest["modules"]):
        assert row["version"] == module["version"]
        assert row["claude-code"]["integration"] == module["hosts"]["claude-code"]
        assert row["codex"]["integration"] == module["hosts"]["codex"]


def test_channels_follow_the_components_and_the_coverage(manifest):
    by_id = {row["id"]: row for row in host_matrix(manifest)}
    for module in manifest["modules"]:
        row = by_id[module["id"]]
        assert "plugin" in row["claude-code"]["channels"]
        assert ("hooks" in row["claude-code"]["channels"]) == ("hooks" in module["components"])
        unsupported = module["hosts"]["codex"] == "unsupported"
        assert ("copy" in row["codex"]["channels"]) == (not unsupported)
        assert ("plugin (skills)" in row["codex"]["channels"]) == codex_plugin_eligible(module)
        assert codex_plugin_eligible(module) == (not unsupported and "skills" in module["components"])


def test_CONTROLE_eligibility_discriminates_in_both_directions(manifest):
    by_id = {module["id"]: module for module in manifest["modules"]}
    assert codex_plugin_eligible(by_id["operator-kit"])            # skills, explicit-command on Codex
    assert codex_plugin_eligible(by_id["lane-kit"])                # skills (lane-coordinator, house-session)
    assert not codex_plugin_eligible(by_id["claude-dev-kit"])      # skills, but unsupported on Codex
    assert not codex_plugin_eligible(by_id["kit-forge"])           # supported, but carries no skills


def test_the_render_is_a_markdown_table_in_both_languages(manifest):
    english = render_host_matrix(manifest, "en")
    portuguese = render_host_matrix(manifest, "pt-BR")
    for text in (english, portuguese):
        lines = text.strip().splitlines()
        assert lines[0].startswith("| ") and set(lines[1]) <= set("|-: ")
        assert len(lines) == 2 + len(manifest["modules"])
    assert english != portuguese
    assert "Claude Code" in english and "Codex CLI" in english


def test_architecture_carries_the_rendered_matrix_in_both_languages(manifest):
    for lang, name in (("en", "ARCHITECTURE.md"), ("pt-BR", "ARCHITECTURE.pt-BR.md")):
        text = (DOCS / name).read_text(encoding="utf-8")
        assert render_host_matrix(manifest, lang).strip() in text, (
            f"{name} does not carry the matrix rendered from the manifest; regenerate with "
            f"`python -m hpp doctor --matrix` (en) / `render_host_matrix(manifest, 'pt-BR')`")


def test_CONTROLE_a_changed_manifest_renders_a_different_matrix(manifest):
    changed = copy.deepcopy(manifest)
    changed["modules"][0]["hosts"]["codex"] = "unsupported"
    assert render_host_matrix(changed, "en") != render_host_matrix(manifest, "en")


def test_doctor_matrix_prints_the_english_render(manifest, capsys):
    assert cli.main(["doctor", "--matrix"]) == 0
    assert capsys.readouterr().out.strip() == render_host_matrix(manifest, "en").strip()
