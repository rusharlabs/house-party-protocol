---
name: pp-raiox
description: "Parallel Process Raio-X - leitura linha-a-linha de um modulo/repo externo com evidencias, riscos e chamadas de proxima investigacao"
type: skill
---

> **Auto-Trigger:** Quando o usuario pedir raio-x tecnico, auditoria linha-a-linha, leitura profunda de modulo externo ou explicacao com evidencias de arquivos.
> **Keywords:** "pp-raiox", "raio-x", "linha a linha", "auditoria profunda", "repo externo", "ler tudo", "mapa cabo a cabo"
> **Prioridade:** ALTA
> **Tools:** Bash, Read, Grep, Glob

# pp-raiox - raio-x com evidencia

## Objetivo

Produzir uma leitura tecnica rastreavel de um alvo delimitado. Diferente de `pp-discovery`, esta skill entra no conteudo dos arquivos selecionados e registra achados com caminho, linha e impacto.

Use depois de uma descoberta ou quando o usuario ja forneceu um escopo pequeno o bastante para leitura profunda.

## Quando NAO Ativar

- O alvo ainda e amplo demais para leitura completa; use `pp-discovery`.
- O trabalho e juntar relatorios/agentes ja executados; use `pp-consolidate`.
- A pergunta exige pesquisa externa atual; use fluxo de pesquisa com fontes.
- O usuario pediu implementacao/correcao imediata; use skill de feature/dev apropriada.

## Processo

1. Fixe escopo e criterio de completude.
2. Capture estado:
   - `git status --short --branch`
   - lista exata de arquivos do alvo.
3. Leia os arquivos em ordem de dependencia: manifests/configs, entrypoints, libs centrais, testes/docs.
4. Para cada achado, registre:
   - arquivo e linha;
   - fato observado;
   - impacto;
   - incerteza ou check pendente.
5. Separe fato de recomendacao.

## Saida Esperada

```md
# PP Raio-X - <alvo>

## Escopo
- incluido:
- excluido:

## Arquivos Lidos
| arquivo | linhas | papel |

## Achados
| severidade | arquivo:linha | fato | impacto |

## Fluxos
1. entrada -> processamento -> saida

## Gaps
| gap | por que impede certeza | como verificar |

## Recomendacoes
| prioridade | acao | motivo |
```

## Guardrails

- Nao afirmar "todo o repo" se o escopo lido foi parcial.
- Nao editar arquivos durante o raio-x, salvo pedido explicito.
- Nao substituir auditoria live por docs antigos.
- Se o alvo for grande demais, volte para `pp-discovery` e proponha ondas.
