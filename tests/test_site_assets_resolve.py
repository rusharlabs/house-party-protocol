"""Every image the pages in `docs/` request exists RELATIVE TO `docs/`.

Why this file exists (measured 2026-09-23, against the live site): the five pages in `docs/`
opened with `<img src="../assets/hpp-logo-header.png">`. In a clone that works -- the file is
one level up. On GitHub Pages it does **not**, because the site publishes `docs/` as the ROOT,
and `../` leaves the published root:

    GET /house-party-protocol/../assets/hpp-logo-header.png  ->  503
    GET /house-party-protocol/assets/hpp-logo-header.png     ->  404
    GET /house-party-protocol/nao-existe-controle.png        ->  404   <- CONTROLE

The control is what closes the argument: the probe returns 404 for a path that truly does not
exist, so the 404s above are not an artefact of the probe. The logo was broken at the top of
every page of the site, and no test could see it, because they all run with the file on disk --
where the path works.

The fix is a path that works in BOTH contexts: `assets/...` with a copy of the asset inside
`docs/`. From disk it resolves to `docs/assets/...`; from Pages, to the site root.
"""
from __future__ import annotations

import re
from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
DOCS = PRODUCT_ROOT / "docs"

IMG = re.compile(r'<img\s[^>]*src="([^"]+)"')
OG_IMAGE = re.compile(r'<meta\s+property="og:image"\s+content="([^"]+)"')


def _pages() -> list[Path]:
    return sorted(DOCS.glob("*.html"))


def test_there_are_pages_to_measure() -> None:
    # Why: without this, the tests below would pass while scanning zero files, and a loop that
    # never iterates looks like a pass.
    assert len(_pages()) >= 5, f"expected the 5 pages of docs/, found {len(_pages())}"


def test_no_page_requests_an_image_ABOVE_docs() -> None:
    outside: list[str] = []
    for page in _pages():
        for src in IMG.findall(page.read_text(encoding="utf-8", errors="replace")):
            if src.startswith("../"):
                outside.append(f"{page.name}: {src}")
    assert not outside, (
        f"image above docs/ -- Pages publishes docs/ as the root and `../` leaves it: {outside}"
    )


def test_every_local_image_exists_relative_to_docs() -> None:
    missing: list[str] = []
    for page in _pages():
        for src in IMG.findall(page.read_text(encoding="utf-8", errors="replace")):
            if src.startswith(("http://", "https://", "data:")):
                continue
            if not (DOCS / src).is_file():
                missing.append(f"{page.name}: {src}")
    assert not missing, f"image the page requests that does not exist under docs/: {missing}"


def test_the_landing_page_declares_a_card_with_an_ABSOLUTE_image() -> None:
    # Why: a social-network crawler does not resolve a relative path. Without an absolute URL the
    # shared link goes out with no image -- and this project already carries a ready social-preview.
    text = (DOCS / "index.html").read_text(encoding="utf-8")
    found = OG_IMAGE.findall(text)
    assert found, "the landing page does not declare og:image"
    for url in found:
        assert url.startswith("https://"), f"a relative og:image is useless to a crawler: {url}"
        name = url.rsplit("/", 1)[-1]
        assert (DOCS / "assets" / name).is_file(), f"og:image points to {name}, which does not exist in docs/assets/"


def test_CONTROLE_the_detectors_discriminate() -> None:
    # Why: without this control, the tests above would pass with a broken regex.
    assert IMG.findall('<img src="assets/x.png" alt="y">') == ["assets/x.png"]
    assert IMG.findall('<img\n  src="../assets/x.png">') == ["../assets/x.png"]
    assert not IMG.findall('<image src="x.png">'), "the detector matches a tag that is not img"
    assert OG_IMAGE.findall('<meta property="og:image" content="https://a/b.png">') == ["https://a/b.png"]
    assert not OG_IMAGE.findall('<meta property="og:title" content="x">'), "the detector matches og:title"
