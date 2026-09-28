"""The Discussions setup ships as files: a form for each category that takes one, and the links that lead there.

GitHub renders a discussion category form only from `.github/DISCUSSION_TEMPLATE/<slug>.yml` on the
default branch, and its syntax is not the issue-form one: `body` is the only required top-level key,
`labels` and `title` are the other two, and there is no `name` or `description`. A form with an
issue-form key, a duplicated `id`, a field without `label` or a body type GitHub does not know is
not rendered, and nobody is told: the category opens with an empty editor. The suite is stdlib-only,
so this file reads the shape of each form the way `scripts/repo_readiness.py` reads the workflows,
instead of parsing YAML.

The categories are the five decided on 2026-09-27: Announcements (maintainers post; a release opens
its discussion there), Q&A, Ideas, Show and tell, and Polls (GitHub renders no form for a poll).
Three take a form. The issue chooser (`.github/ISSUE_TEMPLATE/config.yml`) sends a question to Q&A
and an early idea to Ideas through the deep links that open those forms: a link to the root of
Discussions opens a list of categories instead, and a link to a category without a form opens the
empty editor the forms exist to avoid.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FORMS = ROOT / ".github" / "DISCUSSION_TEMPLATE"
CHOOSER = ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml"
LABELS = ROOT / ".github" / "labels.json"
REPOSITORY = "https://github.com/rusharlabs/house-party-protocol"

# slug -> name, as the repository has them. The slug is the form's file name and the key of every link.
CATEGORIES = {"announcements": "Announcements", "q-a": "Q&A", "ideas": "Ideas",
              "show-and-tell": "Show and tell", "polls": "Polls"}
FORM_SLUGS = {"q-a", "ideas", "show-and-tell"}
NO_FORM = {"announcements", "polls"}
TOP_LEVEL_KEYS = {"body", "labels", "title"}
BODY_TYPES = {"markdown", "textarea", "input", "dropdown", "checkboxes"}
ID = re.compile(r"^[A-Za-z0-9_-]+$")
DEEP_LINK = re.compile(re.escape(REPOSITORY) + r"/discussions/(?:new\?category=|categories/)([\w-]+)")


def read_form(text: str) -> dict:
    """The shape of a discussion category form: top-level keys, labels, and one entry per body item."""
    lines = text.splitlines()
    top = [m.group(1) for line in lines if (m := re.match(r"^([A-Za-z_][\w-]*):", line))]
    labels_match = re.search(r"(?m)^labels:\s*\[(.*)\]\s*$", text)
    labels = ([item.strip().strip("\"'") for item in labels_match.group(1).split(",") if item.strip()]
              if labels_match else [])
    items: list[dict] = []
    item = None
    in_options = False
    for line in lines:
        head = re.match(r"^  - type: (\S+)\s*$", line)
        if head:
            item = {"type": head.group(1), "id": None, "label": None, "value": False, "options": [], "required": None}
            items.append(item)
            in_options = False
            continue
        if item is None:
            continue
        if re.match(r"^ {0,6}\S", line):  # a key at the item's own depth or shallower ends an `options:` list
            in_options = re.match(r"^      options:\s*$", line) is not None
        if (m := re.match(r"^    id: (\S+)\s*$", line)):
            item["id"] = m.group(1)
        elif re.match(r"^      label: \S", line):
            item["label"] = line.split(":", 1)[1].strip()
        elif re.match(r"^      value:", line):
            item["value"] = True
        elif (m := re.match(r"^      required: (true|false)\s*$", line)):
            item["required"] = m.group(1) == "true"
        elif in_options and (m := re.match(r"^        - (?:label: )?(.+?)\s*$", line)):
            item["options"].append(m.group(1))
    return {"top": top, "labels": labels, "items": items}


def findings(form: dict, known_labels: set[str], text: str) -> list[str]:
    """Every way the form would not render, as `CODE:detail`. Empty means GitHub renders it."""
    found = [f"TOP-LEVEL-KEY:{key}" for key in form["top"] if key not in TOP_LEVEL_KEYS]
    if "body" not in form["top"]:
        found.append("NO-BODY")
    if "\r" in text:
        found.append("CRLF")
    found.extend(f"UNKNOWN-LABEL:{label}" for label in form["labels"] if label not in known_labels)
    ids = [item["id"] for item in form["items"] if item["id"] is not None]
    found.extend(f"DUPLICATE-ID:{duplicate}" for duplicate in sorted({i for i in ids if ids.count(i) > 1}))
    found.extend(f"INVALID-ID:{bad}" for bad in ids if not ID.match(bad))
    if not any(item["type"] != "markdown" for item in form["items"]):
        found.append("MARKDOWN-ONLY")
    for number, item in enumerate(form["items"], 1):
        kind = item["type"]
        where = f"{kind}#{number}"
        if kind not in BODY_TYPES:
            found.append(f"BODY-TYPE:{where}")
            continue
        if kind == "markdown":
            if not item["value"]:
                found.append(f"MARKDOWN-WITHOUT-VALUE:{where}")
            if item["required"] is not None:
                found.append(f"MARKDOWN-WITH-VALIDATION:{where}")
            continue
        if not item["label"]:
            found.append(f"NO-LABEL:{where}")
        if kind in {"dropdown", "checkboxes"}:
            if not item["options"]:
                found.append(f"NO-OPTIONS:{where}")
            elif len(set(item["options"])) != len(item["options"]):
                found.append(f"DUPLICATE-OPTION:{where}")
    return found


def _forms() -> list[Path]:
    return sorted(FORMS.glob("*.yml"))


def _known_labels() -> set[str]:
    return {entry["name"] for entry in json.loads(LABELS.read_text(encoding="utf-8"))}


def _chooser_urls() -> list[str]:
    return re.findall(r"(?m)^\s*url:\s*(\S+)", CHOOSER.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- the forms

def test_the_forms_shipped_are_exactly_the_categories_that_take_one():
    # Why: the glob is the denominator of every test below; if it came back empty they would all
    # pass on nothing. The set is fixed, so a form for a category that was not decided fails here too.
    shipped = {path.stem for path in _forms()}
    assert shipped == FORM_SLUGS, f"forms: {sorted(shipped)}; categories with a form: {sorted(FORM_SLUGS)}"
    assert not list(FORMS.glob("*.yaml")), "GitHub reads `<slug>.yml`; a `.yaml` is not rendered"


def test_no_form_is_shipped_for_announcements_or_polls():
    for slug in NO_FORM:
        assert not (FORMS / f"{slug}.yml").exists(), f"{slug}: maintainers post announcements; a poll takes no form"


@pytest.mark.parametrize("path", _forms(), ids=lambda p: p.name)
def test_the_form_has_the_shape_github_renders(path: Path):
    text = path.read_text(encoding="utf-8")
    assert path.stem in CATEGORIES, f"{path.name} is not the slug of a category"
    assert findings(read_form(text), _known_labels(), text) == []


def test_the_ideas_form_carries_the_idea_label_and_the_others_carry_none():
    # Why: an issue created from a discussion keeps the discussion's labels, so `idea` on the form
    # is what ties an idea that grew up in Discussions to the idea issues. Questions and show-and-tell
    # posts are not tracked work, and a label there would only dilute the search `label:idea`.
    for path in _forms():
        labels = read_form(path.read_text(encoding="utf-8"))["labels"]
        expected = ["idea"] if path.stem == "ideas" else []
        assert labels == expected, (path.name, labels)


# --------------------------------------------------------------------------- the routes into them

def test_the_issue_chooser_opens_the_q_and_a_and_the_ideas_forms():
    urls = _chooser_urls()
    assert f"{REPOSITORY}/discussions/new?category=q-a" in urls, urls
    assert f"{REPOSITORY}/discussions/new?category=ideas" in urls, urls


def test_the_issue_chooser_links_no_discussion_root_and_no_category_without_a_form():
    for url in _chooser_urls():
        if "/discussions" not in url:
            continue
        match = DEEP_LINK.match(url)
        assert match, f"{url}: the root of Discussions lists categories; it opens no form"
        assert match.group(1) in FORM_SLUGS, f"{url}: a category without a form opens an empty editor"


def test_every_discussion_link_in_the_product_names_a_category_that_exists():
    # Why: the slug is the key. A link to `q-and-a` or `show-tell` is a 404 that only the reader who
    # clicks it sees, and the two links the routing depends on have to be somewhere in the product.
    files = [*ROOT.glob("*.md"), *(p for p in (ROOT / ".github").rglob("*") if p.is_file())]
    seen: dict[str, list[str]] = {}
    for path in files:
        for slug in DEEP_LINK.findall(path.read_text(encoding="utf-8")):
            seen.setdefault(slug, []).append(path.relative_to(ROOT).as_posix())
    unknown = {slug: where for slug, where in seen.items() if slug not in CATEGORIES}
    assert not unknown, unknown
    assert {"q-a", "ideas"} <= set(seen), f"the deep links the routing depends on are missing: {sorted(seen)}"


# --------------------------------------------------------------------------- CONTROLE: the reader discriminates

BROKEN = """name: Broken
description: an issue-form header on a discussion form
labels: ["no-such-label"]
body:
  - type: markdown
    attributes:
      value: |
        text
    validations:
      required: true
  - type: text
    id: first
    attributes:
      label: Unknown type
  - type: textarea
    id: first
    attributes:
      description: no label here
  - type: dropdown
    id: pick.one
    attributes:
      label: Host
      options:
        - A
        - A
  - type: checkboxes
    id: checks
    attributes:
      label: Before posting
"""


def test_CONTROLE_a_planted_broken_form_is_refused_on_every_count():
    text = BROKEN.replace("\n", "\r\n")
    codes = {finding.split(":")[0] for finding in findings(read_form(text), {"idea"}, text)}
    assert codes == {"TOP-LEVEL-KEY", "UNKNOWN-LABEL", "CRLF", "MARKDOWN-WITH-VALIDATION", "BODY-TYPE",
                     "DUPLICATE-ID", "INVALID-ID", "NO-LABEL", "DUPLICATE-OPTION", "NO-OPTIONS"}, sorted(codes)
    no_body = "labels: []\n"
    assert set(findings(read_form(no_body), set(), no_body)) == {"NO-BODY", "MARKDOWN-ONLY"}


def test_CONTROLE_the_reader_sees_every_field_of_the_real_forms():
    # Why: a reader that returned no items would leave `findings` with nothing to refuse; the shape
    # test would then pass on any file. Each real form opens with a paragraph and has fields with ids.
    for path in _forms():
        form = read_form(path.read_text(encoding="utf-8"))
        fields = [item for item in form["items"] if item["type"] != "markdown"]
        assert len(fields) >= 3, path.name
        assert all(item["id"] and item["label"] for item in fields), path.name
        assert form["items"][0]["type"] == "markdown" and form["items"][0]["value"], f"{path.name}: opening paragraph"
        assert any(item["options"] for item in fields), f"{path.name}: no dropdown or checkbox options were read"


def test_CONTROLE_the_deep_link_reader_tells_a_category_link_from_the_root():
    assert DEEP_LINK.findall(f"{REPOSITORY}/discussions/new?category=q-a") == ["q-a"]
    assert DEEP_LINK.findall(f"{REPOSITORY}/discussions/categories/show-and-tell") == ["show-and-tell"]
    assert DEEP_LINK.findall(f"{REPOSITORY}/discussions") == []
    assert DEEP_LINK.match(f"{REPOSITORY}/discussions/12") is None
