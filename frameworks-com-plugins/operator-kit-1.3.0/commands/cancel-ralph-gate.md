---
description: "Cancela o /ralph-gate ativo"
allowed-tools: ["Bash(python ${CLAUDE_PLUGIN_ROOT}/hooks/ralph_gate.py:*)"]
hide-from-slash-command-tool: "true"
---

# Cancelar /ralph-gate

```!
python "${CLAUDE_PLUGIN_ROOT}/hooks/ralph_gate.py" cancel
```

Reporte o resultado exato impresso pelo comando (havia loop ativo ou não).
