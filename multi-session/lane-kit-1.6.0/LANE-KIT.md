[English](LANE-KIT.md) · [Português](LANE-KIT.pt-BR.md)

# lane-kit — N sessions, 1 repo, zero collisions

> See `scripts/lane_board.py` (whiteboard), `skills/lane-coordinator/SKILL.md` (usage),
> `evals/collision-2lanes.sh` (concurrency test), `templates/` (mailbox + status HTML).

## LANE-ENGINE — registry of live lanes + concurrency guards

Beyond the board (per-item state), the lane-kit keeps a **registry of live lanes**
(`.claude/lanes/registry.json`, runtime — never versioned) and two guards that consult
that registry before a risky action:

| Piece | Role | Hook |
|---|---|---|
| `hooks/_lane_io.py` | library: register/heartbeat/evict/who_owns/alive_count | (not a hook — imported by the 3 below) |
| `hooks/lane_register.py` | registers the lane at boot; warns about unread mailbox | SessionStart (register) + PostToolUse (`--heartbeat`) |
| `hooks/lane_git_guard.py` | blocks `add -A`/`commit -a`/commit-without-pathspec/`stash`/`reset --hard`/`checkout .`/`--amend` when another lane is alive — the git index is **shared** between sessions | PreToolUse (`Bash`) |
| `hooks/lane_territory_guard.py` | WARN (never blocks) if the edited path is a red zone or the exclusive territory of another live lane | PreToolUse (`Edit\|Write`) |

Liveness: heartbeat &lt;10min=alive, 10-30min=suspect (guards degrade to warn even in
`block` mode), &gt;30min=dead (automatic evict, zero false positives in the guards). Config in
`templates/lanes.example.yaml` → copy to `.claude/lanes/lanes.yaml` (tracked in git).
Wiring: `install/wiring.settings.jsonc`. Rollout of the git-guard: **always** start in
`git_guard.mode: warn` for ≥1 week without a false positive before considering `block` (validate
with `evals/collision-git-guard.sh`, 3 green rounds). Territory (`evals/collision-territory-guard.sh`)
is always WARN-only — it never becomes `block`.

## WATCH.log — read-only observability convention

Any READ-ONLY process that observes the board (dashboards, alerts, health cron) writes
what it saw to **`.claude/lanes/WATCH-<observer>.log`** — it NEVER edits `board.jsonl` nor the
artifacts of another lane. Golden rule: **"read-only produces its OWN artifact, never edits
someone else's"**. Line format (append-only, 1 line per observation):

```
<ISO-8601> <observador> <summary de 1 linha do que observou>
2026-07-10T16:00:00-03:00 status-dashboard-cron 3 lanes vivas, 2 itens em UNDER-REVIEW, 0 itens travados >30min
```

A `WATCH.log` that grows without ever being read is the sign of a dead observer — rotation/retention
is up to the target project (it is not part of the lane-kit contract).

## Per-role denies (extends the continuity-kit `settings-continuidade.template.json`)

The continuity-kit template `settings-continuidade.template.json` declares GENERAL continuity deny-rules (never
edit handoff/hooks from one's own session). The lane-kit EXTENDS this per ROLE, mirroring
the maker≠checker split: the reviewer is **physically read-only** (no `Write`/`Edit` in the `allowedTools` of the
reviewer session — the only writes allowed are `lane_board.py set ... VERIFIED|NEEDS-FIX|DEFERRED` and `lane_board.py select`,
via scoped `Bash`). The reviewer may also run `python -m hpp evidence verify` (requires the HPP
core): it only reads, and reconciles a record the builder attached with `--evidence-record`. It never
gets `hpp evidence run`, which writes a record and whatever the command writes — the record is
self-hashed, not signed, so a reviewer that must not trust the builder re-runs the record's command
from its own lane, outside this profile. Reference block (apply in the profile/allowedTools of the
reviewer session, not in the global settings.json — it is per-session config, not a human gate):

```yaml
role: reviewer
allowedTools: ["Read", "Glob", "Grep", "Bash(python scripts/lane_board.py set * VERIFIED:*)", "Bash(python scripts/lane_board.py set * NEEDS-FIX:*)", "Bash(python scripts/lane_board.py set * DEFERRED:*)", "Bash(python scripts/lane_board.py select:*)", "Bash(python -m hpp evidence verify:*)"]
# NEVER: Write, Edit, MultiEdit - enforces in code that a reviewer edits nothing
# NEVER: python -m hpp evidence run - it writes; a re-run belongs in the reviewer's own lane
```

Red zones (WARN for ALL lanes, any role): `.claude/settings*.json`,
`**/MEMORY.md`, `docs/plans/execution/00-STATE.md` (single-writer = planner — executors
write in their own `00-STATE-LANE-<id>.md`, never in the shared file).

## Optional mode — convergence of 2 lanes

When TWO lanes need to merge work on the SAME item (e.g. planner + executor
paired on a complex item), the convergence mode lets both appear in the item's
history WITHOUT violating maker≠checker:

1. Both do `CLAIMED`/`BUILDING` on the same `item_id` (the board accepts it — `_TRANSITIONS` allows
   `CLAIMED→CLAIMED` and `BUILDING→BUILDING`, each event carries the lane that recorded it).
2. `CHECKPOINT-READY` is only accepted from the lane that did the LAST `CLAIMED`/`BUILDING` (current
   enforcement rule) — that is, convergence is **sequential on the board** even if the real
   work is parallel: the lane that "closes" the checkpoint is whoever writes last.
3. The reviewer, at `VERIFIED` time, still has to be from a DIFFERENT lane+family than the
   **builder recorded in the original `CLAIMED` event** (not the last `BUILDING`) — the
   enforcement looks up the item's first `CLAIMED` event as "the builder", on purpose,
   so that convergence of 2 builder lanes does not become a self-approval loophole.
4. Use the `REORIENT-MAILBOX.template.md` for the lane entering the item to notify the one
   already on it (and vice versa) — the board records STATE, not the coordination conversation.

This mode is **optional and has no extra enforcement in the code** beyond what already exists —
it works because the state machine is already permissive enough for 2 builders on the same logical
lane; there is no need for a separate switchable "mode", it is the natural behaviour of the
board when 2 lanes cooperate on the same item_id.

## Competitions — N lanes attempt the same task, one winner

The opposite of convergence: instead of two lanes on ONE item, N lanes each build their OWN item
for the same task, and a reviewer keeps the best attempt. The board records it with three commands
(`compete`, `select`, `withdraw`) and two extra item states (`NOT-SELECTED`, `WITHDRAWN`):

1. **`compete --task T --items A,B[,C...]`** declares the items as candidates of `T`. Each must
   already be claimed and not finished, no builder lane (any lane that wrote `CLAIMED`/`BUILDING`/
   `CHECKPOINT-READY` on it) may be shared between two candidates — so the convergence mode above
   cannot pass one attempt off as two — an item competes in one task only, and a task is declared
   once.
2. **`select --task T --winner A`** needs every remaining (not withdrawn) candidate
   `CHECKPOINT-READY` with evidence, or `VERIFIED`, and a reviewer whose lane differs from EVERY
   builder lane of EVERY candidate — withdrawn ones included: a lane that attempted the task never
   judges it — and whose model family differs from the family of every remaining candidate's
   builders. The competition event keeps the winner, the losers, the withdrawn items, the reviewer,
   the reason and the evidence it compared.
3. The losers get a `NOT-SELECTED` item event: terminal, and no row of `_TRANSITIONS` lists it as a
   target, so `set` can never write it and a losing attempt can never move on to `MERGED`. Their
   lanes are owed the news through `lane_effects.py`, like any verdict.
4. A candidate cannot be `MERGED` while its task has no winner, even after its own `VERIFIED` —
   otherwise whoever finishes first wins without a comparison. The winner keeps its state and
   still needs its ordinary `VERIFIED` before `MERGED`: selecting compares, it does not verify.
5. **`select --task T --checker-unavailable`** records `DEFERRED` for the competition, never a
   winner; a later `select` with a reviewer decides it.
6. **`withdraw --task T --item C --lane <coordinator> --model <m> --reason "<why>"`** takes a
   candidate out of an undecided competition — the case where its lane died and the task would
   otherwise stay undecidable forever. It records a competition event (`state: WITHDRAWN`, `item`,
   `reason`) and a `WITHDRAWN` item event: terminal, written only by `withdraw`, and its lane is
   owed the news through `lane_effects.py` like `NOT-SELECTED`. The item stops counting for
   readiness and for selection. Refused: a decided task, an item that is not a remaining
   candidate (or was already withdrawn), an empty reason, the last remaining candidate (at least
   1 stays; with exactly 1 left, `select` of that one is allowed), and a lane that built a rival
   candidate. `render` and `status T` show the withdrawal.

Competition events live in `board.jsonl` beside the item events, with `kind: competition` and a
`task_id` instead of an `item_id`; `render` prints them under **COMPETITIONS**.
