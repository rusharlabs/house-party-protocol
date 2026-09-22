#!/usr/bin/env python3
"""
handoff_guard -- Stop + PreCompact: ensures a fresh handoff exists, without EVER blocking.

Merges the formal design (pseudocode: freshness<15min, degraded-auto on the 2nd Stop) with
the simpler mechanism of a reference guard (stop_state_guard.py): pure anti-loop via `stop_hook_active`
(no marker-file of its own) and freshness check by mtime. Never truly blocks (the only
"decision:block" is a single /pre-clear express request on Stop; without stop_hook_active it does
not repeat -- the 2nd time it becomes degraded-auto and releases).

Flow:
  PreCompact: fresh handoff (<15min)? exit 0. Otherwise: additionalContext asking for a refresh, exit 0
              (PreCompact NEVER blocks -- there is no way to refuse the compaction).
  Stop:       fresh handoff? exit 0.
              1st time (stop_hook_active absent) -> decision:block asking for /pre-clear express.
              2nd time (stop_hook_active=true, already tried) -> writes degraded-auto, exit 0 (releases).

Usage (hook): echo '{"hook_event_name":"Stop","session_id":"...","stop_hook_active":false}' | python handoff_guard.py
Exit: always 0 (a Stop/PreCompact hook must never bring down the harness process).

stdlib only. v1.0.0 -- 2026-07-10 (continuity-kit - Tier 1)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _handoff_io  # noqa: E402
import turn_checkpoint  # noqa: E402

_FRESH_SECONDS = 15 * 60
# The hook's own timeout is 30s; the checkpoint gets a slice of it and gives up quietly, because
# a turn that cannot be photographed still has to end.
_CHECKPOINT_BUDGET_SECONDS = 12.0

_PEDIDO_PRECOMPACT = (
    "⚠️ handoff_guard: context is about to compact without a fresh handoff. Write one BEFORE "
    "compaction — schema in schemas/handoff-v2.0.schema.json (fields: state.summary, "
    "next_step[].verify_first_cmd). `python hooks/_handoff_io.py write --stdin`."
)
_PEDIDO_STOP = (
    "⚠️ handoff_guard: no fresh handoff (<15min) from this session. Run /pre-clear (express) "
    "BEFORE stopping — or stop anyway and this hook writes a degraded handoff on the 2nd attempt."
)


def _lane_id(payload: dict) -> str:
    return payload.get("lane_id") or "solo"


def _fresh_handoff(lane_id: str):
    h = _handoff_io.newest_handoff(lane_id)
    if not h:
        return None
    p = _handoff_io.current_path(lane_id)
    if not p.exists():
        return None
    age = time.time() - p.stat().st_mtime
    return h if age < _FRESH_SECONDS else None


def _take_checkpoint(payload: dict) -> tuple:
    """(ref, commit) of this turn's checkpoint, or ("", "") — never raises, never blocks."""
    session = payload.get("session_id") or _lane_id(payload)
    if (os.environ.get("HPP_TURN_CHECKPOINT") or "").strip().casefold() == "off":
        return "", ""
    try:
        # Why (adversarial review of 2.5.0, ALTA): the checkpoint used to resolve its repository from
        # CLAUDE_PROJECT_DIR / cwd on its own, so this hook's self-test — which redirects
        # `_handoff_io._PROJECT_ROOT` to a temp dir — still wrote `refs/hpp/checkpoints/s1/turn/1` and
        # a full snapshot into WHATEVER git repository contained the cwd. kit_doctor runs that
        # self-test with cwd = the module dir, i.e. inside the user's repository, in a stage whose
        # contract is "writes nothing to the target"; on a large repository it also blew the 30 s
        # smoke timeout and the install was refused. The checkpoint now goes where the handoff goes.
        ok, info = turn_checkpoint.write_checkpoint(
            session, label=payload.get("hook_event_name", ""),
            repo=_handoff_io._PROJECT_ROOT,
            budget_seconds=_CHECKPOINT_BUDGET_SECONDS)
    except Exception:  # noqa: BLE001 -- Why: the checkpoint is EVIDENCE about the turn, not the turn.
        # A git that is missing, locked or slow must cost the user one missing ref, never a blocked
        # Stop/PreCompact — a Stop hook that raises makes the session unable to end.
        return "", ""
    if not ok or not isinstance(info, dict) or not info.get("ref"):
        return "", ""
    return info["ref"], info["commit"]


def handle(payload: dict) -> dict:
    lane_id = _lane_id(payload)
    event = payload.get("hook_event_name", "")

    # The turn ends on the paths that RELEASE the session; a `decision: block` means "keep going",
    # so it is not a turn boundary and gets no checkpoint. Photographing the block path too would
    # double the cost of every Stop chain and file a checkpoint for a turn still in progress.
    if _fresh_handoff(lane_id):
        _take_checkpoint(payload)
        return {}

    if event == "PreCompact":
        _take_checkpoint(payload)
        return {"hookSpecificOutput": {"hookEventName": "PreCompact", "additionalContext": _PEDIDO_PRECOMPACT}}

    # Stop: pure anti-loop via stop_hook_active (reference technique -- simpler than a marker-file)
    if not payload.get("stop_hook_active"):
        return {"decision": "block", "reason": _PEDIDO_STOP}

    ckpt_ref, ckpt_commit = _take_checkpoint(payload)

    # 2nd attempt (already blocked once in this chain) -- writes degraded-auto and releases. Never blocks.
    degraded = _handoff_io.degraded_auto_aggregate(lane_id, payload.get("session_id", ""),
                                                    checkpoint_ref=ckpt_ref, checkpoint_commit=ckpt_commit)
    ok, result = _handoff_io.write(degraded)
    if not ok:
        # even if validation fails for some reason, NEVER block the session because of this
        return {"systemMessage": f"handoff_guard: degraded-auto failed validation ({result}) — releasing anyway"}
    suffix = f" · checkpoint {ckpt_ref}" if ckpt_ref else ""
    return {"systemMessage": f"handoff_guard: degraded handoff written ({result}){suffix}"}


def _self_test() -> int:
    import shutil
    import tempfile

    import subprocess

    tmp = Path(tempfile.mkdtemp(prefix="handoff_guard_selftest_"))
    # A real (tiny) repository for the checkpoint to land in — never the repository around the cwd.
    for cmd in (["init", "-q"], ["config", "user.email", "selftest@localhost.invalid"], ["config", "user.name", "selftest"]):
        subprocess.run(["git", "-C", str(tmp), *cmd], capture_output=True)
    (tmp / "seed.txt").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp), "add", "seed.txt"], capture_output=True)
    subprocess.run(["git", "-C", str(tmp), "commit", "-q", "-m", "seed"], capture_output=True)
    cwd_repo_refs_before = subprocess.run(["git", "for-each-ref", "refs/hpp/"], capture_output=True, text=True).stdout
    orig_root = _handoff_io._PROJECT_ROOT
    orig_dir = _handoff_io._HANDOFF_DIR
    orig_ledger = _handoff_io.LEDGER_PATH
    try:
        _handoff_io._PROJECT_ROOT = tmp
        _handoff_io._HANDOFF_DIR = tmp / ".claude" / "handoff"
        _handoff_io.LEDGER_PATH = _handoff_io._HANDOFF_DIR / "HANDOFF-LEDGER.jsonl"

        # with no handoff at all, Stop 1st time -> block
        out1 = handle({"hook_event_name": "Stop", "session_id": "s1", "stop_hook_active": False, "lane_id": "solo"})
        assert out1.get("decision") == "block", f"1st Stop without handoff should block: {out1}"

        # 2nd time (stop_hook_active=true) -> writes degraded-auto, releases
        out2 = handle({"hook_event_name": "Stop", "session_id": "s1", "stop_hook_active": True, "lane_id": "solo"})
        assert "decision" not in out2, f"2nd Stop should release (degraded-auto): {out2}"
        assert _handoff_io.current_path("solo").exists(), "degraded-auto was not written"

        # fresh handoff -> releases directly
        out3 = handle({"hook_event_name": "Stop", "session_id": "s1", "stop_hook_active": False, "lane_id": "solo"})
        assert out3 == {}, f"fresh handoff should release without block: {out3}"

        # PreCompact without a fresh handoff -> additionalContext, never block
        _handoff_io.current_path("solo").unlink()
        out4 = handle({"hook_event_name": "PreCompact", "session_id": "s1", "lane_id": "solo"})
        assert "decision" not in out4 and "additionalContext" in out4.get("hookSpecificOutput", {}), f"PreCompact should only warn: {out4}"

        # The cwd's repository (if any) must have gained NO checkpoint ref from this self-test.
        cwd_repo_refs_after = subprocess.run(["git", "for-each-ref", "refs/hpp/"], capture_output=True, text=True).stdout
        assert cwd_repo_refs_after == cwd_repo_refs_before, "self-test wrote a checkpoint into the repository around the cwd"
        sandbox_refs = subprocess.run(["git", "-C", str(tmp), "for-each-ref", "refs/hpp/"], capture_output=True, text=True).stdout
        assert sandbox_refs.strip(), "the checkpoint should have landed in the sandbox repository"
        print("self-test OK — Stop 1st=block, Stop 2nd=degraded-auto+release, fresh handoff=release, PreCompact=warn only, checkpoint in sandbox only")
        return 0
    finally:
        _handoff_io._PROJECT_ROOT = orig_root
        _handoff_io._HANDOFF_DIR = orig_dir
        _handoff_io.LEDGER_PATH = orig_ledger
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv) -> int:
    if argv and argv[0] in ("--self-test", "-t"):
        return _self_test()
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:  # noqa: BLE001 -- always fail-open
        payload = {}
    try:
        result = handle(payload)
    except Exception as e:  # noqa: BLE001 -- fail-open: never block the session because of a hook bug
        result = {"systemMessage": f"handoff_guard: internal error ignored (fail-open): {e}"}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
