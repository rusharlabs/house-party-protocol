#!/usr/bin/env python3
"""
handoff_inject -- SessionStart: injects the newest valid handoff (<=4KB) + writes 'consumed'.

Fail-open (pattern of a reference session_start.py): any error = exit 0 with no output, never brings
down the session boot. Transition compat: no JSON handoff but with RESUME-NEXT.md (the house's
legacy) -> injects only the pointer + the LC-4 rule, without inventing structure.

Usage (hook): echo '{"hook_event_name":"SessionStart","session_id":"..."}' | python handoff_inject.py
Exit: always 0.

stdlib only. v1.0.0 -- 2026-07-10 (continuity-kit - Tier 1)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _handoff_io  # noqa: E402


def build_context(payload: dict) -> str | None:
    lane_id = payload.get("lane_id") or "solo"
    h = _handoff_io.newest_handoff(lane_id) or _handoff_io.newest_handoff(None)
    if h:
        text = _handoff_io.render(h, cap_bytes=4096)
        _handoff_io.consume(h["handoff_id"], payload.get("session_id", ""), h.get("session", {}).get("lane_id", lane_id))
        return text

    resume_next = _handoff_io._PROJECT_ROOT / ".claude" / "RESUME-NEXT.md"
    if resume_next.exists():
        return (
            "⚠️ RESTORED CONTEXT = HISTORICAL REFERENCE, NOT A QUEUE (LC-4)\n"
            "No JSON handoff yet — .claude/RESUME-NEXT.md (legacy) exists: read it as "
            "REFERENCE and reconfirm everything at the live source before acting."
        )
    return None


def _self_test() -> int:
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="handoff_inject_selftest_"))
    orig_root, orig_dir, orig_ledger = _handoff_io._PROJECT_ROOT, _handoff_io._HANDOFF_DIR, _handoff_io.LEDGER_PATH
    try:
        _handoff_io._PROJECT_ROOT = tmp
        _handoff_io._HANDOFF_DIR = tmp / ".claude" / "handoff"
        _handoff_io.LEDGER_PATH = _handoff_io._HANDOFF_DIR / "HANDOFF-LEDGER.jsonl"

        assert build_context({"session_id": "s1"}) is None, "without handoff and without RESUME-NEXT it should return None"

        (tmp / ".claude").mkdir(parents=True, exist_ok=True)
        (tmp / ".claude" / "RESUME-NEXT.md").write_text("pending: x", encoding="utf-8")
        ctx_legacy = build_context({"session_id": "s1"})
        assert ctx_legacy and "LC-4" in ctx_legacy and "RESUME-NEXT" in ctx_legacy

        ok, _ = _handoff_io.write(_handoff_io._demo_handoff("solo"))
        assert ok
        ctx = build_context({"session_id": "s1", "lane_id": "solo"})
        assert ctx and "LC-4" in ctx and len(ctx.encode("utf-8")) <= 4096

        ledger_lines = _handoff_io.LEDGER_PATH.read_text(encoding="utf-8").splitlines()
        assert any(json.loads(l)["event"] == "consumed" for l in ledger_lines), "consumed event not recorded"

        print("self-test OK — no handoff+no legacy=None, legacy RESUME-NEXT.md=pointer+LC-4, real handoff=injects+consumed")
        return 0
    finally:
        _handoff_io._PROJECT_ROOT, _handoff_io._HANDOFF_DIR, _handoff_io.LEDGER_PATH = orig_root, orig_dir, orig_ledger
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv) -> int:
    if argv and argv[0] in ("--self-test", "-t"):
        return _self_test()
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        ctx = build_context(payload)
        if ctx:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}}, ensure_ascii=False))
    except Exception:  # noqa: BLE001 -- total fail-open (reference pattern)
        pass
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
