#!/usr/bin/env python3
"""
gotcha_preflight — PreToolUse hook (WARN-only): injeta as lições ANTES do comando.

Port standalone do `agentic_preflight.py` do repo-de-origem, reduzido ao loop de
gotchas (o operation_guard/task_complexity ficam no operator-kit — este kit é só
o ciclo falha→lição→prevenção). ANTES de cada Bash, deriva a task_key
(description ou cmd[:80]) e, se houver gotchas curated/recorrentes que casem,
imprime o preâmbulo no stderr — visível no chat, sem bloquear nada.

NUNCA bloqueia (WARN-not-block) — exit 0 sempre. Defensivo: qualquer erro -> exit 0.

v1.0.0 — 2026-07-11 (kit gotcha-memory)
"""
import json
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parent.parent / "_lib"


def _stderr_utf8() -> None:
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass


def _task_key(data: dict) -> str:
    """task_key = description do tool_input, senão cmd[:80]. '' se não for Bash com comando."""
    if data.get("tool_name") != "Bash":
        return ""
    ti = data.get("tool_input") or {}
    cmd = ti.get("command", "")
    if not cmd:
        return ""
    return ti.get("description") or cmd[:80]


def main() -> None:
    try:
        raw = sys.stdin.read() or "{}"
        data = json.loads(raw)
    except Exception:
        sys.exit(0)

    key = _task_key(data)
    if not key:
        sys.exit(0)

    try:
        if str(_LIB) not in sys.path:
            sys.path.insert(0, str(_LIB))
        import gotchas_memory as gm

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
        pass  # um hook de aprendizado jamais quebra o fluxo

    sys.exit(0)


def _self_test() -> None:
    assert _task_key({"tool_name": "Bash", "tool_input": {"command": "ls", "description": "lista"}}) == "lista"
    assert _task_key({"tool_name": "Bash", "tool_input": {"command": "x" * 200}}) == "x" * 80
    assert _task_key({"tool_name": "Read", "tool_input": {"command": "ls"}}) == ""
    assert _task_key({"tool_name": "Bash", "tool_input": {}}) == ""
    assert _task_key({}) == ""
    # ponta-a-ponta com store temporário: curated dispara no preâmbulo
    import tempfile
    if str(_LIB) not in sys.path:
        sys.path.insert(0, str(_LIB))
    import gotchas_memory as gm
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
