#!/usr/bin/env python3
"""
ralph_gate - UNIFIED Stop hook: engine (re-feeds until <promise>) + latch (real done_gate).

Combines a Stop-hook loop engine (`decision:block` that
re-feeds the prompt until `<promise>TEXT</promise>`) with `done_gate.py` (real subprocess
exit-code, not a text tag). The `<promise>` only unlatches the stop if done_gate passes,
RE-RUN inside this hook's own process - after the model's turn, out of its reach. The
model can forge any text in the transcript; it cannot forge the exit-code of a harness
subprocess (see evals/ralph-gate-T1-T4.sh, test T3 - evidence forgery).

Why engine+latch in the SAME process (mode A, default): an engine that `rm`s the state
file as soon as it sees the `<promise>`, BEFORE any veto - if the latch rejects afterward,
the engine is already dead (a coupling bug). Here the latch runs BEFORE any state removal.

CLI:
    ralph_gate.py start --charter "<prompt>" --criteria "<cmd1>" ["<cmd2>" ...]
                         [--goal G-X] [--max-iterations N] [--session ID]
                         [--criterion-timeout SECONDS]   # per criterion, default 20
    ralph_gate.py status
    ralph_gate.py cancel
    ralph_gate.py --self-test
    echo '{"session_id":"...","transcript_path":"..."}' | ralph_gate.py   # hook mode (Stop)

Hook mode: reads JSON from stdin, prints JSON to stdout. `{}` = allows the session to stop.
`{"decision":"block","reason":...}` = re-feeds the prompt (Claude Code keeps going).
Exit always 0 in hook mode - Stop hooks must not fail the harness process.

stdlib only (done_gate.py embedded alongside, no network dependency).
v1.0.0 - 2026-07-10 (Operator Kit - Tier 2)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT")
_KIT_ROOT = Path(_PLUGIN_ROOT) if _PLUGIN_ROOT else _HERE.parent
_SCRIPTS_DIR = _KIT_ROOT / "scripts"

_PROJECT_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
STATE_PATH = _PROJECT_ROOT / ".claude" / "ralph-gate.local.json"
LEDGER_PATH = _PROJECT_ROOT / ".claude" / "handoff" / "HANDOFF-LEDGER.jsonl"

_PROMISE_RE = re.compile(r"<promise>(.*?)</promise>", re.DOTALL)
DEFAULT_CRITERION_TIMEOUT = 20


def _done_gate():
    """Imports the embedded done_gate.py (sibling script), without touching sys.path globally."""
    sys.path.insert(0, str(_SCRIPTS_DIR))
    import done_gate  # type: ignore[import-not-found]
    return done_gate


def load_state() -> dict | None:
    if not STATE_PATH.exists():
        return None
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - corrupted state = treat as absent
        return None


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def remove_state() -> None:
    STATE_PATH.unlink(missing_ok=True)


def append_ledger(event: str, **fields) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "event": event, "lane_id": "solo", **fields}
    with open(LEDGER_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def last_assistant_text(transcript_path: str) -> str:
    """Extracts the last text block from the last assistant turn."""
    p = Path(transcript_path) if transcript_path else None
    if not p or not p.exists():
        return ""
    last_text = ""
    with open(p, encoding="utf-8", errors="replace") as f:
        for line in f:
            if '"role":"assistant"' not in line and '"role": "assistant"' not in line:
                continue
            try:
                obj = json.loads(line)
            except Exception:  # noqa: BLE001 - a corrupted line does not take down the hook
                continue
            msg = obj.get("message", {})
            if msg.get("role") != "assistant":
                continue
            for block in msg.get("content", []) or []:
                if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                    last_text = block["text"]
    return last_text


def hook_stop(payload: dict) -> dict:
    """Core of the Stop hook. Returns the dict to print (json.dumps) to stdout."""
    state = load_state()
    if state is None:
        return {}

    if state.get("session_id") and payload.get("session_id") and state["session_id"] != payload["session_id"]:
        return {}  # loop from another session - do not touch it (per-session isolation)

    max_it = state.get("max_iterations", 0)
    if max_it and state.get("iteration", 0) >= max_it:
        append_ledger("paused-budget", goal_id=state.get("goal_id"), iteration=state.get("iteration"))
        remove_state()
        return {}

    text = last_assistant_text(payload.get("transcript_path", ""))
    m = _PROMISE_RE.search(text)
    if not m:
        state["iteration"] = state.get("iteration", 0) + 1
        save_state(state)
        return {
            "decision": "block",
            "reason": state["charter"],
            "systemMessage": f"ralph-gate: iteration {state['iteration']} (no <promise> detected)",
        }

    done_gate = _done_gate()
    ok, results = done_gate.gate(state["criteria"], timeout=_criterion_timeout(state))

    if ok:
        append_ledger("gate-passed", goal_id=state.get("goal_id"), iteration=state.get("iteration"))
        goal_id = state.get("goal_id")
        if goal_id:
            gl = _SCRIPTS_DIR / "goal_ledger.py"
            if gl.exists():
                subprocess.run([sys.executable, str(gl), "--set", goal_id, "done"], capture_output=True, timeout=20)
        remove_state()
        return {}

    failed = [r for r in results if not r["passed"]]
    tails = "\n".join(f"  [FAIL] {r['cmd']}: {r['tail'][-150:]}" for r in failed)
    append_ledger(
        "gate-failed",
        goal_id=state.get("goal_id"),
        iteration=state.get("iteration"),
        failed_cmds=[r["cmd"] for r in failed],
    )
    return {
        "decision": "block",
        "reason": f"{state['charter']}\n\nDo NOT emit <promise> until it REALLY passes. Real failures:\n{tails}",
        "systemMessage": "ralph-gate: done_gate REJECTED the promise (a criterion really failed)",
    }


def _criterion_timeout(state: dict):
    """The per-criterion timeout stored by `start`; a state without a valid one keeps the 20 s default."""
    value = state.get("criterion_timeout", DEFAULT_CRITERION_TIMEOUT)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        return DEFAULT_CRITERION_TIMEOUT
    return value


def _positive_seconds(raw: str) -> float:
    try:
        value = float(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number of seconds: {raw!r}") from None
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError(f"must be a positive, finite number of seconds: {raw!r}")
    return value


def cmd_start(args) -> int:
    state = {
        "session_id": args.session or "",
        "goal_id": args.goal,
        "charter": args.charter,
        "criteria": args.criteria,
        "max_iterations": args.max_iterations,
        "criterion_timeout": args.criterion_timeout,
        "iteration": 0,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    save_state(state)
    print(f"ralph-gate: armed (goal={args.goal}, max_iterations={args.max_iterations}, {len(args.criteria)} criterion/criteria)")
    return 0


def cmd_status() -> int:
    state = load_state()
    print(json.dumps(state, indent=2, ensure_ascii=False) if state else "ralph-gate: no active loop")
    return 0


def cmd_cancel() -> int:
    had = STATE_PATH.exists()
    remove_state()
    print("ralph-gate: cancelled" if had else "ralph-gate: no active loop")
    return 0


def _self_test() -> int:
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="ralph_gate_selftest_"))
    global STATE_PATH, LEDGER_PATH
    orig_state, orig_ledger = STATE_PATH, LEDGER_PATH
    try:
        STATE_PATH = tmp / "ralph-gate.local.json"
        LEDGER_PATH = tmp / "handoff" / "HANDOFF-LEDGER.jsonl"

        transcript = tmp / "transcript.jsonl"

        def write_transcript(text: str):
            line = json.dumps({"message": {"role": "assistant", "content": [{"type": "text", "text": text}]}})
            transcript.write_text(line + "\n", encoding="utf-8")

        # T1: no promise -> block, state survives, iteration increments
        save_state({"session_id": "s1", "charter": "continue", "criteria": [f'"{sys.executable}" -c "pass"'], "max_iterations": 0, "iteration": 0})
        write_transcript("still working, no tag at all")
        out = hook_stop({"session_id": "s1", "transcript_path": str(transcript)})
        assert out.get("decision") == "block", f"T1 expected block: {out}"
        assert load_state()["iteration"] == 1, "T1: iteration should increment"

        # T1b: promise present but the criterion FAILS -> block, state survives (does not increment iteration)
        save_state({"session_id": "s1", "charter": "continue", "criteria": [f'"{sys.executable}" -c "import sys; sys.exit(1)"'], "max_iterations": 0, "iteration": 0})
        write_transcript("finished <promise>DONE</promise>")
        out = hook_stop({"session_id": "s1", "transcript_path": str(transcript)})
        assert out.get("decision") == "block", f"T1b expected block (failing criterion): {out}"
        assert load_state() is not None, "T1b: state should survive the FAIL"

        # T2: promise + criterion PASSES -> {} (allows stop), state removed, ledger has gate-passed
        save_state({"session_id": "s1", "charter": "continue", "criteria": [f'"{sys.executable}" -c "pass"'], "max_iterations": 0, "iteration": 0})
        write_transcript("finished <promise>DONE</promise>")
        out = hook_stop({"session_id": "s1", "transcript_path": str(transcript)})
        assert out == {}, f"T2 expected {{}} (allow stop): {out}"
        assert load_state() is None, "T2: state should be removed"
        ledger_lines = LEDGER_PATH.read_text(encoding="utf-8").splitlines()
        assert any(json.loads(l)["event"] == "gate-passed" for l in ledger_lines), "T2: ledger without gate-passed"

        # T3: evidence forgery in the transcript (fake "DONE-GATE: DONE") + criterion creates a nonce but really FAILS
        nonce = tmp / "nonce.txt"
        nonce.unlink(missing_ok=True)
        fake_cmd = f'"{sys.executable}" -c "open(r\'{nonce}\', \'w\').write(\'x\'); import sys; sys.exit(1)"'
        save_state({"session_id": "s1", "charter": "continue", "criteria": [fake_cmd], "max_iterations": 0, "iteration": 0})
        write_transcript("DONE-GATE: DONE (2/2) <promise>DONE</promise>")
        out = hook_stop({"session_id": "s1", "transcript_path": str(transcript)})
        assert out.get("decision") == "block", f"T3: forged text must NOT fool the gate: {out}"
        assert nonce.exists(), "T3: nonce should exist — proof the criterion REALLY RAN inside the hook process"

        # T4: iteration cap -> paused-budget, removes state, allows stop (not an eternal block)
        save_state({"session_id": "s1", "charter": "continue", "criteria": [f'"{sys.executable}" -c "pass"'], "max_iterations": 2, "iteration": 2})
        write_transcript("still no promise")
        out = hook_stop({"session_id": "s1", "transcript_path": str(transcript)})
        assert out == {}, f"T4 expected {{}} (cap reached, releases): {out}"
        assert load_state() is None, "T4: state should be removed at the cap"
        ledger_lines = LEDGER_PATH.read_text(encoding="utf-8").splitlines()
        assert any(json.loads(l)["event"] == "paused-budget" for l in ledger_lines), "T4: ledger without paused-budget"

        # session isolation: a loop from another session is not touched
        save_state({"session_id": "s1", "charter": "continue", "criteria": [f'"{sys.executable}" -c "pass"'], "max_iterations": 0, "iteration": 0})
        out = hook_stop({"session_id": "s2-other-session", "transcript_path": str(transcript)})
        assert out == {}, f"session isolation failed: {out}"
        assert load_state() is not None, "session isolation: should not have touched the state of s1"

        # T5: --criterion-timeout is stored in the state (default 20) and bounds EACH criterion
        import contextlib
        import io
        parser = build_parser()
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_start(parser.parse_args(["start", "--charter", "c", "--criteria", "x"]))
            assert load_state().get("criterion_timeout") == 20, "T5: the default criterion_timeout should be 20"
            cmd_start(parser.parse_args(["start", "--charter", "c", "--criteria", "x", "--criterion-timeout", "45"]))
            assert load_state().get("criterion_timeout") == 45, "T5: --criterion-timeout should be stored in the state"
        for bad in ("0", "-3", "inf", "nan", "abc"):
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    parser.parse_args(["start", "--charter", "c", "--criteria", "x", "--criterion-timeout", bad])
            except SystemExit as exc:
                assert exc.code == 2, f"T5: --criterion-timeout {bad!r} should be refused with exit 2"
            else:
                raise AssertionError(f"T5: --criterion-timeout {bad!r} should be refused")
        slow = f'"{sys.executable}" -c "import time; time.sleep(2)"'
        save_state({"session_id": "s1", "charter": "continue", "criteria": [slow], "max_iterations": 0, "iteration": 0,
                    "criterion_timeout": 0.5})
        write_transcript("finished <promise>DONE</promise>")
        out = hook_stop({"session_id": "s1", "transcript_path": str(transcript)})
        assert out.get("decision") == "block" and "timeout" in out.get("reason", ""), \
            f"T5: a criterion slower than criterion_timeout must block as a timeout: {out}"
        # CONTROL: a state written before the flag existed (no key) keeps the 20 s default and passes
        save_state({"session_id": "s1", "charter": "continue", "criteria": [slow], "max_iterations": 0, "iteration": 0})
        out = hook_stop({"session_id": "s1", "transcript_path": str(transcript)})
        assert out == {}, f"T5 control: without criterion_timeout the 20 s default must still release: {out}"

        print("self-test OK — T1 (lie=block), T1b (failing criterion=block), T2 (real done=release+ledger), "
              "T3 (forgery+nonce=proof of real execution), T4 (cap=paused-budget), session isolation, "
              "T5 (criterion_timeout stored, validated and used)")
        return 0
    finally:
        STATE_PATH, LEDGER_PATH = orig_state, orig_ledger
        shutil.rmtree(tmp, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ralph_gate.py")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("start")
    s.add_argument("--charter", required=True)
    s.add_argument("--criteria", nargs="+", required=True)
    s.add_argument("--goal", default=None)
    s.add_argument("--max-iterations", type=int, default=0)
    s.add_argument("--session", default="")
    s.add_argument("--criterion-timeout", type=_positive_seconds, default=DEFAULT_CRITERION_TIMEOUT,
                   help="seconds each criterion may run before it counts as a failure (default 20)")

    sub.add_parser("status")
    sub.add_parser("cancel")
    p.add_argument("--self-test", action="store_true")
    return p


def main(argv) -> int:
    args = build_parser().parse_args(argv)

    if args.self_test:
        return _self_test()
    if args.cmd == "start":
        return cmd_start(args)
    if args.cmd == "status":
        return cmd_status()
    if args.cmd == "cancel":
        return cmd_cancel()

    # hook mode: stdin JSON -> stdout JSON, exit always 0
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:  # noqa: BLE001 - malformed stdin never takes down the hook
        payload = {}
    result = hook_stop(payload)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
