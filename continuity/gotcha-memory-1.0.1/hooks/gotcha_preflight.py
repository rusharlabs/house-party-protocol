#!/usr/bin/env python3
"""
gotcha_preflight -- PreToolUse hook (WARN-only): injects the lessons BEFORE the command.

Standalone port of the origin repo's `agentic_preflight.py`, reduced to the gotcha
loop (the operation_guard/task_complexity stay in the operator-kit -- this kit is just
the failure->lesson->prevention cycle). BEFORE every Bash, it derives the task_key
(description or cmd[:80]) and, if there are matching curated/recurring gotchas, prints
the preamble to stderr -- visible in the chat, without blocking anything.

NEVER blocks (WARN-not-block) -- exit 0 always. Defensive: any error -> exit 0.

v1.0.0 -- 2026-07-11 (gotcha-memory kit)
"""
import json
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parent.parent / "_lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
try:
    import gotchas_memory as gm
except Exception:  # noqa: BLE001 -- Why: a preflight hook can never bring down the user's
    # command. Without the lib (partial install or a broken import) the hook no-ops and
    # exits 0; removing this guard would only turn an import failure into a Bash failure.
    gm = None  # type: ignore[assignment]


def _stderr_utf8() -> None:
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass


def _task_key(data: dict) -> str:
    """task_key = tool_input's description, else cmd[:80]. '' if it's not a Bash with a command."""
    if data.get("tool_name") != "Bash":
        return ""
    ti = data.get("tool_input") or {}
    cmd = ti.get("command", "")
    if not cmd:
        return ""
    if ti.get("description"):
        return ti["description"]
    # Why: the key derived from the command has to match the one the postflight writes, and it
    # redacts the command BEFORE truncating -- without the same step here, the lesson never
    # fires for a command that carried a credential.
    return (gm.redact_secrets(cmd) if gm is not None else cmd)[:80]


def main() -> None:
    try:
        raw = sys.stdin.read() or "{}"
        data = json.loads(raw)
    except Exception:
        sys.exit(0)

    key = _task_key(data)
    if not key or gm is None:
        sys.exit(0)

    try:
        _stderr_utf8()
        cfg = gm.config()
        preamble = gm.inject_preamble(
            key,
            top=cfg["top"],
            window_hours=cfg["window_hours"],
            min_count=cfg["min_count"],
        )
        if preamble:
            print(f"[gotcha-memory] {preamble}", file=sys.stderr)
    except Exception:
        pass  # a learning hook must never break the flow

    sys.exit(0)


def _self_test() -> None:
    assert _task_key({"tool_name": "Bash", "tool_input": {"command": "ls", "description": "lista"}}) == "lista"
    assert _task_key({"tool_name": "Bash", "tool_input": {"command": "x" * 200}}) == "x" * 80
    assert _task_key({"tool_name": "Read", "tool_input": {"command": "ls"}}) == ""
    assert _task_key({"tool_name": "Bash", "tool_input": {}}) == ""
    assert _task_key({}) == ""
    # end-to-end with a temporary store: curated fires in the preamble
    import tempfile
    assert gm is not None, "lib vendorizada nao importou"
    with tempfile.TemporaryDirectory() as d:
        gm.add_curated_gotcha("deploy", "cheque o backend, nao so o gate", store_dir=d)
        pre = gm.inject_preamble("rodar o deploy do site", store_dir=d)
        assert "backend" in pre, "curated deveria disparar no preflight"
    print("self-test OK")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("--self-test", "-t"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
        _self_test()
    else:
        main()
