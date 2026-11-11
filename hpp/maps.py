"""Deterministic, data-only projections for lanes and operational topology."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from hpp.context import compile_context


class MapError(ValueError):
    """A map source cannot support an honest projection."""


def _node(node_id: str, kind: str, label: str) -> dict[str, str]:
    return {"id": node_id, "kind": kind, "label": label}


def _edge(source: str, target: str, relation: str) -> dict[str, str]:
    return {"from": source, "to": target, "relation": relation}


def _sorted_graph(view: str, nodes: list[dict[str, str]], edges: list[dict[str, str]], **extra: Any) -> dict[str, Any]:
    unique_nodes = {node["id"]: node for node in nodes}
    return {
        "schema": "hpp.map/v1",
        "view": view,
        "nodes": [unique_nodes[node_id] for node_id in sorted(unique_nodes)],
        "edges": sorted(edges, key=lambda edge: (edge["from"], edge["to"], edge["relation"])),
        **extra,
    }


def _normalise_path(value: str) -> str:
    return value.replace("\\", "/").strip("/")


def _paths_overlap(left: str, right: str) -> bool:
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def _liveness(lane: dict[str, Any], now: int | None, suspect_after: int, dead_after: int) -> str:
    declared = lane.get("status", "declared")
    if declared in {"closed", "dead", "inactive"}:
        return "dead"
    if now is None:
        return declared
    heartbeat = lane.get("heartbeat_at")
    if heartbeat is None:
        return "unknown"
    if not isinstance(heartbeat, int) or heartbeat < 0 or heartbeat > now:
        raise MapError(f"lane {lane['id']} has invalid heartbeat_at")
    age = now - heartbeat
    if age <= suspect_after:
        return "alive"
    if age <= dead_after:
        return "suspect"
    return "dead"


def build_lane_map(
    lanes: list[dict[str, Any]],
    now: int | None = None,
    suspect_after: int = 300,
    dead_after: int = 900,
    *,
    codegraph: dict[str, Any] | None = None,
    target: str | Path | None = None,
) -> dict[str, Any]:
    """Project lane ownership, liveness and exclusive path collisions."""
    if not isinstance(lanes, list):
        raise MapError("lanes must be a list")
    if now is not None and (not isinstance(now, int) or now < 0):
        raise MapError("now must be a non-negative integer")
    if not 0 < suspect_after < dead_after:
        raise MapError("lane thresholds must satisfy 0 < suspect_after < dead_after")
    nodes: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []
    seen: set[str] = set()
    projected: list[dict[str, Any]] = []
    liveness: dict[str, str] = {}
    for lane in lanes:
        if not isinstance(lane, dict) or not isinstance(lane.get("id"), str) or not lane["id"]:
            raise MapError("every lane needs an id")
        lane_id = lane["id"]
        if lane_id in seen:
            raise MapError(f"duplicate lane: {lane_id}")
        seen.add(lane_id)
        territory = lane.get("territory")
        if not isinstance(territory, list) or not territory or not all(isinstance(value, str) and value for value in territory):
            raise MapError(f"lane {lane_id} needs non-empty territory")
        paths = sorted({_normalise_path(value) for value in territory})
        if any(not value for value in paths):
            raise MapError(f"lane {lane_id} has invalid territory")
        state = _liveness(lane, now, suspect_after, dead_after)
        liveness[lane_id] = state
        projected.append({"id": lane_id, "paths": paths, "exclusive": lane.get("exclusive", True), "liveness": state})
        lane_node = f"lane:{lane_id}"
        nodes.append(_node(lane_node, "lane", lane_id))
        for path in paths:
            territory_node = f"territory:{path}"
            nodes.append(_node(territory_node, "territory", path))
            edges.append(_edge(lane_node, territory_node, f"owns:{state}"))
    collisions: list[dict[str, Any]] = []
    for left_index, left in enumerate(projected):
        for right in projected[left_index + 1:]:
            if not left["exclusive"] or not right["exclusive"]:
                continue
            if left["liveness"] == "dead" or right["liveness"] == "dead":
                continue
            overlaps = sorted({
                path
                for left_path in left["paths"]
                for right_path in right["paths"]
                if _paths_overlap(left_path, right_path)
                for path in (left_path, right_path)
            })
            if overlaps:
                collisions.append({"lanes": sorted([left["id"], right["id"]]), "territory": overlaps})
    collisions.sort(key=lambda item: (item["lanes"], item["territory"]))
    result = _sorted_graph("lane", nodes, edges, collisions=collisions,
                           liveness={key: liveness[key] for key in sorted(liveness)})
    if codegraph is not None:
        from hpp.territories import territory_coupling
        result["territory_coupling"] = territory_coupling(
            target, [{"id": lane["id"], "territory": lane["paths"]} for lane in projected
                     if lane["exclusive"] and lane["liveness"] != "dead"], codegraph)
    return result


def build_agent_map(manifest: dict[str, Any], events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Project roles, modules, capabilities and recorded execution events."""
    if not isinstance(manifest, dict):
        raise MapError("manifest must be an object")
    roles = manifest.get("roles", [])
    modules = manifest.get("modules", [])
    if not isinstance(roles, list) or not all(isinstance(role, str) and role for role in roles):
        raise MapError("manifest roles must be strings")
    if not isinstance(modules, list):
        raise MapError("manifest modules must be a list")
    nodes: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []
    for role in sorted(set(roles)):
        nodes.append(_node(f"role:{role}", "role", role))
    for module in sorted(modules, key=lambda item: item.get("id", "") if isinstance(item, dict) else ""):
        if not isinstance(module, dict) or not isinstance(module.get("id"), str) or not module["id"]:
            raise MapError("every module needs an id")
        module_id = module["id"]
        module_node = f"module:{module_id}"
        nodes.append(_node(module_node, "module", module_id))
        for capability in sorted(set(module.get("capabilities", []))):
            if not isinstance(capability, str) or not capability:
                raise MapError(f"module {module_id} has invalid capability")
            capability_node = f"capability:{capability}"
            nodes.append(_node(capability_node, "capability", capability))
            edges.append(_edge(module_node, capability_node, "provides"))
    for index, event in enumerate(events or [], 1):
        if not isinstance(event, dict) or not isinstance(event.get("type"), str) or not event["type"]:
            raise MapError(f"event {index} needs a type")
        event_node = f"event:{index}:{event['type']}"
        nodes.append(_node(event_node, "execution", event["type"]))
        if index > 1:
            previous = events[index - 2]
            edges.append(_edge(f"event:{index - 1}:{previous['type']}", event_node, "then"))
    return _sorted_graph("agent", nodes, edges)


def build_context_map(inputs: list[dict[str, Any]], budget: int) -> dict[str, Any]:
    """Project bounded context provenance; this is not a general knowledge database."""
    compiled = compile_context(inputs, budget)
    nodes = [_node("context:compiled", "context", "compiled context")]
    edges: list[dict[str, str]] = []
    provenance: list[dict[str, Any]] = []
    for status in ("included", "omitted"):
        for record in compiled[status]:
            source_id = f"source:{record['source']}"
            nodes.append(_node(source_id, "source", record["source"]))
            edges.append(_edge(source_id, "context:compiled", status))
            provenance.append({**record, "status": status})
    return _sorted_graph(
        "context",
        nodes,
        edges,
        budget=compiled["budget"],
        used=compiled["used"],
        remaining=compiled["remaining"],
        provenance=sorted(provenance, key=lambda item: item["source"]),
    )


def build_monitor_map(monitors: list[dict[str, Any]], now: int, skew_tolerance: int = 5) -> dict[str, Any]:
    """Project declared probes only; it neither schedules nor starts monitoring."""
    if not isinstance(monitors, list):
        raise MapError("monitors must be a list")
    if not isinstance(now, int) or now < 0:
        raise MapError("now must be a non-negative integer")
    if not isinstance(skew_tolerance, int) or skew_tolerance < 0:
        raise MapError("skew_tolerance must be a non-negative integer")
    projected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for monitor in monitors:
        if not isinstance(monitor, dict):
            raise MapError("every monitor must be an object")
        if any(not isinstance(monitor.get(field), str) or not monitor[field] for field in ("id", "target", "type", "severity", "cost", "consumer_gate")):
            raise MapError("monitor needs non-empty id, target, type, severity, cost and consumer_gate")
        monitor_id = monitor["id"]
        if monitor_id in seen:
            raise MapError(f"duplicate monitor: {monitor_id}")
        seen.add(monitor_id)
        cadence = monitor.get("cadence")
        freshness = monitor.get("freshness")
        signal = monitor.get("last_signal")
        if not isinstance(cadence, int) or cadence <= 0 or not isinstance(freshness, int) or freshness <= 0:
            raise MapError(f"monitor {monitor_id} needs positive cadence and freshness")
        if signal is not None and (not isinstance(signal, int) or signal < 0):
            raise MapError(f"monitor {monitor_id} has invalid last_signal")
        # Why: a signal dated after `now` beyond the declared tolerance is not evidence of
        # freshness; a skewed clock or a fabricated timestamp must stay distinguishable from healthy.
        if signal is None:
            status = "unknown"
        elif signal > now + skew_tolerance:
            status = "skew"
        elif now - signal <= freshness:
            status = "healthy"
        else:
            status = "stale"
        projected.append({
            "id": monitor_id, "target": monitor["target"], "type": monitor["type"], "cadence": cadence,
            "freshness": freshness, "last_signal": signal, "status": status, "severity": monitor["severity"],
            "cost": monitor["cost"], "consumer_gate": monitor["consumer_gate"],
        })
    return {"schema": "hpp.monitor-map/v1", "now": now, "skew_tolerance": skew_tolerance,
            "monitors": sorted(projected, key=lambda item: item["id"])}


def monitor_graph(projection: dict[str, Any]) -> dict[str, Any]:
    """The monitor map as nodes and edges, for drawing: a monitor node labelled `<id> · <status>`
    `observes` its target and `gates` its consumer gate. The monitor map itself has no graph."""
    nodes: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []
    for monitor in projection["monitors"]:
        monitor_node = f"monitor:{monitor['id']}"
        target_node = f"target:{monitor['target']}"
        gate_node = f"gate:{monitor['consumer_gate']}"
        nodes.extend((_node(monitor_node, "monitor", f"{monitor['id']} · {monitor['status']}"),
                      _node(target_node, "target", monitor["target"]),
                      _node(gate_node, "gate", monitor["consumer_gate"])))
        edges.extend((_edge(monitor_node, target_node, "observes"), _edge(monitor_node, gate_node, "gates")))
    unique = {node["id"]: node for node in nodes}
    return {"nodes": [unique[node_id] for node_id in sorted(unique)],
            "edges": sorted(edges, key=lambda edge: (edge["from"], edge["to"], edge["relation"]))}


def map_graph(projection: dict[str, Any]) -> dict[str, Any]:
    """The nodes and edges `hpp map --format mermaid` draws; the JSON projection is left as it is.

    A lane collision is drawn as one `collides:<paths>` edge between the two lanes (in the order of
    the collision's `lanes`); in the JSON it stays in the `collisions` field. The monitor map is
    drawn through `monitor_graph`.
    """
    if projection.get("schema") == "hpp.monitor-map/v1":
        return monitor_graph(projection)
    edges = list(projection["edges"])
    for collision in projection.get("collisions", []):
        left, right = collision["lanes"]
        edges.append(_edge(f"lane:{left}", f"lane:{right}", "collides:" + ", ".join(collision["territory"])))
    return {"nodes": projection["nodes"],
            "edges": sorted(edges, key=lambda edge: (edge["from"], edge["to"], edge["relation"]))}


_FEED_SOURCES = {
    "board": ".claude/lanes/board.jsonl",
    "effects": ".claude/lanes/effects.json",
    "mailbox": ".claude/lanes/mailbox",
    "handoff": ".claude/handoff/HANDOFF-LEDGER.jsonl",
    "registry": ".claude/lanes/registry.json",
}
_BOARD_VERDICTS = {"VERIFIED", "NEEDS-FIX", "DEFERRED", "NOT-SELECTED", "WITHDRAWN", "SELECTED", "APPROVED"}
_BOARD_TRANSITIONS = {"BUILDING", "CHECKPOINT-READY", "UNDER-REVIEW", "FIX-QUEUED", "MERGED", "DECLARED"}
_FEED_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")
_PRIVATE_ID = re.compile(r"(?:gh[pousr]_|github_pat_|sk-)[A-Za-z0-9_-]{16,}|(?:AKIA|ASIA)[A-Z0-9]{16}")
_FEED_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)?"
)
_MAIL_TO = re.compile(rb"^##\s*(?:To|Para):\s*(\S+)\s*$")
_MAIL_WHEN = re.compile(rb"^##\s*When:\s*(\S+)\s*$")
_MAIL_METADATA = re.compile(rb"^##\s*(?:To|Para|When|From|De|Affected item\(s\)):")


def _feed_id(value: Any) -> str | None:
    if isinstance(value, str) and _FEED_ID.fullmatch(value) and not _PRIVATE_ID.fullmatch(value):
        return value
    return None


def _feed_offset(value: str | None) -> timezone | None:
    if value is None:
        return None
    match = re.fullmatch(r"([+-])([01][0-9]|2[0-3]):([0-5][0-9])", value)
    if not match:
        raise MapError("local offset must be signed HH:MM, such as -03:00")
    sign, hours, minutes = match.groups()
    delta = timedelta(hours=int(hours), minutes=int(minutes))
    return timezone(-delta if sign == "-" else delta)


def _feed_time(value: Any, assumed_zone: timezone | None, basis: str) -> tuple[str | None, str]:
    if isinstance(value, str) and _FEED_TIMESTAMP.fullmatch(value):
        try:
            stamp = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
            if stamp.tzinfo is None and assumed_zone is None:
                return stamp.isoformat(), "unanchored-local"
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=assumed_zone)
            else:
                basis = "recorded-offset"
            return stamp.astimezone(timezone.utc).isoformat().removesuffix("+00:00") + "Z", basis
        except (ValueError, OverflowError):
            pass
    return None, "unknown"


def _read_feed_bytes(workspace: Path, path: Path, info: dict[str, Any]) -> bytes | None:
    try:
        if not path.resolve().is_relative_to(workspace):
            info["status"] = "outside-target"
            return None
        return path.read_bytes()
    except FileNotFoundError:
        info["status"] = "missing"
    except (OSError, RuntimeError):
        info["status"] = "unreadable"
    return None


def _feed_json_records(workspace: Path, path: Path, info: dict[str, Any],
                       mapping_key: str | None = None) -> list[tuple[int, dict[str, Any]]]:
    raw = _read_feed_bytes(workspace, path, info)
    if raw is None:
        return []
    info["sha256"] = hashlib.sha256(raw).hexdigest()
    if mapping_key is None:
        candidates = []
        for sequence, line in enumerate(raw.splitlines(), 1):
            if line.strip():
                try:
                    candidates.append((sequence, json.loads(line)))
                except (ValueError, RecursionError):
                    info["invalid_records"] += 1
    else:
        try:
            payload = json.loads(raw)
            mapping = payload.get(mapping_key) if isinstance(payload, dict) else None
            if not isinstance(mapping, dict):
                raise ValueError("expected a record mapping")
        except (ValueError, RecursionError):
            info.update(status="invalid", invalid_records=1)
            return []
        candidates = [(sequence, {**record, "_key": key} if isinstance(record, dict) else None)
                      for sequence, (key, record) in enumerate(sorted(mapping.items()), 1)]
    records = [(sequence, record) for sequence, record in candidates if isinstance(record, dict)]
    info["invalid_records"] += len(candidates) - len(records)
    return records


def _feed_mail(workspace: Path, mailbox: Path, info: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    records = []
    fingerprint = hashlib.sha256()
    try:
        mailbox.stat()
        if not mailbox.is_dir():
            info["status"] = "invalid"
            return records
        files = []
        for directory, archived in ((mailbox, False), (mailbox / "_read", True)):
            if directory.resolve().is_relative_to(workspace):
                files.extend((path, archived) for path in sorted(directory.glob("*.md")))
            else:
                info["invalid_records"] += 1
    except FileNotFoundError:
        info["status"] = "missing"
        return records
    except (OSError, RuntimeError):
        info["status"] = "unreadable"
        return records
    for sequence, (path, archived) in enumerate(files, 1):
        raw = _read_feed_bytes(workspace, path, {})
        if raw is None:
            info["invalid_records"] += 1
            continue
        digest = hashlib.sha256(raw).hexdigest()
        fingerprint.update(b"archive:" if archived else b"inbox:")
        fingerprint.update(digest.encode("ascii"))
        to = set()
        when = None
        in_metadata = False
        for line in raw.splitlines():
            if _MAIL_METADATA.match(line):
                in_metadata = True
            elif in_metadata and line.strip():
                break
            routing = _MAIL_TO.match(line)
            if routing:
                lane = _feed_id(routing.group(1).decode("ascii", errors="replace"))
                if lane is not None:
                    to.add(lane)
            stamp = _MAIL_WHEN.match(line)
            if stamp and when is None:
                when = stamp.group(1).decode("ascii", errors="replace")
        records.append((sequence, {"digest": digest, "archived": archived, "to": sorted(to), "ts": when}))
    info["sha256"] = fingerprint.hexdigest()
    return records


def build_feed_map(target: Path, mailbox_path: str | None = None,
                   local_offset: str | None = None) -> dict[str, Any]:
    """Project the metadata of local lane records, without executing a writer or reading ambient time."""
    workspace = target.resolve()
    if not workspace.is_dir():
        raise MapError("feed target must be a directory")
    mailbox = (workspace / (mailbox_path or _FEED_SOURCES["mailbox"])).resolve()
    if not mailbox.is_relative_to(workspace):
        raise MapError("mailbox must resolve inside the target")
    offset = _feed_offset(local_offset)
    sources = []
    events = []

    def emit(source: str, sequence: int, kind: str, ts: Any, zone: timezone | None, basis: str,
             **metadata: Any) -> None:
        at, time_basis = _feed_time(ts, zone, basis)
        events.append({
            "id": f"{source}:{sequence}:{kind}", "source": source, "sequence": sequence,
            "kind": kind, "at": at, "time_basis": time_basis,
            **{key: value for key, value in metadata.items() if value is not None},
        })

    for source, relative_path in _FEED_SOURCES.items():
        path = mailbox if source == "mailbox" else workspace / relative_path
        info = {
            "id": source, "path": path.relative_to(workspace).as_posix(), "status": "present",
            "sha256": None, "records": 0, "invalid_records": 0,
        }
        sources.append(info)
        if source == "mailbox":
            records = _feed_mail(workspace, path, info)
        else:
            key = {"effects": "effects", "registry": "lanes"}.get(source)
            records = _feed_json_records(workspace, path, info, key)
        for sequence, record in records:
            lane = _feed_id(record.get("lane_id"))
            item = _feed_id(record.get("item_id")) or _feed_id(record.get("task_id"))
            stamp = record.get("ts")
            if source == "board":
                state = _feed_id(record.get("state"))
                if state == "CLAIMED":
                    kind = "claim"
                elif state in _BOARD_VERDICTS:
                    kind = "verdict"
                elif state in _BOARD_TRANSITIONS:
                    kind = "transition"
                else:
                    info["invalid_records"] += 1
                    continue
                emit(source, sequence, kind, stamp, offset, "provided-offset",
                     lane=lane, item=item, state=state, reservation=_feed_id(record.get("reservation_id")))
            elif source == "effects" and record.get("effect_state") == "delivered":
                emit(source, sequence, "delivery", record.get("delivered_at"), None, "recorded-offset",
                     lane=_feed_id(record.get("target")), item=item, reservation=_feed_id(record.get("reservation_id")))
            elif source == "handoff":
                action = record.get("event")
                if action not in ("written", "consumed"):
                    info["invalid_records"] += 1
                    continue
                emit(source, sequence, f"handoff-{action}", stamp, None, "recorded-offset",
                     lane=lane, handoff=_feed_id(record.get("handoff_id")))
            elif source == "registry" and record.get("heartbeat_at"):
                emit(source, sequence, "heartbeat", record["heartbeat_at"], timezone.utc, "writer-utc",
                     lane=_feed_id(record["_key"]))
            elif source == "mailbox":
                metadata = {"message_sha256": record["digest"], "to": record["to"]}
                emit(source, sequence, "message-sent", stamp, offset, "provided-offset", **metadata)
                if record["archived"]:
                    emit(source, sequence, "message-archived", None, None, "unknown", **metadata)
            info["records"] += 1
        if info["status"] == "present":
            info["status"] = "partial" if info["invalid_records"] else ("present" if records else "empty")

    source_order = {source: index for index, source in enumerate(_FEED_SOURCES)}

    def order(event: dict[str, Any]) -> tuple[int, datetime, int, int, str]:
        at = event["at"]
        tier = 2 if at is None else (1 if event["time_basis"] == "unanchored-local" else 0)
        stamp = datetime.fromisoformat(at.removesuffix("Z")) if tier == 0 else datetime.min
        return tier, stamp, source_order[event["source"]], event["sequence"], event["kind"]

    return {
        "schema": "hpp.feed-map/v1", "view": "feed", "local_offset": local_offset,
        "sources": sources, "events": sorted(events, key=order),
        "limitations": [
            "UTC timestamps sort first. Unanchored local and untimed records follow in source order.",
            "A supplied offset applies to timezone-free board and mailbox stamps only.",
            "Archive presence is evidence of archiving; reading and its time are not recorded.",
            "The lane registry retains only the latest heartbeat per lane.",
            "The mailbox uses the default directory unless one is supplied explicitly.",
            "Source fingerprints identify the bytes read; they are not a cross-source transaction or an attestation.",
        ],
    }
