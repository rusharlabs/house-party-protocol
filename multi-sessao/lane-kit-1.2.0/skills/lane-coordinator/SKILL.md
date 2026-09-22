---
name: lane-coordinator
description: Coordinates N concurrent sessions (lanes) over the same repo through a whiteboard with a state machine (lane_board.py) — from CLAIMED to MERGED, with cross-model maker≠checker enforced in code, not by textual discipline.
---

> **Auto-Trigger:** When 2+ sessions (planner/executor/reviewer) work on the same repo at the same time, or before an executor claims a work item, or before a reviewer approves/rejects an item.
> **Keywords:** "lane", "lanes", "whiteboard", "board", "coordinate sessions", "maker checker", "claimed", "checkpoint-ready", "verified", "session collision", "multiple sessions"
> **Priority:** HIGH
> **Tools:** Bash, Read

## When NOT to Activate
- Single session (`solo`) with no concurrency — the board is overhead without 2+ live lanes.
- Coordinating a handoff BETWEEN sequential sessions (one at a time) → use `continuity-kit` (handoff/pre-clear), not this module (this one is for SIMULTANEOUS sessions).
- Merge decision for a 🔴 item without the human — even with `VERIFIED`, `--human-approved` is literal: only the operator decides.

## Contract

**INPUT:** `item_id` + role (`executora`/`revisora`) + `lane_id` + `model` + (depending on the state) evidence or verdict.

**OUTPUT:** 1 append-only event in `.claude/lanes/board.jsonl` + (via `render`) a readable snapshot in `docs/plans/execucao/LANE-BOARD.md`.

**EXIT CODES:**

| Exit | Meaning |
|---|---|
| 0 | transition accepted, event written |
| 1 | transition refused by the enforcement (see message — maker=checker, no evidence, wrong lane, etc.) |
| 2 | invalid usage / lock not obtained within 2s |

**STATE IT TOUCHES:**

| File | Reads/Writes | Purpose |
|---|---|---|
| `.claude/lanes/board.jsonl` | Reads+Writes (append, under lock) | the item's event history |
| `.claude/lanes/.lock` (dir) | Creates+removes | serializes concurrent writes |
| `docs/plans/execucao/LANE-BOARD.md` | Writes (via `render`) | readable snapshot, committed only at session-harvest |

## State machine

```
CLAIMED → BUILDING → CHECKPOINT-READY → UNDER-REVIEW → VERIFIED | NEEDS-FIX → MERGED
                                                       ↘ DEFERRED (checker indisponível) ↗
```

- **CHECKPOINT-READY**: only `role=executora`, only the lane that did `CLAIMED`, and requires a non-empty `--evidencia` (pasted hash/exit code — never "I ran it").
- **VERIFIED/NEEDS-FIX**: only `role=revisora`, with `--verdict-by-lane` DIFFERENT from the lane that built AND `--verdict-by-model` from a DIFFERENT family (cross-model maker≠checker, in code — cannot be bypassed).
- **Checker unavailable** (`--checker-indisponivel`): only `DEFERRED` is accepted — never `VERIFIED`.
- **MERGED**: requires a `VERIFIED` in the item's history; if `--tag red`, also requires `--human-approved` (literal human gate).

## Process

1. **Claim the item** (you become the owner, role executora):
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py claim ITEM-1 --lane exec-a --model claude-opus-4-8
   ```
2. **Advance to BUILDING** while you work:
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py set ITEM-1 BUILDING --lane exec-a --role executora --model claude-opus-4-8
   ```
3. **When done, CHECKPOINT-READY with real evidence** (command + output pasted, not "done"):
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py set ITEM-1 CHECKPOINT-READY --lane exec-a --role executora --model claude-opus-4-8 --evidencia "pytest -q: 42 passed, exit=0"
   ```
4. **The reviewer (another lane, another model family) takes over and genuinely verifies** — NEVER accept "it's ready" without running:
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py set ITEM-1 UNDER-REVIEW --lane exec-a --role executora --model claude-opus-4-8
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py set ITEM-1 VERIFIED --lane exec-a --role revisora --model gpt-5.5 --verdict-by-lane rev-a --verdict-by-model gpt-5.5
   ```
5. **Merge** (human gate if `--tag red`):
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py set ITEM-1 MERGED --lane rev-a --role revisora --model gpt-5.5
   ```
6. **Render the snapshot** whenever you want to see the whole board:
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py render
   ```

## Executed examples

```console
$ python scripts/lane_board.py claim ITEM-1 --lane exec-a --model claude-opus-4-8
{"ts": "2026-07-10T15:56:30", "item_id": "ITEM-1", "estado": "CLAIMED", "lane_id": "exec-a", "role": "executora", "model": "claude-opus-4-8", "tag": "green"}
```
<!-- executed: 2026-07-10 · exit=0 -->

```console
$ python scripts/lane_board.py set ITEM-1 BUILDING --lane exec-a --role executora --model claude-opus-4-8
$ python scripts/lane_board.py set ITEM-1 CHECKPOINT-READY --lane exec-a --role executora --model claude-opus-4-8 --evidencia "pytest -q: 42 passed"
$ python scripts/lane_board.py set ITEM-1 UNDER-REVIEW --lane exec-a --role executora --model claude-opus-4-8
$ python scripts/lane_board.py set ITEM-1 VERIFIED --lane exec-a --role revisora --model claude-opus-4-8 --verdict-by-lane exec-a --verdict-by-model claude-opus-4-8
lane_board: recusado — maker≠checker violado: revisora (exec-a) é a MESMA lane do builder (exec-a)
```
<!-- executed: 2026-07-10 · exit=1 -->
(after the full CLAIMED→BUILDING→CHECKPOINT-READY→UNDER-REVIEW cycle, the SAME lane trying to be the reviewer of its own work is refused IN CODE — it does not depend on discipline.)

```console
$ bash evals/collision-2lanes.sh 10
[OK] zero corrupcao: 10/10 linhas validas, 10 items distintos, 0 processos com exit!=0
```
<!-- executed: 2026-07-10 · exit=0 -->
(10 concurrent processes writing to the SAME board — the lock serializes, zero corrupted lines.)

## Proof

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py --self-test
```
