"""SECURITY.md supports the current minor line, and says which one.

Measured 2026-09-27: both security pages said `2.6.x -- current line` while the package was 2.9.0
and 2.10.0 was being prepared. A reader on 2.9 was told their version received no fixes; nothing
in the suite compared the table with the version the package carries. The supported line may run
ahead of the package (the page is updated with the release that ships it), never behind it; the
two languages name the same line, and the row that tells older versions where to go names it too.
"""
from __future__ import annotations

import re
from pathlib import Path

from hpp import __version__

ROOT = Path(__file__).resolve().parent.parent
PAGES = ("SECURITY.md", "SECURITY.pt-BR.md")
PACKAGE_MINOR = tuple(int(part) for part in __version__.split(".")[:2])
SUPPORTED = re.compile(r"(?m)^\| (\d+)\.(\d+)\.x \| (?:yes|sim) ")
UPGRADE = re.compile(r"(?:upgrade to|atualize para) (\d+)\.(\d+)\.x")
UNSUPPORTED_RANGE = re.compile(r"(?m)^\| (\d+)\.(\d+) – (\d+)\.(\d+) \| (?:no|não) ")


def _text(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _supported(text: str) -> tuple[int, int]:
    match = SUPPORTED.search(text)
    assert match, "no `| X.Y.x | yes ...` row in the supported-versions table"
    return int(match.group(1)), int(match.group(2))


def test_the_supported_line_is_not_older_than_the_package():
    for name in PAGES:
        supported = _supported(_text(name))
        assert supported >= PACKAGE_MINOR, (
            f"{name} supports {supported[0]}.{supported[1]}.x; the package is {__version__}"
        )


def test_both_languages_name_the_same_line():
    assert _supported(_text(PAGES[0])) == _supported(_text(PAGES[1]))


def test_the_older_versions_row_points_at_the_supported_line():
    for name in PAGES:
        text = _text(name)
        supported = _supported(text)
        upgrade = UPGRADE.search(text)
        assert upgrade, f"{name}: the row for older versions does not say where to upgrade"
        assert (int(upgrade.group(1)), int(upgrade.group(2))) == supported, name
        older = UNSUPPORTED_RANGE.search(text)
        assert older, f"{name}: no `| X.Y – X.Z | no ...` row"
        assert (int(older.group(3)), int(older.group(4))) == (supported[0], supported[1] - 1), (
            f"{name}: the unsupported range does not end right below the supported line"
        )


def test_CONTROLE_the_table_reader_sees_a_row_and_ignores_the_others():
    assert _supported("| 2.10.x | yes — current line |") == (2, 10)
    assert _supported("| 2.10.x | sim — linha atual |") == (2, 10)
    assert SUPPORTED.search("| 1.x | no |\n| 2.0 – 2.9 | no — upgrade to 2.10.x |") is None
    assert UPGRADE.search("upgrade to 2.10.x").groups() == ("2", "10")
    assert UNSUPPORTED_RANGE.search("| 2.0 – 2.9 | não — atualize para 2.10.x |").groups() == ("2", "0", "2", "9")
