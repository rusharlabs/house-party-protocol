[English](LANE-KIT.md) · [Português](LANE-KIT.pt-BR.md)

# lane-kit — N sessions, 1 repo, zero collisions

> See `scripts/lane_board.py` (whiteboard), `scripts/lane_dashboard.py` (the board as a local web page),
> `skills/lane-coordinator/SKILL.md` (usage),
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
3. The reviewer, at `VERIFIED` time, has to be from a lane AND a model family different from
   **every lane that built the item** (any `CLAIMED`/`BUILDING`/`CHECKPOINT-READY` event) — on
   purpose, so that neither the convergence of 2 builder lanes nor a fix routed to another
   executor (`release-fix`) becomes a self-approval loophole.
4. Use the `REORIENT-MAILBOX.template.md` for the lane entering the item to notify the one
   already on it (and vice versa) — the board records STATE, not the coordination conversation.

This mode is **optional and has no extra enforcement in the code** beyond what already exists —
it works because the state machine is already permissive enough for 2 builders on the same logical
lane; there is no need for a separate switchable "mode", it is the natural behaviour of the
board when 2 lanes cooperate on the same item_id.

## Operator hand-offs — routing a fix, opening a review

Two writes let the operator hand work to a named lane. Both check the registry (the target must be
registered, alive, and of the right role), both write a `## Para:` kickoff to the mailbox that
`lane_register.py` routes, and neither starts an agent — that is the dashboard's launcher, below.

1. **`release-fix <item> --target-lane <executor>`** turns a `NEEDS-FIX` into `FIX-QUEUED`
   (`NEEDS-FIX → FIX-QUEUED → BUILDING`). The kickoff carries the reviewer's direction and the
   previous checkpoint. Only the lane named may write the next `BUILDING`; `set` can never write
   `FIX-QUEUED`. **Reroute valve**: a fix queued for a lane that stopped beating can be released
   again to ANOTHER lane, and the event records `reroute` with the abandoned lane and the measured
   reason; a live lane's fix is never taken from it. The builder may still resume a `NEEDS-FIX`
   directly with `BUILDING` — routing is an option, not a new obligation.
2. **`start-review <item> --target-lane <reviewer>`** turns a `CHECKPOINT-READY` (or `DEFERRED`)
   into `UNDER-REVIEW` for a reviewer lane that did not build the item. The model family is checked
   where the verdict is recorded, as for every review: opening a review is cheap and reversible, and
   refusing it by family would make `DEFERRED` unreachable when no other family is at hand.

The tag of an item belongs to the item: once any event said `red`, `MERGED` needs
`--human-approved` whatever a later `--tag` says (a caller omitting the flag used to merge a red
item and record it as green).

## Lane Dashboard — the board in a browser, from any IDE

`scripts/lane_dashboard.py` serves the board as a local page (`127.0.0.1` only) that updates as
`board.jsonl` changes: the backlog of specs and the waves started from it, the columns, the lanes
and their heartbeat, the competitions, and the effects still owed to a lane. It is a READ-ONLY
observer in the sense of the convention above — it never edits `board.jsonl` or the registry
itself: every board write goes through `lane_board.py` and every lane through `_lane_io.py`, so it
is refused exactly what a lane would be. Its own artifacts are the wave requests
(`waves/<wave>.request.json`), the session prompts and logs (`sessions/`), the decision briefs
(`decision-briefs/`) and, when the operator adds a spec from the page, `BACKLOG.json`.

What it adds is the launcher. After a confirmation dialog it starts an agent session — Claude Code,
Codex, Gemini CLI or Cursor Agent, as found on PATH — in the operator's environment, detected from
where the dashboard runs: a terminal of the project's **Orca** worktree, a window of the **tmux** session
it runs in (or of the detached session `hpp-lanes` when there is no screen), a new window of the
system **terminal** (Terminal on macOS, the desktop's terminal on Linux, a PowerShell console on
Windows), or the agent's **headless** mode with a log. It never hands over a command to paste: a
session that does not start keeps its lane and its prompt, and starts again from the dialog. One
dashboard serves several projects and the worktrees of each — every `--project-dir`, the other
worktrees of its repository, and the Orca worktrees that use lane-kit — grouped by the git directory
they share, each worktree with its own board; the page shows every project, one project or one
worktree, and an action names its worktree by an id from the server's list, never by a path. The session gets `CLAUDE_LANE_ID/ROLE/MODEL`, so the lane hooks register it
under the right identity. A review can only be launched with an agent of another family than the
builders. A decision brief (options and a recommendation for a `NEEDS-FIX`, a `DEFERRED` or a red
`VERIFIED`) is asked of a headless agent of another family when the operator presses the button —
`--auto-brief` asks as soon as the item arrives — and it never acts on the board.

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
