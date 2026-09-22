# LOOP-MAKER-CHECKER — Maker ≠ Checker (cross-model) + hard tool-split

> **Auto-Trigger:** In ANY build loop (/goal, /loop, workflow agent, generation cycle) — before reviewing, BEFORE push/merge and BEFORE closing (marking [x]) a /goal.
> **Keywords:** "maker", "checker", "review", "cross-model", "de-bias", "gate", "goal", "/goal", "loop", "build", "push", "merge", "close goal", "code-review", "verify", "reviewer", "builder"
> **Priority:** HIGH
> **Version:** 1.0.0 (generalized for the operator-kit)
> **Origin:** codifies "Maker≠Checker on a different model + hard tool-split" as a rule of the autonomous loop.

---

## PRINCIPLE

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   WHOEVER BUILDS IS NOT WHOEVER APPROVES. AND WHOEVER APPROVES RUNS IN       ║
║   ANOTHER BRAIN.                                                             ║
║                                                                              ║
║   MAKER   = builds (Opus / the workflow agent that wrote the code)           ║
║   CHECKER = reviews, on a DIFFERENT MODEL/PROVIDER, WITHOUT write power      ║
║                                                                              ║
║   The maker's bias (self-justification, "looks good", blindness to its own   ║
║   error) is cancelled by a reviewer that (a) has no love for the code and    ║
║   (b) physically cannot "fix it and move on" — it can ONLY point.            ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

Why cross-model (not just "another instance"): two Opus share the same training biases — one approves what the other would get equally wrong. A model from another provider (Codex/GPT) errs on different axes, so it catches what the maker does not see. This is **cross-model de-biasing**, not redundancy.

---

## RULE 0 · YAGNI LADDER — the MAKER stops at the rung that holds BEFORE writing code

> **UNBREAKABLE scope:** applies ONLY to CODE (`core/`, `scripts/`, `engine/`, `hooks/`). **NEVER** to
> `AGENT.md`/`SOUL.md`/`DNA-CONFIG`/dossiers/`MEMORY` — there the traceable `^[FONTE]` density is the feature, not bloat;
> **`agent-integrity.md` ALWAYS overrides**. "Fewer lines" is NOT a success metric (importing a LOC KPI is forbidden).

Before the MAKER writes ANY new code, go down the ladder and **stop at the 1st rung that solves it**:

```
1. DOES IT NEED TO EXIST?       — does it require new code, or does a doc/config/1 line solve it? (YAGNI)
2. DOES IT ALREADY EXIST?       — grep/ls/codegraph: a function/script/module that already does this? → reuse.
                                  (= learned-corrections.md LC-3, turned into a PROACTIVE pre-code gate)
3. STDLIB / NATIVE TOOL?        — do Read/Write/Edit/Bash/Grep or the stdlib solve it? (CLAUDE.md: native > MCP)
4. DEP ALREADY INSTALLED?       — does a dependency of the repo already cover it? (do not add a new dep out of laziness)
5. FITS IN 1 LINE / existing file? — avoid a new file/module if a snippet serves.
6. ONLY THEN                    — the MINIMUM that solves the REAL task (not the generic/imagined future one).
```

The cross-model CHECKER (RULE 1) gains an objective FAIL criterion: **"did the MAKER skip the ladder?"** — created a
dep/module/file that the stdlib, existing code or 1 line already solved = over-engineering → **FAIL**.

> The ladder above is the same discipline as LC-3 (`learned-corrections.md`) turned into a numbered
> pre-code gate — rung 2 ("does it already exist?") is literally LC-3 applied BEFORE writing, not
> after discovering the duplicate.

---

## RULE 1 · MAKER ≠ CHECKER, ON A DIFFERENT MODEL

```
IF there is a build loop (something was built/edited by an agent):
   → the CHECKER that reviews MUST be a DIFFERENT model/provider from the maker.

PREFERRED CHECKER = an MCP from another provider (e.g. Codex), read-only sandbox, IF available in your environment
   └─ cross-model de-biasing: catches what Opus does not see in its own output.

FORBIDDEN:
✗ Opus maker reviewed by another Opus (same training bias).
✗ The agent that wrote it declaring "reviewed, it is fine" itself.
✗ Skipping the checker "because it is simple" (that is where the silent error lives — LC-1).
```

If `mcp__codex__codex` is unavailable, explicitly declare that the cross-model review was NOT done (do not pretend it was) and treat the gate as FAILED until it runs.

---

## RULE 1b · CHECKER TIMEOUT-BOX & DRAIN (when the cross-model checker hangs/is unavailable)

> **Why:** an unavailable/hung cross-model checker can hold the whole loop waiting for
> an answer that never comes — and that hang is usually SILENT (nobody notices until the
> whole downstream is stopped).

The cross-model CHECKER (RULE 1) has a **TIMEOUT-BOX**. If it does not answer within the budget:
```
1. TIMEOUT           — the checker has a time/attempt ceiling; do NOT wait indefinitely.
2. EXPLICIT DEFERRAL — on expiry, do NOT hang or fake a review: record in the commit/log
                       "cross-model review DEFERRED (checker unavailable)" — truth, not silence.
3. LOGGED BEST-EFFORT— the MAKER does the self-check it can (tests/diff) and moves on, marking the gate
                       PENDING (NOT ✅). push/merge/close-goal stay BLOCKED until the real review.
4. PING              — warn (no silent hang) that the checker is down + the item is pending.
```
Pairs with `loop-operator.md` (identical stack trace 2× = abort) and `loop-cost-budget.md` (ceiling). Delta: the timeout is
the **unavailable checker's own** (not the maker's) — and the deferral becomes logged EVIDENCE, not a false DONE.

---

## RULE 2 · THE CHECKER IS READ-ONLY (PHYSICAL suggest-only)

```
The CHECKER receives neither Write nor Edit. It only reads and reports.
   └─ the checker's allowedTools = ["Read","Glob","Grep","Bash(ro)"]  — NEVER Write/Edit.
   └─ mcp__codex__codex runs in a read-only sandbox by default — keep it that way.

Why physical, not "by trust": if the checker could edit, it would
"fix it and move on" — and the process defect (blind maker) would never
surface. Without a pen, it is forced to POINT. The maker (original model)
applies the fix and re-submits to the checker. The loop closes when the checker passes.
```

This is "suggest-only" made physical — aligned with `partial-autonomy-slider.md`.

### RULE 2b · ISOLATE the external checker — read-only BY CONSTRUCTION, and label the provider

A sandbox flag can fail open; an empty room cannot. When the checker is an external CLI
(Codex or equivalent), run it so that there is nothing to write and nothing to read beyond
the package you hand it — then say, in the report, which provider actually reviewed.

```
1. EMPTY ROOM      temporary cwd, created empty; the package arrives on stdin.
                   No project config, no rules, no repo checkout inherited.
2. NO TOOLS        every tool/MCP/web toggle OFF (shell, exec, browser, plugins, hooks,
                   sub-agents, file search). A reviewer that cannot act cannot "fix and move on".
3. PINNED VERSION  the adapter declares the CLI version it supports and FAILS CLOSED on any
                   other — flags drift, and a silently different CLI is an unverified review.
4. BOUNDED         prompt <= 64 KB, timeout 60-120 s. Over the limit is a REFUSAL to review,
                   never a truncated review passed off as complete.
5. CONSENT         invoking an external provider sends your diff off-box: ask first, every time.
6. HONEST LABEL    every review carries `cross-provider` / `same-provider` / `unverified`, and
                   a review that did not happen is written `external review absent: <reason>`.
                   Substituting a same-provider checker in silence is the one thing this
                   whole rule exists to prevent.
```

⚠️ **The label is not decoration — it is the claim.** "Reviewed" without a provider label
lets a same-model second opinion be read as de-biasing (RULE 1), which is exactly the failure
mode RULE 1 measures. When in doubt, write `unverified`.

*Isolation recipe adapted from ECC (MIT) — doctrine only; no adapter is shipped with this kit.*

---

## RULE 3 · MANDATORY GATE — run the cross-model checker BEFORE:

```
[ ] git push        → NEVER push without a green cross-model review.
[ ] merge (PR)      → the checker is a prerequisite of the merge (adds to the other review layers of your flow).
[ ] closing a /goal → BEFORE marking it complete / declaring 'done' in your ledger,
                      run the cross-model checker over the goal's diff.

IF the checker returns FAIL or a critical WARNING:
   → NO push · NO merge · do NOT close the goal.
   → Maker fixes · re-submits · repeats until PASS.
```

**On a rework FAIL, reset — do not patch on top.** Reopening the rejected attempt keeps its
reproduction, its scaffolding and the checker's first verdict in the context, and the maker
converges on the shape of its own first mistake. Close the attempt, branch again from the
integration base, reproduce the defect, and rebuild with the finding as input.
*Adapted from openai/symphony (Apache-2.0) — concept only, no code reused.*

Complements (does not replace) your own verification that the code works (tests, self-test):
that validates that the thing WORKS; this rule requires that **another brain** confirm it, without a pen in hand.

---

## RULE 4 · LINK WITH THE AUTONOMY SLIDER

```
The CHECKER always operates as autonomy_level 0/1 (proposes · does NOT execute):
   └─ level 0 (suggest-only) = this rule's physical read-only. It is the checker's floor.

The MAKER respects its own autonomy_level (`partial-autonomy-slider.md`):
   └─ In sensitive areas (financial · contracts · DELETE · live engine/cron),
      a maker at level 0/1 → even with a green checker, push/merge still depends on the operator.
   └─ A green checker NEVER promotes the maker above its level — it only unlocks what
      the level already allowed.
```

---

## EXAMPLE (build loop → gate → close goal)

```
1. MAKER (Opus / workflow agent) writes scripts/foo.py + tests.
2. MAKER runs the tests locally (verification-before-completion) → green.
3. Cross-model CHECKER (mcp__codex__codex, read-only sandbox):
     "Review the diff of scripts/foo.py vs main. Point out bugs, edge cases,
      rule violations. Do NOT edit — only list findings with severity."
4. Checker returns: 1 WARNING (hardcoded path vs core/paths.py) + 0 FAIL.
5. Critical WARNING → MAKER fixes the path → re-submits to the checker.
6. Checker returns PASS → ONLY NOW: push / merge / mark the item complete in your ledger.
```

Anti-example (FORBIDDEN): Opus writes, Opus re-reads, says "it is great", pushes, closes the goal. Same bias, no pen taken away, gate bypassed.

---

## QUICK CHECKLIST

```
[ ] Is there a build in this loop? → then there is a MAKER and it needs a CHECKER.
[ ] Is the CHECKER a DIFFERENT model/provider from the maker? (prefer mcp__codex__codex)
[ ] Is the CHECKER WITHOUT Write/Edit (physical read-only)?
[ ] Did I run the cross-model checker BEFORE push / merge / closing the /goal?
[ ] On FAIL/critical WARNING: did the maker fix and re-submit (I did not push anyway)?
[ ] In a sensitive area: did I respect autonomy_level 0/1 (human gate) even with a green checker?
```

---

*Rule of the autonomous loop. Universal — any LLM that runs a build loop must apply it. LC-1: prove that the checker ran, do not presume.*
