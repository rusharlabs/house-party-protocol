"""The README sends the reader to a page they can READ.

Why this file exists (measured 2026-09-23): both READMEs linked `docs/MANUAL.html` and
`docs/CATALOG.html` as repository paths. GitHub does not render HTML from inside a
repository -- it shows the SOURCE CODE. Anyone who clicked "manual" from the project page
got a wall of markup, not the manual. And the Portuguese README linked `MANUAL.html`, the
ENGLISH version, with `MANUAL.pt-BR.html` sitting right beside it.

The fix only became possible once Pages went live, because then the same pages came to
exist at an address that RENDERS. This test is what prevents the regression: publishing
HTML by repository path looks right, until someone clicks.
"""
from __future__ import annotations

import re
from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
SITE = "https://rusharlabs.github.io/house-party-protocol/"
READMES = ("README.md", "README.pt-BR.md")

# A markdown link to an .html INSIDE the repository. The `(?!http)` is what separates
# "repo path" from "site address" -- the second renders, the first does not.
REPO_HTML = re.compile(r"\]\((?!http)([^)]*\.html)\)")
# A rendered page that exists in English AND in Portuguese. In the pt-BR README, linking the
# form without `pt-BR` delivers the material in the wrong language.
ENGLISH_ONLY = re.compile(r"/(MANUAL|CATALOG)\.html")


def _text(name: str) -> str:
    return (PRODUCT_ROOT / name).read_text(encoding="utf-8")


def test_both_readmes_link_the_site() -> None:
    for name in READMES:
        assert SITE in _text(name), f"{name} does not link the project site ({SITE})"


def test_no_readme_links_html_by_repository_path() -> None:
    for name in READMES:
        found = REPO_HTML.findall(_text(name))
        assert not found, (
            f"{name} links HTML by repository path: {found}. "
            "GitHub shows the source code of these files; use the site address."
        )


def test_the_portuguese_readme_does_not_send_the_reader_to_the_english_page() -> None:
    found = ENGLISH_ONLY.findall(_text("README.pt-BR.md"))
    assert not found, (
        f"README.pt-BR.md points to the English version of: {found}. "
        "Both pages exist with the .pt-BR.html suffix."
    )


def test_the_address_is_spelled_the_SAME_in_both() -> None:
    # Why: a typo in one of the two produces a 404 for only half of the readers, and nobody
    # who reads in their own language notices.
    hosts = {
        m for name in READMES
        for m in re.findall(r"https://[a-z0-9.-]+\.github\.io/[a-z0-9./-]*", _text(name))
    }
    outside = {h for h in hosts if not h.startswith(SITE.rstrip("/"))}
    assert not outside, f"diverging site address: {sorted(outside)}"


def test_CONTROLE_the_detectors_fire_when_there_is_something_to_flag() -> None:
    # Why: without this control, the two tests above would pass with a broken regex --
    # a pattern that matches nothing returns an empty list, and empty looks like a pass.
    assert REPO_HTML.findall("[manual](docs/MANUAL.html)"), "the detector does not see repo HTML"
    assert not REPO_HTML.findall(f"[manual]({SITE}MANUAL.html)"), "the detector flags the site"
    assert not REPO_HTML.findall("[tips](docs/TIPS.md)"), "the detector flags a .md"
    assert ENGLISH_ONLY.findall(f"{SITE}MANUAL.html"), "the detector does not see the English page"
    assert not ENGLISH_ONLY.findall(f"{SITE}MANUAL.pt-BR.html"), "the detector flags the pt-BR page"
