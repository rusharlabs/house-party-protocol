#!/usr/bin/env python3
"""
verify_ladder (Operator Kit) — escada de verificacao em 6 niveis, portatil e config-driven.

Escada de verificacao em 6 niveis, agnostica de projeto: le a
escada de `verificacao.ladder` do operator-profile.yaml (dict nivel->comando)
e roda cada nivel que TEM comando. Os 6 niveis canonicos sao:
    lint · test · build · visual · staging · security

Principio anti-verde-falso: um nivel com comando VAZIO/ausente nao "passa" — ele
e SKIPPED e nao conta no score. O score e X/N onde N = numero de niveis com comando
de verdade (os SKIPPED nao inflam o denominador nem o numerador).

PASS/FAIL geral:
    FAIL se QUALQUER nivel obrigatorio (verificacao.ladder_obrigatorios) falhou,
    OU se o score (niveis que passaram) < verificacao.ladder_score_minimo.
    Caso contrario PASS. (Um obrigatorio sem comando = SKIPPED = nao satisfeito = FAIL.)

Uso:
    python verify_ladder.py                 # le ladder do operator-profile.yaml
    python verify_ladder.py --json          # saida JSON estruturada
    python verify_ladder.py --self-test

Exit: 0 = PASS · 1 = FAIL · 2 = uso/config invalida (sem escada utilizavel).
stdlib + PyYAML (via loader). Cross-platform (shell=True respeita o SO). Degrada
para defaults seguros sem profile: sem escada -> nada a verificar -> FAIL (nunca verde-falso).

v1.0.0 — 2026-06-19 (Operator Kit · Tier 1 · generaliza verify-6-levels)
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
except Exception:  # noqa: BLE001 — sem loader, modo profile fica indisponivel; resto funciona
    load_profile = None  # type: ignore[assignment]
    get = None  # type: ignore[assignment]

# Ordem canonica dos 6 niveis.
NIVEIS_CANONICOS = ["lint", "test", "build", "visual", "staging", "security"]


def run_nivel(nivel: str, cmd: str, cwd: str | None = None, timeout: int = 600) -> dict:
    """Roda um nivel da escada. Sem comando -> status SKIPPED (nunca verde-falso).

    Retorna dict {nivel, cmd, status, passed, exit_code, tail}.
    status in {"PASS", "FAIL", "SKIPPED"}. SKIPPED nunca conta como passed.
    """
    cmd = (cmd or "").strip()
    if not cmd:
        return {"nivel": nivel, "cmd": "", "status": "SKIPPED",
                "passed": False, "exit_code": None, "tail": "sem comando configurado"}
    try:
        r = subprocess.run(
            cmd, shell=True, cwd=cwd,
            capture_output=True, text=True, timeout=timeout,
        )
        tail = ((r.stdout or "") + (r.stderr or "")).strip()[-400:]
        passed = r.returncode == 0
        return {"nivel": nivel, "cmd": cmd, "status": "PASS" if passed else "FAIL",
                "passed": passed, "exit_code": r.returncode, "tail": tail}
    except subprocess.TimeoutExpired:
        return {"nivel": nivel, "cmd": cmd, "status": "FAIL",
                "passed": False, "exit_code": 124, "tail": f"timeout {timeout}s"}
    except Exception as e:  # noqa: BLE001 — escada jamais crasha; erro = nivel falho
        return {"nivel": nivel, "cmd": cmd, "status": "FAIL",
                "passed": False, "exit_code": 1, "tail": f"erro: {e}"}


def evaluate(ladder: dict, obrigatorios=None, score_minimo: int = 1,
             cwd: str | None = None, timeout: int = 600) -> dict:
    """Roda a escada inteira e avalia PASS/FAIL geral.

    ladder: dict {nivel: comando}. Niveis seguem NIVEIS_CANONICOS quando presentes,
            extras (se houver) rodam no fim em ordem alfabetica.
    obrigatorios: lista de niveis que DEVEM passar (default []).
    score_minimo: minimo de niveis com PASS para nao falhar por score.

    Retorna dict com results, score, total (niveis com comando), pass/fail e razao.
    """
    obrigatorios = list(obrigatorios or [])
    # Ordena: canonicos primeiro (na ordem fixa), depois extras alfabeticos.
    chaves = [n for n in NIVEIS_CANONICOS if n in ladder]
    chaves += sorted(k for k in ladder if k not in NIVEIS_CANONICOS)

    results = [run_nivel(n, ladder.get(n, ""), cwd=cwd, timeout=timeout) for n in chaves]

    com_comando = [r for r in results if r["status"] != "SKIPPED"]
    total = len(com_comando)                                  # N = niveis com comando real
    score = sum(1 for r in com_comando if r["passed"])        # X = niveis que passaram

    # Obrigatorio satisfeito SO se status == PASS (SKIPPED ou FAIL nao contam).
    status_por_nivel = {r["nivel"]: r["status"] for r in results}
    obrig_falhos = [n for n in obrigatorios if status_por_nivel.get(n) != "PASS"]

    ok = (not obrig_falhos) and (score >= score_minimo)
    razao = []
    if obrig_falhos:
        razao.append(f"obrigatorio(s) nao satisfeito(s): {', '.join(obrig_falhos)}")
    if score < score_minimo:
        razao.append(f"score {score} < minimo {score_minimo}")
    if total == 0:
        razao.append("nenhum nivel com comando configurado (nada verificado)")

    return {
        "passed": ok,
        "score": score,
        "total": total,
        "score_minimo": score_minimo,
        "obrigatorios": obrigatorios,
        "obrigatorios_falhos": obrig_falhos,
        "results": results,
        "razao": razao,
    }


def ladder_from_profile() -> tuple[dict, list, int]:
    """Le verificacao.ladder / ladder_obrigatorios / ladder_score_minimo do profile.

    Retorna (ladder_dict, obrigatorios_list, score_minimo_int). Defaults seguros se ausente.
    """
    if load_profile is None or get is None:
        return {}, [], 1
    prof = load_profile()
    ladder = get(prof, "verificacao.ladder", {}) or {}
    if not isinstance(ladder, dict):
        ladder = {}
    obrig = get(prof, "verificacao.ladder_obrigatorios", []) or []
    obrig = [str(x) for x in obrig] if isinstance(obrig, list) else []
    minimo = get(prof, "verificacao.ladder_score_minimo", 1)
    try:
        minimo = int(minimo)
    except (TypeError, ValueError):
        minimo = 1
    return {k: str(v or "") for k, v in ladder.items()}, obrig, minimo


def _render(report: dict) -> str:
    """Renderiza o relatorio humano (texto). Mostra tail por nivel, score e veredito."""
    linhas = []
    for r in report["results"]:
        mark = {"PASS": "OK  ", "FAIL": "FAIL", "SKIPPED": "SKIP"}[r["status"]]
        ec = "" if r["exit_code"] is None else f" exit {r['exit_code']}"
        linhas.append(f"  [{mark}] {r['nivel']:<9}{ec}  {r['cmd'] or '(sem comando)'}")
        if r["status"] == "FAIL" and r["tail"]:
            linhas.append(f"          ^ {r['tail'][-200:]}")
    veredito = "PASS" if report["passed"] else "FAIL"
    linhas.append(f"\nLADDER: {veredito}  (score {report['score']}/{report['total']}, "
                  f"minimo {report['score_minimo']})")
    if report["razao"]:
        linhas.append("  motivo: " + "; ".join(report["razao"]))
    return "\n".join(linhas)


def _self_test() -> None:
    # ladder fake inline — sem profile, sem rede; comandos deterministicos cross-platform.
    ok_cmd = f'"{sys.executable}" -c "import sys; sys.exit(0)"'
    fail_cmd = f'"{sys.executable}" -c "import sys; sys.exit(1)"'

    # 1) Nivel sem comando => SKIPPED, nao conta no total.
    rep = evaluate({"lint": "", "test": ok_cmd}, obrigatorios=["test"], score_minimo=1)
    assert rep["total"] == 1, f"SKIPPED nao deveria contar no total: {rep['total']}"
    assert rep["score"] == 1, f"score deveria ser 1: {rep['score']}"
    assert rep["passed"] is True, "obrigatorio test passou e score>=min => PASS"
    skip = next(r for r in rep["results"] if r["nivel"] == "lint")
    assert skip["status"] == "SKIPPED", "lint sem comando deve ser SKIPPED"

    # 2) Obrigatorio que falha => FAIL geral mesmo com outro nivel ok.
    rep2 = evaluate({"test": fail_cmd, "build": ok_cmd}, obrigatorios=["test"], score_minimo=1)
    assert rep2["passed"] is False, "obrigatorio test falhou => FAIL"
    assert "test" in rep2["obrigatorios_falhos"]

    # 3) Score abaixo do minimo => FAIL.
    rep3 = evaluate({"test": ok_cmd}, obrigatorios=[], score_minimo=2)
    assert rep3["passed"] is False, "score 1 < minimo 2 => FAIL"

    # 4) Obrigatorio SEM comando (SKIPPED) NAO satisfaz => FAIL (anti-verde-falso).
    rep4 = evaluate({"security": ""}, obrigatorios=["security"], score_minimo=0)
    assert rep4["passed"] is False, "obrigatorio SKIPPED nao satisfaz"
    assert "security" in rep4["obrigatorios_falhos"]

    # 5) Escada vazia => total 0, nada verificado => FAIL.
    rep5 = evaluate({}, obrigatorios=[], score_minimo=1)
    assert rep5["total"] == 0 and rep5["passed"] is False, "escada vazia nunca passa"

    # 6) Ordem canonica respeitada quando presente.
    rep6 = evaluate({"security": ok_cmd, "lint": ok_cmd}, obrigatorios=[], score_minimo=1)
    ordem = [r["nivel"] for r in rep6["results"]]
    assert ordem == ["lint", "security"], f"ordem canonica errada: {ordem}"

    print("self-test OK")


def main(argv) -> int:
    if argv and argv[0] in ("--self-test", "-t"):
        _self_test()
        return 0
    as_json = "--json" in argv

    ladder, obrig, minimo = ladder_from_profile()
    if not ladder:
        msg = "verify_ladder: nenhuma escada em verificacao.ladder do operator-profile.yaml " \
              "(ou perfil/PyYAML ausente) — nada a verificar"
        if as_json:
            print(json.dumps({"passed": False, "score": 0, "total": 0,
                              "razao": [msg]}, ensure_ascii=False, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 2

    report = evaluate(ladder, obrigatorios=obrig, score_minimo=minimo)
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_render(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
