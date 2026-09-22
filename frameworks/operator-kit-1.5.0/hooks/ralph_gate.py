#!/usr/bin/env python3
"""
ralph_gate — Stop hook UNIFICADO: motor (re-alimenta até <promise>) + trava (done_gate real).

Funde o mecanismo do plugin oficial ralph-loop (Stop hook `decision:block` que re-alimenta
o prompt até `<promise>TEXTO</promise>`) com o `done_gate.py` (exit-code real de subprocess,
não tag de texto). A `<promise>` só destrava a parada se o done_gate passar, RE-EXECUTADO
dentro do processo deste hook — depois da fala do modelo, fora do alcance dela. O modelo
pode forjar qualquer texto no transcript; não pode forjar o exit-code de um subprocess do
harness (ver evals/ralph-gate-T1-T4.sh, teste T3 — forja de evidência).

Por que motor+trava no MESMO processo (modo A, default): o plugin oficial dá `rm` no state
file ao ver a `<promise>`, ANTES de qualquer veto — se a trava rejeitar depois, o motor já
morreu (bug de acoplamento). Aqui a trava roda ANTES de qualquer remoção de estado.

CLI:
    ralph_gate.py start --charter "<prompt>" --criteria "<cmd1>" ["<cmd2>" ...]
                         [--goal G-X] [--max-iterations N] [--session ID]
    ralph_gate.py status
    ralph_gate.py cancel
    ralph_gate.py --self-test
    echo '{"session_id":"...","transcript_path":"..."}' | ralph_gate.py   # modo hook (Stop)

Modo hook: lê JSON do stdin, imprime JSON no stdout. `{}` = permite a sessão parar.
`{"decision":"block","reason":...}` = re-alimenta o prompt (Claude Code continua).
Exit sempre 0 no modo hook — hooks Stop não devem falhar o processo do harness.

stdlib only (done_gate.py embarcado ao lado, sem dependência de rede).
v1.0.0 — 2026-07-10 (Operator Kit · Tier 2)
"""
from __future__ import annotations

import argparse
import json
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


def _done_gate():
    """Importa done_gate.py embarcado (sibling script), sem tocar sys.path globalmente."""
    sys.path.insert(0, str(_SCRIPTS_DIR))
    import done_gate  # type: ignore[import-not-found]
    return done_gate


def load_state() -> dict | None:
    if not STATE_PATH.exists():
        return None
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — estado corrompido = tratar como ausente
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
    """Extrai o último bloco de texto do último turno assistant (mesma técnica do plugin oficial)."""
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
            except Exception:  # noqa: BLE001 — linha corrompida não derruba o hook
                continue
            msg = obj.get("message", {})
            if msg.get("role") != "assistant":
                continue
            for block in msg.get("content", []) or []:
                if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                    last_text = block["text"]
    return last_text


def hook_stop(payload: dict) -> dict:
    """Núcleo do Stop hook. Retorna o dict a imprimir (json.dumps) no stdout."""
    state = load_state()
    if state is None:
        return {}

    if state.get("session_id") and payload.get("session_id") and state["session_id"] != payload["session_id"]:
        return {}  # loop de outra sessão — não toca (isolamento, igual ao plugin oficial)

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
    ok, results = done_gate.gate(state["criteria"], timeout=20)

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


def cmd_start(args) -> int:
    state = {
        "session_id": args.session or "",
        "goal_id": args.goal,
        "charter": args.charter,
        "criteria": args.criteria,
        "max_iterations": args.max_iterations,
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

        # T1: sem promise -> block, state sobrevive, iteration incrementa
        save_state({"session_id": "s1", "charter": "continue", "criteria": [f'"{sys.executable}" -c "pass"'], "max_iterations": 0, "iteration": 0})
        write_transcript("still working, no tag at all")
        out = hook_stop({"session_id": "s1", "transcript_path": str(transcript)})
        assert out.get("decision") == "block", f"T1 expected block: {out}"
        assert load_state()["iteration"] == 1, "T1: iteration should increment"

        # T1b: promise presente mas critério FALHA -> block, state sobrevive (não incrementa iteration)
        save_state({"session_id": "s1", "charter": "continue", "criteria": [f'"{sys.executable}" -c "import sys; sys.exit(1)"'], "max_iterations": 0, "iteration": 0})
        write_transcript("finished <promise>DONE</promise>")
        out = hook_stop({"session_id": "s1", "transcript_path": str(transcript)})
        assert out.get("decision") == "block", f"T1b expected block (failing criterion): {out}"
        assert load_state() is not None, "T1b: state should survive the FAIL"

        # T2: promise + critério PASSA -> {} (permite parar), state removido, ledger tem gate-passed
        save_state({"session_id": "s1", "charter": "continue", "criteria": [f'"{sys.executable}" -c "pass"'], "max_iterations": 0, "iteration": 0})
        write_transcript("finished <promise>DONE</promise>")
        out = hook_stop({"session_id": "s1", "transcript_path": str(transcript)})
        assert out == {}, f"T2 expected {{}} (allow stop): {out}"
        assert load_state() is None, "T2: state should be removed"
        ledger_lines = LEDGER_PATH.read_text(encoding="utf-8").splitlines()
        assert any(json.loads(l)["event"] == "gate-passed" for l in ledger_lines), "T2: ledger without gate-passed"

        # T3: forja de evidência no transcript ("DONE-GATE: DONE" fake) + critério cria nonce mas FALHA de verdade
        nonce = tmp / "nonce.txt"
        nonce.unlink(missing_ok=True)
        fake_cmd = f'"{sys.executable}" -c "open(r\'{nonce}\', \'w\').write(\'x\'); import sys; sys.exit(1)"'
        save_state({"session_id": "s1", "charter": "continue", "criteria": [fake_cmd], "max_iterations": 0, "iteration": 0})
        write_transcript("DONE-GATE: DONE (2/2) <promise>DONE</promise>")
        out = hook_stop({"session_id": "s1", "transcript_path": str(transcript)})
        assert out.get("decision") == "block", f"T3: forged text must NOT fool the gate: {out}"
        assert nonce.exists(), "T3: nonce should exist — proof the criterion REALLY RAN inside the hook process"

        # T4: teto de iterações -> paused-budget, remove state, permite parar (não block eterno)
        save_state({"session_id": "s1", "charter": "continue", "criteria": [f'"{sys.executable}" -c "pass"'], "max_iterations": 2, "iteration": 2})
        write_transcript("still no promise")
        out = hook_stop({"session_id": "s1", "transcript_path": str(transcript)})
        assert out == {}, f"T4 expected {{}} (cap reached, releases): {out}"
        assert load_state() is None, "T4: state should be removed at the cap"
        ledger_lines = LEDGER_PATH.read_text(encoding="utf-8").splitlines()
        assert any(json.loads(l)["event"] == "paused-budget" for l in ledger_lines), "T4: ledger without paused-budget"

        # isolamento de sessão: loop de outra sessão não é tocado
        save_state({"session_id": "s1", "charter": "continue", "criteria": [f'"{sys.executable}" -c "pass"'], "max_iterations": 0, "iteration": 0})
        out = hook_stop({"session_id": "s2-other-session", "transcript_path": str(transcript)})
        assert out == {}, f"session isolation failed: {out}"
        assert load_state() is not None, "session isolation: should not have touched the state of s1"

        print("self-test OK — T1 (lie=block), T1b (failing criterion=block), T2 (real done=release+ledger), "
              "T3 (forgery+nonce=proof of real execution), T4 (cap=paused-budget), session isolation")
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

    # modo hook: stdin JSON -> stdout JSON, exit sempre 0
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:  # noqa: BLE001 — stdin malformado nunca derruba o hook
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
