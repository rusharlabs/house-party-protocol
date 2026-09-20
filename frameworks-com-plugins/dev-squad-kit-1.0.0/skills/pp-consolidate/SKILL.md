---
name: pp-consolidate
description: "Parallel Process Consolidate - consolida outputs de sessoes/agentes paralelos em um veredito unico, deduplicado e verificavel"
type: skill
---

> **Auto-Trigger:** Quando houver multiplos outputs de agentes, sessoes, auditorias ou waves e o usuario pedir sintese, veredito, consolidacao ou top findings.
> **Keywords:** "pp-consolidate", "consolidar", "sintese de agentes", "outputs paralelos", "veredito", "dedup", "juntar auditorias"
> **Prioridade:** ALTA
> **Tools:** Bash, Read, Grep, Glob

# pp-consolidate - consolidacao de ondas paralelas

## Objetivo

Transformar varias respostas ou artefatos paralelos em uma unica decisao rastreavel. O foco e remover duplicatas, resolver conflitos e apontar o que esta provado, o que e hipotese e o que ainda precisa de verificacao live.

## Quando NAO Ativar

- Ainda nao ha multiplos outputs ou artefatos para consolidar.
- O pedido e inventariar um repo/pasta antes da analise; use `pp-discovery`.
- O pedido e leitura profunda de um unico alvo; use `pp-raiox`.
- A consolidacao exigiria executar acoes operacionais; gere o veredito e roteie para seu executor operacional.

## Processo

1. Inventarie os inputs: arquivos, mensagens, task ids, commits ou relatorios.
2. Para cada input, extraia achados atomicos com fonte.
3. Deduplicate por entidade + causa raiz + evidencia, nao por texto parecido.
4. Classifique conflitos:
   - confirmados por duas fontes;
   - contraditorios;
   - stale ou sem evidencia.
5. Produza TOP-N com severidade, impacto e proximo passo.

## Saida Esperada

```md
# PP Consolidate - <tema>

## Inputs
| id | fonte | data | confianca |

## Veredito
- status:
- decisao:
- bloqueios:

## Achados Deduplicados
| rank | estado | achado | fontes | evidencia | acao |

## Conflitos
| tema | fonte A | fonte B | resolucao |

## Gaps
| gap | dono | evidencia necessaria |

## TOP-10
1. ...
```

## Guardrails

- Nao promover consenso sem evidencia.
- Nao apagar divergencias; resolva ou marque como conflito.
- Nao tratar output de agente como fato live sem verificar quando a informacao pode ter mudado.
- Nao executar tarefas operacionais; esta skill consolida conhecimento para decisao.
