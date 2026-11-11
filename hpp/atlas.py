"""Render HPP's read-only projections as a standalone local HTML atlas."""
from __future__ import annotations

import hashlib
import json
import shlex
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, Iterable

from hpp.attest import _repo_root as attestation_repo_root, verify_attestation
from hpp.deliberation import verify_record
from hpp.graph import build_graph
from hpp.manifest import find_manifest, validate_manifest
from hpp.maps import build_agent_map, build_context_map, build_feed_map, build_lane_map, build_monitor_map
from hpp.workgraph import compile_workgraph, workgraph_graph

MAX_SOURCE_BYTES = 4 * 1024 * 1024

STYLE = """
:root {color-scheme: light dark; font: 1rem/1.6 system-ui, sans-serif;}
body {max-width: 68rem; margin: auto; padding: 1rem 1.5rem 3rem;}
h1, h2, h3 {line-height: 1.2;}
nav ul {display: flex; flex-wrap: wrap; gap: .4rem 1.4rem;}
section {border-top: 1px solid GrayText; margin-top: 2rem; padding-top: 1rem;}
code, td {overflow-wrap: anywhere;}
.table {overflow-x: auto;}
table {border-collapse: collapse; width: 100%;}
td, th {border-bottom: 1px solid GrayText; text-align: left; padding: .35rem .6rem;}
svg {width: 100%; height: auto; color: CanvasText;}
svg line, svg rect {stroke: currentColor;}
svg rect {fill: Canvas;}
svg text, svg polygon {fill: currentColor;}
details {margin: .6rem 0;}
"""


@dataclass(frozen=True)
class View:
    key: str
    title: str
    command: tuple[str, ...]
    data: dict[str, Any] | None
    sources: tuple[tuple[str, str], ...] = ()
    missing: str = ""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_source(path: Path, root_type: type) -> tuple[Any, str]:
    try:
        if not path.is_file():
            raise ValueError(f"atlas source is not a regular file: {path.name}")
        with path.open("rb") as stream:
            raw = stream.read(MAX_SOURCE_BYTES + 1)
        if len(raw) > MAX_SOURCE_BYTES:
            raise ValueError(f"atlas source exceeds {MAX_SOURCE_BYTES} bytes: {path.name}")
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read atlas source {path.name}: {exc}") from exc
    if not isinstance(value, root_type):
        raise ValueError(f"atlas source {path.name} must contain a JSON {root_type.__name__}")
    return value, _sha(raw)


def _project_path(target: Path, value: str) -> tuple[Path, str]:
    path = (target / value).resolve()
    if not path.is_relative_to(target):
        raise ValueError("atlas source must resolve inside --target")
    return path, "./" + path.relative_to(target).as_posix()


def _content(value: Any) -> str:
    if value is None:
        return "—"
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    # JSON permits escaped lone surrogates. Keep them visible without emitting invalid UTF-8.
    return escape(text.encode("utf-8", "backslashreplace").decode("utf-8"))


def _table(columns: tuple[str, ...], rows: Iterable[Iterable[Any]]) -> str:
    body = "".join("<tr>" + "".join(f"<td>{_content(cell)}</td>" for cell in row) + "</tr>" for row in rows)
    if not body:
        return "<p>No records in this projection.</p>"
    head = "".join(f'<th scope="col">{_content(name)}</th>' for name in columns)
    return f'<div class="table" tabindex="0"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _diagram(key: str, graph: dict[str, Any]) -> str:
    nodes, edges = graph["nodes"], graph["edges"]
    if not nodes or len(nodes) > 18 or len(edges) > 32:
        return ""
    clusters = graph.get("clusters") or [
        {"nodes": [node["id"] for node in nodes[index:index + 4]]} for index in range(0, len(nodes), 4)
    ]
    points = {
        node_id: (30 + column * 200, 20 + row * 70)
        for column, cluster in enumerate(clusters) for row, node_id in enumerate(cluster["nodes"])
    }
    width = len(clusters) * 200 + 20
    height = max(len(cluster["nodes"]) for cluster in clusters) * 70 + 10
    arrow = f"arrow-{key}"
    lines = []
    for edge in edges:
        x1, y1 = points[edge["from"]]
        x2, y2 = points[edge["to"]]
        if x1 < x2:
            x1 += 158
        elif x1 > x2:
            x2 += 158
        lines.append(f'<line x1="{x1}" y1="{y1 + 17}" x2="{x2}" y2="{y2 + 17}" marker-end="url(#{arrow})"/>')
    boxes = []
    for node in nodes:
        x, y = points[node["id"]]
        label = node["label"]
        short = label if len(label) <= 19 else label[:18] + "…"
        boxes.append(f'<rect x="{x}" y="{y}" width="158" height="34" rx="4"/>'
                     f'<text x="{x + 6}" y="{y + 22}" font-size="12">{_content(short)}</text>')
    return (f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Topology; full labels are in the tables">'
            f'<defs><marker id="{arrow}" markerWidth="8" markerHeight="8" refX="8" refY="4" orient="auto">'
            '<polygon points="0,0 8,4 0,8"/></marker></defs>'
            + "".join(lines) + "".join(boxes) + "</svg>")


def _topology(key: str, graph: dict[str, Any]) -> str:
    return (
        _diagram(key, graph)
        + '<details><summary>Nodes</summary>'
        + _table(("ID", "Kind", "Label"), ((node["id"], node["kind"], node["label"]) for node in graph["nodes"]))
        + '</details><details open><summary>Relationships</summary>'
        + _table(("From", "Relation", "To"), ((edge["from"], edge["relation"], edge["to"]) for edge in graph["edges"]))
        + "</details>"
    )


def _view_content(view: View, data: dict[str, Any]) -> str:
    if view.key == "feed":
        events = _table(
            ("Time", "Time basis", "Activity", "Source", "Lane", "Item", "Recipient"),
            ((event["at"], event["time_basis"], event["kind"], event["source"],
              event.get("lane"), event.get("item"), event.get("to")) for event in data["events"]),
        )
        sources = _table(
            ("Source", "Path", "Status", "Records", "Invalid", "SHA-256"),
            ((source["id"], source["path"], source["status"], source["records"], source["invalid_records"],
              source["sha256"]) for source in data["sources"]),
        )
        limitations = "".join(f"<li>{_content(item)}</li>" for item in data["limitations"])
        return events + "<h3>Source coverage</h3>" + sources + f"<h3>Limitations</h3><ul>{limitations}</ul>"
    if view.key == "workgraph":
        waves = _table(("Wave", "Work IDs"), ((wave["index"], wave["work"]) for wave in data["waves"]))
        return waves + _topology(view.key, workgraph_graph(data))
    if view.key == "lanes":
        lanes = _table(("Lane", "Liveness"), data["liveness"].items())
        collisions = _table(("Lanes", "Overlapping paths"),
                            ((item["lanes"], item["territory"]) for item in data["collisions"]))
        return lanes + "<h3>Collisions</h3>" + collisions + _topology(view.key, data)
    if view.key == "monitor":
        return _table(
            ("Monitor", "Target", "Status", "Last signal", "Consumer gate"),
            ((item["id"], item["target"], item["status"], item["last_signal"], item["consumer_gate"])
             for item in data["monitors"]),
        )
    if view.key == "context":
        return _table(
            ("Budget", "Used", "Remaining"), [(data["budget"], data["used"], data["remaining"])]
        ) + _table(("Source", "Status"), ((item["source"], item["status"]) for item in data["provenance"]))
    if view.key in {"deliberation", "attestation"}:
        return _table(("Field", "Value"), sorted(data.items()))
    return _topology(view.key, data)


def _render_view(view: View) -> str:
    section = (f'<section id="{view.key}"><h2>{_content(view.title)}</h2>'
               f'<p>Reproduce: <code>{_content(shlex.join(("hpp", *view.command)))}</code></p>')
    if view.data is None:
        return section + f"<p>Unavailable: {_content(view.missing)}</p></section>"
    canonical = json.dumps(view.data, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    section += f"<p>Projection SHA-256: <code>{_sha(canonical.encode('ascii'))}</code></p>"
    if view.sources:
        section += _table(("Input", "SHA-256 of file bytes"), view.sources)
    return section + _view_content(view, view.data) + "</section>"


def render_atlas(
    target: Path, *, manifest_file: str | None = None, work_spec: str | None = None, lanes_file: str | None = None,
    agent_events: str | None = None, monitors_file: str | None = None, now: int | None = None,
    context_file: str | None = None, budget: int | None = None, mailbox: str | None = None,
    local_offset: str | None = None, deliberation: str | None = None, attestation: str | None = None,
) -> str:
    """Read the selected project sources and return one deterministic, inert HTML document."""
    target = target.resolve()
    if not target.is_dir():
        raise ValueError("atlas --target must be a directory")
    if monitors_file is not None and now is None:
        raise ValueError("atlas --monitors requires --now for a deterministic projection")
    if context_file is not None and budget is None:
        raise ValueError("atlas --context requires --budget")
    if manifest_file is None:
        manifest_path = find_manifest(start=target)
        manifest_label = "hpp.manifest.json (discovered by hpp)"
        manifest_args = ()
    else:
        manifest_path, manifest_label = _project_path(target, manifest_file)
        manifest_args = ("--manifest", manifest_label)
    manifest, digest = _json_source(manifest_path, dict)
    validate_manifest(manifest)
    manifest_sources = ((manifest_label, digest),)
    views = [
        View(view, title, ("graph", "--view", view, *manifest_args), build_graph(manifest, view), manifest_sources)
        for view, title in (
            ("capability", "Capabilities"), ("operational", "Operational loop"), ("evidence", "Evidence chain"),
        )
    ]

    events, event_args, event_sources = None, (), ()
    if agent_events is not None:
        path, label = _project_path(target, agent_events)
        events, digest = _json_source(path, list)
        event_args, event_sources = ("--events", label), ((label, digest),)
    views.append(View("agents", "Agent roles", ("map", "agent", *manifest_args, *event_args),
                      build_agent_map(manifest, events), (*manifest_sources, *event_sources)))

    feed_args = ("map", "feed", "--target", ".")
    if mailbox is not None:
        _path, mailbox = _project_path(target, mailbox)
        feed_args += ("--mailbox", mailbox)
    if local_offset is not None:
        feed_args += (f"--local-offset={local_offset}",)
    views.append(View("feed", "Activity feed", feed_args, build_feed_map(target, mailbox, local_offset)))

    entries = (
        ("workgraph", "WorkGraph waves", "--spec", work_spec, dict, ("work", "plan"), (), compile_workgraph),
        ("lanes", "Lanes", "--lanes", lanes_file, list, ("map", "lane"),
         ("--now", str(now)) if now is not None else (), lambda records: build_lane_map(records, now=now)),
        ("monitor", "Monitor signals", "--monitors", monitors_file, list, ("map", "monitor"),
         ("--now", str(now) if now is not None else "<unix-seconds>"), lambda records: build_monitor_map(records, now)),
        ("context", "Context budget", "--context", context_file, list, ("map", "context"),
         ("--budget", str(budget) if budget is not None else "<tokens>"), lambda records: build_context_map(records, budget)),
        ("deliberation", "House Session verification", "--deliberation", deliberation, dict,
         ("deliberate", "verify"), (), verify_record),
    )
    for key, title, option, value, kind, prefix, flags, builder in entries:
        if value is None:
            views.append(View(key, title, (*prefix, "<file>", *flags), None, missing=f"supply {option}"))
            continue
        path, label = _project_path(target, value)
        raw, digest = _json_source(path, kind)
        views.append(View(key, title, (*prefix, label, *flags), builder(raw), ((label, digest),)))

    if attestation is None:
        views.append(View("attestation", "Attestation verification", ("attest", "verify", "<file>", "--repo", "."), None,
                          missing="supply --attestation"))
    else:
        path, label = _project_path(target, attestation)
        record, digest = _json_source(path, dict)
        # The verifier looks for the Git root and follows the spec named by the record. Keep the
        # atlas bounded to the selected root even when a JSON file supplies a different path.
        if attestation_repo_root(target) != target:
            raise ValueError("atlas --attestation requires --target to be the Git repository root")
        spec = record.get("spec")
        if isinstance(spec, dict) and spec.get("path"):
            _project_path(target, str(spec["path"]))
        verification = verify_attestation(path, target)
        if _json_source(path, dict)[1] != digest:
            raise ValueError("attestation changed while generating the atlas")
        views.append(View("attestation", "Attestation verification", ("attest", "verify", label, "--repo", "."),
                          verification, ((label, digest),)))

    nav = "".join(f'<li><a href="#{view.key}">{_content(view.title)}</a></li>' for view in views)
    body = "".join(_render_view(view) for view in views)
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; '
        'base-uri \'none\'; form-action \'none\'">\n'
        f"<title>HPP project atlas</title><style>{STYLE}</style></head><body>\n"
        '<header><h1>HPP project atlas</h1><p>Local projections. Commands use POSIX shell quoting and run from '
        'the target directory. Projection hashes use SHA-256 over compact JSON with sorted keys and ASCII escapes.</p>'
        f'</header><nav aria-label="Atlas views"><ul>{nav}</ul></nav><main>{body}</main></body></html>\n'
    )
