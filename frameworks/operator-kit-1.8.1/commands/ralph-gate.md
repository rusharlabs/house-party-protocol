---
description: "Deprecated alias of /loop-gate (removed in 3.0): arms the loop gate under its former name"
argument-hint: "the same arguments as /loop-gate"
allowed-tools: ["Bash(bash ${CLAUDE_PLUGIN_ROOT}/hooks/pyrun.sh --strict ${CLAUDE_PLUGIN_ROOT}/hooks/loop_gate.py:*)"]
hide-from-slash-command-tool: "true"
---

# /ralph-gate — deprecated alias of `/loop-gate` (removed in 3.0)

The loop gate was renamed. This command stays until 3.0 so that existing habits and wiring keep
working, and it arms exactly the same hook, `hooks/loop_gate.py`.

```!
bash "${CLAUDE_PLUGIN_ROOT}/hooks/pyrun.sh" --strict "${CLAUDE_PLUGIN_ROOT}/hooks/loop_gate.py" start --session "${CLAUDE_SESSION_ID}" $ARGUMENTS
```

From here on, follow `commands/loop-gate.md`: the rules of the loop are the same. Tell the
operator once that `/ralph-gate` is deprecated and that the current name is `/loop-gate`.
