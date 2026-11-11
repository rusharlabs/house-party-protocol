"""Read-only dependency measurements and deterministic lane proposals."""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
import re
from typing import Any
import unicodedata

from hpp._repository import RepositoryError, artifact_status, changed_paths_since, snapshot


class TerritoryError(ValueError):
    """A territory input cannot support a truthful measurement."""


def normalise_territory(value: Any) -> list[str]:
    """Accept relative directory/file prefixes, never globs or parent traversal."""
    if not isinstance(value, list) or not value:
        raise TerritoryError("territory must be a non-empty list of relative paths")
    result = []
    for item in value:
        if (not isinstance(item, str) or not item or "\\" in item or ":" in item
                or any(ord(c) < 32 for c in item) or any(c in item for c in "*?")
                or PurePosixPath(item).is_absolute()
                or any(part in ("", ".", "..") for part in item.split("/"))):
            raise TerritoryError("territory must contain portable relative paths")
        result.append(unicodedata.normalize("NFC", item))
    return sorted(set(result))


def _contains(prefix: str, path: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def _relations(target: str | Path | None, graph: Any) -> tuple[dict, list[tuple[str, str]], dict[str, str]]:
    if target is None:
        return {"status": "not-measured", "reason": "repository target was not supplied"}, [], {}
    state = artifact_status(target, graph)
    if state["status"] != "fresh":
        return {"status": "not-measured", "reason": "code graph is not fresh", "freshness": state}, [], {}
    if (not isinstance(graph, dict) or graph.get("schema") != "hpp.codegraph/v1"
            or not isinstance(graph.get("instrument"), dict)
            or graph["instrument"].get("status") != "measured"):
        return {"status": "not-measured", "reason": "code graph instrument did not measure"}, [], {}
    nodes, edges = graph.get("nodes"), graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise TerritoryError("code graph must contain nodes and edges")
    allowed = set(snapshot(target).files)
    paths: dict[str, str] = {}
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node["id"]:
            raise TerritoryError("code graph nodes need unique ids and repository paths")
        path = normalise_territory([node.get("path")])[0]
        if node["id"] in paths:
            raise TerritoryError("code graph repeats a node id")
        if path not in allowed:
            raise TerritoryError("code graph path is outside the committed universe")
        paths[node["id"]] = path
    imports = []
    for edge in edges:
        if not isinstance(edge, dict):
            raise TerritoryError("code graph edges must be objects")
        if edge.get("relation") == "imports":
            source, dest = edge.get("from"), edge.get("to")
            if not isinstance(source, str) or not isinstance(dest, str) or source not in paths or dest not in paths:
                raise TerritoryError("resolved imports must name known nodes")
            imports.append((paths[source], paths[dest]))
    return {"status": "measured", "commit": graph["commit"], "unit": "resolved import edges"}, sorted(imports), paths


def territory_coupling(target: str | Path | None, territories: list[dict[str, Any]], codegraph: Any) -> dict:
    """Measure directed imports between declared territories without changing them."""
    measured, imports, _ = _relations(target, codegraph)
    owners: dict[str, list[str]] = {}
    for item in territories:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            raise TerritoryError("territories need unique ids")
        if item["id"] in owners:
            raise TerritoryError("territories repeat an id")
        owners[item["id"]] = normalise_territory(item.get("territory"))
    counts: Counter[tuple[str, str]] = Counter()
    for source, dest in imports:
        for left, prefixes in owners.items():
            if not any(_contains(p, source) for p in prefixes):
                continue
            for right, targets in owners.items():
                if left != right and any(_contains(p, dest) for p in targets):
                    counts[left, right] += 1
    return {**measured, "warnings": [{"from": a, "to": b, "edges": count,
                                     "reason": "territories are linked by imports"}
                                    for (a, b), count in sorted(counts.items())]}


def propose_lanes(target: str | Path, inventory: dict, codegraph: dict | None = None,
                  max_lanes: int = 4, depth: int = 2) -> dict:
    """Propose a reversible partition; applying it remains a separate human decision."""
    if isinstance(max_lanes, bool) or not isinstance(max_lanes, int) or not 1 <= max_lanes <= 128:
        raise TerritoryError("max_lanes must be an integer between 1 and 128")
    if isinstance(depth, bool) or not isinstance(depth, int) or not 1 <= depth <= 32:
        raise TerritoryError("depth must be an integer between 1 and 32")
    if not isinstance(inventory, dict) or inventory.get("schema") != "hpp.inventory/v1":
        raise TerritoryError("lane proposals require hpp.inventory/v1")
    if artifact_status(target, inventory)["status"] != "fresh":
        raise TerritoryError("lane proposals require a fresh inventory")
    raw_files = inventory.get("files")
    if not isinstance(raw_files, list):
        raise TerritoryError("inventory must declare its file universe")
    files = normalise_territory(raw_files) if raw_files else []
    snap = snapshot(target)
    if not set(files) <= set(snap.files):
        raise TerritoryError("inventory paths are outside the committed universe")
    measured, imports, node_paths = _relations(target, codegraph)
    # Root files are explicit file territories; nested units use directory depth only.
    def unit(path: str) -> str:
        parts = path.split("/")[:-1]
        return "/".join(parts[:depth]) if parts else path

    units = sorted({unit(path) for path in files})
    universe = set(files)
    omitted = sum(a not in universe or b not in universe for a, b in imports)
    imports = [(a, b) for a, b in imports if a in universe and b in universe]
    measured = {**measured, "scope": "resolved imports within the inventory universe",
                "imports_used": len(imports), "imports_outside_inventory": omitted}
    weights: Counter[tuple[str, str]] = Counter((unit(a), unit(b)) for a, b in imports if unit(a) != unit(b))
    incoming: dict[str, set[str]] = defaultdict(set)
    for left, right in weights:
        incoming[right].add(left)
    threshold = max(2, (len(units) + 1) // 2)
    shared = sorted(u for u in units if len(incoming[u]) >= threshold)
    groups = [{u} for u in units if u not in shared]
    while len(groups) > max_lanes:
        options = []
        for index, left in enumerate(groups):
            for other in range(index + 1, len(groups)):
                right = groups[other]
                strength = sum(n for (a, b), n in weights.items()
                               if (a in left and b in right) or (a in right and b in left))
                options.append((-strength, tuple(sorted(left)), tuple(sorted(right)), index, other))
        _, _, _, left, right = min(options)
        groups[left] |= groups[right]
        del groups[right]
        groups.sort(key=lambda group: tuple(sorted(group)))
    groups.sort(key=lambda group: tuple(sorted(group)))
    owner = {u: f"lane-{i + 1:02d}" for i, group in enumerate(groups) for u in group}
    owner.update({u: "shared:" + u for u in shared})
    lanes = []
    for i, group in enumerate(groups):
        owned_files = [path for path in files if unit(path) in group]
        lanes.append({"id": f"lane-{i + 1:02d}", "territory": sorted(group), "files": len(owned_files),
                      "modules": sum(node_id.startswith("module:") and path in owned_files
                                     for node_id, path in node_paths.items())})
    cut: Counter[tuple[str, str]] = Counter()
    for (a, b), count in weights.items():
        if owner[a] != owner[b]:
            cut[owner[a], owner[b]] += count
    sections = inventory.get("sections", {})
    hotspots = sections.get("hotspots", {}) if isinstance(sections, dict) else {}
    top = hotspots.get("top", []) if isinstance(hotspots, dict) and hotspots.get("status") == "measured" else []
    hot_paths = set()
    for entry in top if isinstance(top, list) else []:
        path = entry[0] if isinstance(entry, (list, tuple)) and len(entry) == 2 else entry.get("path") if isinstance(entry, dict) else None
        count = entry[1] if isinstance(entry, (list, tuple)) and len(entry) == 2 else entry.get("count") if isinstance(entry, dict) else None
        if isinstance(path, str) and path in universe and isinstance(count, int) and not isinstance(count, bool) and count > 0:
            hot_paths.add(path)
    touches: dict[str, set[str]] = {p: {owner[unit(p)]} for p in hot_paths}
    for source, dest in imports:
        if dest in touches:
            touches[dest].add(owner[unit(source)])
    return {"schema": "hpp.lane-proposal/v1", "commit": snap.commit,
            "relations": measured["status"], "measurement": measured,
            "lanes": lanes, "cut": [{"from": a, "to": b, "edges": count} for (a, b), count in sorted(cut.items())],
            "cut_cost": sum(cut.values()), "shared": shared,
            "shared_policy": "serialize changes or agree a contract before parallel work",
            "red_zones": [{"path": p, "groups": sorted(groups_)} for p, groups_ in sorted(touches.items()) if len(groups_) > 1],
            "inputs": {"inventory_commit": inventory["commit"],
                       "codegraph_commit": codegraph.get("commit") if isinstance(codegraph, dict) else None},
            "universe": {"files": len(files), "rule": "file paths supplied by the fresh inventory"},
            "parameters": {"max_lanes": max_lanes, "depth": depth, "hub_incoming_territories": threshold},
            "approval": "required before applying territories"}


def measure_blast_radius(repo: str | Path, base_commit: str, codegraph: dict | None) -> dict:
    """Changed tracked paths and their reverse-import closure at a fresh graph."""
    if not isinstance(base_commit, str) or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", base_commit):
        return {"status": "not-measured", "reason": "base commit must be an object identity"}
    measured, imports, _ = _relations(repo, codegraph)
    if measured["status"] != "measured":
        return {**measured, "base_commit": base_commit}
    try:
        changed = list(changed_paths_since(snapshot(repo), base_commit))
    except RepositoryError:
        return {"status": "not-measured", "reason": "base commit could not be measured",
                "base_commit": base_commit, "graph_commit": codegraph["commit"]}
    affected = set(changed)
    reverse: dict[str, set[str]] = defaultdict(set)
    for source, dest in imports:
        reverse[dest].add(source)
    queue = list(changed)
    while queue:
        for parent in sorted(reverse[queue.pop()] - affected):
            affected.add(parent)
            queue.append(parent)
    return {"status": "measured", "base_commit": base_commit, "graph_commit": codegraph["commit"],
            "changed": changed, "dependents": sorted(affected - set(changed)),
            "affected": sorted(affected), "unit": "tracked repository paths", "scope": "resolved imports only"}
