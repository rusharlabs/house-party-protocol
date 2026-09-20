"""Executable positive/negative controls for the public HPP benchmark."""
from __future__ import annotations

import copy
import tempfile
from pathlib import Path

from hpp.context import ContextError, compile_context
from hpp.graph import build_graph
from hpp.manifest import ManifestError, load_manifest, validate_manifest
from hpp.maps import build_lane_map, build_monitor_map
from hpp.policy import assess, exit_for
from hpp.routing import RoutingError, route
from hpp.state import StateError, append_event, project, read_events
from hpp.workgraph import WorkGraphError, compile_workgraph


def _manifest_contract() -> bool:
    manifest, _ = load_manifest()
    if len(manifest["modules"]) != 10:
        return False
    broken = copy.deepcopy(manifest)
    broken["modules"][0]["integrates_with"].append("missing-module")
    try:
        validate_manifest(broken)
    except ManifestError:
        return True
    return False


def _policy_enforcement() -> bool:
    safe = assess("python -m pytest -q")
    dangerous = assess("rm -rf src")
    return safe["action"] == "ALLOW" and dangerous["action"] == "BLOCK" and exit_for(dangerous, "enforce") == 2


def _workgraph_waves() -> bool:
    valid = compile_workgraph({"work": [
        {"id": "spec", "acceptance": ["scope"], "tier": "economy"},
        {"id": "build", "depends_on": ["spec"], "acceptance": ["artifact"], "tier": "balanced"},
    ]})
    if valid["waves"] != [{"index": 1, "work": ["spec"]}, {"index": 2, "work": ["build"]}]:
        return False
    try:
        compile_workgraph({"work": [
            {"id": "a", "depends_on": ["b"], "acceptance": ["a"], "tier": "economy"},
            {"id": "b", "depends_on": ["a"], "acceptance": ["b"], "tier": "economy"},
        ]})
    except WorkGraphError:
        return True
    return False


def _lane_collision() -> bool:
    lanes = [
        {"id": "maker", "territory": ["src"], "heartbeat_at": 980},
        {"id": "checker", "territory": ["src/api"], "heartbeat_at": 850},
        {"id": "old", "territory": ["src/api/routes"], "heartbeat_at": 100},
    ]
    result = build_lane_map(lanes, now=1000, suspect_after=60, dead_after=300)
    return result["liveness"]["old"] == "dead" and result["collisions"] == [
        {"lanes": ["checker", "maker"], "territory": ["src", "src/api"]}
    ]


def _monitor_freshness() -> bool:
    result = build_monitor_map([
        {"id": "fresh", "target": "service", "type": "command", "cadence": 60, "freshness": 120,
         "last_signal": 980, "severity": "block", "cost": "low", "consumer_gate": "doctor"},
        {"id": "old", "target": "data", "type": "timestamp", "cadence": 60, "freshness": 120,
         "last_signal": 700, "severity": "warn", "cost": "low", "consumer_gate": "resume"},
    ], now=1000)
    return {item["id"]: item["status"] for item in result["monitors"]} == {"fresh": "healthy", "old": "stale"}


def _context_provenance() -> bool:
    result = compile_context([{"source": "spec", "priority": 1, "content": "scope"}], budget=5)
    if len(result["included"][0]["sha256"]) != 64:
        return False
    try:
        compile_context([{"source": "unsafe", "priority": 1, "content": "api_key=secret-value"}], budget=100)
    except ContextError:
        return True
    return False


def _routing_floor() -> bool:
    providers = [
        {"id": "economy", "tiers": ["economy"], "stages": ["inspect"], "max_context": 8000},
        {"id": "frontier", "tiers": ["frontier"], "stages": ["review"], "max_context": 64000},
    ]
    low = route({"risk": "low", "complexity": "low", "context": 1000, "stage": "inspect"}, "economy", providers)
    if low["selection"]["tier"] != "economy":
        return False
    try:
        route({"risk": "high", "complexity": "high", "context": 1000, "stage": "inspect"}, "economy", providers)
    except RoutingError:
        return True
    return False


def _event_evidence_gate() -> bool:
    manifest, _ = load_manifest()
    with tempfile.TemporaryDirectory(prefix="hpp-control-") as temp:
        valid_path = Path(temp) / "events.jsonl"
        for event_type in ("work_started", "evidence_recorded", "check_passed", "human_approved", "verified"):
            append_event(valid_path, event_type, manifest)
        if project(read_events(valid_path), manifest)["state"] != "verified":
            return False
        invalid_path = Path(temp) / "invalid.jsonl"
        try:
            append_event(invalid_path, "verified", manifest)
        except StateError:
            return not invalid_path.exists()
    return False


def _graph_determinism() -> bool:
    manifest, _ = load_manifest()
    first = build_graph(manifest, "capability")
    second = build_graph(copy.deepcopy(manifest), "capability")
    return first == second and bool(first["nodes"]) and bool(first["edges"])


_CONTROLS = {
    "manifest-contract": _manifest_contract,
    "policy-enforcement": _policy_enforcement,
    "workgraph-waves": _workgraph_waves,
    "lane-collision": _lane_collision,
    "monitor-freshness": _monitor_freshness,
    "context-provenance": _context_provenance,
    "routing-risk-floor": _routing_floor,
    "event-evidence-gate": _event_evidence_gate,
    "graph-determinism": _graph_determinism,
}


def run_control(control_id: str) -> bool:
    """Run one named control; unknown IDs are suite errors, never implicit passes."""
    if control_id not in _CONTROLS:
        raise ValueError(f"unknown HPP control: {control_id}")
    return _CONTROLS[control_id]()
