"""CITATION.cff describes the product that ships, not an earlier one.

Measured before this file existed (2026-09-21): the citation file said `version: "1.4.0"`,
`date-released: 2026-09-20`, an abstract about "ten installable kits for Claude Code" and no
Codex keyword, while `hpp.__version__` was 2.4.1 and the README opened with the harness. Nothing
tied the two together. The file is parsed here by line, without a YAML library, because the
package is stdlib-only and the fields under test are one scalar per line.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from hpp import __version__

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
CITATION = PRODUCT_ROOT / "CITATION.cff"
README = PRODUCT_ROOT / "README.md"

# Why: the release bump script rewrites `version:` as a whole line; any other layout (inline
# map, trailing comment, indentation) would slip past it and ship a stale citation.
VERSION_LINE = re.compile(r'^version: "(?P<version>[^"]+)"$', re.M)
DATE_LINE = re.compile(r'^date-released: "(?P<date>\d{4}-\d{2}-\d{2})"$', re.M)
ABSTRACT_LINE = re.compile(r'^abstract: "(?P<abstract>[^"]+)"$', re.M)


def _scalar(pattern: re.Pattern[str], text: str, group: str) -> str:
    found = pattern.findall(text)
    assert len(found) == 1, (pattern.pattern, found)
    return found[0]


def _keywords(text: str) -> list[str]:
    block = text.split("keywords:", 1)[1]
    return [line.strip()[2:] for line in block.splitlines() if line.strip().startswith("- ")]


def _readme_first_paragraph() -> str:
    """The first prose paragraph after the H1 and the bold tagline."""
    body = README.read_text(encoding="utf-8").split("\n# House Party Protocol\n", 1)[1]
    paragraphs = [block.strip() for block in body.split("\n\n") if block.strip()]
    prose = [block for block in paragraphs if not block.startswith(("**", "#", "<", "```"))]
    return " ".join(prose[0].split())


def test_citation_version_is_the_package_version() -> None:
    text = CITATION.read_text(encoding="utf-8")
    assert _scalar(VERSION_LINE, text, "version") == __version__


def test_citation_release_date_is_a_real_date_not_in_the_future() -> None:
    text = CITATION.read_text(encoding="utf-8")
    released = dt.date.fromisoformat(_scalar(DATE_LINE, text, "date"))
    assert released <= dt.date.today(), released


def test_citation_abstract_is_the_readme_opening_paragraph() -> None:
    text = CITATION.read_text(encoding="utf-8")
    assert _scalar(ABSTRACT_LINE, text, "abstract") == _readme_first_paragraph()


def test_citation_keywords_name_both_hosts() -> None:
    keywords = _keywords(CITATION.read_text(encoding="utf-8"))
    assert {"claude-code", "codex-cli"} <= set(keywords), keywords
    assert len(keywords) == len(set(keywords)), keywords


def test_CONTROLE_the_version_pattern_rejects_the_layouts_the_bump_script_cannot_rewrite() -> None:
    for layout in ('version: 1.4.0\n', 'version: "1.4.0"  # stale\n', '  version: "1.4.0"\n', 'version: "1.4.0" \n'):
        assert VERSION_LINE.findall(layout) == [], layout
    assert VERSION_LINE.findall('version: "1.4.0"\n') == ["1.4.0"]
