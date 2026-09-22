---
name: pre-clear
description: Before a /clear, consolidates the LONG TERM (conditional doc-rollup — how we got here) and the SHORT TERM (handoff — what comes next), then renders the BOOT BUNDLE.
---

> **Auto-Trigger:** When a wave/feature closes, the context is growing, or the operator signals they are about to compact/clear the session.
> **Keywords:** "pre-clear", "about to clear", "compact", "before the clear", "next session boot", "close session", "prepare next session"
> **Priority:** HIGH
> **Tools:** Read, Write, Bash

## When NOT to Activate
- Mid-task: the wave/feature has not finished (finish first — never consolidate halfway).
- A `/pre-clear` is already installed in the target project (e.g. house-specific, consolidating `00-STATE.md`/its own memory) — **the installed one WINS**; this module's version is only for projects without their own `/pre-clear`. The `kit_assembler` checks for name+keywords collision before installing.
- Trivial read-only session with no new decision/change (nothing to consolidate) — neither the rollup nor the handoff fires; record that instead of forcing an empty entry.
- Do not confuse with the `doc-rollup` skill, which this flow CALLS as step 1 — `doc-rollup` alone covers only the long term (history); `pre-clear` orchestrates the long term + the short term (handoff) + the final boot bundle.

## Contract

**INPUT:** the model mentally fills in (a) the rollup payload (summary/shipments/metrics/decisions/lessons, if something significant closed) and (b) the handoff schema (summary, numbers with `re_derive_cmd`, decisions, open gates, next step with `verify_first_cmd`) and passes each one via stdin to the corresponding command.

**OUTPUT:** (1, conditional) history docs updated via `doc_rollup.py`; (2) `HANDOFF-CURRENT-<lane>.json` written + `written` event in the ledger; (3) BOOT BUNDLE rendered in the chat.

**EXIT CODES** (from `_handoff_io.py write --stdin` — the final, mandatory step):

| Exit | Meaning |
|---|---|
| 0 | valid handoff, written |
| 1 | rejected (secret detected, `verify_first_cmd`/`re_derive_cmd` missing, invalid schema) |
| 2 | invalid usage (malformed JSON on stdin) |

**STATE IT TOUCHES:**

| File | Reads/Writes | Purpose |
|---|---|---|
| `rollup.yaml` + history targets (via `doc_rollup.py`) | Reads+Writes (conditional) | long term — how we got here |
| `.claude/handoff/HANDOFF-CURRENT-<lane>.json` | Writes (atomic) | short term — this lane's live handoff |
| `.claude/handoff/HANDOFF-LEDGER.jsonl` | Writes (append) | `written` event |
| `schemas/handoff-v1.1.schema.json` | Reads (implicitly via validation) | the handoff contract |

## Process

1. **Significance check:** did something close in this session that deserves a long-term record (feature, decision, lesson)? If NOT, skip steps 2-3 and record explicitly why you skipped (e.g. "pure exploration session, no rollup"). Never force an empty entry just to fill the step.
2. **If significant, run the doc-rollup first** (long term, BEFORE the handoff — so the file tree the handoff describes already reflects the updated docs):
   ```bash
   echo '<payload-rollup>' | python ${CLAUDE_PLUGIN_ROOT}/scripts/doc_rollup.py plan  --stdin --config rollup.yaml
   echo '<payload-rollup>' | python ${CLAUDE_PLUGIN_ROOT}/scripts/doc_rollup.py apply --stdin --config rollup.yaml
   ```
   Read the report — `skipped-collision`/`skipped-passive`/`applied:stamp-degrade` are guardrails working, not errors (see the `doc-rollup` SKILL.md).
3. **Assemble the handoff JSON** (short term) — only the model knows this session's real decisions/gates/next step. Minimum fields: `session.lane_id`, `estado.resumo`, `git` (head/branch/dirty/untracked — run `git status --porcelain` and `git rev-parse --short HEAD` first), `proximo_passo[].verify_first_cmd`, `valid_until`.
4. **Write via the command** (never write the file by hand — the secret/LC-1/LC-4 validation only runs through the command):
   ```bash
   echo '<json>' | python ${CLAUDE_PLUGIN_ROOT}/hooks/_handoff_io.py write --stdin
   ```
5. **If rejected (exit 1):** read the printed reasons, fix the JSON (do not remove the required field — fill it in for real), try again.
6. **Render the BOOT BUNDLE** and show it in the chat (never only in a file):
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/hooks/_handoff_io.py render --lane <lane>
   ```
7. **Announce explicitly:** "Ready for /clear — the block above is what the next session receives." + if steps 1-2 ran, mention what was recorded in the history (or why it was skipped). Never suggest `/clear` without the block assembled and displayed.

## Executed examples

```console
$ echo '{"schema_version":"1.1","handoff_id":"HO-20260710-1600-solo","created_at":"2026-07-10T16:00:00-03:00","trigger":"manual","quality":"full","session":{"session_id":"s1","lane_id":"solo"},"estado":{"resumo":"fechei a FASE 5","numeros":[]},"git":{"head":"637561f5","branch":"feat/codex-migration","dirty":true,"untracked":5},"proximo_passo":[{"ordem":1,"descricao":"comecar FASE 6","verify_first_cmd":"test -d lane-kit"}],"valid_until":"2026-07-17T00:00:00-03:00"}' | python hooks/_handoff_io.py write --stdin
_handoff_io: escrito em .claude/handoff/HANDOFF-CURRENT-solo.json
```
<!-- executed: 2026-07-10 · exit=0 -->

```console
$ echo '{"schema_version":"1.1","handoff_id":"HO-x","created_at":"2026-07-10T16:00:00-03:00","trigger":"manual","quality":"full","session":{"session_id":"s1","lane_id":"solo"},"estado":{"resumo":"x"},"git":{"head":"a","branch":"m","dirty":false,"untracked":0},"proximo_passo":[{"ordem":1,"descricao":"sem verify"}],"valid_until":"2026-07-17T00:00:00-03:00"}' | python hooks/_handoff_io.py write --stdin
  [REJEITADO] proximo_passo[0] sem verify_first_cmd (LC-4: próximo passo sem verificação de idempotência)
```
<!-- executed: 2026-07-10 · exit=1 -->
(a handoff without `verify_first_cmd` is REJECTED — the next session never inherits a step with no way to check whether it was already done.)

```console
$ python hooks/_handoff_io.py render --lane solo
⚠️ CONTEXTO RESTAURADO = REFERÊNCIA HISTÓRICA, NÃO FILA (LC-4)
HANDOFF HO-20260710-1600-solo · full · lane=solo
ESTADO: fechei a FASE 5
PRÓXIMO PASSO 1: comecar FASE 6
  → ANTES DE EXECUTAR, RODE: test -d lane-kit (se já feito: pular, registrar)
Arquivo completo: .claude/handoff/HANDOFF-CURRENT-solo.json
```
<!-- executed: 2026-07-10 · exit=0 -->

(examples of the conditional rollup step: see the `doc-rollup` SKILL.md — the same payloads/exit codes apply when called from here.)

## Proof

```bash
python ${CLAUDE_PLUGIN_ROOT}/hooks/_handoff_io.py --self-test
python ${CLAUDE_PLUGIN_ROOT}/scripts/doc_rollup.py --self-test
```
