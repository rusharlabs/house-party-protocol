"""Every architecture, concept and contract document has a page the site can serve.

Why this file exists (measured 2026-09-27): the site publishes `docs/` as its root, and the only
pages it could serve were `index.html`, the catalogue pair and the manual pair. The eleven
documents under `docs/` and the four contract documents at the root (`MANIFESTO`,
`INSTALL-CONTRACT`, `SKILL-CONTRACT`, `INSTALL_FOR_AGENTS`) existed only as Markdown -- and a
Markdown file served by the site arrives as plain text, while the same file opened from the
repository is a different address. A reader who arrived through the site had no way to read the
architecture in the site's own design.

The rule enforced here: every such document has an `.html` pair in `docs/` (English and
Portuguese), the two pages link to each other, the landing page links both, and each page keeps
the Markdown's headings -- so a heading edited in the Markdown and not re-rendered shows up here
instead of silently diverging.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

import pytest

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
DOCS = PRODUCT_ROOT / "docs"
INDEX = DOCS / "index.html"
BRAND = DOCS / "BRAND.md"

# Why: the four contract documents, the roadmap, the governance page and the support page live at
# the ROOT of the product, where the site does not reach (Pages serves `docs/` as the root and `../`
# leaves it). Their pages therefore live in `docs/`.
ROOT_DOCS = ("MANIFESTO", "INSTALL-CONTRACT", "SKILL-CONTRACT", "INSTALL_FOR_AGENTS", "ROADMAP", "GOVERNANCE",
             "SUPPORT")
# Why: the catalogue Markdown is itself generated next to its own HTML pair; it is not a document
# to render, and it only exists in the emitted tree.
GENERATED_MD = {"CATALOG"}
LANG_SUFFIX = {"en": "", "pt-BR": ".pt-BR"}

# Same recognition as the rest of the suite: the emitted tree carries `marketplace.json`.
EMITTED = (PRODUCT_ROOT / "marketplace.json").is_file()

HREF = re.compile(r'href="([^"]+)"')
HEX = re.compile(r"#[0-9a-fA-F]{6}\b")
_TAG = re.compile(r"<[^>]+>")
_FENCE = "```"


def doc_names() -> list[str]:
    """The base names that must have a page: every `docs/X.md` pair, plus the root documents."""
    names = {
        p.name[: -len(".md")] for p in DOCS.glob("*.md")
        if not p.name.endswith(".pt-BR.md") and p.name[: -len(".md")] not in GENERATED_MD
    }
    return sorted(names | set(ROOT_DOCS))


def page(name: str, lang: str) -> Path:
    return DOCS / f"{name}{LANG_SUFFIX[lang]}.html"


def source(name: str, lang: str) -> Path:
    folder = PRODUCT_ROOT if name in ROOT_DOCS else DOCS
    return folder / f"{name}{LANG_SUFFIX[lang]}.md"


def _plain(text: str) -> str:
    """Heading text as a reader sees it: no Markdown punctuation, no tags, entities resolved."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.replace("`", "").replace("**", "").replace("*", "")
    text = html.unescape(_TAG.sub("", text))
    return " ".join(text.split())


def md_headings(markdown: str, levels: tuple[int, ...] = (1, 2)) -> list[tuple[int, str]]:
    """(level, text) of the ATX headings outside fenced blocks."""
    out: list[tuple[int, str]] = []
    inside = False
    for line in markdown.splitlines():
        if line.lstrip().startswith(_FENCE):
            inside = not inside
            continue
        if inside:
            continue
        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if m and len(m.group(1)) in levels:
            out.append((len(m.group(1)), _plain(m.group(2))))
    return out


def html_headings(page_html: str, levels: tuple[int, ...] = (1, 2)) -> list[tuple[int, str]]:
    return [(int(m.group(1)), _plain(m.group(2)))
            for m in re.finditer(r"<h([1-6])\b[^>]*>(.*?)</h\1>", page_html, flags=re.S)
            if int(m.group(1)) in levels]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_there_are_documents_to_measure() -> None:
    # Why: without this, the tests below would pass while iterating zero names.
    assert len(doc_names()) >= 15, f"expected at least 15 documents, found {doc_names()}"


@pytest.mark.parametrize("lang", ["en", "pt-BR"])
def test_every_document_has_an_html_page(lang: str) -> None:
    missing = [page(n, lang).name for n in doc_names() if not page(n, lang).is_file()]
    assert not missing, f"documents without a {lang} page in docs/: {missing}"


@pytest.mark.parametrize("name", doc_names())
def test_the_two_pages_of_a_pair_link_each_other(name: str) -> None:
    en, pt = page(name, "en"), page(name, "pt-BR")
    assert en.is_file() and pt.is_file(), f"{name}: the pair is incomplete"
    for here, lang, other in ((en, "en", pt), (pt, "pt-BR", en)):
        text = _text(here)
        assert text.startswith(f'<!doctype html>\n<html lang="{lang}">'), f"{here.name}: wrong document language"
        assert f'href="{other.name}"' in text, f"{here.name} does not link its pair {other.name}"
        assert f'hreflang="{"pt-BR" if lang == "en" else "en"}"' in text, f"{here.name} lacks hreflang"


@pytest.mark.parametrize("name", doc_names())
def test_every_page_keeps_the_headings_of_its_markdown(name: str) -> None:
    for lang in LANG_SUFFIX:
        md, out = source(name, lang), page(name, lang)
        if not md.is_file():
            # Why: INSTALL-CONTRACT and SKILL-CONTRACT reach the product root only at emission;
            # in the source tree their Markdown lives beside the kits. The page is still required
            # (test above); the comparison runs where the Markdown is.
            if EMITTED:
                pytest.fail(f"{md.name} is missing from the emitted tree")
            continue
        assert out.is_file(), f"{out.name} does not exist"
        expected, found = md_headings(_text(md)), html_headings(_text(out))
        assert found == expected, (
            f"{out.name} does not carry the headings of {md.name} -- re-render it.\n"
            f"only in the Markdown: {[h for h in expected if h not in found]}\n"
            f"only in the page: {[h for h in found if h not in expected]}"
        )


@pytest.mark.parametrize("name", doc_names())
def test_no_page_sends_the_reader_to_markdown_that_has_a_page(name: str) -> None:
    # Why: a link to `X.md` from a page opens the raw Markdown on the site. Where `X.html`
    # exists, the rendered page is the destination.
    names = set(doc_names())
    for lang in LANG_SUFFIX:
        out = page(name, lang)
        if not out.is_file():
            continue
        stale = [h for h in HREF.findall(_text(out))
                 if not h.startswith(("http://", "https://", "#"))
                 and re.sub(r"\.pt-BR$", "", h.split("#", 1)[0].removesuffix(".md")) in names
                 and h.split("#", 1)[0].endswith(".md")]
        assert not stale, f"{out.name} links Markdown that has a page: {stale}"


@pytest.mark.parametrize("name", doc_names())
def test_every_page_uses_only_the_brand_palette_and_the_manual_lockup(name: str) -> None:
    brand = {h.upper() for h in HEX.findall(_text(BRAND))}
    lockup = re.search(r'<img\s[^>]*src="(assets/[^"]+)"[^>]*>', _text(DOCS / "MANUAL.html"))
    assert lockup, "MANUAL.html no longer opens with the lockup"
    for lang in LANG_SUFFIX:
        out = page(name, lang)
        if not out.is_file():
            continue
        text = _text(out)
        outside = {h.upper() for h in HEX.findall(text)} - brand
        assert not outside, f"{out.name} uses a colour outside BRAND: {sorted(outside)}"
        # Why the asset and not the whole tag: the MANUAL's alt carries the publication credit,
        # which the publication gate accepts only where that exception is declared file by file.
        # The document pages show the same artwork, named by what it shows.
        imgs = re.findall(r'<img\s[^>]*src="([^"]+)"', text)
        assert imgs[:1] == [lockup.group(1)], f"{out.name} does not open with the MANUAL's lockup: {imgs[:1]}"
        assert text.index("<img") < text.index("<h1"), f"{out.name}: the lockup is not above the title"
        # Why: DESIGN's own prose mentions `@import` as a thing to avoid, so the check reads the
        # <style> block and the tags, never the text a page quotes.
        styles = " ".join(re.findall(r"<style>(.*?)</style>", text, flags=re.S))
        assert not re.search(r"<script\b", text), f"{out.name} runs a script"
        assert "@import" not in styles and "@font-face" not in styles, f"{out.name} fetches a stylesheet or font"


def _index() -> str:
    if not EMITTED and not INDEX.is_file():
        pytest.skip("docs/index.html is generated into the emitted tree by kit-forge's "
                    "tools/catalog_md.py; this is the source tree, where it never exists")
    return _text(INDEX)


def _sections(text: str) -> dict[str, str]:
    return {p.split('"', 1)[0]: p for p in text.split('<section lang="')[1:]}


def test_the_landing_page_links_every_page_in_its_own_language() -> None:
    sections = _sections(_index())
    assert set(sections) == {"en", "pt-BR"}, f"unexpected sections: {sorted(sections)}"
    for lang, body in sections.items():
        linked = set(HREF.findall(body))
        missing = [page(n, lang).name for n in doc_names() if page(n, lang).name not in linked]
        assert not missing, f"the {lang} section of index.html does not link: {missing}"


def test_CONTROLE_the_checks_discriminate_on_a_known_good_and_a_known_bad_page() -> None:
    # Why: without this control, the heading comparison would pass with extractors that match
    # nothing -- two empty lists are equal -- and the link check would pass with a detector that
    # never fires.
    md = "[English](X.md) · [Português](X.pt-BR.md)\n\n# Title `code`\n\n```text\n## not a heading\n```\n\n## One\n\n### deep\n"
    good = '<h1>Title <code>code</code></h1><section><h2 id="one">One</h2><h3>deep</h3></section>'
    bad = "<h1>Title code</h1><h2>Renamed</h2>"
    assert md_headings(md) == [(1, "Title code"), (2, "One")], md_headings(md)
    assert html_headings(good) == md_headings(md), "a faithful page must match its Markdown"
    assert html_headings(bad) != md_headings(md), "a page with a renamed heading must not match"
    assert html_headings("<p>no heading</p>") == [], "the extractor invents headings"
    # the known-good page in the product: the hand-written manual opens the way every page must
    manual = _text(DOCS / "MANUAL.html")
    assert manual.startswith('<!doctype html>\n<html lang="en">') and 'href="MANUAL.pt-BR.html"' in manual
    assert html_headings(manual, (1,)), "the extractor does not see the manual's <h1>"
