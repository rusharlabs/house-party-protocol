---
name: ralph-loop-driver
description: Turns the agent into an autonomous lead engineer — reads charter+work-list, executes until exhausted, self-prompts, stops at the stop-conditions
---

> **Auto-Trigger:** When the operator authorizes broad execution of a backlog (triggers in `loop.gatilho_autorizacao` of the profile)
> **Keywords:** "/goal", "auto", "100%", "do everything", "maximum capacity", "autonomous loop", "until done", "relentless"
> **Priority:** HIGH
> **Tools:** Read, Write, Edit, Bash, Task/Agent
> **Related doctrine:** `rules/loop-operator.md` (pre-flight + 4 stop-conditions), `rules/loop-patterns-catalog.md` (which loop architecture to use), `rules/learned-corrections.md` (LC-1/LC-2), `rules/loop-cost-budget.md` (budget as a first-class stop).

# ralph-loop-driver — the autonomous loop driver

Generalizes `/goal` (does NOT duplicate it). Turns the agent into a lead engineer who grinds through the work-list alone, without stopping at every item to ask "may I proceed?".

## Contract

**INPUT:** `loop.charter` + `loop.work_list` + `loop.stop_conditions` (read from `operator-profile.yaml` via `_lib/profile_loader`); `paths.state_ssot` (source of truth for LC-1).

**OUTPUT:** work-list with items marked done (in place); git commits per path (0 push); stop report when a stop-condition fires.

**EXIT CODES** (from `done_gate.py`, invoked on every iteration — step 5 of the cycle):

| Exit | Meaning |
|---|---|
| 0 | DONE — all the item's criteria passed; may mark done |
| 1 | NOT-DONE — ≥1 criterion failed (or empty list); item goes back to the work-list |
| 2 | invalid use of done_gate (should not happen in normal operation) |

**STATE IT TOUCHES:**

| File/resource | Reads/Writes | Purpose |
|---|---|---|
| `operator-profile.yaml` (`loop.*`) | Reads | charter, work-list, stop-conditions |
| `paths.state_ssot` | Reads | live source of truth (LC-1) |
| work-list file | Reads+Writes | marks items done |
| `.git` (commits) | Writes | 1 commit per touched path; NEVER push |

## Cycle (each iteration)
1. **Re-align:** read `loop.charter` + the guiding concept + the SSoT (`paths.state_ssot`) — *did I drift? anything half-done?*
2. **Verify live (LC-1):** the real state of the canonical source before citing any number/status.
3. **Choose** the not-done item with the **highest leverage** in `loop.work_list`.
4. **Execute** — in waves via `parallel-dispatch` when parallelizable; with **adversarial verify** (refute before accepting).
5. **Verify:** `python ${CLAUDE_PLUGIN_ROOT}/scripts/done_gate.py --profile <type>` before marking done.
6. **Mark done** in the work-list + **commit per path** (0 push — guardrail).
7. **Capstone per wave:** the project's tests + validators.
8. **Continue** straight to the next iteration, without stopping to ask "may I proceed?" — that is what "autonomous lead engineer" means. **Optional optimization:** if this skill is running INSIDE the dynamic `/loop` main loop, `ScheduleWakeup` can space the self-pacing between cycles — but it is exclusive to the main loop (subagents and headless sessions do NOT see it; see `loop-patterns-catalog`). Without it, the cycle simply continues in the same session — it is never blocking.
9. **Every ~5 cycles — adversarial review:** "which loose end is left? did I drift from the concept? new duplicate/orphan?".

## Guardrails (from the charter; unbreakable)
0 push without an order · backup before mutating prod · snapshot before deleting · credential lock · **human gate** (billing/OAuth/legal/client/deploy-go/secret) becomes a form (see `gate-sheet-collector`), never blocks the loop · LC-1.

## Stop-conditions (`loop.stop_conditions`)
Autonomous lane exhausted · time ceiling · imminent irreversible risk → STOP + report.

## When NOT to Activate
- Without explicit authorization for broad execution (one-off task → direct execution).
- Without a defined charter/work-list → use `loop-charter-template` first.
- Tasks that mostly depend on a human gate (drain into the gate-sheet and stop).

## Executed examples

Step 5 of the cycle (verification before marking done) is the kit's `done_gate.py`. Real examples:

```console
$ python scripts/done_gate.py "python -c \"print(1)\""
  [OK ] (exit 0) python -c "print(1)"

DONE-GATE: DONE (1/1 criteria)
```
<!-- executed: 2026-07-10 · exit=0 -->

```console
$ python scripts/done_gate.py --profile hooks
  [FAIL] (exit 2) python .claude/hooks/agentic_postflight.py --self-test
        ^ python.exe: can't open file '...\.claude\hooks\agentic_postflight.py': [Errno 2] No such file or directory

DONE-GATE: NOT-DONE (0/1 criteria)
```
<!-- executed: 2026-07-10 · exit=1 -->

```console
$ python scripts/done_gate.py --json "python -c \"import sys; sys.exit(0)\""
{
  "done": true,
  "results": [
    {"cmd": "python -c \"import sys; sys.exit(0)\"", "passed": true, "exit_code": 0, "tail": ""}
  ]
}
```
<!-- executed: 2026-07-10 · exit=0 -->

## Proof

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/done_gate.py --self-test
```
