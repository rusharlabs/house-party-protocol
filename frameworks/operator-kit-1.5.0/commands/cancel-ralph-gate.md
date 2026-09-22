---
description: "Cancels the active /ralph-gate"
allowed-tools: ["Bash(python ${CLAUDE_PLUGIN_ROOT}/hooks/ralph_gate.py:*)"]
hide-from-slash-command-tool: "true"
---

# Cancel /ralph-gate

```!
python "${CLAUDE_PLUGIN_ROOT}/hooks/ralph_gate.py" cancel
```

Report the exact result the command printed (whether there was an active loop or not).
