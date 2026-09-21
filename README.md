<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/hpp-banner-dark.svg">
    <img alt="House Party Protocol — operate coding agents under evidence, not trust" src="assets/hpp-banner-light.svg" width="100%">
  </picture>
</p>

<p align="center">
  <a href="LICENSE"><img alt="MIT" src="https://img.shields.io/badge/license-MIT-0C0F0E"></a>
  <a href="#quickstart"><img alt="Python 3.9+" src="https://img.shields.io/badge/Python-3.9%2B-5DE4C7"></a>
  <img alt="Claude Code and Codex CLI" src="https://img.shields.io/badge/hosts-Claude%20Code%20%7C%20Codex%20CLI-D7FF64">
</p>

# House Party Protocol

**Operate coding agents under evidence, not trust.**

House Party Protocol (HPP) é um **harness local-first, modular e cross-host para agentes de
código**. Ele envolve o trabalho de Claude Code e Codex CLI com gates executáveis, revisão
independente, lanes isoladas, continuidade entre sessões, loops governados, avaliação
determinística, monitores explícitos e uma cadeia de distribuição verificável.

O produto é o harness. O protocol define os invariantes. Os módulos implementam capacidades.
O marketplace é apenas um canal de distribuição para Claude Code; o instalador por cópia é o
canal equivalente para Codex CLI.

```text
intent/spec
    │
    ▼
WorkGraph ──waves──▶ lanes ──execute──▶ evidence
    │                   │                    │
    │                   └── Lane Map         ▼
    └── model policy                  independent checker
                                              │
                         monitors ──▶ gate ───┤
                                              ▼
                                      verified / blocked
                                              │
                                              ▼
                                      event log + resume
```

## O que o harness controla

| Camada | Capacidade executável |
|---|---|
| Integridade epistêmica | `done_gate`, evidência fresca, attestation vinculada aos bytes e controles negativos |
| Separação de papéis | maker diferente de checker; revisores sem ferramentas de escrita |
| Segurança operacional | classificação `ALLOW/WARN/BLOCK`, modos `audit` e `enforce`, snapshot e rollback |
| Coordenação | Lane Map com dono, território, heartbeat, colisão e handoff |
| Trabalho spec-driven | WorkGraph com dependências, rejeição de ciclos e waves topológicas |
| Loops | charter, budget, stop conditions, autoprompt e retomada sem aceitar promessa como prova |
| Avaliação | runner standalone de pass@k e pass^k; determinismo medido em `k` execuções |
| Observabilidade | Monitor Map; saúde de serviço separada do frescor e da saúde do dado |
| Memória operacional | falhas recorrentes classificadas, promovidas e reinjetadas com gate humano |
| Supply chain | build determinístico, lint de IP/PII, checksums e ZIP reaberto antes da release |

## Quickstart

Requer Python 3.9+ e não adiciona dependência de runtime.

```bash
git clone https://github.com/rushar-labs/house-party-protocol.git
cd house-party-protocol
python -m hpp doctor
python -m hpp graph --view operational --format mermaid
python -m hpp benchmark -k 3
```

Planejamento do bundle de confiabilidade:

```bash
python -m hpp install --bundle reliable-coding --host codex --target ../meu-repo
```

Esse comando é deliberadamente read-only. A aplicação real usa o instalador verificado de cada
módulo, mostrado na seção Codex CLI; o harness não grava um receipt para fingir que copiou bytes.

Para Claude Code, o canal nativo continua disponível:

```text
/plugin marketplace add rushar-labs/house-party-protocol
/plugin install operator-kit@house-party-protocol
```

## Codex CLI

O Codex recebe cada módulo por cópia verificável, com skills namespaced em `.agents/skills` e
runtime em `.agents/hpp`. Para instalar um módulo emitido:

```bash
python instaladores/kit-forge-1.4.0/kit_doctor.py install \
  --kit frameworks-com-plugins/operator-kit-1.4.0 \
  --host codex --target ../meu-repo --apply
```

Forma compacta: `kit_doctor.py install --kit <módulo> --host codex --target <repo> --apply`.

O comando executa o plano, copia o runtime e roda os smokes declarados. Hooks de lifecycle do
Claude Code não são ativados silenciosamente no Codex; o doctor marca essa integração como
`explicit-command` ou `unsupported`.

## Uma superfície, várias projeções

O HPP não precisa de um banco de grafo para ser explicável. O CLI projeta arquivos e eventos
locais em mapas determinísticos:

```bash
python -m hpp graph --view capability --format json
python -m hpp graph --view agent --format mermaid
python -m hpp graph --view evidence --format json
python -m hpp graph --view operational --format mermaid
```

- **Capability Map:** módulos, capacidades, hosts e bundles.
- **Agent Map:** maker, checker, gate humano, permissões e handoffs.
- **Lane Map:** sessões vivas, territórios, heartbeats e colisões.
- **WorkGraph:** unidades derivadas da spec, dependências e waves seguras.
- **Grafo operacional / Execution/Evidence Graph:** ações, artefatos, medições e vereditos.
- **Context/Knowledge Map:** fontes incluídas ou omitidas, prioridade, hash e orçamento.
- **Monitor Map:** probe, alvo, cadência, frescor, severidade e consumidor.

O `Code Map` raiz mostra módulos e componentes declarados; não finge ser um grafo AST de chamadas.
Quando análise semântica de código for necessária, ela entra como fonte/adaptador, não como banco
obrigatório do produto.

Veja [arquitetura](docs/ARCHITECTURE.md) e [modelo de grafos](docs/GRAPH-MODEL.md).

## Spec-driven em waves

Uma spec vira unidades com `id`, dependências, critério de aceite e tier. O WorkGraph rejeita
ciclos e só coloca na mesma wave itens sem dependência entre si. A barreira fecha uma wave antes
de abrir a próxima; evidência e review continuam obrigatórios por unidade.

```bash
python -m hpp work plan examples/reliable-coding/workgraph.json
python -m hpp work waves examples/reliable-coding/workgraph.json
```

O roteador escolhe um tier provider-neutral (`economy`, `balanced`, `frontier`) por risco,
complexidade, contexto e estágio. Ele não chama modelos e não esconde fallback:

```bash
python -m hpp route \
  --request examples/reliable-coding/route-request.json \
  --providers examples/reliable-coding/providers.json \
  --policy economy
```

Risco, complexidade e tamanho de contexto estabelecem um piso: uma política econômica nunca
rebaixa trabalho de alto risco. O fallback só pode subir de tier e fica registrado no output.

Contexto também é compilado antes da execução, sob orçamento e com proveniência:

```bash
python -m hpp context compile examples/reliable-coding/context.json --budget 160
python -m hpp map context examples/reliable-coding/context.json --budget 160
```

## Lane Map e Monitor Map

Lane Map deriva ownership e colisões de territórios exclusivos. Quando `--now` é informado, o
estado `alive/suspect/dead` vem do heartbeat e de limites explícitos; uma lane morta não mantém um
bloqueio eterno.

```bash
python -m hpp map lane examples/reliable-coding/lanes.json \
  --now 1000 --suspect-after 60 --dead-after 300
python -m hpp map agent
python -m hpp map monitor examples/reliable-coding/monitors.json --now 1000
```

Monitor Map não inicia processos. Ele projeta probes declaradas em `healthy`, `stale`, `skew` ou
`unknown`. `healthy` significa sinal fresco dentro daquela régua — não resultado correto, dado
atualizado ou operação concluída. `skew` é sinal com timestamp no futuro, além da tolerância
declarada (`--skew-tolerance`): relógio adiantado ou timestamp fabricado não é frescor.

## Estado, loops e retomada

O event log é append-only. A projeção atual pode ser reconstruída, auditada e resumida sem
depender da memória de uma conversa.

```bash
python -m hpp event append --type work_started --data '{"work":"ITEM-1","actor":"maker-a"}'
python -m hpp event append --type evidence_recorded --data '{"work":"ITEM-1","ref":"pytest.txt"}'
python -m hpp status --json
python -m hpp resume
```

Autoprompt é continuidade; não é autonomia ilimitada. O loop para por sucesso provado, budget,
bloqueio ou gate humano. Veja [loops](docs/LOOPS.md).

## Attestation de evidência

Uma aprovação pode estar correta e ainda assim ficar obsoleta quando a spec ou o checkout muda.
O HPP vincula o veredito a `spec hash`, repositório, commit-base, snapshot completo, maker,
checker e sessão. Arquivos rastreados, staged, removidos e untracked participam do snapshot;
qualquer divergência posterior bloqueia a reutilização da aprovação.

```bash
python -m hpp attest create --repo . --spec SPEC.md \
  --maker maker-a --checker checker-b --session review:001 \
  --verdict approved --output .hpp/attestation.json
python -m hpp attest verify .hpp/attestation.json --repo .
```

O registro guarda somente um hash da identidade remota; URL e caminho pessoal não são gravados.
Uma resposta vazia, maker igual ao checker ou veredito diferente de `approved` nunca vira prova.

## Avaliação reproduzível

```bash
python -m hpp eval run examples/reliable-coding/benchmark-suite.json -k 3 --gate both
```

- `pass@k`: o caso passou ao menos uma vez; mede capacidade.
- `pass^k`: o caso passou em todas as execuções; mede confiabilidade.
- release-critical exige `pass^k = 1.00` para o universo declarado.

O [benchmark](docs/BENCHMARK.md) usa controles positivos e negativos e pode ser repetido em
clone limpo. Resultado sem comando, saída, versão e escopo não é tratado como prova.

## Os módulos

| Módulo | Papel no harness |
|---|---|
| `operator-kit` | gates, política, loops, pass@k/pass^k, preflight e checkers |
| `lane-kit` | Lane Board, territórios, liveness e maker/checker |
| `continuity-kit` | handoff, anti-replay, pre-compact e retomada |
| `health-kit` | probes, cache, statusline e separação serviço/dado |
| `gotcha-memory` | memória de falhas recorrentes com promoção controlada |
| `kit-forge` | montagem, instalação, IP/PII lint, checksums e verificação |
| `claude-dev-kit` | construção e validação de skills, hooks e plugins |
| `dev-squad-kit` | papéis especializados e leitores paralelos com teto |
| `agent-framework-wizard` | scaffold guiado e validado para novas capacidades |
| `supabase-pack` | RLS auditável e scaffold de Edge Functions |

Cada módulo continua instalável separadamente. O Capability Map distingue dependência dura de
integração opcional; modularidade não é tratada como ausência de arquitetura.

## Cobertura por host

| Capacidade | Claude Code | Codex CLI |
|---|---|---|
| skills/instruções | nativa por plugin | cópia em `.agents/skills` |
| hooks de lifecycle | nativa quando configurada | não disponível; comando explícito |
| política audit/enforce | hook + CLI | CLI/preflight explícito |
| event log, attestation, maps, WorkGraph, eval | CLI | CLI |
| instalação | marketplace ou CLI | CLI por cópia |

`hpp doctor` reporta `native`, `explicit-command` ou `unsupported`; não converte ausência de hook
em promessa de enforcement.

## Limites honestos

HPP 2.1 é um harness CLI local, não um daemon ou serviço remoto. Ele não agenda tarefas, não
executa modelos por API, não guarda credenciais, não inicia monitores ocultos e não usa banco de
grafo. Os mapas são projeções determinísticas de manifestos, eventos e estado local. Essa escolha
mantém o sistema auditável, portátil e reversível.

## Desenvolvimento e verificação

Os diretórios versionados dos módulos são artefatos emitidos. Mudanças nascem nas fontes,
recebem teste vermelho→verde e passam pela forja.

Antes de instalar ou concluir trabalho, `preflight.py` verifica os pré-requisitos declarados pelo
Operator Kit; o doctor raiz verifica o contrato do harness.

```bash
python -m pytest -q
python -m hpp doctor
python -m hpp benchmark -k 3
python instaladores/kit-forge-1.4.0/kit_doctor.py marketplace .
```

Leitura adicional: [manual](docs/MANUAL.html) · [catálogo](docs/CATALOGO.html) ·
[provas](docs/PROOF.md) · [identidade](docs/BRAND.md) · [dicas](docs/TIPS.md).

## Licença

MIT. Componentes adaptados preservam os respectivos arquivos `NOTICE` e atribuições.
