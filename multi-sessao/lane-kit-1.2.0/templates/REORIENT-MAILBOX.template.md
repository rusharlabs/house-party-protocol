# REORIENT-MAILBOX — {{lane_id}}

> Generated from the lane-kit template. Replace the `{{placeholders}}` — never leave
> a `{{...}}` unfilled in the final file. This mailbox is the ASYNCHRONOUS post box
> between lanes (planner → executor, reviewer → executor) when the board alone is not
> enough to convey rich context (e.g. a scope reorientation in the middle of the work).
> The `## Para:` line is the literal `lane_register.py` matches to route the message
> to its lane — keep it exactly as written.

## Para: {{lane_id_destino}}
## From: {{lane_id_origem}} ({{role_origem}})
## When: {{timestamp}}
## Affected item(s): {{item_ids}}

### What changed
{{descricao_da_reorientacao}}

### Why
{{motivo}}

### What the target lane must do
- [ ] {{acao_1}}
- [ ] {{acao_2}}

### Evidence/context
{{evidencia_ou_link}}

---
*Consumption: the target lane READS this file at the next `lane_register.py` heartbeat/register
and marks it as read by moving it to `.claude/lanes/mailbox/_read/{{filename}}` (convention —
never edit in place; the mailbox is write-once, read-and-archive).*
