# 🔄 CHARTER — Autonomous loop «{NAME}» ({DATE})

> **This is the loop driver.** The next session enters here, runs relentless, self-prompts, self-reviews, and only stops when the autonomous lane is exhausted OR the time ceiling OR an imminent irreversible risk.
> **Work-list:** `{paths.work_list}` · **Guiding concept:** `{boot_doc}` (do not drift).
> Fill in the `{…}`. Defaults come from `operator-profile.yaml`.

---

## 🎯 MISSION
{What to crush, alone and in workflows. What genuinely depends on the human becomes a FORM (§HUMAN-GATE), never a blocker.}

## 🛡️ GUARDRAILS
**KEPT (seat belt — unbreakable):**
1. **0 push** without an order · never force-push.
2. **Backup before ANY prod mutation** (config/db/container).
3. **Snapshot + verify before deleting** (destructive-actions).
4. **Credential lock** (verify the right account before touching a token/secret).
5. **Human gate for:** billing, OAuth, legal, message to a client, deploy-prod-go, secret rotation.
6. **LC-1:** verify live before declaring "done". Do not break what works.

**RELAXED (friction — for autonomy):**
- Auto-proceed (no confirm-every-step) · plan inline · self-prompt the next item · continuous across batches · workflows in waves of ≤{concorrencia.teto}.

## 🔁 CYCLE (each iteration)
1. **Re-align:** read this charter + boot-doc (concept) + SSoT §Now.
2. **Verify live (LC-1):** real state of the project's canonical source.
3. **Pick** the next not-done item of **highest leverage**.
4. **Execute** via workflow waves-of-{concorrencia.teto} + **adversarial verify** (refute before accepting).
5. **Mark done** in the work-list + commit per path (0 push).
6. **Capstone per wave:** `python operator-kit/scripts/done_gate.py --profile {kind}` + the project's validators.
7. **Self-prompt (OPTIONAL):** `ScheduleWakeup` with this charter for the next cycle — a tool **exclusive to the `/loop` main-loop**, not a dependency of this charter. Outside the main-loop it does not exist: the fallback is to re-invoke the charter by hand in the next cycle.
8. **Every ~5 cycles — adversarial review:** "which loose end is left? did I drift from the concept? new duplicate/orphan?".

## ⚙️ ATTACK ORDER
1. {Item 1 — autonomous}
2. {Item 2 — autonomous}
3. {Items delegable to a 2nd agent — only after prerequisite X}
4. {Staged for the human gate}

## 📋 HUMAN-GATE (the wall — cleared in one sitting)
Each item: `{gate, reason, EXACT command/step, what-it-unblocks}`. Output in `{paths.gate_sheet}`.

## 🛑 STOP CONDITIONS
- Autonomous lane exhausted (everything non-gate done) → report + wait for the gate.
- {stop_conditions: time ceiling}.
- Imminent irreversible risk flagged by a guardrail → STOP + report.

## 🚀 SELF-PROMPT / BOOT (paste after /clear · `ScheduleWakeup` repeats this **when available**)

> `ScheduleWakeup` is **optional** and **exclusive to the `/loop` main-loop** — it is not a dependency of this
> charter. Outside the main-loop, the fallback is to paste the block below by hand in the next cycle.

```
Autonomous loop «{NAME}». Folder {project-root}, branch {branch}.
READ (in this order): {this charter} → {boot_doc} → {paths.work_list} → SSoT §Now.
STEP 0 LIVE (LC-1): {the project's live verification command(s)}.
GUARDRAILS: keep (0 push · backup-before-prod · snapshot-before-delete · credential-lock · human-gate billing/OAuth/legal · LC-1). Relax friction (auto-proceed · self-prompt · continuous).
EXECUTE (waves-of-{teto} + adversarial verify): order of the charter §. Commit per path, 0 push. Capstone per wave: done_gate --profile {kind}.
SELF-REVIEW every ~5 cycles. Human gate → single form, NEVER blocks the loop.
ScheduleWakeup for the next cycle (OPTIONAL — tool exclusive to the /loop main-loop; outside it, the fallback is to re-paste this block by hand). STOP on: lane-exhausted OR time-ceiling OR irreversible-risk.
```

*Living charter. Each cycle re-verifies at the source (LC-1). Strike items off the work-list as they complete.*
