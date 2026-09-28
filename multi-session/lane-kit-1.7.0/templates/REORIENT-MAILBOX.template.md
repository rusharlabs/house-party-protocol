# REORIENT-MAILBOX — {{lane_id}}

> Generated from the lane-kit template. Replace the `{{placeholders}}` — never leave
> a `{{...}}` unfilled in the final file. This mailbox is the ASYNCHRONOUS post box
> between lanes (planner → executor, reviewer → executor) when the board alone is not
> enough to convey rich context (e.g. a scope reorientation in the middle of the work).
> The `## To:` line is the literal `lane_register.py` matches to route the message to
> its lane — keep it exactly as written: one lane id, alone on the line (a second
> `## To:` line addresses a second lane). The legacy `## Para:` line still routes, for
> mailboxes written before this version.

## To: {{target_lane_id}}
## From: {{source_lane_id}} ({{source_role}})
## When: {{timestamp}}
## Affected item(s): {{item_ids}}

### What changed
{{what_changed}}

### Why
{{why}}

### What the target lane must do
- [ ] {{action_1}}
- [ ] {{action_2}}

### Evidence/context
{{evidence_or_link}}

---
*Consumption: `lane_register.py` tells the target lane about this file at its next register
(SessionStart) or, if the lane is already running, on the first heartbeat that lands after the
file appears (PostToolUse `--heartbeat`, once per message — a throttled heartbeat waits for the
next one). The lane reads it and marks it as read by moving it to
`.claude/lanes/mailbox/_read/{{filename}}` (convention — never edit in place; the mailbox is
write-once, read-and-archive). On Codex CLI there are no lifecycle hooks: the lane hears about
the file when it runs `lane_register.py` (register or `--heartbeat`) itself.*
