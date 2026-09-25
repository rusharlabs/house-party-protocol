---
description: "Runs a House Session: a panel of read-only seats from two model families, counted, stopped and sealed"
argument-hint: "<question and options> [--type plan|review|release-gate|incident|design]"
allowed-tools: ["Bash(python ${CLAUDE_PLUGIN_ROOT}/scripts/house_session.py:*)", "Bash(python -m hpp deliberate:*)", "Bash(python -m hpp findings check:*)", "Bash(git worktree:*)", "Read", "Write"]
---

# /deliberate — a panel you can check afterwards

First, the host:

```!
python "${CLAUDE_PLUGIN_ROOT}/scripts/house_session.py" families --maker claude
```

If the status is `DEFERRED`, stop and say so: this host offers one model family, and a panel of
one family is not a panel. Record the deferral; do not run the session with one family.

Otherwise follow the `house-session` skill of this module for: $ARGUMENTS

1. Write `panel.json` (`hpp.panel/v1`) with the roles the session type needs, two families among
   the participants, and the judge in a lane no participant uses. Check it with
   `python -m hpp deliberate plan panel.json --context context.json --out panel.json`.
2. One git worktree per seat. Round 1 is blind: run every seat through
   `house_session.py seat ... --round 1 -- <the seat's CLI in read-only mode>`, in parallel.
3. `python -m hpp deliberate stop`. On `continue`, run the next round with `--seen`.
4. The judge answers in its own lane; over grounded dissent it also writes the rationale.
   Seal with `python -m hpp deliberate record` and check with `python -m hpp deliberate verify`.

A seat whose runner exits 2 wrote to its worktree or answered out of contract: its turn does not
exist. A seat that exits 1 is not judged — never count it as a vote. You write only the panel, the
prompts, the judge's answer and the rationale; the seats write nothing.
