---
name: delegate-with-handback
description: Delegates a long/independent task to a 2nd agent with explicit context and a verification gate on the return
---

> **Auto-Trigger:** Long/independent task (audit, broad refactor, research) that would benefit from a 2nd agent or a second opinion
> **Keywords:** "delegate", "codex", "second agent", "second opinion", "run in parallel", "offload", "review"
> **Priority:** MEDIUM
> **Tools:** Task/Agent, Bash, Read, Grep

# delegate-with-handback — delegate with a verified handback

Generalizes `codex-delegate` into a **provider-agnostic** framework. Never trusts the delegate's "done".

## Contract

**INPUT:** the explicit context package (path/branch/commit + objective + acceptance criterion + constraints) assembled in step 2; the delegate's output on disk.

**OUTPUT:** acceptance (item marked done) OR re-queue with the gap pointed out.

**EXIT CODES** (from `done_gate.py`, used in the handback — step 4):

| Exit | Meaning |
|---|---|
| 0 | DONE — acceptance criterion passed; accept the handback |
| 1 | NOT-DONE — criterion failed; re-queue with the gap |
| 2 | invalid use of done_gate |

**STATE IT TOUCHES:**

| Resource | Reads/Writes | Purpose |
|---|---|---|
| delegate's output (file/diff on disk) | Reads | real verification (not the "done" message) |
| `operator-profile.yaml` (`autonomia`) | Reads | which provider to dispatch to |
| `rule_capture` hook (if wired) | Writes | preserves the pattern in `.claude/memory/_captured-rules.md` for `distill_corrections.py` to distill later |

## Process
1. **Decide to delegate** when: the task is long, independent, repetitive, or when a **second opinion** reduces risk.
2. **Assemble the explicit context package** (without it the output comes back useless):
   - exact `path/branch/commit` · objective in 1 sentence · **testable acceptance criterion** · constraints (what NOT to touch) · return format.
3. **Dispatch** to the configured provider (`autonomia`/environment decides which — Codex/other). In fan-out, respect `parallel-dispatch` (ceiling + waves).
4. **Handback = GATE, not trust.** On receiving the result:
   - Read the REAL output on disk (not the "done" message).
   - Run `python ${CLAUDE_PLUGIN_ROOT}/scripts/done_gate.py --profile <type>` (or the test/acceptance criterion).
   - Only accept if the gate passes; otherwise **re-queue** with the gap pointed out.
5. **Record** the recurring failure (the `rule_capture` hook, if wired, preserves the pattern for `distill_corrections.py` to distill later).

## When NOT to Activate
- Short task you do faster yourself.
- No secondary provider available → do it locally + verify.
- When the context does not fit in an explicit package (refine the scope first).
- Fan-out of N independent tasks (no individual handback) → use `parallel-dispatch`; this skill is 1 delegation with a gate on the return.

## Executed examples

```console
$ python scripts/done_gate.py "python -c \"print(1)\""
  [OK ] (exit 0) python -c "print(1)"

DONE-GATE: DONE (1/1 criteria)
```
<!-- executed: 2026-07-10 · exit=0 -->

```console
$ python scripts/done_gate.py "python -c \"import sys; sys.exit(1)\""
  [FAIL] (exit 1) python -c "import sys; sys.exit(1)"

DONE-GATE: NOT-DONE (0/1 criteria)
```
<!-- executed: 2026-07-11 · exit=1 -->
(handback rejected — exactly the behavior expected in step 4: "only accept if the gate passes". Self-contained criterion — it depends on no file outside the kit.)

```console
$ python scripts/done_gate.py --json "python -c \"import sys; sys.exit(0)\""
{"done": true, "results": [{"cmd": "python -c \"import sys; sys.exit(0)\"", "passed": true, "exit_code": 0, "tail": ""}]}
```
<!-- executed: 2026-07-10 · exit=0 -->

## Proof

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/done_gate.py --self-test
```
