---
name: pp-discovery
description: "Parallel Process Discovery - inventario token-safe de repositorios, pastas e artefatos grandes antes de analise profunda"
type: skill
---

> **Auto-Trigger:** Quando o usuario pedir descoberta inicial de um repo/pasta grande, mapa de arquivos, inventario token-safe ou preparacao para analise paralela.
> **Keywords:** "pp-discovery", "discovery", "mapear repo", "inventario token-safe", "deep-read", "repo grande", "descoberta paralela"
> **Prioridade:** MEDIA
> **Tools:** Bash, Read, Grep, Glob

# pp-discovery - descoberta token-safe

## Objetivo

Mapear rapidamente uma base grande sem despejar conteudo demais no contexto. A saida deve dizer o que existe, onde olhar primeiro, quais arquivos sao fonte de verdade e quais areas parecem risco ou ruido.

Use quando o pedido ainda e amplo. Se a pergunta ja exige uma tese com evidencias externas, use pesquisa dedicada/deep-research em vez desta skill.

## Quando NAO Ativar

- Escopo pequeno e ja delimitado para leitura linha-a-linha; use `pp-raiox`.
- Consolidacao de outputs paralelos ja existentes; use `pp-consolidate`.
- Pesquisa externa com web/citacoes; use fluxo de pesquisa apropriado.
- Execucao operacional no seu executor; use skills de dispatch/executor.

## Processo

1. Defina o alvo exato: repo, pasta, commit ou pacote.
2. Colete estrutura com comandos baratos:
   - `git status --short --branch`
   - `rg --files`
   - `find <alvo> -maxdepth 3 -type f` quando `rg` nao cobrir.
3. Classifique por tipo: codigo, docs, configs, dados, logs, builds, vendored/deps.
4. Leia apenas headers, manifests e arquivos de indice antes de ler corpos grandes.
5. Liste candidatos para analise seguinte com motivo concreto.

## Saida Esperada

```md
# PP Discovery - <alvo>

## Fonte
- alvo:
- branch/commit:
- data:

## Mapa
| area | tipo | tamanho/sinal | prioridade | motivo |

## Fontes De Verdade
| arquivo | por que importa |

## Riscos
| risco | evidencia | proximo check |

## Proxima Onda
1. ...
```

## Guardrails

- Nao resumir arquivo que nao foi lido.
- Nao contar itens por estimativa; use comando real.
- Nao criar plano de execucao operacional no seu executor; este skill e do seu sistema de conhecimento e so prepara conhecimento.
- Nao copiar conteudo massivo para memoria; referencie caminhos e hashes quando util.
