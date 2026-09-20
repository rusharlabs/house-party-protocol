#!/usr/bin/env python3
"""
done_gate (Operator Kit) — Definition-of-Done programática, config-driven.

Definition-of-Done programatica e config-driven: além de receber critérios
soltos (argv/stdin), aceita `--profile <tipo>` e lê os comandos de
`verificacao.done_criterios[<tipo>]` do operator-profile.yaml. É o gate
determinístico entre "achei que terminei" e "está verificado": exit 0 SÓ se
TODOS os critérios passarem (AND). Lista vazia = NÃO-done (nunca passa por omissão).

Uso:
    python done_gate.py "python -m pytest -q" "ruff check ."      # critérios soltos
    python done_gate.py --profile py                              # lê do perfil (tipo 'py')
    python done_gate.py --profile py --json                       # saída JSON p/ o loop
    echo '{"criteria":["pytest -q"]}' | python done_gate.py --stdin
    python done_gate.py --self-test

TRÊS ESTADOS, e só um é proibido (v1.1.0):

    DONE                todos os critérios passaram E ninguém declarou pendência.  exit 0
    PARCIAL-DECLARADO   quem executou DISSE o que falta (--declare-partial ou o
                        campo `partial` do stdin). Não é verde — exit 1 — mas é
                        um estado honesto, legível por máquina, com a lista do
                        que falta. A declaração VENCE o verde: critérios todos
                        passando + declaração = PARCIAL, porque quem executou
                        sabe mais que os critérios.                             exit 1
    NOT-DONE            falhou e ninguém declarou nada. É o estado que a casa
                        chama de "parcial silencioso" — o único PROIBIDO. O
                        gate não consegue impedir o silêncio, mas o NOMEIA na
                        saída e diz o que fazer.                                exit 1

    python done_gate.py "pytest -q" --declare-partial "faltam os testes de borda: X, Y"
    echo '{"criteria":["pytest -q"],"partial":{"missing":["X","Y"],"reason":"..."}}' \
        | python done_gate.py --stdin

    # Why: um gate binario empurra para um de dois erros — o agente pinta de verde o que nao
    # terminou, ou o loop trava num NOT-DONE sem saber o que falta. O terceiro estado e a saida
    # honesta: "nao terminei, e ESTE e o buraco". Downstream (handoff, ledger, o proprio loop)
    # le `partial: true` + `declared.missing` e sabe onde retomar. O exit continua 1 nos dois
    # casos nao-verdes: nada a jusante pode tratar parcial como pronto. A distincao mora no payload.

Exit: 0 = DONE · 1 = PARCIAL-DECLARADO ou NOT-DONE · 2 = uso inválido.
stdlib + PyYAML (só no modo --profile). Cross-platform (shell=True respeita o SO).

v1.1.0 — 2026-09-20 (A4: três estados) · v1.0.0 — 2026-06-19 (Operator Kit · Tier 1)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# importa o loader compartilhado do kit (.../operator-kit/_lib/profile_loader.py)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from _lib.profile_loader import load_profile, get
except Exception:  # noqa: BLE001 — sem loader, modo --profile fica indisponível mas o resto funciona
    load_profile = None  # type: ignore[assignment]
    get = None  # type: ignore[assignment]


def run_criterion(cmd: str, cwd: str | None = None, timeout: int = 600) -> dict:
    """Roda um comando-critério. Retorna {cmd, passed, exit_code, tail}. Nunca crasha."""
    try:
        r = subprocess.run(
            cmd, shell=True, cwd=cwd,
            capture_output=True, text=True, timeout=timeout,
        )
        tail = ((r.stdout or "") + (r.stderr or "")).strip()[-400:]
        return {"cmd": cmd, "passed": r.returncode == 0, "exit_code": r.returncode, "tail": tail}
    except subprocess.TimeoutExpired:
        return {"cmd": cmd, "passed": False, "exit_code": 124, "tail": f"timeout {timeout}s"}
    except Exception as e:  # noqa: BLE001 — gate jamais crasha; falha = não-done
        return {"cmd": cmd, "passed": False, "exit_code": 1, "tail": f"erro: {e}"}


# Why: `cwd` mantem o kit configuravel para consumidores externos; o fluxo local usa o default.
def gate(criteria, cwd: str | None = None, timeout: int = 600):
    """Roda todos os critérios (AND). Retorna (all_passed, results). Lista vazia = não-done."""
    results = [run_criterion(c, cwd=cwd, timeout=timeout) for c in criteria if str(c).strip()]
    return (bool(results) and all(r["passed"] for r in results)), results


def criteria_from_profile(task_type: str) -> list[str]:
    """Lê verificacao.done_criterios[<task_type>] do operator-profile.yaml. [] se ausente."""
    if load_profile is None or get is None:
        return []
    prof = load_profile()
    crit = get(prof, f"verificacao.done_criterios.{task_type}", [])
    return [str(c) for c in crit] if isinstance(crit, list) else []


DONE = "DONE"
PARCIAL = "PARCIAL-DECLARADO"
NOT_DONE = "NOT-DONE"


def parse_declaration(raw) -> dict | None:
    """Normaliza a declaração de pendência. None = nada declarado.

    Aceita texto livre ("faltam X e Y") ou dict {"missing": [...], "reason": "..."}.
    Declaração VAZIA não é declaração — vira None, e o estado cai em NOT-DONE.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        txt = raw.strip()
        if not txt:
            return None
        return {"missing": [txt], "reason": ""}
    if isinstance(raw, dict):
        missing = [str(m).strip() for m in (raw.get("missing") or []) if str(m).strip()]
        reason = str(raw.get("reason") or "").strip()
        if not missing and not reason:
            return None
        return {"missing": missing or [reason], "reason": reason}
    return None


def decide(all_passed: bool, declared: dict | None) -> str:
    """O terceiro estado. A declaração VENCE o verde."""
    if declared is not None:
        return PARCIAL
    return DONE if all_passed else NOT_DONE


def _self_test() -> None:
    # Why: `python` a seco nao existe no macOS (so python3) e o self-test falhava com exit 127.
    # O interprete certo e o que esta rodando ISTO; entre aspas porque shell=True e o caminho
    # pode ter espaco.
    py = f'"{sys.executable}"'
    ok, res = gate([f'{py} -c "import sys; sys.exit(0)"'])
    assert ok and res[0]["passed"], "exit 0 deveria passar"
    assert gate([f'{py} -c "import sys; sys.exit(3)"'])[0] is False, "exit 3 deveria falhar"
    assert gate([f'{py} -c "pass"', f'{py} -c "raise SystemExit(1)"'])[0] is False, "AND: 1 falha derruba"
    assert gate([])[0] is False, "lista vazia = não-done"

    # os tres estados
    assert decide(True, None) == DONE
    assert decide(False, None) == NOT_DONE
    assert decide(False, {"missing": ["x"], "reason": ""}) == PARCIAL
    assert decide(True, {"missing": ["x"], "reason": ""}) == PARCIAL, \
        "a declaracao VENCE o verde: quem executou sabe mais que os criterios"

    # declaracao vazia nao e declaracao
    assert parse_declaration("") is None
    assert parse_declaration("   ") is None
    assert parse_declaration({}) is None
    assert parse_declaration({"missing": [], "reason": ""}) is None
    assert parse_declaration("faltam X e Y") == {"missing": ["faltam X e Y"], "reason": ""}
    d = parse_declaration({"missing": ["X", " Y "], "reason": "sem acesso ao staging"})
    assert d == {"missing": ["X", "Y"], "reason": "sem acesso ao staging"}, d
    assert parse_declaration({"reason": "so o motivo"}) == {"missing": ["so o motivo"], "reason": "so o motivo"}

    # o instrumento discrimina: os tres estados sao alcancaveis e distintos
    assert len({decide(True, None), decide(False, None), decide(False, {"missing": ["x"], "reason": ""})}) == 3
    print("self-test OK")


def main(argv) -> int:
    if argv and argv[0] in ("--self-test", "-t"):
        _self_test()
        return 0
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]

    # --declare-partial "<texto>" pode vir em qualquer posicao
    declared_raw = None
    if "--declare-partial" in argv:
        i = argv.index("--declare-partial")
        if i + 1 >= len(argv):
            print("uso: --declare-partial \"<o que falta e por que>\"", file=sys.stderr)
            return 2
        declared_raw = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]

    if argv and argv[0] == "--profile":
        if len(argv) < 2:
            print("uso: done_gate.py --profile <tipo>   (tipo = chave em verificacao.done_criterios)", file=sys.stderr)
            return 2
        task_type = argv[1]
        criteria = criteria_from_profile(task_type)
        if not criteria:
            print(f"done_gate: nenhum critério p/ tipo '{task_type}' no operator-profile.yaml "
                  "(ou perfil/PyYAML ausente)", file=sys.stderr)
            return 2
    elif argv and argv[0] == "--stdin":
        try:
            payload = json.loads(sys.stdin.read() or "{}")
            criteria = payload.get("criteria", [])
            if declared_raw is None and "partial" in payload:
                declared_raw = payload.get("partial")
        except Exception:
            print("done_gate: stdin JSON inválido", file=sys.stderr)
            return 2
    else:
        criteria = argv

    if not criteria:
        print('uso: done_gate.py "<cmd1>" [...]  |  --profile <tipo>  |  --stdin', file=sys.stderr)
        return 2

    all_passed, results = gate(criteria)
    declared = parse_declaration(declared_raw)
    state = decide(all_passed, declared)

    if as_json:
        print(json.dumps({
            "done": state == DONE,
            "state": state,
            "partial": state == PARCIAL,
            "declared": declared,
            "results": results,
        }, ensure_ascii=False, indent=2))
    else:
        for r in results:
            mark = "OK " if r["passed"] else "FAIL"
            print(f"  [{mark}] (exit {r['exit_code']}) {r['cmd']}")
            if not r["passed"] and r["tail"]:
                print(f"        ^ {r['tail'][-200:]}")
        passed = sum(1 for r in results if r["passed"])
        print(f"\nDONE-GATE: {state} ({passed}/{len(results)} criterios)")
        if state == PARCIAL:
            for m in declared["missing"]:
                print(f"  falta: {m}")
            if declared["reason"]:
                print(f"  porque: {declared['reason']}")
            if all_passed:
                print("  (criterios todos verdes — a declaracao venceu: quem executou sabe mais)")
        elif state == NOT_DONE:
            print("  sem declaracao de pendencia. Se isto e PARCIAL, declare o que falta")
            print("  (--declare-partial \"...\"); se e FALHA, conserte. Silencio nao e estado.")
    return 0 if state == DONE else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
