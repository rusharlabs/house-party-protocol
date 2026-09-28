---
name: lane-coordinator
description: Coordinates N concurrent sessions (lanes) over the same repo through a whiteboard with a state machine (lane_board.py) — from CLAIMED to MERGED, with cross-model maker≠checker enforced in code, not by textual discipline.
---

> **Auto-Trigger:** When 2+ sessions (planner/executor/reviewer) work on the same repo at the same time, or before an executor claims a work item, or before a reviewer approves/rejects an item.
> **Keywords:** "lane", "lanes", "whiteboard", "board", "coordinate sessions", "maker checker", "claimed", "checkpoint-ready", "verified", "session collision", "multiple sessions", "best-of-n", "compete", "competing attempts", "pick the best attempt", "release-fix", "start-review", "approve", "fix-queued", "lane dashboard"
> **Priority:** HIGH
> **Tools:** Bash, Read

## When NOT to Activate
- Single session (`solo`) with no concurrency — the board is overhead without 2+ live lanes.
- Coordinating a handoff BETWEEN sequential sessions (one at a time) → use `continuity-kit` (handoff/pre-clear), not this module (this one is for SIMULTANEOUS sessions).
- Merge decision for a 🔴 item without the human — even with `VERIFIED`, `--human-approved` is literal: only the operator decides.

## Contract

**INPUT:** `item_id` + role (`executor`/`reviewer`) + `lane_id` + `model` + (depending on the state) evidence or verdict.

**OUTPUT:** 1 append-only event in `.claude/lanes/board.jsonl` + (via `render`) a readable snapshot in `docs/plans/execution/LANE-BOARD.md`.

**EXIT CODES:**

| Exit | Meaning |
|---|---|
| 0 | transition accepted, event written |
| 1 | transition refused by the enforcement (see message — maker=checker, no evidence, wrong lane, an evidence record that is not `valid`, etc.) |
| 2 | invalid usage / lock not obtained within 2s / `--evidence-record` without the HPP core importable |

**STATE IT TOUCHES:**

| File | Reads/Writes | Purpose |
|---|---|---|
| `.claude/lanes/board.jsonl` | Reads+Writes (append, under lock) | the item's event history |
| `.claude/lanes/.lock` (dir) | Creates+removes | serializes concurrent writes |
| `docs/plans/execution/LANE-BOARD.md` | Writes (via `render`) | readable snapshot, committed only at session-harvest |
| `.claude/lanes/effects.json` | Writes (on every verdict) | the effect ledger: the verdict was decided, and whether the builder lane was told |
| `.claude/lanes/mailbox/<item>-<verdict>-<reservation>.md` | Writes (on every verdict, unless `mailbox.notify_on_verdict: false` in `lanes.yaml`) | the verdict message to the builder lane, routed with `## To: <lane>`; the reservation is marked delivered with that path, and a Codex lane is also nudged with `codex queue` (`mailbox.native_doorbell`) |

## State machine

```
CLAIMED → BUILDING → CHECKPOINT-READY → UNDER-REVIEW → VERIFIED | NEEDS-FIX → MERGED
                                                       ↘ DEFERRED (checker indisponível) ↗
NEEDS-FIX → FIX-QUEUED → BUILDING   (FIX-QUEUED written only by `release-fix`; only the named lane takes it)
VERIFIED → APPROVED → MERGED        (APPROVED written only by `approve`: the human gate of a red item)
CHECKPOINT-READY | VERIFIED → NOT-SELECTED   (terminal — written only by `select`, for a losing candidate)
any state of an undecided candidate → WITHDRAWN   (terminal — written only by `withdraw`)
```

- **CHECKPOINT-READY**: only `role=executor`, only the lane that did `CLAIMED`, and requires a non-empty `--evidence` (pasted hash/exit code — never "I ran it") or an `--evidence-record` the HPP core verifies as `valid`.
- **VERIFIED/NEEDS-FIX**: only `role=reviewer`, with `--verdict-by-lane` DIFFERENT from every lane that built the item AND `--verdict-by-model` from a family none of those builders is (cross-model maker≠checker, in code — cannot be bypassed; `codex-*`, `openai-*`, `chatgpt-*` and `o<digit>` ids count as `gpt`).
- **Checker unavailable** (`--checker-unavailable`): only `DEFERRED` is accepted — never `VERIFIED`.
- **MERGED**: requires a `VERIFIED` in the item's history; a red item (red once any event said so, whatever `--tag` the caller passes) also requires the human gate — an `APPROVED` event, or `--human-approved` on the MERGED; if the item is a candidate of a competition, that competition must already have a winner.
- **`--branch <branch>`** on `claim` and on `set` of a build state records the builder's branch, the one an integration check measures.

## Operator hand-offs and the Lane Dashboard

The operator routes work with three commands (each also a button of `scripts/lane_dashboard.py`):

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py release-fix ITEM-1 --target-lane exec-b
python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py start-review ITEM-1 --target-lane rev-x
python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py approve ITEM-1
```

- **release-fix**: NEEDS-FIX → FIX-QUEUED for a registered, live executor the board would let build the item; a kickoff with the reviewer's direction goes to its mailbox (`## To: <lane>`). A queued fix whose lane stopped beating can be routed again.
- **start-review**: CHECKPOINT-READY or DEFERRED → UNDER-REVIEW for a registered, live reviewer that built no attempt at the item.
- **approve**: VERIFIED → APPROVED for a red item. It does not merge; `set ITEM-1 MERGED` comes after the merge.
- **The dashboard** (`python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_dashboard.py --project-dir .`) shows the board, lanes, mailbox and sessions and offers these actions; every one of them is also a terminal command (`lane_dashboard.py --help`), and it records MERGED only when `git cherry` shows the builder's branch integrated.

## Best-of-N — several lanes, one task, one winner

When the same task is worth attempting more than once, give each attempt its own item and its own lane, then:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py compete --task TASK-1 --items ITEM-A,ITEM-B --lane coord --model claude-opus-5-5
python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py select --task TASK-1 --winner ITEM-A --lane rev-x --model gpt-5.6-sol --reason "same tests, half the diff"
python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py withdraw --task TASK-1 --item ITEM-C --lane coord --model claude-opus-5-5 --reason "lane exec-c died mid-build"
```

- **compete**: 2+ distinct items, each already claimed, no builder lane shared between two candidates; an item competes in one task only, and a task is declared once.
- **select**: every remaining candidate CHECKPOINT-READY with evidence (or VERIFIED); the reviewer's lane differs from every candidate's builder lanes (withdrawn ones included) and its model family from every remaining candidate's builder family; the winner is one of the remaining candidates. The losers become `NOT-SELECTED` and their lanes are owed the news — delivered to their mailbox by default (`mailbox.notify_on_verdict`), or listed by `lane_effects.py pending` when that is `false`.
- **No reviewer available**: `select --task TASK-1 --checker-unavailable --lane rev-x --model gpt-5.6-sol` records DEFERRED for the competition — never a winner.
- **A candidate's lane died**: `withdraw` takes it out of the undecided competition with a `--reason`; the item becomes `WITHDRAWN` (terminal), stops counting for readiness and selection, and its lane is owed the news — delivered to its mailbox by default, or listed by `lane_effects.py pending` when `mailbox.notify_on_verdict` is `false`. Refused: a decided task, a non-candidate or already withdrawn item, an empty reason, the last remaining candidate, and a coordinator lane that built a rival candidate. With exactly 1 candidate left, `select` of that one is allowed. `render` and `status TASK-1` show the withdrawal.
- The winner still goes through its ordinary review before MERGED: a selection compares attempts, it does not verify one.

## Process

1. **Claim the item** (you become the owner, role executor):
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py claim ITEM-1 --lane exec-a --model claude-opus-5-5
   ```
2. **Advance to BUILDING** while you work:
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py set ITEM-1 BUILDING --lane exec-a --role executor --model claude-opus-5-5
   ```
3. **When done, CHECKPOINT-READY with real evidence** (command + output pasted, not "done"):
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py set ITEM-1 CHECKPOINT-READY --lane exec-a --role executor --model claude-opus-5-5 --evidence "pytest -q: 42 passed, exit=0"
   ```
   Or attach the record of a run made with `python -m hpp evidence run` instead of pasted text (requires the HPP core, `python -m hpp`). The board asks the core to verify it and accepts only `valid` (an intact record of a passed run), storing `{path, record_sha256, id}`; `not-evidence` and `blocked` are refused (exit 1), and without the core the flag exits 2 — it never falls back to free text:
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py set ITEM-1 CHECKPOINT-READY --lane exec-a --role executor --model claude-opus-5-5 --evidence-record .hpp/evidence/<id>-<UTC>.json
   ```
4. **The reviewer (another lane, another model family) takes over and genuinely verifies** — NEVER accept "it's ready" without running:
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py set ITEM-1 UNDER-REVIEW --lane exec-a --role executor --model claude-opus-5-5
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py set ITEM-1 VERIFIED --lane exec-a --role reviewer --model gpt-5.6-sol --verdict-by-lane rev-a --verdict-by-model gpt-5.6-sol
   ```
5. **Merge** (human gate if `--tag red`):
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py set ITEM-1 MERGED --lane rev-a --role reviewer --model gpt-5.6-sol
   ```
6. **Render the snapshot** whenever you want to see the whole board:
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py render
   ```

## Executed examples

```console
$ python scripts/lane_board.py claim ITEM-1 --lane exec-a --model claude-opus-5-5
{"ts": "2026-07-10T15:56:30", "item_id": "ITEM-1", "state": "CLAIMED", "lane_id": "exec-a", "role": "executor", "model": "claude-opus-5-5", "tag": "green"}
```
<!-- executed: 2026-09-22 · exit=0 -->

```console
$ python scripts/lane_board.py set ITEM-1 BUILDING --lane exec-a --role executor --model claude-opus-5-5
$ python scripts/lane_board.py set ITEM-1 CHECKPOINT-READY --lane exec-a --role executor --model claude-opus-5-5 --evidence "pytest -q: 42 passed"
$ python scripts/lane_board.py set ITEM-1 UNDER-REVIEW --lane exec-a --role executor --model claude-opus-5-5
$ python scripts/lane_board.py set ITEM-1 VERIFIED --lane exec-a --role reviewer --model claude-opus-5-5 --verdict-by-lane exec-a --verdict-by-model claude-opus-5-5
lane_board: refused — maker≠checker violated: reviewer (exec-a) is the SAME lane as the builder (exec-a)
```
<!-- executed: 2026-09-22 · exit=1 -->
(after the full CLAIMED→BUILDING→CHECKPOINT-READY→UNDER-REVIEW cycle, the SAME lane trying to be the reviewer of its own work is refused IN CODE — it does not depend on discipline.)

```console
$ bash evals/collision-2lanes.sh 10
[OK] zero corruption: 10/10 valid lines, 10 distinct items, 0 processes with exit!=0
```
<!-- executed: 2026-09-22 · exit=0 -->
(10 concurrent processes writing to the SAME board — the lock serializes, zero corrupted lines.)

## Proof

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py --self-test
python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_dashboard.py --self-test
```
