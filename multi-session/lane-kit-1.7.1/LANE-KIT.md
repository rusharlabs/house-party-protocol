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
| `hooks/lane_register.py` | registers the lane at boot and lists its unread mail; the heartbeat announces mail that arrived mid-session, once per message | SessionStart (register) + PostToolUse (`--heartbeat`) |
| `hooks/lane_git_guard.py` | blocks `add -A`/`commit -a`/commit-without-pathspec/`stash`/`reset --hard`/`checkout .`/`--amend` when another lane is alive — the git index is **shared** between sessions | PreToolUse (`Bash`) |
| `hooks/lane_territory_guard.py` | WARN (never blocks) if the edited path is a red zone or the exclusive territory of another live lane | PreToolUse (`Edit\|Write`) |

Liveness: heartbeat &lt;10min=alive, 10-30min=suspect (guards degrade to warn even in
`block` mode), &gt;30min=dead (automatic evict, zero false positives in the guards). Config in
`templates/lanes.example.yaml` → copy to `.claude/lanes/lanes.yaml` (tracked in git).
Wiring: `install/wiring.settings.jsonc`. Rollout of the git-guard: **always** start in
`git_guard.mode: warn` for ≥1 week without a false positive before considering `block` (validate
with `evals/collision-git-guard.sh`, 3 green rounds). Territory (`evals/collision-territory-guard.sh`)
is always WARN-only — it never becomes `block`.

## Mailbox — the asynchronous post box between lanes

`.claude/lanes/mailbox/*.md` carries what the board cannot: a scope change in the middle of the
work and — since this version — every verdict. The contract, enforced in `lane_register.py` and
`lane_board.py` (proof: `evals/mailbox-e2e.sh`, 3 green rounds):

1. **Routing is a LINE.** `## To: <lane_id>` — one lane id, alone on the line; the legacy
   `## Para: <lane_id>` still routes. The match is whole-line with the id bounded: `exec-b` never
   receives `exec-bb`'s mail, and a routing line quoted inside the prose routes nothing.
2. **A lane is told once per message.** The register (SessionStart) lists every unread message; the
   heartbeat (PostToolUse `--heartbeat`) announces a message that arrived while the lane was running,
   on the first heartbeat that lands after it (a throttled beat waits), as
   `hookSpecificOutput.additionalContext`. What was announced is kept per lane in
   `mailbox/.announced/<lane_id>.json`, so neither half repeats the other; any failure inside the scan
   fails open — the heartbeat still lands and the hook prints `{}`.
3. **Read-and-archive.** The lane moves a read message to `mailbox/_read/`; nothing in `_read/` is
   ever announced, and a message is never edited in place.
4. **A verdict delivers itself** (`mailbox.notify_on_verdict`, default ON — a behaviour change of this
   version): VERIFIED, NEEDS-FIX, DEFERRED, NOT-SELECTED and WITHDRAWN write
   `<item>-<verdict>-<reservation_id>.md` to the builder lane and mark the reservation delivered with
   that path as evidence, idempotent by `reservation_id` (a retry writes nothing new, a new round writes
   its own). `false` restores delivery by hand (`lane_effects.py deliver`), with the reservation left
   pending on purpose.
5. **A Codex lane also gets a doorbell** (`mailbox.native_doorbell`, default ON): `codex queue --thread
   <its session id> --message "<path + item + verdict>"`, only when `codex` is on PATH, bounded (5s),
   no retry, fail-open — the outcome is recorded as `doorbell` beside the evidence and never changes the
   delivery. A Claude Code lane gets none: the host has no CLI that reaches a running session. HPP wires
   no hook on Codex CLI, so a Codex lane hears about ordinary mail when it runs
   `lane_register.py` (register or `--heartbeat`) itself.

```
## To: exec-a
## From: rev-a (reviewer, gpt-5.6-sol)
## When: 2026-09-27T14:53:43
## Affected item(s): ITEM-1
```

## Operator hand-offs and the Lane Dashboard

Three commands of the board are the operator's, and each writes one event (contributed with the Lane
Dashboard by @kleinelizeu, PR #18):

| Command | Transition | What makes it safe |
|---|---|---|
| `release-fix <item> --target-lane <executor>` | `NEEDS-FIX → FIX-QUEUED` | the target is registered, alive, an executor, and could build the item; only it may write the next `BUILDING`; a queued fix whose lane stopped beating is routed again with a `reroute` record |
| `start-review <item> --target-lane <reviewer>` | `CHECKPOINT-READY` / `DEFERRED → UNDER-REVIEW` | the target is registered, alive, a reviewer, and built no attempt at the item |
| `approve <item>` | `VERIFIED → APPROVED` | the item is red, verified, and its competition (if any) is decided; the event carries `human_approved` |

`FIX-QUEUED` and `APPROVED` are written only by these commands — `set` refuses both. `APPROVED` is the
human gate of a red item and **not** an integration: `MERGED` still comes after the merge
(`VERIFIED → APPROVED → MERGED`, or `VERIFIED → MERGED` for a green item, or with `--human-approved` in
one step). The hand-offs write a kickoff to the target's mailbox (`## To: <lane>`) and ring the Codex
doorbell like a verdict. `claim`/`set --branch <branch>` record the builder's branch on the build
events.

The **Lane Dashboard** (`scripts/lane_dashboard.py`) is a local page over the same files. It is not a
read-only observer in the sense of the next section: it acts — but only through the writers a lane uses
(`lane_board.py`, `_lane_io.py`), and every action it offers is a terminal command that does the same
(the table is in the README). It records `MERGED` only when `git cherry` shows the builder's branch in
the target. The page binds loopback, requires a per-run token on every action, refuses to be framed,
and starts an agent only when the operator confirms an action; a headless session runs under a
supervisor with a timeout, a stop and a capped log.

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
3. The reviewer, at `VERIFIED` time, still has to be from a DIFFERENT lane AND a different model
   family than **every lane that built the item** — every lane that wrote `CLAIMED`, `BUILDING` or
   `CHECKPOINT-READY` on it, not only the claimer — so that convergence of 2 builder lanes, or a fix
   rebuilt by an executor of another family, never becomes a self-approval loophole.
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
