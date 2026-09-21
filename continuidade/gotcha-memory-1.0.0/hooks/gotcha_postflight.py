#!/usr/bin/env python3
"""
gotcha_postflight — PostToolUse hook (WARN-only) que FECHA o loop de aprendizado.

Port standalone do `agentic_postflight.py` do repo-de-origem, usando SÓ a lib
vendorizada deste kit (zero dependência de core.*). DEPOIS de cada comando Bash,
se ele FALHOU, chama `gotchas_memory.record_failure()`. Quando o MESMO tipo de
falha recorre >= N vezes numa janela, vira um GOTCHA que o `gotcha_preflight`
injeta ANTES da próxima execução da mesma tarefa. Preflight LÊ as lições,
postflight ESCREVE as falhas.

NUNCA bloqueia (WARN-not-block) — exit 0 sempre. Defensivo: qualquer erro -> exit 0.
Conservador na detecção: só registra falha com sinal CLARO de erro (exit-code != 0
/ is_error / campo error) — NUNCA inventa falha (ambíguo = não-falha).

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


def _extract_failure(tool_response):
    """Detecta falha no tool_response do Bash, CONSERVADOR. Retorna (is_fail, msg).

    Só reporta falha com sinal CLARO: exit-code != 0, is_error True, ou campo
    error não-vazio. Ambíguo -> não-falha (não inventa). msg = stderr/error
    truncado. Aceita várias convenções de nome de campo (portabilidade de harness).

    # Why: o harness real do Claude Code nao envia dict com exit code — uma falha de Bash chega
    # como STRING "Error: Exit code N\n<saida>" (medido em transcripts reais: todas as falhas
    # assim; todos os sucessos, dict). Sem este ramo o kit inteiro e vacuo: registra zero
    # falhas e nunca aprende. Conservador de proposito: "Error: PreToolUse:..." (bloqueio de
    # hook) e "Error: Permission..." (negacao) nao sao falha de execucao do comando e ficam de fora.
    """
    if isinstance(tool_response, str):
        import re
        m = re.match(r"Error: Exit code (\d+)\s*\n?(.*)", tool_response, re.DOTALL)
        if m:
            corpo = m.group(2).strip()
            return True, (corpo or f"exit {m.group(1)}")[:500]
        return False, ""
    if not isinstance(tool_response, dict):
        return False, ""
    # exit code em várias convenções (bool NÃO conta como exit code)
    for k in ("exit_code", "exitCode", "returncode", "return_code", "code", "status"):
        v = tool_response.get(k)
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)) and int(v) != 0:
            err = str(tool_response.get("stderr") or tool_response.get("error") or "").strip()
            return True, (err or f"exit {int(v)}")[:500]
    # flags de erro explícitas
    for k in ("is_error", "isError", "error_occurred"):
        if tool_response.get(k) is True:
            err = str(tool_response.get("stderr") or tool_response.get("error") or "").strip()
            return True, (err or "tool reported error")[:500]
    # campo error string não-vazio
    err_field = tool_response.get("error")
    if isinstance(err_field, str) and err_field.strip():
        return True, err_field.strip()[:500]
    return False, ""


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

    is_fail, err = _extract_failure(data.get("tool_response"))
    if not is_fail:
        sys.exit(0)  # sucesso (ou ambíguo) -> nada a aprender

    try:
        if str(_LIB) not in sys.path:
            sys.path.insert(0, str(_LIB))
        import gotchas_memory as gm

        _stderr_utf8()
        # task_key CASA com o do gotcha_preflight: description or cmd[:80]
        # Why: truncar antes de redigir pode cortar um token ao meio e deixar o prefixo
        # dele fora do alcance da redacao; a redacao vem primeiro, o corte depois.
        desc = gm.redact_secrets(ti.get("description") or gm.redact_secrets(cmd)[:80])
        gm.record_failure(desc, err, context={"cmd": gm.redact_secrets(cmd)[:200]})
        try:
            # Why: o append era sem teto (1,9 MB / 1.744 linhas em um mes) e o preflight rele o
            # arquivo INTEIRO a cada Bash.
            gm.rotate_failures()
        except Exception:  # noqa: BLE001 — retencao e' conveniencia; nunca derruba o hook
            pass

        # se a falha já fez recorrer >= min_count, a lição está ativa — avisa (transparência)
        try:
            if gm.gotchas_for_task(desc):
                print(
                    f"[gotcha-memory] falha registrada p/ '{desc[:55]}' — "
                    "lição ativa no próximo preflight desta tarefa.",
                    file=sys.stderr,
                )
        except Exception:
            pass
    except Exception:
        pass  # um hook de aprendizado jamais quebra o fluxo

    sys.exit(0)


def _self_test() -> None:
    assert _extract_failure({"exit_code": 1, "stderr": "boom"}) == (True, "boom")
    assert _extract_failure({"exitCode": 0})[0] is False
    assert _extract_failure({"is_error": True, "error": "x"})[0] is True
    assert _extract_failure({"stdout": "ok"})[0] is False
    assert _extract_failure("not a dict")[0] is False
    # a forma REAL do harness — estes 2 FALHAVAM antes do port de 2026-09-03
    assert _extract_failure("Error: Exit code 1\nboom") == (True, "boom")
    assert _extract_failure("Error: Exit code 143") == (True, "exit 143")
    # controles: bloqueio de hook e negacao NAO sao falha (conservador)
    assert _extract_failure("Error: PreToolUse:Bash hook blocked the command")[0] is False
    assert _extract_failure("Error: Permission to use Bash denied")[0] is False
    assert _extract_failure({"error": "failed hard"})[0] is True
    assert _extract_failure({"exit_code": True})[0] is False  # bool não é exit code
    assert _extract_failure({"returncode": 2})[0] is True
    # ponta-a-ponta: registrar num store temporário via env (sem tocar o projeto)
    import os
    import tempfile
    if str(_LIB) not in sys.path:
        sys.path.insert(0, str(_LIB))
    import gotchas_memory as gm
    with tempfile.TemporaryDirectory() as d:
        ev = gm.record_failure("task:teste", "ETIMEDOUT", store_dir=d)
        assert ev["family"] == "transient"
        assert (Path(d) / "failures.jsonl").exists()
        _ = os  # (env não usado no teste direto; record_failure recebe store_dir)
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
