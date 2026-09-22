---
description: "Arms the /ralph-gate: an autonomous loop that only accepts <promise> if the done_gate really passes"
argument-hint: "--goal G-X | --charter \"prompt\" --criteria \"cmd1\" [\"cmd2\" ...] [--max-iterations N]"
allowed-tools: ["Bash(python ${CLAUDE_PLUGIN_ROOT}/hooks/ralph_gate.py:*)"]
hide-from-slash-command-tool: "true"
---

# /ralph-gate — the Ralph that does not accept a promise without proof

Arms the unified autonomous loop (engine + lock in the same process — see `hooks/ralph_gate.py`).
Difference from the official ralph-loop: the `<promise>` only releases the stop if `done_gate.py`
really passes, RE-EXECUTED inside the hook process — after your turn, out of your reach.
You cannot forge the exit code of a harness subprocess.

```!
python "${CLAUDE_PLUGIN_ROOT}/hooks/ralph_gate.py" start --session "${CLAUDE_SESSION_ID}" $ARGUMENTS
```

Work on the task. When you try to stop (Stop), `ralph_gate.py` will:
1. Look for `<promise>TEXT</promise>` in your last message.
2. If NOT found → re-feed the charter (you continue, without asking "may I proceed?").
3. If found → really run the criteria (`done_gate.gate`). It only PASSES if ALL exit 0.
4. If passed → release the stop, record `gate-passed` in the ledger, remove the state.
5. If failed → re-feed with the real failures and the instruction "do NOT emit `<promise>` until it REALLY passes".

CRITICAL RULE: only emit `<promise>DONE</promise>` when the statement is literally and
verifiably true. Emitting a false promise to escape the loop does not work —
the gate runs the criterion again; it does not believe the text. If the iteration ceiling (`--max-iterations`)
is reached before finishing, the loop releases on its own and records `paused-budget` in the ledger
(LC-5) — that is not an "I did not finish", it is a legitimate budget stop.

Use `/cancel-ralph-gate` to cancel manually.
