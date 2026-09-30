"""The support pages send every kind of request to the channel that takes it.

Originally contributed in #19 by @PandaHUN777: the English and Portuguese support pages, and the
first two tests below -- the channels each page links, and the two pages keeping the same heading
structure. The heading extraction of the second test now lives in `heading_levels`, so the CONTROLE
at the end exercises the very check the parity test runs.

Extended since: both pages route feedback (something confusing, slow, or a reason to stop using a
piece) and ideas to their issue forms; every form the repository ships is linked from both pages;
the feedback section asks for the report of `hpp doctor --report`, and this file runs the command
the pages print, offline, so a page cannot name a flag the CLI no longer has; each README links
the page of its language in the links above its title.
"""
from pathlib import Path
import re
import shlex
import socket
import urllib.request

from hpp import cli

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

READMES = {"README.md": "SUPPORT.md", "README.pt-BR.md": "SUPPORT.pt-BR.md"}
FORM = "https://github.com/rusharlabs/house-party-protocol/issues/new?template="
DISCUSSIONS = "https://github.com/rusharlabs/house-party-protocol/discussions"
# The two categories the routing depends on: questions are answered in Q&A; an idea that does not
# yet name its failure, its change and its proof starts in Ideas and comes back as an idea issue.
Q_AND_A = DISCUSSIONS + "/categories/q-a"
IDEAS = DISCUSSIONS + "/categories/ideas"
ISSUE_FORMS = ROOT / ".github" / "ISSUE_TEMPLATE"
REPORT_COMMAND = "hpp doctor --report"
# The verb that asks the reader to paste the report, in the language of each page.
PASTE = {"SUPPORT.md": r"\bpaste\b", "SUPPORT.pt-BR.md": r"\bcole\b"}
FENCED = re.compile(r"^```[^\n]*\n(.*?)^```", re.M | re.S)
LOCAL_LINK = re.compile(r"\]\((?!https?://)([^)#\s]+)(?:#([^)\s]+))?\)")


def heading_levels(text):
    """The level of every Markdown heading of one to three `#`, in the order they appear."""
    return [
        len(match.group(1))
        for line in text.splitlines()
        if (match := re.match(r"^(#{1,3})\s", line))
    ]


def _read(filename):
    return (ROOT / filename).read_text(encoding="utf-8")


def _sections(text):
    """The page cut at its `## ` headings; what comes before the first one is left out."""
    return re.split(r"(?m)^## ", text)[1:]


def _commands(text):
    """Every `hpp ...` line of the page's fenced blocks."""
    return [
        line.strip()
        for block in FENCED.findall(text)
        for line in block.splitlines()
        if line.strip().startswith("hpp ")
    ]


def _slug(heading):
    """The anchor GitHub gives a heading."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def _no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("hpp opened a network connection")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(urllib.request, "urlopen", refuse)


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
        structures.append(heading_levels(text))
    assert structures[0] == structures[1], "English and Portuguese headings have diverged"


def test_support_pages_link_the_feedback_and_the_idea_forms():
    for filename in LANGUAGE_PAGES:
        text = _read(filename)
        for template in ("feedback.yml", "idea.yml"):
            assert FORM + template in text, f"{filename} does not link the {template} form"


def test_every_issue_form_the_repository_ships_is_linked_and_every_linked_form_exists():
    # Why: a form added to `.github/ISSUE_TEMPLATE` and not named here is a channel nobody finds,
    # and a link to a form that was renamed opens the issue chooser without saying why.
    shipped = {path.name for path in ISSUE_FORMS.glob("*.yml")} - {"config.yml"}
    assert shipped >= {"problem.yml", "feedback.yml", "idea.yml"}, sorted(shipped)
    for filename in LANGUAGE_PAGES:
        linked = set(re.findall(r"issues/new\?template=([\w.-]+)", _read(filename)))
        assert linked == shipped, f"{filename} links {sorted(linked)}; the repository ships {sorted(shipped)}"


def test_the_feedback_section_asks_for_the_doctor_report():
    for filename, paste in PASTE.items():
        section = next((s for s in _sections(_read(filename)) if FORM + "feedback.yml" in s), None)
        assert section is not None, f"{filename} has no section that links the feedback form"
        assert REPORT_COMMAND in _commands(section), (
            f"{filename}: the feedback section does not give `{REPORT_COMMAND}` in a block to copy"
        )
        assert re.search(paste, section), f"{filename}: the feedback section does not ask to paste the report"


def test_the_command_the_pages_give_runs_offline(monkeypatch, capsys):
    # Why: a page that names a flag the CLI dropped sends the reader straight to an error. The
    # commands are read from the pages and run through the CLI, with every network path refused.
    commands = sorted({command for filename in LANGUAGE_PAGES for command in _commands(_read(filename))})
    assert REPORT_COMMAND in commands, commands
    _no_network(monkeypatch)
    for command in commands:
        assert cli.main(shlex.split(command)[1:]) == 0, command
    assert FORM + "feedback.yml" in capsys.readouterr().out


def test_each_readme_links_the_support_page_of_its_language_above_the_title():
    for readme, page in READMES.items():
        top = _read(readme).split("\n# ", 1)[0]
        assert f'href="{page}"' in top, f"{readme} does not link {page} in the links above its title"


def test_every_local_link_of_the_pages_resolves():
    for filename in LANGUAGE_PAGES:
        for target, anchor in LOCAL_LINK.findall(_read(filename)):
            path = ROOT / target
            assert path.is_file(), f"{filename} links {target}, which does not exist"
            if anchor:
                headings = re.findall(r"(?m)^#{1,6}\s+(.*?)\s*$", path.read_text(encoding="utf-8"))
                assert anchor in {_slug(h) for h in headings}, f"{filename} links {target}#{anchor}: no such heading"


def test_CONTROLE_the_heading_check_tells_a_diverged_pair_from_the_real_one():
    # Why: two empty lists are equal, so an extractor that matched nothing would pass the parity
    # test on any pair; a check that cannot fail cannot be told apart from one that is absent.
    english = "# Support\n\n## Questions\n\ntext\n\n## Give feedback\n\ntext\n"
    level_changed = "# Suporte\n\n## D\u00favidas\n\ntexto\n\n### Dar feedback\n\ntexto\n"
    section_dropped = "# Suporte\n\n## D\u00favidas\n\ntexto\n"
    assert heading_levels(english) == [1, 2, 2]
    assert heading_levels(level_changed) != heading_levels(english), "a changed level went unnoticed"
    assert heading_levels(section_dropped) != heading_levels(english), "a dropped section went unnoticed"
    real = [heading_levels(_read(filename)) for filename in LANGUAGE_PAGES]
    assert real[0][:1] == [1] and 2 in real[0], f"the extractor does not see the real page's headings: {real[0]}"
    assert real[0] == real[1], "the real pair diverged"


def test_the_questions_section_sends_questions_to_q_and_a_and_early_ideas_to_ideas():
    # Why (2026-09-27): the section linked the root of Discussions, a list of every category. A reader
    # with a question is not told that questions are answered in Q&A, nor that an idea without its
    # failure and proof starts in Ideas rather than in the idea form the page links further down.
    for filename in LANGUAGE_PAGES:
        section = next((s for s in _sections(_read(filename)) if DISCUSSIONS in s), None)
        assert section is not None, f"{filename} has no section that links Discussions"
        assert Q_AND_A in section, f"{filename}: the questions section does not send questions to Q&A"
        assert IDEAS in section, f"{filename}: the questions section does not send early ideas to Ideas"


def test_each_readme_links_discussions_beside_the_support_page():
    for readme, page in READMES.items():
        top = _read(readme).split("\n# ", 1)[0]
        line = next((candidate for candidate in top.splitlines() if f'href="{page}"' in candidate), None)
        assert line is not None, f"{readme} does not link {page} above its title"
        assert f'href="{DISCUSSIONS}"' in line, f"{readme}: the line that lists Support does not link Discussions"
