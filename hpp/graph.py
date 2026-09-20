"""Deterministic, inspectable graph projections from the HPP manifest."""
from __future__ import annotations

from typing import Any


def _node(node_id: str, kind: str, label: str) -> dict[str, str]:
    return {"id": node_id, "kind": kind, "label": label}


def _edge(source: str, target: str, relation: str) -> dict[str, str]:
    return {"from": source, "to": target, "relation": relation}


def build_graph(manifest: dict[str, Any], view: str) -> dict[str, Any]:
    nodes: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []
    if view == "capability":
        for host in manifest["hosts"]:
            nodes.append(_node(f"host:{host}", "host", host))
        for module in manifest["modules"]:
            module_id = f"module:{module['id']}"
            nodes.append(_node(module_id, "module", module["id"]))
            for capability in module["capabilities"]:
                capability_id = f"capability:{capability}"
                nodes.append(_node(capability_id, "capability", capability))
                edges.append(_edge(module_id, capability_id, "provides"))
            for host, coverage in sorted(module["hosts"].items()):
                edges.append(_edge(module_id, f"host:{host}", f"supports:{coverage}"))
            for dependency in module.get("requires", []):
                edges.append(_edge(module_id, f"module:{dependency}", "requires"))
            for integration in module.get("integrates_with", []):
                edges.append(_edge(module_id, f"module:{integration}", "integrates-with"))
        for name, bundle in manifest["bundles"].items():
            bundle_id = f"bundle:{name}"
            nodes.append(_node(bundle_id, "bundle", name))
            for module_id in bundle["modules"]:
                edges.append(_edge(bundle_id, f"module:{module_id}", "includes"))
    elif view == "operational":
        for transition in manifest["loop"]["transitions"]:
            nodes.extend((_node(f"state:{transition['from']}", "state", transition["from"]),
                          _node(f"state:{transition['to']}", "state", transition["to"]),
                          _node(f"gate:{transition['gate']}", "gate", transition["gate"])))
            edges.append(_edge(f"state:{transition['from']}", f"gate:{transition['gate']}", transition["event"]))
            edges.append(_edge(f"gate:{transition['gate']}", f"state:{transition['to']}", "permits"))
    elif view == "agent":
        nodes.extend((_node("role:maker", "role", "maker"), _node("role:checker", "role", "checker (read-only)"),
                      _node("role:human-gate", "role", "human gate")))
        edges.extend((_edge("role:maker", "role:checker", "submits"),
                      _edge("role:checker", "role:human-gate", "reports"),
                      _edge("role:human-gate", "role:maker", "approves-or-returns")))
    elif view == "evidence":
        nodes.extend((_node("criterion:fresh-evidence", "criterion", "fresh evidence"),
                      _node("evidence:record", "evidence", "recorded evidence"),
                      _node("verdict:verified", "verdict", "verified")))
        edges.extend((_edge("criterion:fresh-evidence", "evidence:record", "requires"),
                      _edge("evidence:record", "verdict:verified", "supports")))
    elif view == "code":
        for module in manifest["modules"]:
            module_id = f"module:{module['id']}"
            nodes.append(_node(module_id, "module", module["id"]))
            for component in module.get("components", []):
                component_id = f"component:{module['id']}:{component}"
                nodes.append(_node(component_id, "component", component))
                edges.append(_edge(module_id, component_id, "declares"))
    else:
        raise ValueError(f"unknown graph view: {view}")
    deduped = {node["id"]: node for node in nodes}
    return {"protocol_version": manifest["protocol_version"], "view": view,
            "nodes": [deduped[key] for key in sorted(deduped)],
            "edges": sorted(edges, key=lambda item: (item["from"], item["to"], item["relation"]))}


def to_mermaid(graph: dict[str, Any]) -> str:
    lines = ["flowchart LR"]
    labels = {node["id"]: node["label"] for node in graph["nodes"]}
    for index, node_id in enumerate(sorted(labels)):
        lines.append(f"  n{index}[\"{labels[node_id]}\"]")
    index_for = {node_id: index for index, node_id in enumerate(sorted(labels))}
    for edge in graph["edges"]:
        lines.append(f"  n{index_for[edge['from']]} -->|{edge['relation']}| n{index_for[edge['to']]}")
    return "\n".join(lines) + "\n"
