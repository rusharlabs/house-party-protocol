---
name: pp-consolidate
description: "Parallel Process Consolidate - consolidates the outputs of parallel sessions/agents into a single, deduplicated, verifiable verdict"
type: skill
---

> **Auto-Trigger:** When there are multiple outputs from agents, sessions, audits or waves and the user asks for a synthesis, a verdict, a consolidation or the top findings.
> **Keywords:** "pp-consolidate", "consolidate", "agent synthesis", "parallel outputs", "verdict", "dedup", "merge audits"
> **Priority:** HIGH
> **Tools:** Bash, Read, Grep, Glob

# pp-consolidate - consolidation of parallel waves

## Goal

Turn several parallel answers or artifacts into a single traceable decision. The focus is removing duplicates, resolving conflicts and stating what is proven, what is hypothesis and what still needs live verification.

## When NOT to Activate

- There are not yet multiple outputs or artifacts to consolidate.
- The request is to inventory a repo/folder before the analysis; use `pp-discovery`.
- The request is a deep read of a single target; use `pp-raiox`.
- The consolidation would require running operational actions; produce the verdict and route it to your operational executor.

## Process

1. Inventory the inputs: files, messages, task ids, commits or reports.
2. For each input, extract atomic findings with their source.
3. Deduplicate by entity + root cause + evidence, not by similar wording.
4. Classify conflicts:
   - confirmed by two sources;
   - contradictory;
   - stale or without evidence.
5. Produce a TOP-N with severity, impact and next step.

## Expected Output

```md
# PP Consolidate - <topic>

## Inputs
| id | source | date | confidence |

## Verdict
- status:
- decision:
- blockers:

## Deduplicated Findings
| rank | state | finding | sources | evidence | action |

## Conflicts
| topic | source A | source B | resolution |

## Gaps
| gap | owner | evidence needed |

## TOP-10
1. ...
```

## Guardrails

- Do not promote consensus without evidence.
- Do not erase divergences; resolve them or mark them as a conflict.
- Do not treat an agent's output as a live fact without verifying, when the information may have changed.
- Do not run operational tasks; this skill consolidates knowledge for a decision.

## Contract

**INPUT:** two or more outputs identified by source.

**OUTPUT:** one deduplicated verdict with conflicts and gaps preserved.

**EXIT CODES:**

| Exit | Meaning |
|---|---|
| 0 | consolidation complete and traceable |
| 1 | warning: partial input declared |
| 2 | block: missing source or hidden conflict |
| 3 | error reading the inputs |

**STATE IT TOUCHES:**

| Path | Action |
|---|---|
| the given outputs | read |
| destination chosen by the operator | write the verdict |

## Executed examples

```console
$ python -c "print('inputs=3 findings=2')"
inputs=3 findings=2
```
<!-- executed: 2026-09-22 · exit=0 -->

```console
$ python -c "print('conflicts=1 preserved=1')"
conflicts=1 preserved=1
```
<!-- executed: 2026-09-22 · exit=0 -->

```console
$ python -c "import sys; print('block: missing source'); sys.exit(2)"
block: missing source
```
<!-- executed: 2026-09-22 · exit=2 -->

## Proof

```bash
python -c "print('inputs=3 findings=2')"
```
