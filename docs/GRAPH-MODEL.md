[English](GRAPH-MODEL.md) · [Português](GRAPH-MODEL.pt-BR.md)

# Graph Model

HPP graphs are local, deterministic projections. Every node and edge has to point at a source and
change an operational decision.

## Types

Each row names the command that produces it. Node kinds and edge relations are the literal
`kind` and `relation` values in the output (`hpp/graph.py`, `hpp/maps.py`, `hpp/workgraph.py`).

| View | Command | Nodes (`kind`) | Edges (`relation`) |
|---|---|---|---|
| Capability | `hpp graph --view capability` | host, module, capability, bundle | `provides` (module → capability) · `supports:<coverage>` (module → host) · `requires`, `integrates-with` (module → module) · `includes` (bundle → module) |
| Operational | `hpp graph --view operational` | state, gate — from the manifest's `loop.transitions` | `<event>`, e.g. `work_started` (state → gate) · `permits` (gate → state) |
| Agent roles | `hpp graph --view agent` | three fixed role nodes: `role:maker`, `role:checker`, `role:human-gate` | `submits` (maker → checker) · `reports` (checker → human-gate) · `approves-or-returns` (human-gate → maker) |
| Evidence | `hpp graph --view evidence` | one fixed node each: criterion, evidence, verdict | `requires` (criterion → evidence) · `supports` (evidence → verdict) |
| Code Map | `hpp graph --view code` | module, component | `declares` (module → component) |
| Agent Map | `hpp map agent [--events <file>]` | role (the manifest's `roles`), module, capability, execution (one per recorded event) | `provides` (module → capability) · `then` (execution → next execution) |
| Lane Map | `hpp map lane <file> [--now <ts>]` | lane, territory | `owns:<liveness>` (lane → territory). Collisions and liveness are separate fields, not edges |
| Context/Knowledge Map | `hpp map context <file> --budget <n>` | context (the compiled context), source | `included` or `omitted` (source → context). Hash, priority and character count are in the `provenance` field |
| Monitor Map | `hpp map monitor <file> --now <ts>` | none: a flat `monitors` list, one record per probe with the fields listed under Monitor Map below | none |
| WorkGraph | `hpp work plan <spec>` | the items of the `work` list | `depends-on` (dependency → dependent). Waves, criteria and tier counts are fields |
| Execution | none | No dedicated projection, although the manifest's `maps` list names `execution`. The closest is the execution nodes joined by `then` in `hpp map agent --events` | — |
| Memory | none in `hpp/` | The gotcha-memory module records classified failures in `failures.jsonl` and derives gotchas from recurrence per task key and error family; it exports no graph | — |

## Event envelope

```json
{
  "seq": 2,
  "id": "event:2",
  "type": "evidence_recorded",
  "data": {
    "work": "ITEM-1",
    "actor": "checker-a",
    "lane": "lane-a",
    "evidence_refs": ["artifacts/test.txt"],
    "caused_by": ["event:1"]
  }
}
```

`seq` and `id` are added by the event log. The payload stays explicit: the runtime does not invent
identity, model, causality or evidence.

## Lane Map

`hpp map lane` reads five fields per lane: `id`, `territory` (a non-empty list of paths),
`exclusive` (default `true`), `status` (default `declared`) and `heartbeat_at` (Unix seconds).
Other keys, such as the `role`, `model` and `branch` that the lane-kit registry records, are
accepted and ignored: they do not appear in the output.

Liveness is derived from one `--now` for every lane. A `status` of `closed`, `dead` or `inactive`
is `dead`. Without `--now`, liveness is the declared `status`. With `--now`, a lane without
`heartbeat_at` is `unknown`, and the heartbeat age gives `alive` (up to `--suspect-after`, default
300), `suspect` (up to `--dead-after`, default 900) or `dead`. A `heartbeat_at` later than `--now`
is an error, not a live lane.

A collision is reported when two exclusive lanes hold paths that are equal or where one is a
directory prefix of the other (`src` and `src/api`, not `src` and `srcx`). It is skipped only
when either lane is `dead`; `suspect`, `unknown` and `declared` lanes still collide. The map
reports collisions and blocks nothing.

Red zones are not a concept of `hpp/maps.py`. They belong to the lane-kit hook
`lane_territory_guard.py`, which warns (never blocks) on edits to `.claude/settings*.json`,
`**/MEMORY.md` and any `red_zones` listed in `.claude/lanes/lanes.yaml`.

## WorkGraph

```json
{
  "work": [
    {"id": "A", "depends_on": [], "acceptance": ["test A"], "tier": "economy"},
    {"id": "B", "depends_on": [], "acceptance": ["test B"], "tier": "economy"},
    {"id": "C", "depends_on": ["A", "B"], "acceptance": ["test C"], "tier": "frontier"}
  ]
}
```

The valid plan yields `wave 1 = [A, B]` and `wave 2 = [C]`. A cycle is an error, not an empty
wave.

## Monitor Map

A monitor is an observation contract:

```text
id · target · type · cadence · freshness · last_signal · status · severity · cost · consumer_gate
```

Each monitor gets one `status`: `healthy` (the signal is at most `freshness` seconds old),
`stale` (older), `skew` (dated more than `--skew-tolerance` seconds after `--now`, default 5) or
`unknown` (no `last_signal`). `cadence` is validated but does not enter the status. There is no
separate online field. A service that answers while its data is old is expressed as two probes
with two targets, as the benchmark does: a `command` probe on the service reads `healthy` while a
`timestamp` probe on the data reads `stale`.
Continuous execution is opt-in for the host; the projection also works with manually fired probes.

## Knowledge and code, without overclaim

The Context/Knowledge Map is a simplified provenance graph of the compiled context: it shows which
sources went in, which stayed out because of the budget, and their hashes. It is not RAG and not a
persistent knowledge graph. The root Code Map is an inventory of declared modules/components, not
an AST graph of symbols or calls. External analysers can feed new projections without becoming a
mandatory dependency of the harness.

## Export

`hpp graph` exports JSON (default) or Mermaid (`--format mermaid`); `hpp map` and `hpp work`
export JSON only. Node and edge order is canonical; a timestamp only appears when it belongs to
the source. The same input produces the same graph.
