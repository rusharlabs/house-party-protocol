[English](RALPH-GATE.md) · [Português](RALPH-GATE.pt-BR.md)

# /ralph-gate — the Ralph that does not accept a promise without proof

> See `hooks/ralph_gate.py` (engine+lock), `commands/ralph-gate.md` (launcher),
> `evals/ralph-gate-T1-T4.sh` (signature test, pass^k=1.00 at k=3).

## The pitch (1 paragraph)

The official `ralph-loop` plugin (Anthropic) has the right mechanics: a Stop hook `decision:block`
that re-feeds the prompt until the model emits `<promise>TEXT</promise>`. But the "done" there is
**self-declared by a text tag, without running anything** — the `stop-hook.sh` compares a string and releases.
Our `done_gate.py` demands a **real exit code 0** on N commands. `/ralph-gate` merges the
two: the `<promise>` only unlocks the exit if the `done_gate` passes, **re-executed INSIDE the
hook's process** — after the model has spoken, out of its reach. The model can forge
any text in the transcript (including faking "DONE-GATE: DONE (2/2)"); it cannot forge the
exit code of a harness subprocess. The proof of that = test T3 (`evals/ralph-gate-T1-T4.sh`).

## Mode A — unified (DEFAULT, no dependencies)

`hooks/ralph_gate.py` is the engine AND the lock in the SAME Python process (stdlib only). Zero jq,
zero bash, zero race between "removing the state" and "validating the promise". It is the mode this kit
uses by default (wired in `hooks/hooks.json` → `Stop`, `timeout: 120`).

Why NOT use the official plugin as the engine by default:
- **DOA on machines without `jq`** — `stop-hook.sh` uses `jq` in 3 places + `set -euo pipefail`;
  without `jq` in the PATH, it crashes silently on the very 1st iteration (verified on this machine 2026-07-10).
- **Coupling bug** — the official `stop-hook.sh` runs `rm` on the state file
  (`.claude/ralph-loop.local.md`) **upon seeing the `<promise>`, BEFORE any veto**. If an
  external lock rejected AFTERWARDS, the engine would already be dead — there is no way to re-arm cleanly.

## Mode B — official + re-arm sidecar (OPT-IN, dependency check mandatory)

For those who already use the official `ralph-loop` plugin and only want to ADD the `done_gate` lock
on top, without switching engines:

1. **Dependency check first:** `command -v jq` and `command -v bash` in the target runtime's PATH.
   Without both, Mode B is not viable there — fall back to Mode A.
2. Keep the official `stop-hook.sh` as is.
3. Add a **sidecar** that runs BEFORE the official hook on the same Stop event (the order of the
   hooks in the array matters — the sidecar comes first):
   - Reads `.claude/ralph-loop.local.md` (frontmatter: `completion_promise`).
   - If the last transcript message contains the promise **AND** the `done_gate` criteria
     (declared separately, e.g. `.claude/ralph-gate.criteria.json`) **fail**: the sidecar
     **rewrites** `.claude/ralph-loop.local.md` with the promise **temporarily empty**
     (`completion_promise: ""`) and injects the failure reasons at the top of the file — so,
     when the official `stop-hook.sh` runs next, it will NOT match the promise (an empty
     string never matches) and will re-feed the loop with the updated content.
   - If the criteria PASS: the sidecar touches nothing — the official one releases normally.
4. This is a **workaround**, not a fix for the coupling bug: if the official hook already ran
   and deleted the file BEFORE the sidecar (order swapped), Mode B protects nothing in that
   cycle. **The order of the hooks in the array is the real guarantee — not an optional convention.**

Mode B stays **documented, not implemented as code in this kit** — it is for those who already have
an investment in the official plugin and accept the ordering risk above. Mode A (default) does not
have that risk because engine and lock are the SAME process.

## Goal-by-goal integration

```
goal_ledger.py --next  →  /ralph-gate --goal G-X --criteria "<PRD DoD>" --charter "..."
   → done_gate passes  →  --set G-X done  →  goal_review.py --goal G-X  →  next goal
```

The `--goal` criteria come from the PRD's DoD via `goal_review.extract_criteria` (a chain that already
passes `--self-test` in isolation). Kill-switches by reference: `loop-operator.md` (4
stop-conditions), `loop-cost-budget.md` (LC-5 — the iteration ceiling IS the budget
mechanically enforceable by a Stop hook; token/$ cost is tracked outside, by the session that
calls `/ralph-gate`), `stale-replay-guard.md` (LC-4 — before re-arming a goal, check that
it is not already `done` in the ledger).
