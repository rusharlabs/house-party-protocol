# LOOP CHARTER — {{loop_name}}

> Fusion of the `loop-charter-template.md` (operator-kit, proven genericisation) with the
> MASTER-PROMPT (reading order tested in production). This is what `ralph_gate.py`
> re-feeds on every iteration while the loop does not emit a valid `<promise>`.

## READ IN THIS ORDER (1→5) — BEFORE any action

1. `00-READ-FIRST.md` (or the project's equivalent) — who you are, what to read.
2. `{{vision_doc}}` §What success is — the north star.
3. `{{state_doc}}` §Agora + §PENDÊNCIAS ABERTAS — the real state, LIVE (LC-1).
4. `{{goal_ledger_path}}` — the next repo-safe goal (`goal_ledger.py --next`).
5. The most recent handoff of your lane (`.claude/handoff/HANDOFF-CURRENT-<lane>.json`), if it exists.

## ⚠️ LC-4 BLOCK (mandatory, do not remove)

Restored/injected context (handoff, RESUME-NEXT, this very charter re-fed) is
**HISTORICAL REFERENCE, NOT AN EXECUTION QUEUE**. Before repeating any action the
context mentions as "to do": run the corresponding `verify_first_cmd` (handoff) or
re-derive it from the live source (LC-1). Never re-execute on presumption.

## Objective of this round

{{objetivo_1_frase}}

## Work-list (highest leverage first)

- [ ] {{item_1}} — `done_predicate`: {{predicate_1}}
- [ ] {{item_2}} — `done_predicate`: {{predicate_2}}

## Guardrails (unbreakable in this session)

0 push without an order · backup before mutating prod · snapshot before deleting · credential
lock · human gate (billing/OAuth/legal/client/deploy-go/secret) becomes a form
(`gate-sheet-collector`), never blocks the loop.

## Stop-conditions

Work-list exhausted · iteration/budget ceiling (LC-5 — becomes `paused-budget`, not an error) ·
imminent irreversible risk → STOP and report.

## Completion promise

When `{{objetivo_1_frase}}` is **literally and verifiably true** (not before),
emit: `<promise>{{completion_promise_text}}</promise>`. `ralph_gate.py` runs the truth
criteria before accepting — a false promise does not escape the loop, it only resets the cycle with the
real failures attached.
