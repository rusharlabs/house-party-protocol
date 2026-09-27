from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
PAIR = "[English](SUPPORT.md) \u00b7 [Portugu\u00eas](SUPPORT.pt-BR.md)"
COMMON_URLS = (
    "https://github.com/rusharlabs/house-party-protocol/discussions",
    "https://github.com/rusharlabs/house-party-protocol/issues/new?template=problem.yml",
    "https://github.com/rusharlabs/house-party-protocol/security/advisories/new",
    "https://rusharlabs.com",
)
LANGUAGE_PAGES = {
    "SUPPORT.md": (
        "https://rusharlabs.github.io/house-party-protocol/MANUAL.html",
        "https://rusharlabs.github.io/house-party-protocol/CATALOG.html",
    ),
    "SUPPORT.pt-BR.md": (
        "https://rusharlabs.github.io/house-party-protocol/MANUAL.pt-BR.html",
        "https://rusharlabs.github.io/house-party-protocol/CATALOG.pt-BR.html",
    ),
}


def test_support_pages_exist_and_link_to_the_right_channels():
    for filename, language_pages in LANGUAGE_PAGES.items():
        path = ROOT / filename
        assert path.is_file(), f"{filename} is missing"
        text = path.read_text(encoding="utf-8")
        assert text.splitlines()[0] == PAIR, f"{filename} does not link to its language pair"
        for url in (*COMMON_URLS, *language_pages):
            assert url in text, f"{filename} is missing {url}"


def test_support_pages_keep_the_same_heading_structure():
    structures = []
    for filename in LANGUAGE_PAGES:
        text = (ROOT / filename).read_text(encoding="utf-8")
        structures.append(
            [
                len(match.group(1))
                for line in text.splitlines()
                if (match := re.match(r"^(#{1,3})\s", line))
            ]
        )
    assert structures[0] == structures[1], "English and Portuguese headings have diverged"
