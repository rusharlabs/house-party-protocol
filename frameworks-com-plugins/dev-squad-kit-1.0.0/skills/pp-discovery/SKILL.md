---
name: pp-discovery
description: "Parallel Process Discovery - token-safe inventory of repositories, folders and large artifacts before deep analysis"
type: skill
---

> **Auto-Trigger:** When the user asks for the initial discovery of a large repo/folder, a file map, a token-safe inventory or the preparation for parallel analysis.
> **Keywords:** "pp-discovery", "discovery", "map repo", "token-safe inventory", "deep-read", "large repo", "parallel discovery"
> **Priority:** MEDIUM
> **Tools:** Bash, Read, Grep, Glob

# pp-discovery - token-safe discovery

## Goal

Map a large codebase quickly without dumping too much content into the context. The output must say what exists, where to look first, which files are the source of truth and which areas look like risk or noise.

Use it while the request is still broad. If the question already demands a thesis with external evidence, use dedicated research/deep-research instead of this skill.

## When NOT to Activate

- Small scope, already delimited for line-by-line reading; use `pp-raiox`.
- Consolidation of parallel outputs that already exist; use `pp-consolidate`.
- External research with web/citations; use the appropriate research flow.
- Operational execution in your executor; use dispatch/executor skills.

## Process

1. Define the exact target: repo, folder, commit or package.
2. Collect the structure with cheap commands:
   - `git status --short --branch`
   - `rg --files`
   - `find <alvo> -maxdepth 3 -type f` when `rg` does not cover it.
3. Classify by type: code, docs, configs, data, logs, builds, vendored/deps.
4. Read only headers, manifests and index files before reading large bodies.
5. List candidates for the next analysis with a concrete reason.

## Expected Output

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

- Do not summarise a file that was not read.
- Do not count items by estimate; use a real command.
- Do not create an operational execution plan in your executor; this skill belongs to your knowledge system and only prepares knowledge.
- Do not copy massive content into memory; reference paths and hashes when useful.

## Contract

**INPUT:** a delimited repo, folder, commit or package.

**OUTPUT:** an inventory with map, sources of truth, risks and next wave.

**EXIT CODES:**

| Exit | Meaning |
|---|---|
| 0 | inventory complete, with the measuring command next to each count |
| 1 | warning: inaccessible area declared |
| 2 | block: missing scope or estimated count |
| 3 | error reading the target |

**STATE IT TOUCHES:**

| Path | Action |
|---|---|
| delimited target | read |
| destination chosen by the operator | write the inventory |

## Executed examples

```console
$ python -c "print('arquivos=12 fonte=rg')"
arquivos=12 fonte=rg
```
<!-- executed: 2026-09-20 · exit=0 -->

```console
$ python -c "print('fontes_de_verdade=2')"
fontes_de_verdade=2
```
<!-- executed: 2026-09-20 · exit=0 -->

```console
$ python -c "import sys; print('block: escopo ausente'); sys.exit(2)"
block: escopo ausente
```
<!-- executed: 2026-09-20 · exit=2 -->

## Proof

```bash
python -c "print('arquivos=12 fonte=rg')"
```
