"""The docs folder has a landing page, and it is generated — not written by hand.

Why this file exists: GitHub does not render `.html` from a repository; it shows the source.
Measured before the page existed: the four catalogue and manual pages were reachable only by
someone who cloned, and the Pages root answered 404. The landing page is what makes them a site.

It is asserted here rather than only in the generator's self-test because the self-test proves
the tool can build a page, while this proves the page that SHIPPED is the one the tool builds
and that it points at files which exist next to it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
DOCS = PRODUCT_ROOT / "docs"
INDEX = DOCS / "index.html"

# Why: a site that fetches a stylesheet or a script from someone else's domain stops being
# self-contained the day that domain does. The four pages carry their CSS inline; the landing
# page has to hold the same line.
EXTERNAL = re.compile(r'(?:src|href)="https?://[^"]+\.(?:js|css)"')
HREF = re.compile(r'href="([^"]+)"')

# Why (2.6.1): `docs/hpp.css`, `docs/index.html` and `docs/CATALOG*.html` are GENERATED into the
# emitted tree by kit-forge's `tools/catalog_md.py` (run by the release step), so the SOURCE tree
# never has them and these tests failed there with FileNotFoundError -- red that proved nothing.
# The emitted tree is recognised the way the rest of this suite recognises it (`marketplace.json`
# beside the manifest). There a missing page is still a FAILURE, never a skip.
EMITTED = (PRODUCT_ROOT / "marketplace.json").is_file()


def _generated(path: Path) -> Path:
    """The generated page, or a skip that names why -- only in the source tree."""
    if not EMITTED and not path.is_file():
        pytest.skip(f"{path.relative_to(PRODUCT_ROOT).as_posix()} is generated into the emitted tree "
                    f"by kit-forge's tools/catalog_md.py; this is the source tree, where it never exists")
    return path


def _text() -> str:
    return _generated(INDEX).read_text(encoding="utf-8")


def test_the_landing_page_exists() -> None:
    assert _generated(INDEX).is_file(), "docs/index.html does not exist — the Pages root would answer 404"


def test_it_links_the_four_pages_and_all_of_them_exist() -> None:
    targets = {"CATALOG.html", "CATALOG.pt-BR.html", "MANUAL.html", "MANUAL.pt-BR.html"}
    hrefs = set(HREF.findall(_text()))
    missing = targets - hrefs
    assert not missing, f"the landing page does not link: {sorted(missing)}"
    for target in targets:
        assert _generated(DOCS / target).is_file(), f"the landing page links {target}, which does not exist"


def test_does_not_fetch_third_party_css_or_js() -> None:
    found = EXTERNAL.findall(_text())
    assert not found, f"external dependency on the landing page: {found}"


def test_declares_the_language_in_both_sections() -> None:
    # Why: both languages live on the same page; without `lang` a screen reader reads Portuguese
    # with English phonemes, and a crawler indexes the two as one.
    text = _text()
    assert 'lang="en"' in text and 'lang="pt-BR"' in text


def test_CONTROLE_the_external_detector_fires_when_there_is_a_match() -> None:
    # Why: without this control, `test_does_not_fetch_third_party_css_or_js` would pass with a
    # broken regex — a pattern that matches nothing returns an empty list, and empty looks like a
    # pass.
    assert EXTERNAL.findall('<link href="https://cdn.example/x.css">'), "the detector does not see an external CSS"
    assert not EXTERNAL.findall('<link href="style.css">'), "the detector flags a local CSS"


# Why (2026-09-23): the landing page linked the four pages and the publisher's site, and did NOT
# link the code. Anyone reaching the site through a shared link had no path to the repository --
# the material sold the harness and hid where to download it. Measured the day Pages went live:
# `href=` on the page returned five targets, none of them the repository.
REPO = re.compile(r'href="(https://github\.com/[^"]+)"')


def _sections() -> dict[str, str]:
    """{language: section html} — the page carries one section per language."""
    return {p.split('"', 1)[0]: p for p in _text().split('<section lang="')[1:]}


def test_the_landing_page_links_the_repository() -> None:
    assert REPO.findall(_text()), "the landing page does not link the project repository"


def test_the_repository_appears_in_BOTH_language_sections() -> None:
    # Why: a reader reads the section in their own language and stops. A link that exists only in
    # the other section does not exist for them.
    sections = _sections()
    assert set(sections) == {"en", "pt-BR"}, f"unexpected sections: {sorted(sections)}"
    for lang, html_ in sections.items():
        assert REPO.findall(html_), f"the {lang} section does not link the repository"


def test_the_repository_address_is_just_ONE() -> None:
    # Why: two different addresses on the same page mean one of them is wrong, and nothing on the
    # page says which.
    assert len(set(REPO.findall(_text()))) == 1, f"diverging addresses: {sorted(set(REPO.findall(_text())))}"


def test_CONTROLE_the_repository_detector_discriminates() -> None:
    # Why: without this control, the three tests above would pass with a broken regex.
    assert REPO.findall('<a href="https://github.com/org/repo">code</a>'), "the detector does not see the repo"
    assert not REPO.findall('<a href="https://example.com">publisher</a>'), "the detector flags another domain"
