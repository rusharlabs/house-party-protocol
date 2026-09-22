# LOOP-COST-BUDGET — LC-5 · Token/cost budget is a FIRST-CLASS STOP condition

> **Auto-Trigger:** When starting/declaring ANY autonomous loop (/goal, /loop, ralph-loop, multi-wave workflow, continuously running cron, squad dispatch in batch) — BEFORE firing the 1st iteration; and at every checkpoint of the loop before continuing.
> **Keywords:** "loop", "/goal", "/loop", "ralph", "ralph-loop", "autonomous", "auto mode", "maximum capacity", "100%", "budget", "token budget", "budget_tokens", "budget_custo", "cost", "kill-switch", "killswitch", "blow the budget", "weekly limit", "rate limit", "quota", "subscription", "pay-per-use", "stop loop", "stop condition", "circuit breaker", "wave", "batch", "iteration"
> **Priority:** HIGH
> **Version:** 1.0.0 (generalized for the operator-kit)
> **Origin:** token/cost budget as a FIRST-CLASS STOP condition, distilled into a rule — registered as **LC-5**. Extension of `learned-corrections.md` (LC-1/LC-2/LC-3 + LC-4 in `stale-replay-guard.md`). Universal: applies to any autonomous loop. Counterweight to LC-2 ("do everything 100%" — but within the budget).

---

## LC-5 · Every loop declares its budget BEFORE running; blowing the budget STOPS the loop

An autonomous loop without an explicit budget is a loop without brakes. Tokens and cost are NOT a "side effect" of the work — they are a **finite resource** whose exhaustion is a **first-class stop condition**, on the same level as `done_predicate` (objective reached) and `circuit breaker` (repeated failure). A loop may end for THREE legitimate reasons: (1) it **completed** the objective, (2) it **stalled** (circuit breaker), or (3) it **blew the budget** (cost kill-switch). The third is as valid and as mandatory as the first two.

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  BUDGET BLOWN = LEGITIMATE STOP (not a failure, not giving up)               ║
║                                                                              ║
║  done_predicate satisfied      →  STOP · objective reached                   ║
║  circuit breaker (N failures)  →  STOP · loop stalled, escalate to operator  ║
║  budget_tokens/cost blown      →  STOP · kill-switch · report and wait       ║
║                                                                              ║
║  Loop without a declared budget = loop FORBIDDEN to start.                   ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

### 1. DECLARE the budget before the 1st iteration (mandatory)

Every autonomous loop declares, in its ledger/state/header, BEFORE firing:

| Field | What it is | Conservative default |
|-------|---------|---------------------|
| `budget_tokens` | Ceiling of tokens consumed by the whole loop (sum of the iterations) | Set it explicitly — no magic default |
| `budget_custo` | Ceiling of equivalent monetary cost, when trackable | `0` in a subscription-only regime (see §3) |
| `budget_iteracoes` | Ceiling of iterations/waves before a mandatory checkpoint | ≤ 3 waves (avoids blowing the rate limit in a burst) |
| `budget_tempo` | Maximum wall-clock window before pausing and reporting | Declare it (e.g. "until X" or "N hours") |
| `consumido_ate_agora` | Live counter of what has already been spent (updated every iteration) | `0` at the start |

Without these fields declared, the loop **does not start** — propose the budget to the operator and wait, or apply the conservative defaults above and DECLARE that you did.

### 2. KILL-SWITCH on blowing it (mandatory)

At every loop checkpoint (end of iteration/wave), BEFORE continuing:

1. Update `consumido_ate_agora` (tokens/cost/iterations/time) with the REAL number — audited live (LC-1), never estimated from memory.
2. Compare with the declared budget.
3. **If `consumido_ate_agora >= budget_*` in ANY dimension → KILL-SWITCH:**
   - STOP the loop immediately (do not start the next iteration).
   - Do NOT re-fire, NO "just one more" (that is exactly what the budget exists to stop).
   - Report to the operator: what was done, what it cost (real), what is missing, and the additional budget needed to finish.
   - Wait for explicit authorization to extend the budget — extending the budget is the operator's decision, never self-granted by the loop.
4. Record the budget stop in the ledger as a legitimate end (status `paused-budget`), not as a silent failure.

```
IF consumed >= budget in any dimension:
   → KILL-SWITCH · stop NOW · report the real numbers · wait for the operator
ELSE:
   → continue to the next iteration (within the budget)
```

### 3. Billing regime declared in the profile (never escalate on your own to a more expensive provider)

The cost regime (fixed subscription vs pay-per-use vs quota shared across processes) is
an operator decision, declared in the profile — not something the loop decides on its own when
things get tight:

- **FORBIDDEN** to switch provider/key to "gain more budget" when the loop blows it —
  the kill-switch does NOT authorize working around the limit that way. Blown = stop and report; not =
  "open the paid tap".
- **If the regime is a subscription with a quota shared** across multiple processes/agents (e.g.
  a 24/7 cron and an interactive session sharing the same account), the loop's real budget is the
  fraction of the quota it can consume without starving the other processes. `budget_custo` in that
  regime is a fraction of the quota, not money — declare how much of the window the loop may burn and stop
  on reaching it.
- If the loop needs more volume and blew the quota, the way out is to **delegate to an alternative provider/account
  already authorized in the profile** (if any) OR pause and report — never escalate
  to pay-per-use without explicit operator authorization.
- Do not blindly trust quota monitors with fragile parsing — audit the real consumption
  live (LC-1) before declaring "quota blown" or "quota ok".

### 4. Healthy COUNTERWEIGHT to LC-2 (do 100% — but within the budget)

`LC-2` says to really execute, 100% in batch, without stalling, when the operator authorizes
("maximum capacity", "/goal", "finish everything 100%"). This rule does NOT contradict LC-2 — it
**bounds** it:

```
LC-2:  "execute the WHOLE scope, 100%, no half-executions"
LC-5:  "...within the declared budget. Blew the budget BEFORE
        finishing 100%? → stop, report the real gap, and ask for more budget —
        do not stall, but do not burn the whole budget blindly either."
```

"100% effort" and "100% of the scope in this window" are not the same thing when the resource is
finite. The perfect behavior is: really go deep (LC-2) **up to** the budget, and on
hitting the ceiling, make the honest, traceable stop (LC-5) — report exactly where it stopped and
what it cost, so the operator can decide to extend. Blowing the budget in silence (without
reporting) violates LC-5; stopping short of the scope "to save" without authorization violates LC-2. The
balance is: **maximum effort within the declared envelope, transparent stop at the limit.**

---

## Checklist (before starting ANY loop)

```
[ ] budget_tokens declared? (no magic default)
[ ] budget_custo declared? (0 in subscription-only, or a fraction of the shared quota)
[ ] budget_iteracoes / budget_tempo declared? (≤3 waves default)
[ ] consumido_ate_agora initialized and to be updated at every checkpoint (LC-1: real)?
[ ] kill-switch defined: blew any dimension → STOP + report + wait for the operator?
[ ] FORBIDDEN to switch provider/key to escape the limit without authorization?
[ ] Volume fallback (if any) is an already-authorized account/provider, not surprise pay-per-use?
[ ] Budget stop recorded as a legitimate end (paused-budget), not a failure?
```

```
⚠️ LOOP WITHOUT A BUDGET = LOOP WITHOUT BRAKES = FORBIDDEN TO START
⚠️ BUDGET BLOWN = FIRST-CLASS STOP (same as done_predicate / circuit breaker)
⚠️ BLOWN ≠ "open the paid tap" — the declared limit IS the limit
```

---

*Token/cost budget as a first-class stop condition. Universal — applies to
any LLM that runs autonomous loops. Pairs with `learned-corrections.md` LC-2 (counterweight) and
`loop-operator.md` (trigger 3). Live quota/cost state = audit LIVE (LC-1).*
