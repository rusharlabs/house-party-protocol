---
name: gotcha-memory
description: Operational learning loop — records command failures, detects recurrence and injects the lesson as a preamble before the next execution of the same task. Use to query/seed/debug the project's gotcha memory.
---

> **Auto-Trigger:** When the user asks "why does this always fail?", "what have we already learned about this task?", wants to seed curated rules, or wants to inspect/clean the project's failure memory.
> **Keywords:** "gotcha", "gotchas", "recurring failure", "recurring error", "lesson learned", "failure memory", "preamble", "curated", "rule seed", "operational learning"
> **Priority:** MEDIUM
> **Tools:** Bash, Read

## When NOT to Activate
- Debugging ONE new, one-off failure — this module handles RECURRENCE (>= N identical failures within a window); for the first occurrence, debug normally.
- Managing conversational/semantic memory (session context, RAG) — this module is memory of EXECUTION FAILURES, not of knowledge.

## Contract

**INPUT:** Bash failure events (recorded automatically by the `gotcha_postflight.py` hook) + your curated lessons (YAML/JSONL seed). Config in `gotchas.*`/`paths.gotcha_store` of `operator-profile.yaml`.

**OUTPUT:** `failures.jsonl` + `curated.jsonl` in the store (default `.claude/gotchas/`) and a "⚠️ GOTCHAS" preamble on the preflight's stderr when a lesson matches the task.

**EXIT CODES:**

| Exit | Meaning |
|---|---|
| 0 | always (hooks and CLI) — the learning loop never breaks the caller's flow |
| 1 | only in `--self-test` when an assertion fails |

**STATE IT TOUCHES:**

| Resource | Reads/Writes | Purpose |
|---|---|---|
| `operator-profile.yaml` (`gotchas.*`, `paths.gotcha_store`) | Reads | config (window, min_count, top, store) |
| `<store>/failures.jsonl` | Writes (append) | failure events classified by family |
| `<store>/curated.jsonl` | Reads/Writes (idempotent append) | your always-on rules |

## Process
1. **Install the hooks** (via plugin or manual wire — see README): `PreToolUse Bash → gotcha_preflight.py` and `PostToolUse` + `PostToolUseFailure Bash → gotcha_postflight.py`, all `timeout: 30`, WARN-only. The two exit events point to the same script because the host emits `PostToolUseFailure` when Bash fails — the case this memory exists to record.
2. **Seed your rules** (optional, idempotent):
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/_lib/gotchas_memory.py" --seed curated.seed.example.yaml
   ```
3. **Query what the system has learned** about a task:
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/_lib/gotchas_memory.py" --preamble "rodar o deploy do site"
   ```
4. **See the whole loop working** (demo with a temporary store, zero effect on the project):
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/_lib/gotchas_memory.py"
   ```

## Executed examples

The three below were genuinely run (2026-09-19) against a temporary store via
`GOTCHA_STORE_DIR` — zero effect on the project. The output is the real one, with the store
path abbreviated to `<store>`.

**1 · Seed the curated rules (first time):**

```
$ GOTCHA_STORE_DIR=<store> python "${CLAUDE_PLUGIN_ROOT}/_lib/gotchas_memory.py" --seed curated.seed.example.yaml
Seedados 5 gotchas curated em <store>/curated.jsonl
$ echo $?
0
```
<!-- executed: 2026-09-19 · exit=0 -->

**2 · Seed the SAME file again — the idempotency proof:**

```
$ GOTCHA_STORE_DIR=<store> python "${CLAUDE_PLUGIN_ROOT}/_lib/gotchas_memory.py" --seed curated.seed.example.yaml
Seedados 0 gotchas curated em <store>/curated.jsonl
```
<!-- executed: 2026-09-19 · exit=0 -->

Zero, not five again: re-seeding does not duplicate. That is what allows leaving the seed in a
project's setup and running it in every session.

**3 · Query what the system knows about a task:**

```
$ GOTCHA_STORE_DIR=<store> python "${CLAUDE_PLUGIN_ROOT}/_lib/gotchas_memory.py" --preamble "rodar o deploy do site"
⚠️ GOTCHAS (evite repetir — aprendido de falhas anteriores):
  • [regra] Deploy/routing: verifique que o BACKEND trocou (rota exclusiva da versão nova + marca de build), não só o gate de auth ou o status do processo.
$ echo $?
0
```
<!-- executed: 2026-09-19 · exit=0 -->

The rule that appeared is a **curated** one (seeded in example 1) — it matched by substring
on "deploy". A **learned** lesson (from recurring failures) would appear in the same list
with the `[Nx]` counter in front.

## Proof

```bash
python "${CLAUDE_PLUGIN_ROOT}/_lib/gotchas_memory.py" --self-test     # -> self-test OK ✓  · exit 0
python "${CLAUDE_PLUGIN_ROOT}/_lib/error_strategy.py" --self-test     # -> self-test OK    · exit 0
python "${CLAUDE_PLUGIN_ROOT}/hooks/gotcha_preflight.py" --self-test  # -> self-test OK
python "${CLAUDE_PLUGIN_ROOT}/hooks/gotcha_postflight.py" --self-test # -> self-test OK
```

The four self-tests cover: classification by family (with word boundary —
an isolated `ENOTFOUND` is network, `ModuleNotFoundError` is dependency), recurrence that becomes a
gotcha after `min_count` failures within the window, seed idempotency, and the hooks'
conservative detection (ambiguous = not a failure).

**Operational success criterion:** after 3 identical failures recorded in < 24h,
`--preamble "<same task>"` returns a non-empty preamble with `[3x]`.

## Known failures / limits
- Failure detection is CONSERVATIVE: only exit code != 0, `is_error: true` or a non-empty `error` field count. A "silent" failure (exit 0 with wrong output) is not captured — by design (it does not invent failures).
- Covers only the Bash tool (the hooks' matcher). Other tools would require new matchers.
- YAML seed requires PyYAML; without PyYAML, use a `.jsonl` seed (stdlib).
