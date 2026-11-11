"""The atlas renders reproducible, escaped projections without persisting state."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

from hpp.atlas import render_atlas
from hpp.attest import create_attestation
from hpp.cli import main
from hpp.maps import build_feed_map, build_lane_map


FIXTURE = Path(__file__).resolve().parents[1] / "hpp" / "examples" / "reliable-coding"


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()


def test_default_atlas_is_standalone_and_declares_missing_inputs(tmp_path):
    page = render_atlas(tmp_path)
    assert page == render_atlas(tmp_path)
    assert page.startswith("<!doctype html>")
    assert "<svg " in page
    assert page.count("<section id=") == 11
    assert page.count("Projection SHA-256:") == 5
    assert "Unavailable: supply --spec" in page
    assert "Unavailable: supply --attestation" in page
    assert "Source coverage" in page
    assert list(tmp_path.iterdir()) == []


def test_atlas_uses_the_existing_projections_and_prints_hashes(tmp_path, monkeypatch, capsys):
    for name in ("workgraph.json", "lanes.json", "monitors.json", "context.json"):
        shutil.copyfile(FIXTURE / name, tmp_path / name)
    (tmp_path / "events.json").write_text('[{"type":"checkpoint"}]', encoding="utf-8")
    (tmp_path / "deliberation.json").write_text('{"schema":"hpp.deliberation/v2"}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    args = [
        "atlas", "--html", "--spec", "workgraph.json", "--lanes", "lanes.json",
        "--monitors", "monitors.json", "--now", "1700000100", "--context", "context.json",
        "--budget", "200", "--agent-events", "events.json", "--deliberation", "deliberation.json",
    ]
    assert main(args) == 0
    page = capsys.readouterr().out
    assert main(args) == 0
    assert capsys.readouterr().out == page
    for command in (
        ["work", "plan", "workgraph.json"], ["map", "lane", "lanes.json", "--now", "1700000100"],
        ["map", "monitor", "monitors.json", "--now", "1700000100"], ["map", "context", "context.json", "--budget", "200"],
        ["map", "feed", "--target", "."], ["map", "agent", "--events", "events.json"],
    ):
        assert main(command) == 0
        assert digest(json.loads(capsys.readouterr().out)) in page
    assert "hpp work plan ./workgraph.json" in page
    assert "hpp map lane ./lanes.json --now 1700000100" in page
    assert "hpp deliberate verify ./deliberation.json" in page and "broken" in page
    assert hashlib.sha256((tmp_path / "lanes.json").read_bytes()).hexdigest() in page


def test_feed_keeps_recorded_activity_and_source_provenance(tmp_path):
    board = tmp_path / ".claude" / "lanes" / "board.jsonl"
    board.parent.mkdir(parents=True)
    board.write_text(
        '{"state":"CLAIMED","lane_id":"maker","item_id":"item-1","ts":"2026-10-01T12:00:00"}\n',
        encoding="utf-8",
    )
    projection = build_feed_map(tmp_path, local_offset="-03:00")
    page = render_atlas(tmp_path, local_offset="-03:00")
    assert projection["events"], "control: the feed source is valid"
    assert "2026-10-01T15:00:00Z" in page
    assert "hpp map feed --target . --local-offset=-03:00" in page
    assert digest(projection) in page
    assert hashlib.sha256(board.read_bytes()).hexdigest() in page
    assert "reading and its time are not recorded" in page


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def test_record_text_is_inert_in_tables_and_svg(tmp_path):
    lane = '<img src=x onerror="alert(1)">'
    records = [{"id": lane, "territory": ["team/<script>.py"]}]
    (tmp_path / "lanes.json").write_text(json.dumps(records), encoding="utf-8")
    page = render_atlas(tmp_path, lanes_file="lanes.json")
    html = Tags()
    html.feed(page)
    assert digest(build_lane_map(records)) in page
    assert '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;' in page
    assert "team/&lt;script&gt;.py" in page
    assert all(tag not in {"script", "img", "iframe", "form", "object", "link"} for tag, _ in html.tags)
    assert all(
        not attr.startswith("on") and (attr not in {"href", "src"} or value.startswith("#"))
        for _, attrs in html.tags for attr, value in attrs.items()
    )
    assert "default-src 'none'" in page


def test_invalid_explicit_sources_fail_without_partial_html(tmp_path, capsys):
    source = tmp_path / "target"
    source.mkdir()
    (tmp_path / "outside.json").write_text("[]", encoding="utf-8")
    (source / "context.json").write_text("{}", encoding="utf-8")
    for flags, message in (
        (["--lanes", "../outside.json"], "inside --target"),
        (["--context", "context.json"], "requires --budget"),
        (["--context", "context.json", "--budget", "10"], "must contain a JSON list"),
        (["--monitors", "missing.json"], "requires --now"),
        (["--lanes", "missing.json"], "not a regular file"),
    ):
        assert main(["atlas", "--html", "--target", str(source), *flags]) == 2
        output = capsys.readouterr()
        assert output.out == "" and message in output.err


def test_attestation_projects_the_local_verifier_and_rejects_outside_spec(tmp_path):
    repo = tmp_path / "target"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    spec = repo / "spec.md"
    spec.write_text("Test the release spec.\n", encoding="utf-8")
    message = tmp_path / "commit.txt"
    message.write_text("test: bind release spec\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "spec.md"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
         "-c", "commit.gpgSign=false", "commit", "-q", "-F", str(message)], check=True,
    )
    artifact = repo / "attestation.json"
    record = create_attestation(
        repo=repo, spec=spec, output=artifact, maker="a", checker="b", session="example", verdict="approved",
    )
    page = render_atlas(repo, attestation="attestation.json")
    assert "hpp attest verify ./attestation.json --repo ." in page
    assert "<td>status</td><td>valid</td>" in page
    assert "not-signed" in page
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() in page
    record["spec"]["path"] = "../commit.txt"
    artifact.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="inside --target"):
        render_atlas(repo, attestation="attestation.json")
