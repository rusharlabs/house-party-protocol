#!/usr/bin/env python3
"""
gotcha_postflight -- PostToolUse hook (WARN-only) that CLOSES the learning loop.

Standalone hook that uses ONLY this
kit's vendored lib (no external dependencies). AFTER every Bash command,
if it FAILED, it calls `gotchas_memory.record_failure()`. When the SAME kind
of failure recurs >= N times within a window, it becomes a GOTCHA that
`gotcha_preflight` injects BEFORE the next run of the same task. Preflight
READS the lessons, postflight WRITES the failures.

NEVER blocks (WARN-not-block) -- exit 0 always. Defensive: any error -> exit 0.
Conservative in detection: only records a failure with a CLEAR error signal
(exit-code != 0 / is_error / error field) -- NEVER invents a failure (ambiguous = not-a-failure).

v1.0.0 -- 2026-07-11 (gotcha-memory kit)
"""
import json
import re
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parent.parent / "_lib"


def _stderr_utf8() -> None:
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass


def _extract_failure(tool_response):
    """Detects a failure in the Bash tool_response, CONSERVATIVE. Returns (is_fail, msg).

    Only reports a failure with a CLEAR signal: exit-code != 0, is_error True, or a
    non-empty error field. Ambiguous -> not-a-failure (never invents one). msg =
    stderr/error, truncated. Accepts several field-name conventions (harness portability).

    # Why: the real Claude Code harness doesn't send a dict with an exit code -- a Bash failure
    # arrives as the STRING "Error: Exit code N\n<output>" (measured in real transcripts: every
    # failure looks like that; every success is a dict). Without this branch the kit is vacuous: it
    # records zero failures and never learns. Deliberately conservative: "Error: PreToolUse:..." (hook
    # block) and "Error: Permission..." (denial) aren't command-execution failures, and are left out.
    """
    if isinstance(tool_response, str):
        import re
        m = re.match(r"Error: Exit code (\d+)\s*\n?(.*)", tool_response, re.DOTALL)
        if m:
            body = m.group(2).strip()
            return True, (body or f"exit {m.group(1)}")[:500]
        return False, ""
    if not isinstance(tool_response, dict):
        return False, ""
    # exit code in several conventions (bool does NOT count as an exit code)
    for k in ("exit_code", "exitCode", "returncode", "return_code", "code", "status"):
        v = tool_response.get(k)
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)) and int(v) != 0:
            err = str(tool_response.get("stderr") or tool_response.get("error") or "").strip()
            return True, (err or f"exit {int(v)}")[:500]
    # explicit error flags
    for k in ("is_error", "isError", "error_occurred"):
        if tool_response.get(k) is True:
            err = str(tool_response.get("stderr") or tool_response.get("error") or "").strip()
            return True, (err or "tool reported error")[:500]
    # non-empty error string field
    err_field = tool_response.get("error")
    if isinstance(err_field, str) and err_field.strip():
        return True, err_field.strip()[:500]
    return False, ""


# hook block and permission denial are not command-execution failures (conservative)
_NAO_E_FALHA_DE_EXECUCAO = re.compile(r"^(?:Error:\s*)?(?:PreToolUse:|Permission to use\b)")


def _extract_failure_event(data: dict):
    """Detects a failure in the hook's WHOLE payload, whatever the event. Returns (is_fail, msg).

    # Why: the host emits `PostToolUseFailure` (field `error`) when the tool fails, and
    # `PostToolUse` (field `tool_response`) when it finishes fine; a postflight that only reads
    # `tool_response` never sees the Bash failure -- the only event this memory exists to record.
    # The legacy form (string "Error: Exit code N" in `tool_response`) is still accepted.
    """
    if data.get("hook_event_name") == "PostToolUseFailure":
        err = data.get("error")
        if isinstance(err, dict):
            err = err.get("message") or err.get("error") or json.dumps(err, ensure_ascii=False)
        err = str(err or "").strip()
        if _NAO_E_FALHA_DE_EXECUCAO.match(err):
            return False, ""
        return True, (err or "tool reported failure")[:500]
    return _extract_failure(data.get("tool_response"))


def main() -> None:
    try:
        raw = sys.stdin.read() or "{}"
        data = json.loads(raw)
    except Exception:
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)
    ti = data.get("tool_input") or {}
    cmd = ti.get("command", "")
    if not cmd:
        sys.exit(0)

    is_fail, err = _extract_failure_event(data)
    if not is_fail:
        sys.exit(0)  # success (or ambiguous) -> nothing to learn

    try:
        if str(_LIB) not in sys.path:
            sys.path.insert(0, str(_LIB))
        import gotchas_memory as gm

        _stderr_utf8()
        # task_key MATCHES the one in gotcha_preflight: description or cmd[:80]
        # Why: truncating before redacting could cut a token in half and leave its
        # prefix outside the redaction's reach; redaction comes first, truncation after.
        desc = gm.redact_secrets(ti.get("description") or gm.redact_secrets(cmd)[:80])
        # the same tool call (tool_use_id) becomes ONE record, no matter how many events arrive
        tool_use_id = data.get("tool_use_id")
        dedupe_key = f"tool_use:{tool_use_id}" if isinstance(tool_use_id, str) and tool_use_id else None
        gm.record_failure(desc, err, context={"cmd": gm.redact_secrets(cmd)[:200]}, dedupe_key=dedupe_key)
        try:
            # Why: the append had no ceiling (1.9 MB / 1,744 lines in a
            # month) and the preflight re-reads the WHOLE file on every Bash.
            gm.rotate_failures()
        except Exception:  # noqa: BLE001 -- retention is a convenience; it must never bring down the hook
            pass

        # if the failure has already recurred >= min_count, the lesson is active -- warn (transparency)
        try:
            if gm.gotchas_for_task(desc):
                print(
                    f"[gotcha-memory] failure recorded for '{desc[:55]}' — "
                    "lesson active on the next preflight of this task.",
                    file=sys.stderr,
                )
        except Exception:
            pass
    except Exception:
        pass  # a learning hook must never break the flow

    sys.exit(0)


def _self_test() -> None:
    assert _extract_failure({"exit_code": 1, "stderr": "boom"}) == (True, "boom")
    assert _extract_failure({"exitCode": 0})[0] is False
    assert _extract_failure({"is_error": True, "error": "x"})[0] is True
    assert _extract_failure({"stdout": "ok"})[0] is False
    assert _extract_failure("not a dict")[0] is False
    # the harness's REAL shape: a failed Bash arrives as the string "Error: Exit code N"
    assert _extract_failure("Error: Exit code 1\nboom") == (True, "boom")
    assert _extract_failure("Error: Exit code 143") == (True, "exit 143")
    # controls: hook block and denial are NOT a failure (conservative)
    assert _extract_failure("Error: PreToolUse:Bash hook blocked the command")[0] is False
    assert _extract_failure("Error: Permission to use Bash denied")[0] is False
    assert _extract_failure({"error": "failed hard"})[0] is True
    assert _extract_failure({"exit_code": True})[0] is False  # bool is not an exit code
    assert _extract_failure({"returncode": 2})[0] is True
    # the host's failure event (PostToolUseFailure) carries `error`, not `tool_response`
    failure = {"hook_event_name": "PostToolUseFailure", "error": "Command exited with code 1: boom"}
    assert _extract_failure_event(failure) == (True, "Command exited with code 1: boom")
    assert _extract_failure_event({"hook_event_name": "PostToolUseFailure", "error": {"message": "m"}}) == (True, "m")
    assert _extract_failure_event({"hook_event_name": "PostToolUseFailure"})[0] is True  # a failure with no text is still a failure
    # controls: hook block / denial stay out, and the legacy form keeps passing
    assert _extract_failure_event({"hook_event_name": "PostToolUseFailure", "error": "PreToolUse:Bash hook blocked"})[0] is False
    assert _extract_failure_event({"hook_event_name": "PostToolUseFailure", "error": "Permission to use Bash denied"})[0] is False
    assert _extract_failure_event({"hook_event_name": "PostToolUse", "tool_response": "Error: Exit code 1\nboom"}) == (True, "boom")
    assert _extract_failure_event({"tool_response": {"stdout": "ok"}})[0] is False
    # end-to-end: record into a temporary store via env (without touching the project)
    import os
    import tempfile
    if str(_LIB) not in sys.path:
        sys.path.insert(0, str(_LIB))
    import gotchas_memory as gm
    with tempfile.TemporaryDirectory() as d:
        ev = gm.record_failure("task:teste", "ETIMEDOUT", store_dir=d)
        assert ev["family"] == "transient"
        assert (Path(d) / "failures.jsonl").exists()
        # the same tool call arriving twice becomes ONE record
        gm.record_failure("task:dup", "boom", store_dir=d, dedupe_key="tool_use:x")
        gm.record_failure("task:dup", "boom", store_dir=d, dedupe_key="tool_use:x")
        lines = (Path(d) / "failures.jsonl").read_text(encoding="utf-8").splitlines()
        assert sum(1 for l in lines if '"tool_use:x"' in l) == 1
        _ = os  # (env not used in the direct test; record_failure receives store_dir)
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
