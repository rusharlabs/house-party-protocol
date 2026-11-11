"""The feed projects existing records without fabricating historical facts."""
from __future__ import annotations

import json

from hpp import cli


def _write(target, relative_path, value):
    path = target / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return path


def _jsonl(*records):
    return "".join(json.dumps(record) + "\n" for record in records)


def _feed(target, capsys, *args):
    assert cli.main(["map", "feed", "--target", str(target), *args]) == 0
    output = capsys.readouterr().out
    return output, json.loads(output)


def test_feed_orders_real_sources_and_does_not_echo_payloads(tmp_path, capsys):
    sentinel = "secret-command-fixture-must-not-be-published"
    board = _write(tmp_path, ".claude/lanes/board.jsonl", _jsonl(
        {"ts": "2026-10-31T12:00:00", "state": "CLAIMED", "item_id": "ITEM-1", "lane_id": "maker"},
        {"ts": "2026-10-31T12:00:00", "state": "BUILDING", "item_id": "ITEM-1", "lane_id": "maker"},
        {"ts": "2026-10-31T12:01:00", "state": "VERIFIED", "item_id": "ITEM-1", "lane_id": "checker",
         "reason": sentinel},
    ) + "{bad line\n")
    _write(tmp_path, ".claude/lanes/effects.json", json.dumps({"effects": {
        "abc123": {"reservation_id": "abc123", "item_id": "ITEM-1", "target": "maker",
                   "effect_state": "delivered", "delivered_at": "2026-10-31T15:02:00Z",
                   "payload": {"command": sentinel}},
        "not-delivered": {"effect_state": "pending"},
    }}))
    _write(tmp_path, ".claude/lanes/mailbox/_read/" + sentinel + ".md",
           "# " + sentinel + "\n\n## To: maker\n## When: 2026-10-31T12:02:00\n\n" + sentinel + "\n## To: " + sentinel)
    _write(tmp_path, ".claude/handoff/HANDOFF-LEDGER.jsonl", _jsonl(
        {"ts": "2026-10-31T12:03:00-03:00", "event": "written", "handoff_id": "HO-1", "lane_id": "maker",
         "details": {"secret": sentinel}},
    ))
    _write(tmp_path, ".claude/lanes/registry.json", json.dumps({"lanes": {
        "maker": {"started_at": "2026-10-31T11:00:00", "heartbeat_at": "2026-10-31T15:04:00",
                  "session_id": sentinel},
    }}))
    before = board.read_bytes()
    raw, report = _feed(tmp_path, capsys, "--local-offset=-03:00")
    repeated, _ = _feed(tmp_path, capsys, "--local-offset=-03:00")
    assert raw == repeated and sentinel not in raw and board.read_bytes() == before
    assert report["schema"] == "hpp.feed-map/v1"
    assert [event["kind"] for event in report["events"]] == [
        "claim", "transition", "verdict", "delivery", "message-sent", "handoff-written", "heartbeat",
        "message-archived",
    ]
    assert [event["sequence"] for event in report["events"][:2]] == [1, 2]
    assert report["events"][0]["at"] == "2026-10-31T15:00:00Z"
    assert report["events"][-1]["at"] is None
    assert report["events"][-1]["time_basis"] == "unknown"
    sources = {source["id"]: source for source in report["sources"]}
    assert sources["board"]["status"] == "partial"
    assert sources["board"]["invalid_records"] == 1
    assert len(sources["board"]["sha256"]) == 64


def test_feed_reports_missing_sources_and_never_assumes_a_board_timezone(tmp_path, capsys):
    _write(tmp_path, ".claude/lanes/board.jsonl", _jsonl(
        {"ts": "2026-10-31T12:00:00", "state": "CLAIMED", "item_id": "ITEM-1", "lane_id": "maker"},
    ))
    _, report = _feed(tmp_path, capsys)
    assert report["events"][0]["at"] == "2026-10-31T12:00:00"
    assert report["events"][0]["time_basis"] == "unanchored-local"
    assert {entry["id"] for entry in report["sources"] if entry["status"] == "missing"} == {
        "effects", "mailbox", "handoff", "registry",
    }
    assert report["limitations"]


def test_feed_accepts_project_relative_mailbox_and_refuses_outside_target(tmp_path, capsys):
    target = tmp_path / "project"
    target.mkdir()
    _write(target, "project-mail/inbox.md", "## To: maker\n## When: 2026-10-31T12:00:00Z\n")
    _, report = _feed(target, capsys, "--mailbox", "project-mail")
    assert report["events"][0]["kind"] == "message-sent"
    assert cli.main(["map", "feed", "--target", str(target), "--mailbox", ".."]) != 0
    captured = capsys.readouterr()
    assert captured.out == "" and "inside the target" in captured.err
