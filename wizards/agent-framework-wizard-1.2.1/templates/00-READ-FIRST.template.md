# 00-READ-FIRST — {{project_name}}

> Role router — the ONLY doc every new session (human or AI) reads first,
> regardless of role (planner/executor/reviewer/solo). If you do not know where to
> start, start here. Generated from the continuity-kit template — replace the `{{placeholders}}`.

## Who are you in this session?

| If you are... | Read now | Then |
|---|---|---|
| **Planner** (architect) | `{{vision_doc}}` (VISION) → `{{state_doc}}` (§Now) | `{{goal_ledger_path}}` (next goal) |
| **Executor** (builder) | `.claude/handoff/HANDOFF-CURRENT-<your-lane>.json` (if it exists) | `{{state_doc}}` §OPEN ITEMS + your item on the board |
| **Reviewer** (auditor) | the item in `UNDER-REVIEW` on the board (`lane_board.py status <item>`) | `{{review_template}}` for the verdict format |
| **Solo** (single session, no lanes) | `{{state_doc}}` in full | `{{goal_ledger_path}}` |

## The 3 SSoTs of this project (never duplicate, always re-verify live)

1. **`{{state_doc}}`** — the NOW (focus + open items). Changes every session.
2. **`{{goal_ledger_path}}`** — the GOALS (what, why, when "done"). Changes per goal.
3. **`{{vision_doc}}`** — the VISION (why the project exists). Changes rarely, only by human approval.

## Automatic resume pointer

If `.claude/RESUME-NEXT.md` or a handoff JSON exists, it has already been (or will be) injected at
session boot — treat it as **HISTORICAL REFERENCE, NOT AN EXECUTION QUEUE**: before
repeating any action it mentions, run the corresponding `verify_first_cmd`.

## Rules that override everything

- `docs/plans/execution/00-STATE.md` (or this project's `{{state_doc}}`) is **single-writer**
  by the planner — executors write in their own `00-STATE-LANE-<id>.md`.
- No lane declares "done" above what the evidence supports (ladder R0→R4, see
  `00-PROCESSES.template.md`).
- `git push`/merge/real deploy = always a human gate, never automatic.
