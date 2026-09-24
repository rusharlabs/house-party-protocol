[English](GRAPH-MODEL.md) · [Português](GRAPH-MODEL.pt-BR.md)

# Graph Model

Os grafos do HPP são projeções locais e determinísticas. Cada nó e aresta precisa apontar para uma
fonte e mudar uma decisão operacional.

## Tipos

Cada linha nomeia o comando que a produz. Os tipos de nó e as relações de aresta são os valores
literais de `kind` e `relation` na saída (`hpp/graph.py`, `hpp/maps.py`, `hpp/workgraph.py`).

| Visão | Comando | Nós (`kind`) | Arestas (`relation`) |
|---|---|---|---|
| Capability | `hpp graph --view capability` | host, module, capability, bundle | `provides` (module → capability) · `supports:<coverage>` (module → host) · `requires`, `integrates-with` (module → module) · `includes` (bundle → module) |
| Operational | `hpp graph --view operational` | state, gate — a partir de `loop.transitions` do manifesto | `<event>`, p. ex. `work_started` (state → gate) · `permits` (gate → state) |
| Agent roles | `hpp graph --view agent` | três nós de papel fixos: `role:maker`, `role:checker`, `role:human-gate` | `submits` (maker → checker) · `reports` (checker → human-gate) · `approves-or-returns` (human-gate → maker) |
| Evidence | `hpp graph --view evidence` | um nó fixo de cada: criterion, evidence, verdict | `requires` (criterion → evidence) · `supports` (evidence → verdict) |
| Code Map | `hpp graph --view code` | module, component | `declares` (module → component) |
| Agent Map | `hpp map agent [--events <arquivo>]` | role (os `roles` do manifesto), module, capability, execution (um por evento registrado) | `provides` (module → capability) · `then` (execution → execution seguinte) |
| Lane Map | `hpp map lane <arquivo> [--now <ts>]` | lane, territory | `owns:<liveness>` (lane → territory). Colisões e liveness são campos separados, não arestas |
| Context/Knowledge Map | `hpp map context <arquivo> --budget <n>` | context (o contexto compilado), source | `included` ou `omitted` (source → context). Hash, prioridade e contagem de caracteres ficam no campo `provenance` |
| Monitor Map | `hpp map monitor <arquivo> --now <ts>` | nenhum: uma lista plana `monitors`, um registro por probe com os campos listados em Monitor Map abaixo | nenhuma |
| WorkGraph | `hpp work plan <spec>` | os itens da lista `work` | `depends-on` (dependência → dependente). Waves, critérios e contagem por tier são campos |
| Execution | nenhum | Nenhuma projeção dedicada, embora a lista `maps` do manifesto nomeie `execution`. O mais próximo são os nós execution ligados por `then` em `hpp map agent --events` | — |
| Memory | nenhum em `hpp/` | O módulo gotcha-memory registra falhas classificadas em `failures.jsonl` e deriva gotchas da recorrência por chave de tarefa e família de erro; ele não exporta grafo | — |

## Envelope de evento

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

`seq` e `id` são acrescentados pelo event log. O payload continua explícito: o runtime não
inventa identidade, modelo, causalidade ou evidência.

## Lane Map

`hpp map lane` lê cinco campos por lane: `id`, `territory` (lista não vazia de caminhos),
`exclusive` (padrão `true`), `status` (padrão `declared`) e `heartbeat_at` (segundos Unix).
Outras chaves, como `role`, `model` e `branch` que o registro do lane-kit grava, são aceitas e
ignoradas: não aparecem na saída.

A liveness vem de um único `--now` para todas as lanes. `status` igual a `closed`, `dead` ou
`inactive` vale `dead`. Sem `--now`, a liveness é o `status` declarado. Com `--now`, lane sem
`heartbeat_at` fica `unknown`, e a idade do heartbeat dá `alive` (até `--suspect-after`, padrão
300), `suspect` (até `--dead-after`, padrão 900) ou `dead`. `heartbeat_at` posterior a `--now` é
erro, não lane viva.

Colisão é reportada quando duas lanes exclusivas têm caminhos iguais ou um é prefixo de diretório
do outro (`src` e `src/api`, não `src` e `srcx`). Ela só é descartada quando uma das lanes está
`dead`; lanes `suspect`, `unknown` e `declared` continuam colidindo. O mapa reporta colisões e
não bloqueia nada.

Red zone não é conceito de `hpp/maps.py`. Ela pertence ao hook do lane-kit
`lane_territory_guard.py`, que avisa (nunca bloqueia) em edições de `.claude/settings*.json`,
`**/MEMORY.md` e de qualquer `red_zones` listada em `.claude/lanes/lanes.yaml`.

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

O plano válido gera `wave 1 = [A, B]` e `wave 2 = [C]`. Um ciclo é erro, não uma wave vazia.

## Monitor Map

Monitor é um contrato de observação:

```text
id · target · type · cadence · freshness · last_signal · status · severity · cost · consumer_gate
```

Cada monitor recebe um único `status`: `healthy` (sinal com no máximo `freshness` segundos),
`stale` (mais antigo), `skew` (datado mais de `--skew-tolerance` segundos depois de `--now`, padrão
5) ou `unknown` (sem `last_signal`). `cadence` é validada, mas não entra no status. Não existe
campo separado de online. Um serviço que responde com dado antigo é expresso como duas probes com
dois targets, como faz o benchmark: uma probe `command` no serviço fica `healthy` enquanto uma
probe `timestamp` no dado fica `stale`.
Execução contínua é opt-in do host; a projeção funciona também com probes disparadas manualmente.

## Conhecimento e código, sem overclaim

O Context/Knowledge Map é um grafo simplificado de proveniência do contexto compilado: mostra quais
fontes entraram, quais ficaram fora pelo orçamento e seus hashes. Não é RAG nem knowledge graph
persistente. O Code Map raiz é inventário de módulos/componentes declarados, não um grafo AST de
símbolos ou chamadas. Analisadores externos podem alimentar novas projeções sem virar dependência
obrigatória do harness.

## Export

`hpp graph` exporta JSON (padrão) ou Mermaid (`--format mermaid`); `hpp map` e `hpp work`
exportam só JSON. Ordem de nós e arestas é canônica; timestamp só aparece quando pertence à
fonte. O mesmo input produz o mesmo grafo.
