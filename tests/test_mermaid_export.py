"""Mermaid export for the maps and the WorkGraph, and the bytes the command line writes to stdout.

Measured before this file existed, on Windows: `hpp graph --view agent --format mermaid` wrote its
7 lines with 7 CR bytes, so the same output hashed differently on Windows and on every other
system; `hpp map lane` with a lane id outside cp1252, piped on a cp1252 locale, exited 2 with
`'charmap' codec can't encode character`; and `hpp map` and `hpp work` had no `--format`.

The expected diagrams below are written by hand from the projection rules (nodes sorted by id and
numbered in that order, edges sorted by source, target and relation), and each one is pinned by
its sha256 as well, so a diagram that moves has to be moved here on purpose.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from hpp import maps, workgraph
from hpp.graph import build_graph, to_mermaid
from hpp.maps import build_agent_map, build_context_map, build_lane_map, build_monitor_map
from hpp.workgraph import compile_workgraph

PRODUCT_ROOT = Path(__file__).resolve().parent.parent

LANES = [
    {"id": "lane-b", "territory": ["src/api"]},
    {"id": "lane-a", "territory": ["src", "docs"]},
    {"id": "lane-c", "territory": ["tests"], "status": "closed"},
]
MONITORS = [
    {"id": "api-up", "target": "api", "type": "command", "cadence": 60, "freshness": 120, "last_signal": 1000,
     "severity": "high", "cost": "low", "consumer_gate": "deploy"},
    {"id": "data-fresh", "target": "warehouse", "type": "timestamp", "cadence": 300, "freshness": 600,
     "last_signal": 100, "severity": "medium", "cost": "low", "consumer_gate": "deploy"},
]
CONTEXT = [
    {"source": "b.md", "priority": 1, "content": "bbbb"},
    {"source": "a.md", "priority": 2, "content": "aaaaaa"},
    {"source": "c.md", "priority": 1, "content": "cccccccccc"},
]
MANIFEST = {"roles": ["maker", "checker"],
            "modules": [{"id": "m2", "capabilities": ["y"]}, {"id": "m1", "capabilities": ["x", "y"]}]}
EVENTS = [{"type": "start"}, {"type": "done"}]
SPEC = {"work": [
    {"id": "C", "depends_on": ["A", "B"], "acceptance": ["test C"], "tier": "frontier"},
    {"id": "A", "depends_on": [], "acceptance": ["test A"], "tier": "economy"},
    {"id": "B", "depends_on": [], "acceptance": ["test B"], "tier": "economy"},
]}

LANE_MERMAID = (
    "flowchart LR\n"
    '  n0["lane-a"]\n'
    '  n1["lane-b"]\n'
    '  n2["lane-c"]\n'
    '  n3["docs"]\n'
    '  n4["src"]\n'
    '  n5["src/api"]\n'
    '  n6["tests"]\n'
    "  n0 -->|collides:src, src/api| n1\n"
    "  n0 -->|owns:declared| n3\n"
    "  n0 -->|owns:declared| n4\n"
    "  n1 -->|owns:declared| n5\n"
    "  n2 -->|owns:dead| n6\n"
)
MONITOR_MERMAID = (
    "flowchart LR\n"
    '  n0["deploy"]\n'
    '  n1["api-up · healthy"]\n'
    '  n2["data-fresh · stale"]\n'
    '  n3["api"]\n'
    '  n4["warehouse"]\n'
    "  n1 -->|gates| n0\n"
    "  n1 -->|observes| n3\n"
    "  n2 -->|gates| n0\n"
    "  n2 -->|observes| n4\n"
)
CONTEXT_MERMAID = (
    "flowchart LR\n"
    '  n0["compiled context"]\n'
    '  n1["a.md"]\n'
    '  n2["b.md"]\n'
    '  n3["c.md"]\n'
    "  n1 -->|included| n0\n"
    "  n2 -->|included| n0\n"
    "  n3 -->|omitted| n0\n"
)
AGENT_MERMAID = (
    "flowchart LR\n"
    '  n0["x"]\n'
    '  n1["y"]\n'
    '  n2["start"]\n'
    '  n3["done"]\n'
    '  n4["m1"]\n'
    '  n5["m2"]\n'
    '  n6["checker"]\n'
    '  n7["maker"]\n'
    "  n2 -->|then| n3\n"
    "  n4 -->|provides| n0\n"
    "  n4 -->|provides| n1\n"
    "  n5 -->|provides| n1\n"
)
WORK_MERMAID = (
    "flowchart LR\n"
    '  subgraph c0["wave 1"]\n'
    '    n0["A · economy"]\n'
    '    n1["B · economy"]\n'
    "  end\n"
    '  subgraph c1["wave 2"]\n'
    '    n2["C · frontier"]\n'
    "  end\n"
    "  n0 -->|depends-on| n2\n"
    "  n1 -->|depends-on| n2\n"
)

# Pinned: sha256 of the UTF-8 bytes of each diagram above.
PINNED = {
    "lane": (LANE_MERMAID, "d1ff0988343f574435a29590cd147eedd00afc84a54a296aee9bfb53f104581c"),
    "monitor": (MONITOR_MERMAID, "e0857d7a36e79af368e63fd831b52c33bdb6b5947366f7c351cc33c2989294de"),
    "context": (CONTEXT_MERMAID, "92f259c4752a36b655eedd0b87794722593189ebf90579187db284c0dfd11975"),
    "agent": (AGENT_MERMAID, "37b32a333097db1868af504474a0d0024fced73da66783736db889fcfa6764c8"),
    "work": (WORK_MERMAID, "2e46600b47534b4444fbdd0bed5379c4f8e331f8b21c3f774e9f4876b7f64e52"),
}
# `hpp graph --view agent --format mermaid`: three fixed role nodes, measured before this file
# existed as the string `to_mermaid` returned (the stdout differed from it only by the CR bytes).
GRAPH_AGENT_SHA256 = "9ae1c00f64a95f8b2a02675e375c55251d76b05078d3049e90cde6a3d312f1c6"
GRAPH_EVIDENCE_SHA256 = "fe34db0c21887158665bfda7c03fd3f0cd762d64892cd3f0fddce3e95691fc29"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hpp(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
    merged = {**os.environ, "PYTHONPATH": str(PRODUCT_ROOT), "PYTHONDONTWRITEBYTECODE": "1", **(env or {})}
    return subprocess.run([sys.executable, "-m", "hpp", *args], cwd=PRODUCT_ROOT, env=merged,
                          capture_output=True, timeout=120)


def _write(path: Path, value: object) -> str:
    path.write_text(json.dumps(value), encoding="utf-8")
    return str(path)


def _permuted(value: list[dict]) -> list[dict]:
    """The same records in reverse order, and every list inside them reversed too."""
    return [{key: list(reversed(item)) if isinstance(item, list) else item for key, item in record.items()}
            for record in reversed(value)]


# --------------------------------------------------------------------------- labels


def test_mermaid_labels_escape_the_characters_that_end_a_label():
    graph = {"nodes": [{"id": "x", "kind": "k", "label": 'a "b" | <c>\nd\r\ne'}],
             "edges": [{"from": "x", "to": "x", "relation": "r|s"}]}
    text = to_mermaid(graph)
    assert text == ('flowchart LR\n'
                    '  n0["a #quot;b#quot; #124; #lt;c#gt; d e"]\n'
                    '  n0 -->|r#124;s| n0\n')
    assert _sha(text.encode("utf-8")) == "076443c66ee9cf3a1d972b325a6b981ad91aad6f8b88ea9aeae0c15799b20880"


def test_CONTROLE_a_plain_label_is_written_unchanged():
    graph = {"nodes": [{"id": "x", "kind": "k", "label": "plain label: a/b-c"}],
             "edges": [{"from": "x", "to": "x", "relation": "owns:alive"}]}
    assert to_mermaid(graph) == 'flowchart LR\n  n0["plain label: a/b-c"]\n  n0 -->|owns:alive| n0\n'


def test_the_fixed_graph_views_keep_their_mermaid_bytes():
    manifest = {"protocol_version": "x"}
    assert _sha(to_mermaid(build_graph(manifest, "agent")).encode("utf-8")) == GRAPH_AGENT_SHA256
    assert _sha(to_mermaid(build_graph(manifest, "evidence")).encode("utf-8")) == GRAPH_EVIDENCE_SHA256


def test_a_node_in_two_clusters_or_a_cluster_of_an_unknown_node_is_refused():
    graph = {"nodes": [{"id": "a", "kind": "k", "label": "a"}], "edges": []}
    with pytest.raises(ValueError, match="more than one cluster"):
        to_mermaid(graph, [{"label": "one", "nodes": ["a"]}, {"label": "two", "nodes": ["a"]}])
    with pytest.raises(ValueError, match="unknown node"):
        to_mermaid(graph, [{"label": "one", "nodes": ["ghost"]}])


# --------------------------------------------------------------------------- each diagram


@pytest.mark.parametrize("name", sorted(PINNED))
def test_every_expected_diagram_matches_its_pin(name):
    text, pinned = PINNED[name]
    assert _sha(text.encode("utf-8")) == pinned


def _lane(lanes):
    return to_mermaid(maps.map_graph(build_lane_map(lanes)))


def _monitor(monitors):
    return to_mermaid(maps.map_graph(build_monitor_map(monitors, 1050)))


def _context(inputs):
    return to_mermaid(maps.map_graph(build_context_map(inputs, 12)))


def _agent(manifest):
    return to_mermaid(maps.map_graph(build_agent_map(manifest, EVENTS)))


def _work(spec):
    graph = workgraph.workgraph_graph(compile_workgraph(spec))
    return to_mermaid(graph, graph["clusters"])


@pytest.mark.parametrize("name, render, source, permuted", [
    ("lane", _lane, LANES, _permuted(LANES)),
    ("monitor", _monitor, MONITORS, _permuted(MONITORS)),
    ("context", _context, CONTEXT, _permuted(CONTEXT)),
    ("agent", _agent, MANIFEST, {"roles": ["checker", "maker"], "modules": _permuted(MANIFEST["modules"])}),
    ("work", _work, SPEC, {"work": _permuted(SPEC["work"])}),
])
def test_each_diagram_is_the_pinned_text_and_does_not_depend_on_input_order(name, render, source, permuted):
    expected, pinned = PINNED[name]
    first = render(source)
    assert first == expected
    assert render(source) == first
    assert render(permuted) == first
    assert _sha(first.encode("utf-8")) == pinned


def test_CONTROLE_lane_collisions_become_edges_only_in_the_diagram():
    projection = build_lane_map(LANES)
    assert projection["collisions"] == [{"lanes": ["lane-a", "lane-b"], "territory": ["src", "src/api"]}]
    assert not any(edge["relation"].startswith("collides:") for edge in projection["edges"])
    assert any(edge["relation"] == "collides:src, src/api" for edge in maps.map_graph(projection)["edges"])


def test_CONTROLE_a_dead_lane_collides_with_nothing_in_the_diagram_either():
    alive = [{"id": "one", "territory": ["src"]}, {"id": "two", "territory": ["src"], "status": "closed"}]
    assert "collides" not in _lane(alive)


# --------------------------------------------------------------------------- the command line


def test_graph_mermaid_on_stdout_is_utf8_with_lf_and_the_pinned_hash():
    result = _hpp("graph", "--view", "agent", "--format", "mermaid")
    assert result.returncode == 0, result.stderr
    assert b"\r" not in result.stdout
    assert _sha(result.stdout) == GRAPH_AGENT_SHA256


@pytest.mark.parametrize("args, name, source, permuted", [
    (["map", "lane"], "lane", LANES, _permuted(LANES)),
    (["map", "monitor", "--now", "1050"], "monitor", MONITORS, _permuted(MONITORS)),
    (["map", "context", "--budget", "12"], "context", CONTEXT, _permuted(CONTEXT)),
    (["work", "plan"], "work", SPEC, {"work": _permuted(SPEC["work"])}),
    (["work", "waves"], "work", SPEC, {"work": _permuted(SPEC["work"])}),
])
def test_each_cli_diagram_is_byte_identical_across_runs_and_input_order(tmp_path, args, name, source, permuted):
    expected, pinned = PINNED[name]
    command, rest = args[:2], args[2:]
    straight = _write(tmp_path / "source.json", source)
    reordered = _write(tmp_path / "permuted.json", permuted)
    runs = [_hpp(*command, path, *rest, "--format", "mermaid") for path in (straight, straight, reordered)]
    for run in runs:
        assert run.returncode == 0, run.stderr
    assert runs[0].stdout == runs[1].stdout == runs[2].stdout == expected.encode("utf-8")
    assert _sha(runs[0].stdout) == pinned


def test_map_agent_mermaid_is_byte_identical_across_runs():
    first, second = _hpp("map", "agent", "--format", "mermaid"), _hpp("map", "agent", "--format", "mermaid")
    assert first.returncode == 0, first.stderr
    assert first.stdout.startswith(b"flowchart LR\n")
    assert b"\r" not in first.stdout
    assert first.stdout == second.stdout


def test_CONTROLE_work_coverage_has_no_format_option(tmp_path):
    result = _hpp("work", "coverage", _write(tmp_path / "spec.json", SPEC), "--tests", str(tmp_path),
                  "--format", "mermaid")
    assert result.returncode == 2
    assert b"unrecognized arguments: --format" in result.stderr


@pytest.mark.parametrize("fmt", ["json", "mermaid"])
def test_a_label_outside_cp1252_exits_0_and_arrives_as_utf8_on_a_cp1252_stream(tmp_path, fmt):
    lanes = _write(tmp_path / "lanes.json", [{"id": "lane-ğ", "territory": ["src"]}])
    result = _hpp("map", "lane", lanes, "--format", fmt, env={"PYTHONIOENCODING": "cp1252"})
    assert result.returncode == 0, result.stderr
    assert "lane-ğ" in result.stdout.decode("utf-8")
    assert b"\r" not in result.stdout


def test_every_command_writes_lf_line_endings(tmp_path):
    spec = _write(tmp_path / "spec.json", SPEC)
    lanes = _write(tmp_path / "lanes.json", LANES)
    context = _write(tmp_path / "context.json", CONTEXT)
    target = tmp_path / "project"
    target.mkdir()
    commands = [
        ["doctor"], ["doctor", "--json"], ["doctor", "--report"], ["doctor", "--matrix"],
        ["graph", "--view", "operational"], ["map", "lane", lanes], ["work", "plan", spec],
        ["context", "compile", context, "--budget", "12"],
        ["init", "--target", str(target), "--non-interactive", "--no-benchmark", "--json"],
    ]
    for args in commands:
        result = _hpp(*args)
        assert result.stdout, (args, result.stderr)
        assert b"\r" not in result.stdout, args


def test_CONTROLE_the_one_line_report_still_degrades_to_ascii_on_a_cp1252_stream():
    cp1252 = _hpp("doctor", env={"PYTHONIOENCODING": "cp1252"})
    utf8 = _hpp("doctor", env={"PYTHONIOENCODING": "utf-8"})
    assert cp1252.returncode == utf8.returncode == 0
    assert cp1252.stdout.isascii() and b" - modules=" in cp1252.stdout
    assert "· modules=".encode("utf-8") in utf8.stdout
    assert b"\r" not in cp1252.stdout and b"\r" not in utf8.stdout
