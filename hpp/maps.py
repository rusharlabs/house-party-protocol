"""Deterministic, data-only projections for lanes and operational topology."""
from __future__ import annotations

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
    return _sorted_graph("lane", nodes, edges, collisions=collisions,
                         liveness={key: liveness[key] for key in sorted(liveness)})


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
    required = ("id", "target", "type", "cadence", "freshness", "severity", "cost", "consumer_gate")
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
