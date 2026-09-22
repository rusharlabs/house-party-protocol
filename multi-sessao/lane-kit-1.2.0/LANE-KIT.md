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
<ISO-8601> <observador> <resumo de 1 linha do que observou>
2026-07-10T16:00:00-03:00 status-dashboard-cron 3 lanes vivas, 2 itens em UNDER-REVIEW, 0 itens travados >30min
```

A `WATCH.log` that grows without ever being read is the sign of a dead observer — rotation/retention
is up to the target project (it is not part of the lane-kit contract).

## Per-role denies (extension of artifact 15 — `settings-continuidade.template.json`)

Artifact 15 of the TEMPLATE-SET (PHASE 7) declares GENERAL continuity deny-rules (never
edit handoff/hooks from one's own session). The lane-kit EXTENDS this per ROLE, mirroring
table §2.1: the reviewer is **physically read-only** (no `Write`/`Edit` in the `allowedTools` of the
reviewer session — the only write allowed is `lane_board.py --set ... VERIFIED|NEEDS-FIX|DEFERRED`,
via scoped `Bash`). Reference block (apply in the profile/allowedTools of the reviewer session,
not in the global settings.json — it is per-session config, not a human gate):

```yaml
papel: revisora
allowedTools: ["Read", "Glob", "Grep", "Bash(python scripts/lane_board.py set * VERIFIED:*)", "Bash(python scripts/lane_board.py set * NEEDS-FIX:*)", "Bash(python scripts/lane_board.py set * DEFERRED:*)"]
# NUNCA: Write, Edit, MultiEdit — reforça em código o "revisora não edita nada" da tabela §2.1
```

Red zones (WARN for ALL lanes, any role): `.claude/settings*.json`,
`**/MEMORY.md`, `docs/plans/execucao/00-STATE.md` (single-writer = planner — executors
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
