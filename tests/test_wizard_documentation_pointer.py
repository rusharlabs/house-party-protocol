"""`hpp init` ends by naming the documentation this copy carries -- and it may only
name a file that exists on disk.

Measured in this product before the pointer existed (2026-09-23): `CATALOG` appeared
ZERO times and `docs/` ZERO times in `hpp/*.py`, while the distribution shipped eight
generated documentation pages. Whoever ran the installer finished it without ever being
told those pages were there. The reference measurement of the same ruler was `hpp doctor`,
cited 11 times in the same files -- so the ruler did read the sources.

The pointer is MEASURED, never a literal, and the controls are what prove it:
a distribution root with no documentation names nothing at all, and a root carrying only
the `.html` variant of a page names that one instead of its missing `.md` sibling. A
hardcoded list would pass the first test of this file and fail both controls -- which is
the point, because `docs/CATALOG.*` exists only in an emitted product, never in a source
checkout.

The section title is asserted as the rendered header (`  DOCUMENTATION`) and not as a bare
`READ`: the first draft of this file searched for `READ`, which is a substring of the
`READINESS` header that was already there, so the negative control passed with the feature
absent. A probe that cannot come back empty proves nothing.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from hpp import wizard
from hpp.manifest import load_manifest
from hpp.brand import SIGNATURE
from hpp.term import Console

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
HEADER = "  DOCUMENTATION"
ESC = "\033"


@pytest.fixture()
def target(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    return workspace


@pytest.fixture()
def report(target):
    manifest, manifest_path = load_manifest()
    options = wizard.InitOptions(target=target, target_label=str(target), benchmark_k=0)
    return wizard.run_init(options, manifest, manifest_path)


def _render(report: dict) -> tuple[str, Console]:
    console = Console(stream=io.StringIO(), tier="none", animate=False, env={}, width=80)
    wizard.render_report(report, console)
    return console.stream.getvalue(), console


def test_the_report_names_the_documentation_this_copy_carries(report):
    documentation = report["documentation"]
    assert documentation, "the report names no documentation at all"
    for item in documentation:
        assert (PRODUCT_ROOT / item["path"]).is_file(), f"named a path that is not on disk: {item['path']}"
        assert item["note"].strip(), f"{item['path']} is named with no explanation of what it is"


def test_the_human_report_prints_the_section_and_every_path_it_names(report):
    output, _console = _render(report)
    assert HEADER in output
    for item in report["documentation"]:
        assert item["path"] in output, f"{item['path']} is in the report and not in the output"
    assert ESC not in output, "the section emitted colour on a Console with no colour"


def test_the_pointer_comes_before_the_closing_line_and_never_replaces_it(report):
    output, console = _render(report)
    # Why: the signature comes from `hpp.brand.SIGNATURE`, never from a literal copy. A copy
    # here would have to be declared as an exception in the identity ruleset, to say what the
    # import already says better -- the test asserts against the SOURCE, so it cannot drift from it.
    # (this wording was rewritten after the FIRST version of the comment quoted the term and,
    #  by quoting it, triggered the very finding it was explaining.)
    assert output.index(HEADER) < output.index(SIGNATURE)
    assert output.rstrip().endswith("Welcome to the party." + console.glyph("cursor"))


def test_no_path_the_table_offers_is_printed_unless_it_is_named(report):
    output, _console = _render(report)
    named = {item["path"] for item in report["documentation"]}
    for variants, _note in wizard.DOCUMENTATION:
        for candidate in variants:
            if candidate not in named:
                assert candidate not in output, f"{candidate} is printed and was not measured on disk"


def test_CONTROLE_a_root_with_no_documentation_names_nothing(tmp_path):
    """Control: the same ruler, pointed at a root that carries no documentation, must come
    back EMPTY. If it answered the same as the real root, it would be reading a literal."""
    empty_root = tmp_path / "no-docs"
    empty_root.mkdir()
    assert wizard.documentation_on_disk(empty_root) == []


def test_CONTROLE_it_names_the_variant_that_exists_not_the_missing_sibling(tmp_path):
    """Control: with only the `.html` of a page on disk, the `.md` must not be named --
    and when the `.md` appears, it wins. This is the case of a source checkout, where
    `docs/CATALOG.md` is generated at emission and does not exist yet."""
    root = tmp_path / "half-docs"
    (root / "docs").mkdir(parents=True)
    variants = next(variants for variants, _ in wizard.DOCUMENTATION if len(variants) > 1)
    preferred, fallback = variants[0], variants[1]
    (root / fallback).write_text("<html></html>", encoding="utf-8")
    assert [item["path"] for item in wizard.documentation_on_disk(root)] == [fallback]
    (root / preferred).write_text("# page", encoding="utf-8")
    assert [item["path"] for item in wizard.documentation_on_disk(root)] == [preferred]


def test_CONTROLE_the_renderer_prints_no_empty_section(report):
    """Control: a report that names no documentation must print no section header either --
    otherwise a pip install with no docs/ would show an empty block."""
    without = dict(report, documentation=[])
    output, _console = _render(without)
    assert HEADER not in output
