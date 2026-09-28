"""Append-only, hash-chained event store and deterministic LoopGraph projection.

Every appended event carries `prev_sha256`, the sha256 of the line before it as written (without
its line terminator); the first event links to the hash of nothing. A rewritten line breaks the
link of the next one, and the reader names the first step whose link no longer matches instead of
projecting an edited history. Lines written before the chain existed carry no link: they read as
before and `verify_chain` declares them `legacy`. An edit of the last line is outside what the chain
alone can see, and the report says so by publishing its `head_sha256`: the tail is anchored only by
a copy of that head kept outside the line -- the next append (its `prev_sha256`) or one the operator
keeps elsewhere. An attestation does not record it, and binds the log only when `.hpp/events.jsonl`
sits inside its git snapshot (a checkout that ignores `.hpp/` leaves the log out).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Optional

CHAIN_SCHEMA = "hpp.event-chain/v1"
GENESIS_SHA256 = hashlib.sha256(b"").hexdigest()
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class StateError(ValueError):
    """The local event log cannot truthfully produce a projection."""


def event_path(workspace: Path | None = None) -> Path:
    return (workspace or Path.cwd()).resolve() / ".hpp" / "events.jsonl"


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _numbered_lines(path: Path) -> list[tuple[int, bytes]]:
    """Non-blank lines with their 1-based line number; a trailing `\\r` is not part of the line."""
    raw = path.read_bytes()
    lines: list[tuple[int, bytes]] = []
    for number, line in enumerate(raw.split(b"\n"), 1):
        line = line.rstrip(b"\r")
        if line.strip():
            lines.append((number, line))
    return lines


def _parse(line: bytes, line_number: int) -> dict[str, Any]:
    try:
        event = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        detail = getattr(exc, "msg", str(exc))
        raise StateError(f"corrupt event log at line {line_number}: {detail}") from exc
    if not isinstance(event, dict) or not isinstance(event.get("type"), str):
        raise StateError(f"corrupt event log at line {line_number}: event needs a type")
    if "seq" in event and event["seq"] != line_number:
        raise StateError(f"corrupt event log at line {line_number}: non-contiguous seq")
    if "id" in event and event["id"] != f"event:{line_number}":
        raise StateError(f"corrupt event log at line {line_number}: invalid event id")
    return event


def _check_link(event: dict[str, Any], line_number: int, previous_hash: str) -> None:
    link = event["prev_sha256"]
    if not isinstance(link, str) or not _DIGEST.fullmatch(link):
        raise StateError(f"corrupt event log at line {line_number}: prev_sha256 is not a sha256 digest")
    if link != previous_hash:
        anchor = f"line {line_number - 1} as written" if line_number > 1 else "the genesis hash"
        raise StateError(f"corrupt event log at line {line_number}: hash chain broken at event:{line_number} "
                         f"(prev_sha256 does not match {anchor})")


def _read_log(path: Path) -> tuple[list[dict[str, Any]], str]:
    """Every event of the log, and the hash the next appended event must link to."""
    if not path.exists():
        return [], GENESIS_SHA256
    events: list[dict[str, Any]] = []
    previous_hash = GENESIS_SHA256
    for line_number, line in _numbered_lines(path):
        event = _parse(line, line_number)
        if "prev_sha256" in event:
            _check_link(event, line_number, previous_hash)
        previous_hash = _sha256(line)
        events.append(event)
    return events, previous_hash


def read_events(path: Path) -> list[dict[str, Any]]:
    return _read_log(path)[0]


def verify_chain(path: Path) -> dict[str, Any]:
    """The state of the chain without raising: `intact`, `legacy` (lines without a link), `broken`
    (with the first divergent step named) or `empty`; plus the head hash that anchors the tail."""
    report: dict[str, Any] = {"schema": CHAIN_SCHEMA, "log": str(path), "status": "empty", "events": 0,
                              "chained": 0, "legacy": 0, "first_divergent": None, "head_sha256": None}
    if not path.exists():
        return report
    previous_hash = GENESIS_SHA256
    head: Optional[str] = None
    events = chained = legacy = 0
    first_divergent: Optional[str] = None
    for line_number, line in _numbered_lines(path):
        try:
            event = _parse(line, line_number)
        except StateError:
            first_divergent = f"line {line_number}"
            break
        events += 1
        if "prev_sha256" in event:
            try:
                _check_link(event, line_number, previous_hash)
            except StateError:
                first_divergent = f"event:{line_number}"
                break
            chained += 1
        else:
            legacy += 1
        previous_hash = head = _sha256(line)
    report.update(events=events, chained=chained, legacy=legacy, first_divergent=first_divergent, head_sha256=head)
    if first_divergent is not None:
        report["status"] = "broken"
    elif events == 0:
        report["status"] = "empty"
    elif legacy == 0:
        report["status"] = "intact"
    else:
        report["status"] = "legacy"
    return report


def project(events: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Any]:
    transitions = {(item["from"], item["event"]): item for item in manifest["loop"]["transitions"]}
    state = manifest["loop"]["initial"]
    evidence_count = 0
    history: list[str] = []
    for index, event in enumerate(events, 1):
        event_type = event["type"]
        transition = transitions.get((state, event_type))
        if transition is None:
            raise StateError(f"invalid transition at event {index}: {state} --{event_type}--> ?")
        if event_type == "evidence_recorded":
            evidence_count += 1
        if event_type == "verified" and evidence_count < 1:
            raise StateError("verified requires at least one recorded evidence item")
        history.append(event_type)
        state = transition["to"]
    next_steps = {
        "planned": "start work",
        "active": "record fresh evidence",
        "evidenced": "run read-only checker",
        "checked": "request human gate",
        "approved": "verify closure",
        "verified": "no-op",
    }
    return {"state": state, "event_count": len(events), "evidence_count": evidence_count,
            "history": history, "next_step": next_steps[state]}


def append_event(path: Path, event_type: str, manifest: dict[str, Any], data: dict[str, Any] | None = None) -> dict[str, Any]:
    events, previous_hash = _read_log(path)
    sequence = len(events) + 1
    proposed = {"seq": sequence, "id": f"event:{sequence}", "type": event_type, "data": data or {},
                "prev_sha256": previous_hash}
    project([*events, proposed], manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(proposed, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    return project([*events, proposed], manifest)
