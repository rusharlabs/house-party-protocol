---
description: "Deprecated alias of /cancel-loop-gate (removed in 3.0)"
allowed-tools: ["Bash(bash ${CLAUDE_PLUGIN_ROOT}/hooks/pyrun.sh --strict ${CLAUDE_PLUGIN_ROOT}/hooks/loop_gate.py:*)"]
hide-from-slash-command-tool: "true"
---

# Cancel /ralph-gate — deprecated alias of `/cancel-loop-gate` (removed in 3.0)

```!
bash "${CLAUDE_PLUGIN_ROOT}/hooks/pyrun.sh" --strict "${CLAUDE_PLUGIN_ROOT}/hooks/loop_gate.py" cancel
```

Report the exact result the command printed (whether there was an active loop or not), and tell
the operator once that the current name is `/cancel-loop-gate`.
