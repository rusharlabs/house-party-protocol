"""Every release opens its discussion in Announcements, and the job that creates it asks for exactly what that needs.

`gh release create --discussion-category "Announcements"` creates the GitHub Release and a
discussion linked to it, in the category where maintainers post and anyone can comment; the
release notes become a thread instead of a page. Creating a release is a write to Contents
(GitHub lists `POST /repos/{owner}/{repo}/releases` under the Contents permission), and the linked
discussion is a write to Discussions, which the workflow token receives only through
`discussions: write`. The job asks for those two scopes and nothing else, the workflow stays
read-only by default, and every action in the file stays pinned to a commit with its version label.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / ".github" / "workflows" / "release.yml"
# The category's name as the repository has it; its slug and the other four are in
# `test_discussion_forms.CATEGORIES` (not imported: the stdlib gate reads every name imported
# under tests/ as a dependency, and the suite may add only pytest).
ANNOUNCEMENTS = "Announcements"
USES = re.compile(r"(?m)^\s*-?\s*uses:\s*(\S+)(.*)$")
PINNED = re.compile(r"^[\w./-]+@[0-9a-f]{40}$")
LABEL = re.compile(r"^\s+#\s*v\d+\.\d+\.\d+\s*$")


def _read() -> str:
    return RELEASE.read_text(encoding="utf-8")


def _job(text: str, name: str) -> str:
    """The body of one top-level job, from its header to the next job header."""
    match = re.search(rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [\w-]+:\n|\Z)", text)
    assert match, f"job {name!r} not found"
    return match.group(1)


def _permissions(job: str) -> dict[str, str]:
    """The `permissions:` block a job declares for itself, as {scope: level}."""
    block = re.search(r"(?m)^    permissions:\n((?:      [\w-]+: \w+\n)+)", job)
    assert block, "the job declares no permissions of its own"
    return dict(re.findall(r"(?m)^      ([\w-]+): (\w+)$", block.group(1)))


def test_the_release_is_created_with_its_announcement():
    job = _job(_read(), "release")
    assert "gh release create" in job
    assert f'--discussion-category "{ANNOUNCEMENTS}"' in job, "the release opens no discussion"


def test_the_release_job_asks_for_contents_and_discussions_write_and_nothing_else():
    assert _permissions(_job(_read(), "release")) == {"contents": "write", "discussions": "write"}


def test_the_workflow_stays_read_only_by_default():
    assert re.search(r"(?m)^permissions:\n  contents: read\n", _read())


def test_every_action_stays_pinned_to_a_commit_with_a_version_label():
    uses = USES.findall(_read())
    assert len(uses) >= 10, "the reader saw almost no `uses:` lines; the check would be vacuous"
    loose = [ref for ref, label in uses if not PINNED.match(ref) or not LABEL.match(label)]
    assert not loose, loose


def test_CONTROLE_the_job_reader_tells_the_jobs_apart():
    text = _read()
    assert "id-token: write" in _job(text, "attest")
    assert "id-token: write" not in _job(text, "release")
    assert _permissions(_job(text, "attest")) == {"contents": "read", "id-token": "write", "attestations": "write"}
    with pytest.raises(AssertionError):
        _job(text, "no-such-job")


def test_CONTROLE_the_pin_reader_refuses_a_tag_and_a_missing_label():
    assert USES.findall("        uses: actions/checkout@v7\n") == [("actions/checkout@v7", "")]
    assert not PINNED.match("actions/checkout@v7")
    assert PINNED.match("actions/checkout@" + "3d3c42e5aac5ba805825da76410c181273ba90b1")
    assert LABEL.match(" # v7.0.1") and not LABEL.match("") and not LABEL.match(" # latest")
