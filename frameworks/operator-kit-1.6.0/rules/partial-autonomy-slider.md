---
paths:
  - "agents/**/*"
  - ".claude/agents/**/*"
  - "**/AGENT.md"
  - "**/operator-profile.yaml"
---
# Partial Autonomy Slider Protocol

> **Status:** ACTIVE (generalized for the operator-kit)
> **Keywords:** "autonomy" · "autonomy_level" · "human in the loop" · "auto mode" · "approve"
> **Priority:** HIGH

## The pattern

Design the system so an agent's autonomy can slide along a spectrum instead of flipping between fully manual and fully automatic.

UX pattern: a slider that regulates the AI's autonomy level · conservative tab-complete → full agent mode.

## Application to a multi-agent ecosystem

Each agent (CARGO · MINDS · SYSTEM) receives an `autonomy_level` field (0-5) declaring how much it may act without a human in the loop.

```yaml
# In the AGENT.md frontmatter
---
name: closer
type: cargo
autonomy_level: 2  # default conservative
autonomy_history:
  - level: 1
    start: 2026-04-01
    end: 2026-05-01
    reason: "initial onboarding"
  - level: 2
    start: 2026-05-01
    reason: "7 days clean · promoted"
---
```

## The 6 levels (0-5)

| Level | Name | Behavior | Use case |
|-------|------|---------------|----------|
| **0** | Suggest-only | Only proposes · NEVER executes · the operator always approves | New agents · sensitive areas (contracts · payments · DELETE SQL) |
| **1** | Approve-each | Executes after per-action approval · default for `awaits_max_scope` | Crons creating deliverables · new clients |
| **2** | Approve-batch | Batch approval (N actions) · default safe | **DEFAULT for new agents** |
| **3** | Approve-summary | Reports a post-execution summary · no block | Routine crons (briefing · digest · health) |
| **4** | Trusted-auto | Executes autonomously · audit log mandatory | After a 7-day clean record + verifiable success |
| **5** | Full-auto | Executes + auto-recovery · only alerts on failures | Only after 30 days clean + zero false positives |

## Promotion criteria (going up a level)

To promote from level N to N+1:
1. **Time minimum:** 7 days at the current level
2. **Eval pass rate:** ≥80% over the last 50 outputs. For an agent whose output is a choice
   (a label from a fixed set), promotion reads `python -m hpp decide eval <suite.json>` (HPP core):
   selective accuracy, confident errors = 0, instrument failures counted apart. Its
   `hpp.decision/v1` records stay advisory — a decision may raise a block, never grant a pass.
3. **Zero incidents:** no regression / rollback / operator correction
4. **Verifiability:** outputs with a testable success criterion
5. **Audit trail:** logs recorded in your audit log or cron logs

Demotion (going down a level) is AUTOMATIC on:
- Incident detected (false positive / regression / data loss)
- Explicit operator correction ("don't do X")
- Eval pass rate drops below 60%

## Connection with an API authentication tier (if there is one)

An eventual 3-tier auth (admin/service/public) is an **API auth** tier, not an autonomy level. Combined:

```
agent.autonomy_level=4 + caller.auth_tier=service → OK (executes)
agent.autonomy_level=2 + caller.auth_tier=public  → DENY (a high level requires auth)
agent.autonomy_level=0 + any caller               → proposes · does not execute
```

## Implementation by phase (suggested incremental rollout)

### Phase 1 — pilot
- Canonical doc (this file) + the mechanism that consults `autonomy_level` before dispatching an action
- A small pilot group of agents/crons receives `autonomy_level` (manual seeding)

### Phase 2 — migration
- All the agents in your ecosystem (LIVE count, never hardcoded) receive initial level=2 (conservative)
- Periodic promotion job (auto-promotes if the criteria pass)
- Automatic demotion on incident

### Phase 3 — observability
- Panel showing each agent's level
- Change history
- Manual override via your operations channel's command, if applicable

## Initial default level

All agents start at **level 2 (Approve-batch)** except:
- **Sensitive areas (contracts · financial · DELETE):** level 0 forced
- **Heartbeat/monitoring crons (read-only):** level 4 OK
- **Health-sync (snapshot only):** level 3 OK

## Why the level is set per agent

- Competence is uneven: an agent can be reliable at one task and unreliable at the next, so the level is calibrated per agent and per area, never globally.
- Delegating execution does not delegate understanding: at any level, someone must still be able to explain what the agent did and why.

## Dimension 2 — Intensity (lite/full/ultra/off)

`autonomy_level` (above) answers **"how much human approval does this action need?"**. Intensity
answers an ORTHOGONAL question: **"how much verification/machinery runs per action?"**. The two
dimensions are independent — an agent can have high autonomy and low intensity (acts alone,
but with little checking) or low autonomy and maximum intensity (needs approval for every step, but
when it acts, it verifies everything).

```
              autonomy_level (WHO approves)          intensity (HOW MUCH is verified)
              ─────────────────────────────          ────────────────────────────────
level 0-5     suggest-only  →  full-auto             lite  →  full  →  ultra  (→ off)
```

| Mode | Verification per action | When to use |
|---|---|---|
| **lite** | Only the essential — minimum acceptance criterion, no extra passes | Fast/exploratory iteration, disposable prototyping |
| **full** | Standard complete verification (`done_gate`/`verify_ladder` at the mandatory levels) | **DEFAULT** — normal work |
| **ultra** | Maximum verification — multiple passes, cross-model checker always (`loop-maker-checker`), determinism (`determinism_harness`) | Release-critical, sensitive path (financial/DELETE/live engine), promotion of an agent to `autonomy_level` 4-5 |
| **off** | Zero extra verification beyond what the language/runtime already forces | **Emergency/debug only — NEVER the default, never in production** |

**Configuration:** `intensity.default: full` in `operator-profile.yaml` (see the `profile.example.yaml` section
of this kit). Mechanisms that today read `verification.*`/`ladder_min_score` may in the future scale
the rigor based on this field — the scope of this doctrine is the vocabulary + the config, not (yet) an
automatic consumer.

**Combination with `autonomy_level` (the matrix that matters):**

```
autonomy HIGH (4-5) + intensity OFF   →  ⚠️ DANGEROUS — the agent acts alone AND without checking. Explicitly
                                          discouraged; if it appears, treat it as an incident
                                          (automatic demotion of autonomy_level, see above).
autonomy HIGH (4-5) + intensity FULL  →  the normal combination of a "trusted" agent in steady state.
autonomy LOW (0-1) + intensity OFF    →  acceptable only in local debug, never against a sensitive path.
autonomy LOW (0-1) + intensity ULTRA  →  the most conservative pair — use in release-critical work
                                          while the agent still has no promotion history.
```

**Counterweight to LC-2 (`learned-corrections.md`):** "execute 100%, no stalling" when the operator
authorizes broad execution (`/goal`, "maximum capacity") does NOT waive the chosen verification
intensity. "100% effort" and "zero verification" are not the same thing — LC-2 says to go deep
*within* the current intensity mode, never to use it as an excuse to lower `intensity`
to `off` without an explicit decision.

## Objectives, not transitions

The level says *who approves*. It does not say what you hand the agent, and handing it a
transition is the mistake that makes every level behave badly. An agent driven as a rigid node
in a state machine — "run step 4, then move the item to review" — treats the move as the
deliverable, and the move is the one thing it can always accomplish. Give it the **objective**
and the **quality bar** instead, and let the status follow: the item advances when the bar is
met, and the bar is a check someone can run, not the agent's own report that it finished.

```
✗ "execute the migration step and set the task to done"
      the transition IS the instruction -> done becomes a thing the agent SAYS
✓ "the table is migrated with zero rows lost; the count matches before and after"
      the objective is the instruction -> done becomes a thing a command DECIDES
```

This is the doctrinal half of a declarative done gate: the gate answers *is the bar met*, and
this rule says the agent is never the one who answers it. A level-5 agent still does not move
an item whose bar has not been checked — high autonomy buys fewer approvals, never a
cheaper definition of done.

## Anti-patterns

- ❌ **Transition as the task:** the instruction names a status move instead of an outcome
- ❌ **All-or-nothing:** binary `manual` vs `auto` — use the slider
- ❌ **Level 5 default:** always start conservative
- ❌ **No demotion:** if something went wrong, the level goes down automatically
- ❌ **Level without an audit log:** no trail = invisible regression

## Sample agent config (post-phase 2)

```yaml
# agents/cargo/sales/closer/AGENT.md
---
name: closer
type: cargo
autonomy_level: 2
last_eval_pass_rate: 87
last_promotion: 2026-05-01
last_demotion: null
incidents_count_30d: 0
---
```

```yaml
# agents/minds/example-advisor/AGENT.md
---
name: example-advisor
type: mind
autonomy_level: 3  # advisory-only · safe default
last_eval_pass_rate: 95
---
```

---

*Autonomy slider for a multi-agent ecosystem.*
