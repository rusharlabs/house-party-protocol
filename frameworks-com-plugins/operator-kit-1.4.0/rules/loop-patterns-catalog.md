# LOOP-PATTERNS-CATALOG — The 6 autonomous-loop architectures mapped to this kit's gates

> **Auto-Trigger:** When DESIGNING/CHOOSING the architecture of an autonomous loop (before arming /goal, /loop, ralph-loop, a squad in batch, a multi-wave workflow, a `claude -p` pipeline) — when the question is "WHICH loop shape to use for this task?", not "may this loop run?" (that one is `loop-operator.md`).
> **Keywords:** "which loop", "what kind of loop", "loop architecture", "design loop", "choose loop", "sequential pipeline", "claude -p pipeline", "nanoclaw", "repl", "infinite agentic loop", "agentic loop", "continuous claude", "pr loop", "de-sloppify", "desloppify", "slop", "ralphinho", "rfc-dag", "rfc dag", "dag", "merge queue", "work unit", "decomposition", "decompose", "wave", "waves", "parallel agents", "worktree loop", "loop catalogue", "loop patterns"
> **Priority:** MEDIUM
> **Version:** 1.0.0 (generalized for the operator-kit)
> **Origin:** Distilled from the public "ECC" catalogue (Excellence Compounding Cycle, github.com/affaan-m/ECC, MIT, © Affaan Mustafa) — 6 autonomous-loop patterns (Sequential Pipeline · NanoClaw REPL · Infinite Agentic Loop · Continuous Claude PR Loop · De-Sloppify · Ralphinho/RFC-DAG). This rule is the **CATALOGUE OF SHAPES** (which loop to use); this kit's `loop-*` rules are the **GATES of any loop** (budget, maker≠checker, pass@k, stop-conditions, replay). Catalogue ⊕ gates = a safe loop with the right shape.

---

## PRINCIPLE

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   FIRST choose the SHAPE of the loop (this catalogue). THEN apply the GATES  ║
║   (the loop-* rules). Wrong shape = a loop that grinds in the wrong pattern; ║
║   missing gate = a loop that grinds without brakes. Both together, always.   ║
║                                                                              ║
║   Every loop in this catalogue GOES THROUGH this kit's unbreakable gates:    ║
║   • pre-flight + 4 stop-conditions ........ loop-operator.md                 ║
║   • token/cost budget (LC-5) .............. loop-cost-budget.md              ║
║   • maker ≠ checker cross-model ........... loop-maker-checker.md            ║
║   • pass@k / pass^k before promoting ...... loop-passk.md                    ║
║   • restored context ≠ queue (LC-4) ....... stale-replay-guard.md            ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

## SPECTRUM OF THE 6 PATTERNS (from simplest to most sophisticated)

| # | Pattern | Complexity | Best for |
|---|--------|--------------|-------------|
| 1 | Sequential Pipeline (`claude -p`) | Low | Daily dev steps, scripted workflow, fresh context per stage |
| 2 | NanoClaw REPL | Low | Persistent interactive session, context accumulated per turn |
| 3 | Infinite Agentic Loop | Medium | Parallel generation of N variations of a spec (uniqueness by assignment) |
| 4 | Continuous Claude PR Loop | Medium | Iterative multi-day project with a CI gate + automatic merge |
| 5 | De-Sloppify | Add-on | Dedicated cleanup step after any Implementer |
| 6 | Ralphinho / RFC-DAG | High | Large feature, N interdependent units, merge queue with eviction |

> ⚠️ **Do NOT duplicate the mechanism:** this catalogue is a DESIGN reference (which SHAPE to use). The
> gates that guarantee any shape runs safely (budget, maker≠checker,
> anti-replay) live in this kit's other `loop-*` rules — use this catalogue to choose the
> SHAPE; use those to RUN safely.

---

## DECISION TREE (which pattern to use)

```
Is the task a single, focused change?
├─ YES → Sequential Pipeline (1) or NanoClaw REPL (2)
└─ NO → Is there a written spec/RFC?
          ├─ YES → Does it need PARALLEL implementation of interdependent units?
          │         ├─ YES → Ralphinho / RFC-DAG (6)
          │         └─ NO → Continuous Claude PR Loop (4)
          └─ NO → Does it need MANY variations of the same thing?
                    ├─ YES → Infinite Agentic Loop (3)
                    └─ NO → Sequential Pipeline (1) + De-Sloppify (5)
```

---

## 1 · SEQUENTIAL PIPELINE (`claude -p`)

**What it is.** The simplest loop: break the work into a SEQUENCE of non-interactive `claude -p` calls, each a focused step with a clear prompt (implement → de-sloppify → verify → commit). Each call = a FRESH context window (zero context bleed between steps). `set -e` propagates the exit code and stops the pipeline on failure. Supports model routing (`--model opus` for research/review, sonnet for implement) and `--allowedTools` for read-only vs write-only passes.

**When to use.** Scripted daily dev steps; a known linear path; when you want context isolation between stages; CI/CD integration (it is the best fit for a pipeline). Do NOT use for exploratory multi-variation work (→ #3) or parallel interdependent units (→ #6).

**Links to this kit's gates:**
- **`loop-maker-checker.md`** — the pipeline's "review" step MUST be the cross-model, read-only CHECKER, BEFORE commit/push. RULE 0 (YAGNI ladder) governs the "implement" step.
- **`loop-cost-budget.md` (LC-5)** — each `claude -p` consumes quota; declare `budget_iteracoes`/`budget_tempo` BEFORE; `set -e` is an error brake, NOT a budget brake — add the cost kill-switch.
- **`loop-operator.md`** — pre-flight (baseline+rollback+branch) before the 1st step; a negative instruction is dangerous (it leaves the model hesitant about everything else) — use a separate step (#5), not a restrictive prompt.

---

## 2 · NANOCLAW REPL

**What it is.** Persistent loop: a session-aware REPL that calls `claude -p` synchronously with the FULL conversation history. Loads history from a session file, appends each reply (Markdown-as-database), sessions survive restarts. Context ACCUMULATES per turn (≠ Sequential, which is fresh per step).

**When to use.** Interactive exploration with session memory; when context must grow between turns; a poor fit for CI/CD (use #1 for automation).

**Links to this kit's gates:**
- **`stale-replay-guard.md` (LC-4)** — a persistent REPL is EXACTLY the "restored context" case. The appended history describes the PAST; NEVER re-fire an action the history mentions as "to do" without verifying live (idempotency).
- **`loop-cost-budget.md`** — context that grows per turn = quota consumption that grows per turn; a turn/time ceiling is mandatory.

---

## 3 · INFINITE AGENTIC LOOP

**What it is.** A TWO-PROMPT system for parallel spec-driven generation. PROMPT 1 (Orchestrator): reads the spec, scans the output dir to find the highest iteration, plans, ASSIGNS each sub-agent a unique creative direction + a specific iteration number (no conflict), manages waves. PROMPT 2 (Sub-agents): receive spec+context, generate a unique output, save. Batching: 1-5 simultaneous · 6-20 in batches of 5 · "infinite" in waves of 3-5 with progressive sophistication until the context runs out. **Key insight: uniqueness by ASSIGNMENT** — the orchestrator assigns direction+number, it does not trust the agent to self-differentiate (avoids duplicate concepts across parallel runs).

**When to use.** Generating N variations of the SAME thing from a spec (UI components, creatives, design options); spec-driven work with parallelism. NOT for a single change (#1) or interdependent units (#6).

**Links to this kit's gates:**
- **`loop-operator.md`** — "waves of 3-5" avoids blowing the rate limit; the pre-flight's `budget_iteracoes` bounds the "infinite". Stop-condition #1 (2 checkpoints without progress) cuts the wave that stops producing new variation.
- **`loop-cost-budget.md`** — "infinite until the context runs out" is cost-drift by construction; convert "infinite" into an explicit `budget_iteracoes`/`budget_tokens`.
- "Uniqueness by assignment" resolves the collision of two agents writing the same path — assign a lane/output per agent before firing (see `lane-kit`, if installed, for an explicit territory mechanism).

---

## 4 · CONTINUOUS CLAUDE PR LOOP

**What it is.** A production-grade shell script that runs Claude in a continuous loop: create branch → `claude -p` → (optional) reviewer pass → commit → push + `gh pr create` → wait for CI → CI failed? auto-fix pass → merge → back to main → repeat. **Critical innovation: a shared notes file** persists across iterations (the model reads it at the start, updates it at the end) — a context bridge between independent `claude -p` invocations. Limits: `--max-runs` · `--max-cost` · `--max-duration` · completion signal (3 consecutive signals = stop, avoids running on finished work). CI-failure recovery = grab the run id, spawn `claude -p` with the log context, fix, wait again.

**When to use.** Iterative multi-day project with a CI gate; when you want automated PR+merge. Install third-party scripts only AFTER reviewing their content; NEVER pipe something external straight into bash.

**Links to this kit's gates:**
- **`stale-replay-guard.md` (LC-4):** the shared ledger/notes are a reference; do NOT re-fire an item already marked done — idempotency.
- **`loop-cost-budget.md` (LC-5):** `--max-cost`/`--max-runs`/`--max-duration` ARE exactly this rule's `budget_*` — under your declared billing regime, "blown" never authorizes escalating to pay-per-use on its own.
- **`loop-maker-checker.md`:** the "reviewer pass" MUST be cross-model, not the same model re-reading its own code; gate BEFORE the merge.
- **`loop-operator.md`:** "completion signal" = your `done_predicate`; "auto-fix on CI failure" — MIND stop-condition #2 (identical stack trace 2× = abort, not blind auto-retry).

---

## 5 · DE-SLOPPIFY (add-on)

**What it is.** An add-on pattern for ANY loop: after each Implementer step, a dedicated CLEANUP step (separate context, focused on removing slop). Problem it solves: a model doing TDD takes "write tests" too literally → tests the type system, redundant defensive checks, tests framework behavior instead of business logic, excessive error handling. **Why NOT use a negative instruction** ("do not test types"): it has a downstream effect — the model becomes hesitant about EVERY test and skips legitimate edge cases. **Solution:** let the Implementer be thorough; then a focused cleanup agent removes the slop and runs the suite. *"Two focused agents beat one restricted agent."*

**When to use.** After any implementation step in any loop (#1, #4, #6). It is a step, not a loop.

**Links to this kit's gates:**
- **`loop-maker-checker.md` RULE 0 (YAGNI ladder):** De-Sloppify is the **post-code complement** of the ladder (which is pre-code). The ladder prevents creating slop; de-sloppify removes what escaped. Same scope as RULE 0: applies ONLY to CODE.
- **`loop-maker-checker.md` RULE 1:** the de-sloppify step can be the cross-model CHECKER itself pointing out the slop (read-only) and the maker removing it.

---

## 6 · RALPHINHO / RFC-DRIVEN DAG ORCHESTRATION

**What it is.** The most sophisticated pattern. RFC/PRD → DECOMPOSITION (the AI breaks it into WorkUnits with a dependency DAG: `id/name/deps/acceptance/tier`) → RALPH LOOP (up to 3 passes): per DAG layer (sequential by dependency), PARALLEL quality pipelines per unit (each in its own worktree: research→plan→implement→test→review, depth varies by tier trivial/small/medium/large) → MERGE QUEUE (rebase on main → test → land OR evict; evicted re-enters with the conflict context). **Key designs:** (a) each stage in a SEPARATE context window with its own model → **the reviewer NEVER wrote the code** (eliminates author bias); (b) merge queue with EVICTION and conflict context (smart re-run, not blind retry); (c) tier-driven depth (trivial skips research/review; large gets maximum scrutiny); (d) resumable state (persisted, not only in memory).

**When to use.** Large feature; multiple interdependent units; parallelism needed; merge conflicts likely; spec/RFC already written. NOT for a single-file change or quick iteration on one thing.

**Links to this kit's gates:**
- **`loop-maker-checker.md`:** "the reviewer never wrote the code" = LITERALLY RULE 1 (maker ≠ checker, cross-model, physical read-only). Ralphinho is the multi-stage form of that rule. The timeout-box (RULE 1b) protects against a hung checker in a long pipeline.
- **`loop-passk.md`:** "tier-driven depth" matches the thresholds — the large tier (release-critical) requires `pass^k = 1.00`; trivial may stop at `pass@k ≥ 0.90`. Unit promotion ⇒ pass@k/pass^k gate.
- **`loop-operator.md`:** "merge-queue stall" and "eviction" = stop-condition #4 (merge-conflict → abort, do NOT auto-resolve in an autonomous loop). "Ralph loop up to 3 passes" = the pre-flight's iteration ceiling. Eviction-with-context ≠ blind-retry = stop-condition #2.

---

## COMBINATIONS (the patterns compose)

```
1 + 5  Sequential + De-Sloppify ........... the most common combination (each implement → cleanup)
4 + 5  Continuous Claude + De-Sloppify ..... --review-prompt with a de-sloppify directive per iteration
any + verification ........................ gate before commit (self-test + loop-maker-checker)
6 (tiers) in simple loops ................. model routing by complexity (light model=trivial, heavy=architectural)
```

---

## ANTI-PATTERNS

```
✗ Infinite loop without an exit condition ......... → loop-cost-budget (budget_*) + loop-operator (done_predicate)
✗ No context bridge between iterations ............ → a persistent ledger/notes (but LC-4: it is a reference, not a queue)
✗ Retrying the SAME failure blindly ............... → loop-operator stop-condition #2 (identical stack trace 2× = abort)
✗ Negative instruction instead of a cleanup pass .. → De-Sloppify (#5) as a separate step
✗ All the agents in one context window ............ → loop-maker-checker (maker ≠ checker, separate contexts)
✗ Ignoring file overlap in parallel ............... → isolated worktrees + uniqueness-by-assignment (#3)
```

---

## QUICK CHECKLIST (when designing a loop)

```
[ ] Did I choose the SHAPE via the decision tree (1-6)?
[ ] Did I check that the task is NOT better served by a simpler pattern (architecture YAGNI)?
[ ] Did I apply the GATES of any loop:
    [ ] loop-operator (pre-flight: baseline+rollback+branch · 4 stop-conditions)?
    [ ] loop-cost-budget (LC-5: budget_tokens/cost/iterations/time · kill-switch)?
    [ ] loop-maker-checker (maker ≠ checker cross-model read-only BEFORE push/merge/close-goal)?
    [ ] loop-passk (pass@k ≥0.90 capability · pass^k =1.00 before release/level 4-5)?
    [ ] stale-replay-guard (LC-4: restored context is a reference, do not re-fire an already-done item)?
[ ] De-Sloppify (#5) after each Implementer — CODE only?
[ ] Loop limits are a live number/JSON (LC-1), not a magic "infinite"?
```

---

*Catalogue of autonomous-loop architectures. Universal — any LLM that designs an autonomous
loop must apply it. This is the "which loop"; the other `loop-*` rules are the "how to run
safely". LC-1: measure live, do not presume; LC-3: do not duplicate what already exists.*
