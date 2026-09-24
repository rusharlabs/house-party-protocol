# GateGuard — Force the facts BEFORE the 1st Edit / destructive Bash

> **Auto-Trigger:** Before the FIRST Edit/Write on an already-existing file; before ANY destructive Bash (rm, rm -rf, DROP, TRUNCATE, git push --force, git clean -fd, mv/rename of a critical path).
> **Keywords:** "gateguard", "before the 1st", "first edit", "before editing", "rm", "rm -rf", "DROP", "TRUNCATE", "force-push", "force push", "git clean", "rollback", "destructive", "importers", "schema", "blast radius", "who uses", "who imports"
> **Priority:** CRITICAL
> **Version:** 1.0.0 (generalized for the operator-kit)
> **Origin:** distilled as actionable ENFORCEMENT of `learned-corrections.md` LC-3 (grep/ls before creating/classifying) + live source-code protection doctrine. Universal (any LLM that uses this kit).

---

## Principle

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   DO NOT TOUCH THE FILE UNTIL YOU KNOW WHAT BREAKS IF YOU GET IT WRONG.      ║
║                                                                              ║
║   LC-3 already says "grep/ls before creating/classifying". GateGuard         ║
║   extends it: grep/ls ALSO before the 1st EDIT and before EVERY destructive  ║
║   action.                                                                    ║
║                                                                              ║
║   The fact (importers · schema · rollback) comes BEFORE the action. Always.  ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

GateGuard is the gate that turns the reactive lesson of LC-3 and of any live source-code
protection doctrine into a mandatory PRE-ACTION checklist. It replaces neither of the
two — it makes them actionable at the exact moment the damage would happen.

---

## GATE 1 · Before the FIRST Edit on a file

Before the 1st `Edit`/`Write` on a file that **already exists**, establish 3 facts (grep + ls/Glob):

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  1. IMPORTERS / CONSUMERS — who uses this file?                              │
│     └─ grep for the module/function/symbol name in the repo                  │
│     └─ Python:  grep -rn "import <modulo>\|from <modulo>" .                  │
│     └─ JS/TS:   grep -rn "require('<path>')\|from '<path>'" .                │
│     └─ Config/rules/.md: grep for the file name (who references it?)         │
│                                                                              │
│  2. SCHEMA / CONTRACT — what shape do others expect?                         │
│     └─ Function signature, JSON/YAML keys, table columns,                    │
│        rule header, output format that consumers parse.                      │
│     └─ Changing the SHAPE without checking consumers = silent breakage.      │
│                                                                              │
│  3. ROLLBACK — how do I undo it if it goes wrong?                            │
│     └─ File tracked by git? (`git status` / `git ls-files <path>`)           │
│        → YES: rollback = `git checkout -- <path>`. You may edit.             │
│        → NO (gitignored/new): a non-trivial edit requires a copy/backup      │
│          BEFORE, or explicitly declaring "no safety net".                    │
└──────────────────────────────────────────────────────────────────────────────┘
```

A trivial additive edit to a git-tracked file (e.g. adding 1 line to a `.md`/rule)
= GATE 1 satisfied by git itself (rollback guaranteed). The weight of the gate is
**proportional to the blast radius**: the more consumers, the more grep beforehand.

### Exceptions (GATE 1 does not apply)
- **NEW** file (your creation) → there are no prior importers; LC-3 (grep before creating) covers it.
- Scratchpad / disposable temporary file.

---

## GATE 2 · Before destructive Bash (rm / DROP / force-push / clean)

For `rm`, `rm -rf`, `DROP TABLE`, `TRUNCATE`, `git push --force`, `git clean -fd`,
`mv`/rename of a critical path — **and the "apparently-safe-but-destructive"** (rebuilds that
discard increments · forced container recreate that wipes ephemeral state · writes to
regenerable indexes/caches that are expensive to recompute) — **REQUIRE before executing**:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  A. WRITTEN ROLLBACK — an explicit sentence on how to revert THIS action     │
│     └─ E.g.: "snapshot in backups/<x>-$(date) before the rm; I restore       │
│        with cp -r back" · "DROP only after a dump/export to <path>".         │
│     └─ No written rollback = do NOT execute. (SNAPSHOT → ROLLBACK → VERIFY   │
│        is the long form of this gate.)                                       │
│                                                                              │
│  B. OPERATOR AUTHORIZATION CITED — where/when THIS was authorized            │
│     └─ Cite the statement/session/gate. Broad-execution authorization (LC-2) │
│        does NOT authorize a destructive action on a critical path without a  │
│        rollback. Sensitive areas (financial/contracts/DELETE/cron/live       │
│        engine) = autonomy level 0/1 (`partial-autonomy-slider`): propose,    │
│        do not auto-execute.                                                  │
│                                                                              │
│  C. Post-action VERIFY — a command that proves the system survived           │
│     └─ E.g.: curl on your service's /health · re-grep what remained.         │
└──────────────────────────────────────────────────────────────────────────────┘
```

### FORBIDDEN unconditionally (live source-code protection)
```
✗ rm -rf on paths containing `engine`, `src`, `apps` (the product's live source code)
✗ git clean -fd in the production repo
✗ moving/renaming application/engine folders in use
✗ rm/DROP/force-push fired by a SEARCH for an ambiguous string (one name can have multiple
   meanings in your project — process, volume, legacy folder). NEVER delete by string match
   without confirming WHICH of the meanings you are targeting.
✗ Touching live source code, `.env`, or production infrastructure from a planning
   session (read-only).
```
Nothing above is unlocked by a rollback — it is a hard floor. GATE 2 (A/B/C) applies to the
*permitted* destructive; the forbidden stays forbidden.

---

## Flow (decision at a glance)

```
About to Edit an existing file? ──► GATE 1 (importers · schema · rollback)
About to run destructive Bash?  ──► critical/forbidden path? ──► STOP (hard floor)
                                     otherwise ──► GATE 2 (written rollback + authorization + verify)
About to CREATE a file / classify as pending? ──► LC-3 (grep+ls first)
```

---

## Application as a hook (human gate — do NOT enable on your own)

> ⚠️ Wiring this as a **PreToolUse** hook touches `settings.json` → **human gate**
> (edits to settings/hooks usually require human review before applying).
> This rule is the doctrine; the wiring below is a **SUGGESTED diff** for the operator to apply.

Suggested diff (human review before applying — `timeout: 30`, exit 0=ok / 1=warn / 2=block).
Recommendation: start in **WARN (exit 1)**, never block, until zero false positives are validated:

```jsonc
// settings.json → hooks → PreToolUse (ADDITIVE; matcher covers Edit/Write/Bash)
{
  "matcher": "Edit|Write|Bash",
  "hooks": [
    {
      "type": "command",
      "command": "python3 .claude/hooks/gateguard.py",
      "timeout": 30
    }
  ]
}
```

Sketch of the hook (to be created by the operator, out of this rule's scope):
- Reads the tool input from stdin (JSON).
- Edit/Write on an existing file without a recent grep in the session → injects a GATE 1 reminder (WARN).
- Bash with `rm -rf`/`DROP`/`--force`/`git clean` → requires rollback+authorization in the context;
  forbidden path match (`engine`/`src`/`apps`) → BLOCK (exit 2).

---

## Links to

| Rule | Relation |
|-------|---------|
| `learned-corrections.md` LC-3 | GateGuard is the pre-action ENFORCEMENT of LC-3 (grep before creating/classifying) extended to the 1st Edit and to the destructive. |
| `learned-corrections.md` LC-1 | The post-action VERIFY (curl /health) proves the live state, it does not assume. |
| `partial-autonomy-slider.md` | Destructive in a sensitive area = level 0/1 (propose, not auto). |

---

*GateGuard v1.0.0 — fact before action. Applies to any LLM that uses this kit.*
