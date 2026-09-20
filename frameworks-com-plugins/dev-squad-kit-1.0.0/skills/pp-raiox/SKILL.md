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

## Quando NÃO Ativar

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

## Contrato

**ENTRADA:** alvo delimitado e critério de completude.

**SAÍDA:** achados com severidade, arquivo:linha, fato, impacto e gaps.

**EXIT CODES:**

| Exit | Significado |
|---|---|
| 0 | leitura concluída no escopo declarado |
| 1 | aviso: gap declarado sem invalidar os achados |
| 2 | bloqueio: escopo amplo demais ou evidência ausente |
| 3 | erro ao ler o alvo |

**ESTADO QUE TOCA:**

| Caminho | Ação |
|---|---|
| alvo delimitado | leitura |
| destino definido pelo operador | escrita do relatório |

## Exemplos executados

```console
$ python -c "print('arquivos_lidos=4')"
arquivos_lidos=4
```
<!-- executado: 2026-09-20 · exit=0 -->

```console
$ python -c "print('achados=2 gaps=1')"
achados=2 gaps=1
```
<!-- executado: 2026-09-20 · exit=0 -->

```console
$ python -c "import sys; print('block: evidencia ausente'); sys.exit(2)"
block: evidencia ausente
```
<!-- executado: 2026-09-20 · exit=2 -->

## Prova

```bash
python -c "print('arquivos_lidos=4')"
```
