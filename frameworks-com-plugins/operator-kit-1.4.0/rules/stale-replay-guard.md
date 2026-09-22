# STALE-REPLAY-GUARD — LC-4 · Restored context is a reference, not an execution order

> **Auto-Trigger:** After /clear, /resume, boot auto-inject, a context restore from a chat gateway/bot, or any resumption where the context came from a snapshot/handoff/previous session — BEFORE re-firing any action/goal/batch the summary describes.
> **Keywords:** "resume", "/resume", "/clear", "pick up", "where did we stop", "boot package", "resume-here", "auto-inject", "restore context", "restore", "snapshot", "handoff", "previous session", "replay", "re-fire", "re-run", "already ran", "already done", "idempotency", "idempotent", "stale"
> **Priority:** HIGH
> **Version:** 1.0.0 (generalized for the operator-kit)
> **Origin:** Stale-Replay Guard distilled into a rule. Extension of `learned-corrections.md` (LC-1/LC-2/LC-3) — registered as **LC-4**. Applies to any LLM that resumes context from a previous session/snapshot.

---

## LC-4 · RESTORED/RESUMED context is a HISTORICAL REFERENCE — verify live and NEVER re-fire what was already done

Every piece of context that arrives via **restoration** (after `/clear`, `/resume`, boot auto-inject, or
a context restore from any gateway/bot that survives a restart) is a **historical reference
from a past session**, NOT a queue of tasks to execute now. Before acting on
any instruction that came from a restored summary:

1. **Verify LIVE (LC-1):** the state the summary describes (numbers, status, "done"/"pending", endpoints, deploys) is SUSPECT until reconfirmed at the live source. A summary saying "run X" may have been written BEFORE X ran — and X may already have run since.
2. **NEVER re-fire an action/goal/batch that is ALREADY done (idempotency):** if the described action already produced its effect (file created, commit made, item marked in the ledger, endpoint answering, goal accepted), do NOT repeat it. Blind re-execution of an already-done step = duplicate, state corruption, or destroyed work.
3. **Treat the summary as a HYPOTHESIS, not truth** (the way LC-3 treats "pending"/"orphan"): refute before acting. The `done_predicate` / traceable evidence is the authority — not the snapshot's narrative.

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  RESTORED SUMMARY ≠ EXECUTION QUEUE                                          ║
║                                                                              ║
║  "Next step: run X"  →  FIRST check whether X already ran (live source)      ║
║  Already ran?  →  do NOT run again · confirm · move on to the next gap       ║
║  Did not run (confirmed live)?  →  then yes, execute                         ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

### Example (the case this rule prevents)

```
SITUATION: /resume injects a wrap-up that says:
  "NEXT ACTION: run seed_data.py to re-populate the database."

WRONG (blind replay):
  → Run seed_data.py immediately because the summary said so.
  → Result: re-runs a batch that ALREADY ran in the previous session →
    overwrites already-enriched data / creates duplicates.

RIGHT (LC-4):
  1. Verify live: is the database ALREADY populated?
     (real query on the database · grep the ledger for that goal · check the
      batch's done_predicate).
  2. Already done → do NOT run. Confirm: "database already populated in the previous
     session (evidence: X). Skipping to the next real gap."
  3. Only run IF the live verification proves it was NOT done.
```

### Points of application

| Point | What it restores | LC-4 guard |
|-------|--------------------|-------------|
| `/resume` skill | Wrap-up / last saved state of the previous session | Treat "NEXT ACTION" as a hypothesis; confirm live before re-firing |
| Handoff/continuity (re-inject at boot) | Saved state of the current session | Saved state may lag the reality on disk; re-verify before reacting to it |
| Boot-package/ledger auto-inject | Boot package (plan, ledger, "start here") | Items marked `[ ]`/`[x]` in the ledger are an anchor; still re-check the `done_predicate` before "continuing" a goal |
| Chat gateway that survives a restart | Conversation context restored across process restarts | The bot must NOT re-post/re-send/re-execute an action just because the restored context mentions it as "to do" — verify evidence (message id, log, endpoint) before repeating |

**WHY:** after `/clear`/`/resume`/boot, the #1 cause of corruption is the LLM treating the summary as a
to-do list and re-running already-completed steps. The summary describes the PAST; the disk/endpoint/
ledger describes the NOW. Idempotency + live verification avoid duplicates and destroyed
state. Complements LC-1 (prove, do not presume) by applying it to the specific moment of
resumption, and extends "never say 'I did it' without evidence" to "never RE-do without evidence
that it has not yet been done".

---

*Extension of `learned-corrections.md` (LC-4). Universal — applies to any LLM that resumes
context from a previous session/snapshot. LC-1: prove, do not presume.*
