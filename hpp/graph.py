"""Deterministic, inspectable graph projections from the HPP manifest."""
from __future__ import annotations

from typing import Any, Optional


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


def _mermaid_text(text: str) -> str:
    """A label or an edge text as Mermaid reads it: the characters that would end it become entity codes."""
    # Why: a `"` closes a node label, a `|` closes an edge text and `<`/`>` are read as HTML, so a
    # label carrying one produced a diagram that no longer parses; a line break splits the statement.
    for raw, code in (('"', "#quot;"), ("|", "#124;"), ("<", "#lt;"), (">", "#gt;"),
                      ("\r\n", " "), ("\r", " "), ("\n", " ")):
        text = text.replace(raw, code)
    return text


def to_mermaid(graph: dict[str, Any], clusters: Optional[list[dict[str, Any]]] = None) -> str:
    """A flowchart of `nodes` and `edges`: nodes numbered in id order, edges sorted by source, target
    and relation, so the same graph gives the same bytes whatever the order it was listed in.

    `clusters` groups nodes into `subgraph` blocks, in the order given, each `{"label", "nodes"}`.
    """
    labels = {node["id"]: _mermaid_text(node["label"]) for node in graph["nodes"]}
    index_for = {node_id: index for index, node_id in enumerate(sorted(labels))}
    grouped: set[str] = set()
    for cluster in clusters or []:
        for node_id in cluster["nodes"]:
            if node_id not in index_for:
                raise ValueError(f"cluster {cluster['label']!r} names an unknown node: {node_id}")
            if node_id in grouped:
                raise ValueError(f"node {node_id} is in more than one cluster")
            grouped.add(node_id)
    lines = ["flowchart LR"]
    for node_id in sorted(labels):
        if node_id not in grouped:
            lines.append(f"  n{index_for[node_id]}[\"{labels[node_id]}\"]")
    for number, cluster in enumerate(clusters or []):
        lines.append(f"  subgraph c{number}[\"{_mermaid_text(cluster['label'])}\"]")
        for node_id in sorted(cluster["nodes"], key=index_for.__getitem__):
            lines.append(f"    n{index_for[node_id]}[\"{labels[node_id]}\"]")
        lines.append("  end")
    for edge in sorted(graph["edges"], key=lambda item: (item["from"], item["to"], item["relation"])):
        lines.append(f"  n{index_for[edge['from']]} -->|{_mermaid_text(edge['relation'])}| n{index_for[edge['to']]}")
    return "\n".join(lines) + "\n"
