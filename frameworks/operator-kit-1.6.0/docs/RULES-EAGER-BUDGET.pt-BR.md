[English](RULES-EAGER-BUDGET.md) · [Português](RULES-EAGER-BUDGET.pt-BR.md)

# Camada de regras: o que ela custa no boot

Todo arquivo que você copia para `.claude/rules/` é carregado em **toda sessão daquele
projeto, antes do seu primeiro prompt** — a menos que ele declare `paths:`. Isso faz da camada
de regras uma conta recorrente de contexto, não um custo único de instalação. Esta página
publica a conta.

## O número

Medido em 2026-09-22, antes de qualquer regra declarar `paths:`:

```
rules 13 · bytes 165.955 · tokens ~41.488 · with-paths 0
```

Depois do escopo, sobre as mesmas 13 regras (mais o conteúdo acrescentado na mesma release):

| | regras | bytes | ~tokens | quando carrega |
|---|---:|---:|---:|---|
| **EAGER** | 7 | **56.770** | **~14.192** | toda sessão |
| com escopo de path | 6 | 116.878 | ~29.219 | só ao tocar o caminho que casa |
| total em disco | 13 | 172.632 | ~43.158 | — |

Re-medido em 2026-09-24 (operator-kit 1.6.0): EAGER 7 regras · **58.038 B** (~14.509 tokens) ·
com escopo de path 123.347 B · total em disco 181.385 B. A folga sob o teto de 59.000 B é de
962 B, ainda menor que a menor regra com escopo (`loop-passk`, 5.179 B).

**O custo por sessão caiu 65,8 %** (165.955 → 56.770 B; eram 55.754 B antes de duas regras eager receberem doutrina nova no mesmo dia). A camada em disco *cresceu* 6.677 B
na mesma release — a camada de julgamento e a doutrina de isolamento do checker são texto
novo. São dois números com duas unidades diferentes, e só o primeiro é cobrado de você toda
vez que abre o projeto.

> Tokens são bytes ÷ 4, a aproximação usual para inglês. É estimativa; a contagem de bytes é a
> medição, e o gate é cobrado em bytes.

## Por que cada regra está onde está

A fronteira: uma regra fica eager quando é **válida em qualquer contexto e cara de não
disparar**. Tudo cujo valor é específico de caminho declara `paths:`.

### Eager — 7 regras

| regra | bytes | por que não pode esperar um caminho |
|---|---:|---|
| `epistemic-standards` | 15.070 | Apresentar hipótese como fato é possível em qualquer resposta, inclusive numa que não toca arquivo nenhum. |
| `loop-maker-checker` | 13.782 | Guarda push / merge / fechamento de goal — momentos alcançáveis de qualquer lugar e irreversíveis depois de passados. |
| `gateguard` | 9.934 | Dispara antes do *primeiro* edit e antes de qualquer comando destrutivo; regra que chega depois do primeiro edit chega tarde. |
| `loop-cost-budget` | 8.657 | Um loop pode ser armado de qualquer diretório, e um sem orçamento gasta até alguém perceber. |
| `stale-replay-guard` | 6.034 | Dispara em `/resume` e em restauração de contexto — eventos sem caminho de arquivo onde pendurar um glob. |
| `learned-corrections` | 4.211 | "Medir ao vivo antes de citar um número" vale para todo relato; 4 KB é seguro barato. |
| `no-secrets-in-memory` | 748 | 748 bytes, e o dano que ela evita (credencial commitada num arquivo de memória) não se desfaz. |

### Com escopo de path — 6 regras

| regra | bytes | escopo | por que o caminho basta |
|---|---:|---|---|
| `agent-integrity` | 34.401 | agents, knowledge, `AGENT.md`, `SOUL.md`, `MEMORY.md`, `DNA-CONFIG.yaml` | Rastreabilidade do conteúdo de agente: templates, formatos de citação, matriz de propagação. Não tem efeito numa sessão que nunca abre um arquivo de agente. |
| `agent-cognition` | 34.120 | agents, knowledge, `AGENT.md`, `SOUL.md` | Como um agente raciocina — lida ao escrever ou editar um, não ao consertar CSS. |
| `loop-patterns-catalog` | 20.325 | caminhos de loop / cron / squad, `.claude/commands/**` | Catálogo de design ("qual forma?"), consultado uma vez por loop, não uma vez por sessão. |
| `loop-operator` | 19.190 | caminhos de loop / cron / squad, `.claude/commands/**` | Pre-flight e stop-conditions em detalhe; a metade sempre-ligada da segurança de loop é a `loop-cost-budget`, que ficou eager. |
| `partial-autonomy-slider` | 10.056 | agents, `operator-profile.yaml` | Governa um valor que mora nesses arquivos; lê-la em outro lugar não muda nada. |
| `loop-passk` | 5.212 | evals, caminhos de loop | pass@k / pass^k vale quando você roda um eval ou promove um agente. |

⚠️ **Escopar não deixa a regra órfã.** As skills do kit citam regras pelo nome
(`> **Related doctrine:** rules/<name>.md`), e ler uma explicitamente sempre funciona. O
`paths:` decide o que é *pré-carregado*, nunca o que está *disponível*.

## Ajustando o escopo ao seu repositório

Os globs foram escritos para layouts comuns (`agents/`, `.claude/agents/`, `knowledge/`,
qualquer coisa com `loop` no nome). Se o seu projeto guarda agentes em `src/ai/personas/`,
acrescente esse glob — uma regra cujos globs nunca casam é uma regra que nunca carrega, o que
é pior que eager:

```yaml
---
paths:
  - "agents/**/*"
  - "src/ai/personas/**/*"
---
```

Para tornar eager de novo uma regra escopada, apague o bloco de front matter. Para escopar uma
eager, acrescente `paths:` — e, nos dois casos, atualize o `EAGER_BY_DESIGN` do gate abaixo,
porque senão ele reprova. Reprovar é justamente o ponto.

## A catraca

Um teste-catraca no pipeline de release do kit guarda o número:

```
EAGER_BUDGET_BYTES = 59000
```

Quatro gates e cinco controles:

- **estrutural** — o conjunto de regras sem `paths:` tem de ser igual ao conjunto eager
  declarado. Pega uma regra que perdeu o front matter *e* uma regra nova que nasceu eager por
  omissão.
- **orçamento** — os bytes eager não podem passar de 59.000. A folga acima de 58.038 (962 B) é
  menor que a menor regra escopada (5.179 B), então nenhuma regra volta ao conjunto eager em
  silêncio, e um gate à parte prende esse invariante para que subir o teto não possa quebrá-lo.
  Subiu de 57.000 em 2026-09-22: com 230 B de folga, a próxima linha honesta de doutrina
  reprovaria o gate — e gate que dispara em trabalho correto tem o número aumentado às pressas
  por quem está travado, que é como uma catraca vira carimbo.
- **sem `paths:` vazio** — uma chave `paths:` sem glob nem escopa nem carrega.
- **doc ↔ gate** — esta página tem de publicar os mesmos números que o gate cobra, para que os
  dois não divirjam.
