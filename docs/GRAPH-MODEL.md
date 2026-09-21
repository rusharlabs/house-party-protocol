[English](GRAPH-MODEL.md) · [Português](GRAPH-MODEL.pt-BR.md)

# Graph Model

HPP graphs are local, deterministic projections. Every node and edge has to point at a source and
change an operational decision.

## Types

| View | Nodes | Useful edges |
|---|---|---|
| Capability Map | module, capability, host, bundle | provides, requires, supports, contains |
| Agent Map | role, agent, permission, gate | can-do, checks, approves, hands-off |
| Lane Map | session, lane, territory, item | owns, claims, overlaps, hands-off |
| WorkGraph | spec, work unit, wave, acceptance | decomposes-to, depends-on, scheduled-in |
| Execution Graph | event, action, tool, artifact | follows, produced, changed |
| Evidence Graph | criterion, evidence, checker, verdict | supports, refutes, verified-by |
| Context/Knowledge Map | source, hash, priority, compiled context | included, omitted |
| Code Map | module, declared component | declares |
| Monitor Map | probe, target, signal, consumer | observes, emits, stale-after, gates |
| Memory Map | failure, family, gotcha, task | classified-as, recurred, applies-to |

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

A live lane combines session identity, role, declared model, branch, heartbeat and territory. A
collision is only asserted when the patterns overlap and both lanes are alive by the same time
ruler. A dead lane produces no false block; a red zone stays separate from exclusive territory.

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

`online` and `fresh` are separate dimensions. The map can show a service online with stale data.
Continuous execution is opt-in for the host; the projection also works with manually fired probes.

## Knowledge and code, without overclaim

The Context/Knowledge Map is a simplified provenance graph of the compiled context: it shows which
sources went in, which stayed out because of the budget, and their hashes. It is not RAG and not a
persistent knowledge graph. The root Code Map is an inventory of declared modules/components, not
an AST graph of symbols or calls. External analysers can feed new projections without becoming a
mandatory dependency of the harness.

## Export

The views export stable JSON for machines and Mermaid for reading. Node and edge order is
canonical; a timestamp only appears when it belongs to the source. The same input produces the
same graph.
