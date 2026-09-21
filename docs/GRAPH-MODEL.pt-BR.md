[English](GRAPH-MODEL.md) · [Português](GRAPH-MODEL.pt-BR.md)

# Graph Model

Os grafos do HPP são projeções locais e determinísticas. Cada nó e aresta precisa apontar para uma
fonte e mudar uma decisão operacional.

## Tipos

| Visão | Nós | Arestas úteis |
|---|---|---|
| Capability Map | módulo, capability, host, bundle | provides, requires, supports, contains |
| Agent Map | papel, agente, permissão, gate | can-do, checks, approves, hands-off |
| Lane Map | sessão, lane, território, item | owns, claims, overlaps, hands-off |
| WorkGraph | spec, work unit, wave, acceptance | decomposes-to, depends-on, scheduled-in |
| Execution Graph | evento, ação, ferramenta, artefato | follows, produced, changed |
| Evidence Graph | critério, evidência, checker, veredito | supports, refutes, verified-by |
| Context/Knowledge Map | fonte, hash, prioridade, contexto compilado | included, omitted |
| Code Map | módulo, componente declarado | declares |
| Monitor Map | probe, target, signal, consumer | observes, emits, stale-after, gates |
| Memory Map | falha, família, gotcha, tarefa | classified-as, recurred, applies-to |

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

Uma lane viva combina identidade de sessão, papel, modelo declarado, branch, heartbeat e
território. Colisão só é afirmada quando os padrões se sobrepõem e as duas lanes estão vivas pela
mesma régua de tempo. Lane morta não produz falso bloqueio; red zone continua separada de
território exclusivo.

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

`online` e `fresh` são dimensões separadas. O mapa pode indicar serviço online com dado stale.
Execução contínua é opt-in do host; a projeção funciona também com probes disparadas manualmente.

## Conhecimento e código, sem overclaim

O Context/Knowledge Map é um grafo simplificado de proveniência do contexto compilado: mostra quais
fontes entraram, quais ficaram fora pelo orçamento e seus hashes. Não é RAG nem knowledge graph
persistente. O Code Map raiz é inventário de módulos/componentes declarados, não um grafo AST de
símbolos ou chamadas. Analisadores externos podem alimentar novas projeções sem virar dependência
obrigatória do harness.

## Export

As visões exportam JSON estável para máquinas e Mermaid para leitura. Ordem de nós e arestas é
canônica; timestamp só aparece quando pertence à fonte. O mesmo input produz o mesmo grafo.
