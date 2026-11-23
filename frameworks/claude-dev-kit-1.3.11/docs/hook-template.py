#!/usr/bin/env python3
"""
hook-template -- scaffold for a REAL Claude Code hook (stdin JSON -> exit code).

A hook is an EXECUTABLE (usually Python) that Claude Code invokes for a lifecycle
event (PreToolUse, PostToolUse, UserPromptSubmit, SessionStart, Stop,
PreCompact, SubagentStop, Notification), passing a JSON payload via STDIN.

Exit code contract (the REAL mechanism -- not a .md frontmatter with trigger:/pattern:):
  0  -> ok. Silent, OR prints JSON with "decision"/"permissionDecision" to warn/inject
        context without blocking. This is the WARN-only mode of this doctrine (never blocks).
  1  -> NON-blocking error. Shows up as a warning; the tool/flow proceeds.
  2  -> BLOCKING error (only makes sense in PreToolUse). stderr goes back to Claude to decide;
        the tool does NOT run. Use sparingly -- block-mode is the exception, not the rule.

Registration (2 forms -- never a .md frontmatter):
  1. PLUGIN mode: your plugin's hooks/hooks.json + .claude-plugin/plugin.json referencing it.
     Commands use ${CLAUDE_PLUGIN_ROOT} (resolved automatically at install time).
  2. MANUAL mode: paste a block into .claude/settings.json / settings.local.json:
       "hooks": { "<Event>": [ { "matcher": "Bash", "hooks": [
         { "type": "command", "command": "python .../this_hook.py", "timeout": 30 }
       ] } ] }

Usage:
    echo '{"tool_name":"Bash","tool_input":{"command":"rm -rf /"}}' | python hook-template.py
    python hook-template.py --self-test

v1.0.0 -- 2026-07-10 (claude-dev-kit - scaffold + BLOCK mode demo)
"""
from __future__ import annotations

import json
import re
import sys

# Patterns that this DEMO blocks (swap in your real logic).
_DANGEROUS = re.compile(r"\brm\s+-rf\s+/(?:\s|$)")


def decide(payload: dict) -> tuple[int, str]:
    """Returns (exit_code, message). Isolate the LOGIC from reading stdin/exit --
    makes it easier to test without a real process (see _self_test)."""
    tool_input = payload.get("tool_input") or {}
    command = str(tool_input.get("command") or "")

    if _DANGEROUS.search(command):
        return 2, f"BLOCKED: destructive command detected ({command!r}). Confirm the intent before running it by hand."

    return 0, ""


def main(argv) -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        # a malformed payload must never break the caller's flow -- degrade safely.
        return 0

    code, message = decide(payload)
    if message:
        print(message, file=sys.stderr if code == 2 else sys.stdout)
    return code


def _self_test() -> int:
    # 1) dangerous command -> BLOCKS (exit 2)
    code1, msg1 = decide({"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}})
    assert code1 == 2 and "BLOCKED" in msg1, (code1, msg1)

    # 2) safe command -> passes (exit 0, no message)
    code2, msg2 = decide({"tool_name": "Bash", "tool_input": {"command": "ls -la"}})
    assert code2 == 0 and msg2 == "", (code2, msg2)

    # 3) payload without tool_input -> never breaks (safe degrade)
    code3, msg3 = decide({})
    assert code3 == 0

    print("self-test OK — blocks a dangerous command (exit 2), allows a safe one (exit 0), degrades without tool_input")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    if len(sys.argv) > 1 and sys.argv[1] in ("--self-test", "-t"):
        sys.exit(_self_test())
    else:
        sys.exit(main(sys.argv[1:]))
