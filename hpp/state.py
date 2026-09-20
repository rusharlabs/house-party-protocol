"""Append-only event store and deterministic LoopGraph projection."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class StateError(ValueError):
    """The local event log cannot truthfully produce a projection."""


def event_path(workspace: Path | None = None) -> Path:
    return (workspace or Path.cwd()).resolve() / ".hpp" / "events.jsonl"


def read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise StateError(f"corrupt event log at line {line_number}: {exc.msg}") from exc
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise StateError(f"corrupt event log at line {line_number}: event needs a type")
        if "seq" in event and event["seq"] != line_number:
            raise StateError(f"corrupt event log at line {line_number}: non-contiguous seq")
        if "id" in event and event["id"] != f"event:{line_number}":
            raise StateError(f"corrupt event log at line {line_number}: invalid event id")
        events.append(event)
    return events


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
    events = read_events(path)
    sequence = len(events) + 1
    proposed = {"seq": sequence, "id": f"event:{sequence}", "type": event_type, "data": data or {}}
    project([*events, proposed], manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(proposed, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    return project([*events, proposed], manifest)
