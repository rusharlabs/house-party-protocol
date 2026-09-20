#!/usr/bin/env python3
"""
handoff_guard — Stop + PreCompact: garante que um handoff fresco existe, sem NUNCA travar.

Fusão do design formal (pseudo-código: freshness<15min, degraded-auto no 2º Stop) com
o mecanismo mais simples de um guard de referência (stop_state_guard.py): anti-loop via `stop_hook_active` puro
(sem marker-file próprio) e checagem de frescor por mtime. Nunca bloqueia de verdade (o único
"decision:block" é 1 pedido único de /pre-clear express no Stop; sem stop_hook_active isso não
se repete — a 2ª vez vira degraded-auto e libera).

Fluxo:
  PreCompact: handoff fresco (<15min)? exit 0. Senão: additionalContext pedindo refresh, exit 0
              (PreCompact NUNCA block — não há como recusar a compactação).
  Stop:       handoff fresco? exit 0.
              1ª vez (stop_hook_active ausente) → decision:block pedindo /pre-clear express.
              2ª vez (stop_hook_active=true, já tentou) → grava degraded-auto, exit 0 (libera).

Uso (hook): echo '{"hook_event_name":"Stop","session_id":"...","stop_hook_active":false}' | python handoff_guard.py
Exit: sempre 0 (hook Stop/PreCompact não deve derrubar o processo do harness).

stdlib only. v1.0.0 — 2026-07-10 (continuity-kit · Tier 1)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _handoff_io  # noqa: E402

_FRESH_SECONDS = 15 * 60

_PEDIDO_PRECOMPACT = (
    "⚠️ handoff_guard: contexto vai compactar sem handoff fresco. Escreva um ANTES da "
    "compactação — schema em schemas/handoff-v1.1.schema.json (campos: estado.resumo, "
    "proximo_passo[].verify_first_cmd). `python hooks/_handoff_io.py write --stdin`."
)
_PEDIDO_STOP = (
    "⚠️ handoff_guard: sem handoff fresco (<15min) desta sessão. Rode /pre-clear (express) "
    "ANTES de parar — ou pare mesmo assim e este hook grava um handoff degradado na 2ª tentativa."
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


def handle(payload: dict) -> dict:
    lane_id = _lane_id(payload)
    event = payload.get("hook_event_name", "")

    if _fresh_handoff(lane_id):
        return {}

    if event == "PreCompact":
        return {"hookSpecificOutput": {"hookEventName": "PreCompact", "additionalContext": _PEDIDO_PRECOMPACT}}

    # Stop: anti-loop puro via stop_hook_active (técnica de referência — mais simples que marker-file)
    if not payload.get("stop_hook_active"):
        return {"decision": "block", "reason": _PEDIDO_STOP}

    # 2ª tentativa (já bloqueou uma vez nesta cadeia) — grava degraded-auto e libera. Nunca trava.
    degraded = _handoff_io.degraded_auto_aggregate(lane_id, payload.get("session_id", ""))
    ok, result = _handoff_io.write(degraded)
    if not ok:
        # mesmo se a validação falhar por algum motivo, NUNCA travar a sessão por causa disto
        return {"systemMessage": f"handoff_guard: degraded-auto falhou ao validar ({result}) — liberando mesmo assim"}
    return {"systemMessage": f"handoff_guard: handoff degradado gravado ({result})"}


def _self_test() -> int:
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="handoff_guard_selftest_"))
    orig_root = _handoff_io._PROJECT_ROOT
    orig_dir = _handoff_io._HANDOFF_DIR
    orig_ledger = _handoff_io.LEDGER_PATH
    try:
        _handoff_io._PROJECT_ROOT = tmp
        _handoff_io._HANDOFF_DIR = tmp / ".claude" / "handoff"
        _handoff_io.LEDGER_PATH = _handoff_io._HANDOFF_DIR / "HANDOFF-LEDGER.jsonl"

        # sem handoff nenhum, Stop 1a vez -> block
        out1 = handle({"hook_event_name": "Stop", "session_id": "s1", "stop_hook_active": False, "lane_id": "solo"})
        assert out1.get("decision") == "block", f"1a Stop sem handoff deveria block: {out1}"

        # 2a vez (stop_hook_active=true) -> grava degraded-auto, libera
        out2 = handle({"hook_event_name": "Stop", "session_id": "s1", "stop_hook_active": True, "lane_id": "solo"})
        assert "decision" not in out2, f"2a Stop deveria liberar (degraded-auto): {out2}"
        assert _handoff_io.current_path("solo").exists(), "degraded-auto não foi escrito"

        # handoff fresco -> libera direto
        out3 = handle({"hook_event_name": "Stop", "session_id": "s1", "stop_hook_active": False, "lane_id": "solo"})
        assert out3 == {}, f"handoff fresco deveria liberar sem block: {out3}"

        # PreCompact sem handoff fresco -> additionalContext, nunca block
        _handoff_io.current_path("solo").unlink()
        out4 = handle({"hook_event_name": "PreCompact", "session_id": "s1", "lane_id": "solo"})
        assert "decision" not in out4 and "additionalContext" in out4.get("hookSpecificOutput", {}), f"PreCompact deveria só avisar: {out4}"

        print("self-test OK — Stop 1a=block, Stop 2a=degraded-auto+libera, handoff fresco=libera, PreCompact=so avisa")
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
    except Exception:  # noqa: BLE001 — fail-open sempre
        payload = {}
    try:
        result = handle(payload)
    except Exception as e:  # noqa: BLE001 — fail-open: nunca travar a sessão por bug do hook
        result = {"systemMessage": f"handoff_guard: erro interno ignorado (fail-open): {e}"}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
