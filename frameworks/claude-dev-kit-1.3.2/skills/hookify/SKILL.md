---
name: hookify
description: Creates REAL hooks for Claude Code — executable scripts (stdin JSON, exit 0/1/2), registered via a plugin's hooks.json or pasted into settings.json. Use when the user wants to create a hook, a safety rule, a custom validation, a lifecycle hook.
---

> **Auto-Trigger:** When the user wants to create a hook, an automatic safety rule, a custom validation, or a lifecycle hook (PreToolUse/PostToolUse/SessionStart/Stop/etc.).
> **Keywords:** "hook", "create hook", "lifecycle", "safety rule", "validation", "security rule", "pre-tool", "post-tool", "block command"
> **Priority:** HIGH
> **Tools:** Read, Write, Edit, Glob, Grep, Bash

## When NOT to Activate
- Discussions about existing hooks with no intent to create new ones, or debugging a hook that is already implemented (read the script directly, do not recreate it).
- **Creating a SKILL** (a SKILL.md triggered by keyword/context) — use `skill-writer` from this same module; skill ≠ hook (a skill is an instruction for the model to follow, a hook is code that runs automatically in the tool lifecycle).
- **Packaging hooks into a distributable plugin** — after creating the hook, use `plugin-dev` from this same module for the `.claude-plugin/plugin.json` + `hooks.json` that installs it.

## Core Purpose

Create REAL hooks: **executable scripts** (not `.md` files with frontmatter) that Claude Code invokes on lifecycle events, receiving a JSON payload via **stdin** and communicating the decision via **exit code** (+ optionally an output JSON).

## Contract

**INPUT:** JSON payload via stdin — the shape varies per event, but typically includes `tool_name`, `tool_input.{...}`, `session_id`, `hook_event_name`.

**OUTPUT:** exit code (mandatory) + optionally text on stdout/stderr or structured JSON (`hookSpecificOutput`/`decision`/`permissionDecision`, depending on the event).

**EXIT CODES** (the REAL Claude Code mechanism — not `mode: warn|block` in frontmatter):

| Exit | Meaning |
|---|---|
| 0 | ok — silent, OR prints a warning/injects context WITHOUT blocking (WARN-only mode, the default of this doctrine) |
| 1 | NON-blocking error — shows up as a warning, the flow continues |
| 2 | BLOCKING error (only takes effect in `PreToolUse`) — stderr goes back to Claude, the tool does NOT run |

**STATE IT TOUCHES:**

| Resource | Reads/Writes | Purpose |
|---|---|---|
| stdin | Reads | the event's JSON payload |
| `<plugin>/hooks/hooks.json` (plugin mode) | Writes | declarative registration, resolved via `${CLAUDE_PLUGIN_ROOT}` |
| `.claude/settings.json`/`settings.local.json` (manual mode) | Writes (pasted by the operator — human gate) | direct registration, without a plugin |

## Available events

| Event | When it fires |
|---|---|
| `SessionStart` | Session start |
| `UserPromptSubmit` | The user sends a message |
| `PreToolUse` | Before a tool runs (the only phase where exit 2 blocks) |
| `PostToolUse` | After a tool runs |
| `Stop` | End of session/response |
| `PreCompact` | Before compacting/clearing context |
| `SubagentStop` | When a subagent finishes |
| `Notification` | Notification events |

`matcher` (only relevant in `PreToolUse`/`PostToolUse`): regex/pipe of tool names, e.g. `"Bash"` or `"Edit|Write|MultiEdit"`.

## Process

### 1. Write the script (stdin → decision → exit code)
Use this module's `docs/hook-template.py` as the scaffold — it already has the `decide(payload) -> (exit_code, mensagem)` structure separated from `main()` (makes it easy to test without simulating a real process) and a `--self-test`.

### 2. Choose WARN-only (default) or BLOCK (exception)
WARN-only (always exit 0, message on stdout) is the default of this doctrine — a safety hook warns; whoever actually decides to block is the human or a dedicated layer (e.g. pre-commit). BLOCK (exit 2) is the exception: only for cases where the action is irreversible AND the detection is reliable enough to never produce a blocking false positive.

### 3. Register — PLUGIN mode (recommended, auto-wire)
```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash", "hooks": [
        { "type": "command", "command": "python \"${CLAUDE_PLUGIN_ROOT}/hooks/seu_hook.py\"", "timeout": 30 }
      ]}
    ]
  }
}
```
Save it as `<your-plugin>/hooks/hooks.json` and reference it in `.claude-plugin/plugin.json` (`"hooks": "./hooks/hooks.json"`) — see the `plugin-dev` skill.

### 4. OR register — MANUAL mode (no plugin, paste directly)
Add the same structure inside the `hooks` array of `.claude/settings.json`/`settings.local.json`. **This is usually a human gate** — automated sessions have a lock against self-editing settings/hooks; paste it yourself.

### 5. Test with the real payload
```bash
echo '{"tool_name":"Bash","tool_input":{"command":"..."}}' | python seu_hook.py
```

## Live example in this module: `secret_scan_on_write.py`

A real, shipped `PreToolUse` hook (matcher `Edit|Write|MultiEdit`), WARN-only: reads `tool_input.{file_path, content, ...}` from stdin, checks whether the path matches a "persistent" glob (memory/CLAUDE.md/docs) AND the content matches a secret pattern, and warns — never blocks (always exit 0). See `hooks/secret_scan_on_write.py`.

## Executed examples

```console
$ echo '{"tool_name":"Write","tool_input":{"file_path":"CLAUDE.md","content":"api_key: \"sk-ant-abcdef1234567890ABCDEF\""}}' | python hooks/secret_scan_on_write.py
[secret_scan_on_write] WARNING: possible secret in a persistent file `CLAUDE.md` (pattern `sk-ant-a...`).
  -> do NOT commit a raw credential. Reference the `.env` (e.g. "key: stored in `.env` as FOO_API_KEY"). WARN-only — the real BLOCK belongs to the pre-commit.
```
<!-- executed: 2026-07-10 · exit=0 -->
(detected the secret and WARNED — but exit=0: WARN-only never prevents the write.)

```console
$ echo '{"tool_name":"Write","tool_input":{"file_path":"CLAUDE.md","content":"API key stored in .env as FOO_API_KEY"}}' | python hooks/secret_scan_on_write.py
```
<!-- executed: 2026-07-10 · exit=0 -->
(no output — clean content, silent hook.)

```console
$ echo '{"tool_name":"Bash","tool_input":{"command":"rm -rf /"}}' | python docs/hook-template.py
BLOCKED: destructive command detected ('rm -rf /'). Confirm the intent before running it by hand.
```
<!-- executed: 2026-07-10 · exit=2 -->
(BLOCK mode — exit 2 in `PreToolUse` really does prevent the tool from running. Use sparingly.)

## Anti-patterns

- ❌ Writing a hook as an `.md` file with `trigger:`/`pattern:`/`mode:` frontmatter — that is NOT how Claude Code hooks work; hooks are executables, not declarative markdown.
- ❌ Using `mode: block` by default — a block-mode false positive locks the user up mid-work; start WARN-only, promote to block only with evidence of zero false positives.
- ❌ Hardcoding `py` as the launcher — always use `python` (cross-OS portability).
- ❌ A hook that raises an unhandled exception on a malformed payload — always degrade to exit 0 on a parsing error (see `docs/hook-template.py::main`).

## Proof

```bash
python docs/hook-template.py --self-test
```
