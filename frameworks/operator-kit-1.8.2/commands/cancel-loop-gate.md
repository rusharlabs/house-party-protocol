---
description: "Cancels the active /loop-gate"
allowed-tools: ["Bash(bash ${CLAUDE_PLUGIN_ROOT}/hooks/pyrun.sh --strict ${CLAUDE_PLUGIN_ROOT}/hooks/loop_gate.py:*)"]
hide-from-slash-command-tool: "true"
---

# Cancel /loop-gate

```!
bash "${CLAUDE_PLUGIN_ROOT}/hooks/pyrun.sh" --strict "${CLAUDE_PLUGIN_ROOT}/hooks/loop_gate.py" cancel
```

Report the exact result the command printed (whether there was an active loop or not).
