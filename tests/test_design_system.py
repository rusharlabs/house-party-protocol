"""The stylesheet is a file, it matches every page, and its palette IS the brand's.

Why this file exists: the CSS that every published page renders with lived as a 3.294-character
string inside `tools/catalog_md.py`. Nothing was wrong with it -- measured, it uses exactly the
four hex values `docs/BRAND.md` declares and no fifth -- but nothing held it there either, and a
contributor who wanted to build in the project's language had to open a Python file and copy a
literal out of it.

The stylesheet is now emitted as `docs/hpp.css` from the same constant the pages inline, so the
two cannot drift by construction. These tests lock the part that a future edit could still break:
that the palette stays the brand's, that no fifth colour arrives through an `rgba()`, and that no
page starts fetching a font or a stylesheet from someone else's domain.
"""
from __future__ import annotations

import re
from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
DOCS = PRODUCT_ROOT / "docs"
CSS = DOCS / "hpp.css"
BRAND = DOCS / "BRAND.md"
# Why: the GENERATED pages inline the generator's stylesheet; the MANUAL is written BY HAND in the
# source (`docs/`) and carries its own CSS. They are different invariants,
# and folding both into one test produced a failure that looked like a product defect and was a
# defect of the assertion. Whoever moves the MANUAL into the generator changes this list -- and the
# test holds them to it.
GENERATED = ("CATALOG.html", "CATALOG.pt-BR.html", "index.html")
HANDWRITTEN = ("MANUAL.html", "MANUAL.pt-BR.html")

HEX = re.compile(r"#[0-9a-fA-F]{6}\b")
# Why: BRAND.md allows a token at reduced alpha explicitly -- "a lighter step is the same token
# at reduced opacity" -- and the stylesheet uses two of them that way, the ink AND the paper. Any
# OTHER rgb triple is a fifth colour arriving through the side door, where a hex scan never sees
# it. The allowed triples are DERIVED from BRAND.md rather than written here: a hard-coded list
# would have to be edited whenever the palette moves, and the edit is what would be forgotten.
RGBA = re.compile(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})")
# Why: BRAND.md — "No published asset carries a webfont: the stack is system-only, and the
# self-contained material makes no external request."
EXTERNAL = re.compile(r"@import|url\(\s*['\"]?https?://|@font-face")


def _palette(text: str) -> set[str]:
    return {h.upper() for h in HEX.findall(text)}


def test_the_stylesheet_is_a_file() -> None:
    assert CSS.is_file(), "docs/hpp.css does not exist — the CSS is back to living only inside the generator"
    assert CSS.stat().st_size > 1000, "hpp.css exists but is empty or truncated"


def test_the_CSS_palette_is_exactly_the_BRAND_palette() -> None:
    from_css = _palette(CSS.read_text(encoding="utf-8"))
    from_brand = _palette(BRAND.read_text(encoding="utf-8"))
    assert from_brand, "BRAND.md stopped declaring hex values — without them there is nothing to compare against"
    assert from_css == from_brand, (
        f"the palette diverged · only in the CSS: {sorted(from_css - from_brand)} · "
        f"only in BRAND: {sorted(from_brand - from_css)}"
    )


def _brand_triples() -> set[tuple[str, str, str]]:
    """The BRAND.md hex values as decimal triples — the allowed universe for an rgb()."""
    out = set()
    for h in _palette(BRAND.read_text(encoding="utf-8")):
        out.add(tuple(str(int(h[i:i + 2], 16)) for i in (1, 3, 5)))
    return out


def test_no_fifth_colour_arrives_through_rgba() -> None:
    allowed = _brand_triples()
    assert allowed, "no hex in BRAND.md means no allowed universe — not reportable"
    outside = [t for t in RGBA.findall(CSS.read_text(encoding="utf-8")) if t not in allowed]
    assert not outside, f"rgb() that is not a BRAND token: {outside}"


def test_the_CSS_makes_no_external_request() -> None:
    found = EXTERNAL.findall(CSS.read_text(encoding="utf-8"))
    assert not found, f"external request in the stylesheet: {found}"


def test_every_page_inlines_the_SAME_stylesheet() -> None:
    # Why: the pages stay self-contained (inline), and the file exists for contributors. They are
    # two consumers of the same constant; this test is what proves they are still the same thing
    # after any edit.
    stylesheet = CSS.read_text(encoding="utf-8").strip()
    for name in GENERATED:
        p = DOCS / name
        assert p.is_file(), f"{name} does not exist"
        assert stylesheet in p.read_text(encoding="utf-8"), f"{name} inlines a CSS different from the file"


def test_the_handwritten_page_uses_the_SAME_palette() -> None:
    # Why: the MANUAL does not come from the generator, so the whole stylesheet cannot be required
    # of it. What can be required -- and it is what matters -- is that it invents no colour: its
    # palette has to fit inside BRAND's. Without this test, a fifth colour would come in through
    # the only door the rest does not cover.
    from_brand = _palette(BRAND.read_text(encoding="utf-8"))
    for name in HANDWRITTEN:
        p = DOCS / name
        assert p.is_file(), f"{name} does not exist"
        outside = _palette(p.read_text(encoding="utf-8")) - from_brand
        assert not outside, f"{name} uses a colour outside BRAND: {sorted(outside)}"


def test_CONTROLE_the_detectors_fire_when_there_is_a_match() -> None:
    # Why: without this control, the four tests above would pass with broken regexes — a pattern
    # that matches nothing returns an empty set, and empty looks like a pass.
    assert _palette("cor: #AABBCC;") == {"#AABBCC"}, "the hex detector does not see a hex value"
    assert RGBA.findall("rgba(1,2,3,.5)") == [("1", "2", "3")], "the rgb detector does not see an rgb()"
    assert EXTERNAL.findall("@import url('https://x/y.css')"), "the external detector does not see @import"
    assert not EXTERNAL.findall("background:url(../assets/x.png)"), "the detector flags a local asset"
