"""Spec-driven work decomposition for reproducible agent operations.

The WorkGraph is intentionally data-only: it schedules declared work into
dependency waves but never launches an agent or a process.
"""
from __future__ import annotations

from typing import Any


TIERS = ("economy", "balanced", "frontier")


class WorkGraphError(ValueError):
    """A work specification cannot be compiled truthfully."""


def _items(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_work = spec.get("work")
    if not isinstance(raw_work, list) or not raw_work:
        raise WorkGraphError("work must be a non-empty list")
    work: dict[str, dict[str, Any]] = {}
    for item in raw_work:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"].strip():
            raise WorkGraphError("every work item needs a non-empty string id")
        work_id = item["id"]
        if work_id in work:
            raise WorkGraphError(f"duplicate work id: {work_id}")
        dependencies = item.get("depends_on", [])
        if not isinstance(dependencies, list) or not all(isinstance(value, str) for value in dependencies):
            raise WorkGraphError(f"work {work_id} needs a list of depends_on ids")
        if len(set(dependencies)) != len(dependencies):
            raise WorkGraphError(f"work {work_id} has duplicate dependency")
        acceptance = item.get("acceptance")
        if not isinstance(acceptance, list) or not acceptance or not all(isinstance(value, str) and value.strip() for value in acceptance):
            raise WorkGraphError(f"work {work_id} needs non-empty acceptance criteria")
        tier = item.get("tier")
        if tier not in TIERS:
            raise WorkGraphError(f"work {work_id} has invalid tier: {tier}")
        work[work_id] = {
            "id": work_id,
            "depends_on": sorted(dependencies),
            "acceptance": list(acceptance),
            "tier": tier,
        }
    for item in work.values():
        for dependency in item["depends_on"]:
            if dependency not in work:
                raise WorkGraphError(f"unknown dependency: {item['id']} -> {dependency}")
    return work


def _assert_acyclic(work: dict[str, dict[str, Any]]) -> None:
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(work_id: str) -> None:
        if work_id in visiting:
            start = visiting.index(work_id)
            cycle = " -> ".join([*visiting[start:], work_id])
            raise WorkGraphError(f"dependency cycle: {cycle}")
        if work_id in visited:
            return
        visiting.append(work_id)
        for dependency in work[work_id]["depends_on"]:
            visit(dependency)
        visiting.pop()
        visited.add(work_id)

    for work_id in sorted(work):
        visit(work_id)


def _waves(work: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    remaining = {work_id: set(item["depends_on"]) for work_id, item in work.items()}
    resolved: set[str] = set()
    result: list[dict[str, Any]] = []
    while remaining:
        ready = sorted(work_id for work_id, dependencies in remaining.items() if dependencies <= resolved)
        if not ready:  # Defensive: _assert_acyclic should have produced the detailed error.
            raise WorkGraphError("dependency cycle prevents scheduling")
        result.append({"index": len(result) + 1, "work": ready})
        resolved.update(ready)
        for work_id in ready:
            del remaining[work_id]
    return result


def compile_workgraph(spec: dict[str, Any]) -> dict[str, Any]:
    """Validate a declarative work spec and return stable topological waves."""
    if not isinstance(spec, dict):
        raise WorkGraphError("workgraph spec must be an object")
    work = _items(spec)
    _assert_acyclic(work)
    ordered_ids = [work_id for wave in _waves(work) for work_id in wave["work"]]
    edges = [
        {"from": dependency, "to": work_id, "relation": "depends-on"}
        for work_id in ordered_ids
        for dependency in work[work_id]["depends_on"]
    ]
    tier_counts = {tier: sum(item["tier"] == tier for item in work.values()) for tier in TIERS}
    return {
        "schema": "hpp.workgraph/v1",
        "work": [work[work_id] for work_id in ordered_ids],
        "edges": sorted(edges, key=lambda edge: (edge["from"], edge["to"])),
        "waves": _waves(work),
        "tier_counts": tier_counts,
    }
