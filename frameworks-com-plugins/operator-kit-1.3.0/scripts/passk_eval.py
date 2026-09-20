#!/usr/bin/env python3
"""
passk_eval — CLI runner pass@k (capacidade) vs pass^k (regressão) p/ o LOOP.

Codifica `.claude/rules/loop-passk.md` (ECC #6) num CLI operador-facing. A MATEMÁTICA
e o k-runs runner são DO FRAMEWORK CANÔNICO (zero duplicação — consolidado 2026-06-29,
opção 1; antes este arquivo tinha um CaseAggregate/PassKReport paralelo ao do scorer
do Codex `e550b757`):

  - k-runs runner : core/intelligence/evals/core/runner.py :: run_suite_k_times
  - scorer        : core/intelligence/evals/scorers/pass_k.py :: compute_pass_k_from_suites
                    (PassKReport + meets_capacity_gate/meets_regression_gate + thresholds)

  pass@k  = case passou em >=1 das k tentativas  (CAPACIDADE — "consegue fazer?")
  pass^k  = case passou em TODAS as k tentativas  (REGRESSÃO/DETERMINISMO — "faz sempre?")

  pass@k agregado >= 0.90  → GATE DE CAPACIDADE   (senão = buraco, volta ao maker)
  pass^k agregado == 1.00  → GATE DE REGRESSÃO    (release-crítico / promoção level 4/5)

Este arquivo = SÓ o CLI: seleção de suites, escolha de --target, aplicação do --gate
(capability/regression/both com razões human-readable), --json, --self-test. A lógica
de pontuação vive (e é testada) no framework canônico (tests/python/test_evals/test_pass_k.py).

Uso:
    python scripts/loop/passk_eval.py --agent closer
    python scripts/loop/passk_eval.py --agent closer -k 5 --json
    python scripts/loop/passk_eval.py --all --gate capability
    python scripts/loop/passk_eval.py --suite agents/cargo/sales/closer/EVALS.yaml
    python scripts/loop/passk_eval.py --target http_agent --agent closer   # LIVE (flakiness real)
    python scripts/loop/passk_eval.py --self-test

Exit codes:
    0 = GATE PASSOU   · 1 = GATE FALHOU   · 2 = uso inválido / sem suite / framework ausente

Gates (escolha via --gate):
    capability (default) → pass@k >= --passk-threshold (default 0.90)
    regression           → pass^k == 1.00 (zero flakiness; release-crítico / level 4-5)
    both                 → exige os dois

v2.0.0 — 2026-06-29 (CONSOLIDAÇÃO opção 1 · ECC #6 · loop-passk.md · usa scorer canônico)
v2.1.0 — 2026-07-10 (Operator Kit · TIER OPCIONAL — depende de
         core.intelligence.evals, um pacote especifico do repo-de-origem. Fora dele
         o import falha e este comando fica indisponível (_FRAMEWORK_OK=False) SEM quebrar
         o resto do kit — done_gate/goal_ledger/goal_review funcionam sem passk_eval.)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

# UTF-8 no Windows (cmd.exe / PowerShell) — evita UnicodeEncodeError nos prints.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass


def _resolve_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env and Path(env).exists():
        return Path(env)
    here = Path(__file__).resolve().parent
    for d in (here, *here.parents):
        if (d / ".git").exists():
            return d
    return here.parent


_HERE = Path(__file__).resolve().parent
_ROOT = _resolve_root()
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Framework canônico de evals (REUSO total — runner + scorer + thresholds).
try:
    from core.intelligence.evals.core.loader import load_suite, load_suites  # type: ignore
    from core.intelligence.evals.core.models import EvalSuite  # type: ignore
    from core.intelligence.evals.core.runner import run_suite_k_times  # type: ignore
    from core.intelligence.evals.environments import (  # type: ignore
        http_agent_target,
        offline_replay_target,
    )
    from core.intelligence.evals.scorers.pass_k import (  # type: ignore
        CAPACITY_THRESHOLD,
        DEFAULT_K,
        REGRESSION_THRESHOLD,
        PassKReport,
        compute_pass_k_from_suites,
    )
    _FRAMEWORK_OK = True
    _FRAMEWORK_ERR = ""
except Exception as exc:  # noqa: BLE001  # pragma: no cover
    _FRAMEWORK_OK = False
    _FRAMEWORK_ERR = f"{type(exc).__name__}: {exc}"
    # defaults p/ o --help mesmo sem o framework (thresholds canônicos de loop-passk.md)
    DEFAULT_K = 3
    CAPACITY_THRESHOLD = 0.90
    REGRESSION_THRESHOLD = 1.0


class UsageError(Exception):
    """Erro de uso → exit code 2 (honra o contrato documentado no docstring)."""


def run_passk(
    suite: "EvalSuite",
    target_fn: Callable[[str], object],
    *,
    k: int = DEFAULT_K,
    target_name: str = "offline_replay",
) -> tuple["PassKReport", str, str, dict[str, str]]:
    """Roda a suite k× e agrega via o framework CANÔNICO.

    run_suite_k_times (k execuções) → compute_pass_k_from_suites (pass@k/pass^k).
    Não duplica matemática. Mantém o guard local de case_id duplicado (bug de
    autoria de suite que corromperia a contagem) e devolve o mapa case→category
    p/ o CLI destacar regressões. Retorna (report_canônico, agent, target, category).
    """
    if k < 1:
        raise ValueError("k deve ser >= 1")
    # Fail-fast: case_id duplicado na suite corromperia a agregação (2 cases viram 1).
    suite_ids = [c.id for c in suite.cases]
    dups = sorted({cid for cid in suite_ids if suite_ids.count(cid) > 1})
    if dups:
        raise ValueError(f"suite '{suite.agent}': case_id duplicado(s): {dups}")
    category = {c.id: getattr(c, "category", "standard") for c in suite.cases}

    suites = run_suite_k_times(suite, target_fn, k=k)
    report = compute_pass_k_from_suites(suites)
    return report, suite.agent, target_name, category


def evaluate_gate(
    report: "PassKReport",
    *,
    gate: str = "capability",
    passk_threshold: float = CAPACITY_THRESHOLD,
) -> dict[str, Any]:
    """Aplica o gate de loop-passk.md ao PassKReport canônico. Veredito + razão (CLI).

    Usa os métodos do próprio report (meets_capacity_gate/meets_regression_gate) —
    fonte única de verdade dos thresholds.
    """
    cap_ok = report.meets_capacity_gate(passk_threshold)
    reg_ok = report.meets_regression_gate()  # pass^k == 1.0

    if gate == "capability":
        passed = cap_ok
        reason = (
            f"pass@k {report.pass_at_k:.2%} >= {passk_threshold:.0%}"
            if cap_ok
            else f"pass@k {report.pass_at_k:.2%} < {passk_threshold:.0%} "
            f"(buraco de capacidade — volta ao maker, não 'calibrar')"
        )
    elif gate == "regression":
        passed = reg_ok
        reason = (
            "pass^k == 100% (zero flakiness — release/level-4-5 ok)"
            if reg_ok
            else f"pass^k {report.pass_caret_k:.2%} < 100% (flaky: {report.flaky_case_ids})"
        )
    elif gate == "both":
        passed = cap_ok and reg_ok
        reason = (
            f"capability {'OK' if cap_ok else 'FAIL'} · "
            f"regression {'OK' if reg_ok else 'FAIL'}"
        )
    else:
        raise ValueError(f"gate inválido: {gate} (use capability|regression|both)")

    return {
        "gate": gate,
        "passed": passed,
        "reason": reason,
        "capability_ok": cap_ok,
        "regression_ok": reg_ok,
        "passk_threshold": passk_threshold,
    }


def _resolve_target(name: str, agent: str) -> tuple[Callable[[str], object], str]:
    if name == "http_agent":
        return http_agent_target(agent), "http_agent"
    return offline_replay_target(agent), "offline_replay"


def _resolve_suites(args: argparse.Namespace) -> list["EvalSuite"]:
    if args.suite:
        return [load_suite(args.suite)]
    if args.all or args.agent_type:
        suites = load_suites(agent=args.agent, agent_type=args.agent_type)
        if not suites:
            raise UsageError("passk_eval: nenhuma EVALS.yaml encontrada para o filtro")
        return suites
    if not args.agent:
        raise UsageError("passk_eval: --agent, --all, --type ou --suite é obrigatório")
    suites = load_suites(agent=args.agent)
    if not suites:
        raise UsageError(f"passk_eval: nenhuma EVALS.yaml para o agente: {args.agent}")
    return suites


def _print_human(
    report: "PassKReport", agent: str, target: str,
    verdict: dict[str, Any], category: dict[str, str],
) -> None:
    mark = "PASS ✅" if verdict["passed"] else "FAIL ❌"
    print(f"\n[{agent}] k={report.k} target={target} cases={report.n_cases}")
    print(
        f"  pass@k (capacidade) = {report.pass_at_k:.2%}   "
        f"pass^k (regressão) = {report.pass_caret_k:.2%}   "
        f"gap-flakiness = {report.gap:.2%}"
    )
    if report.flaky_case_ids:
        items = ", ".join(
            f"{cid}{' (regressão!)' if category.get(cid) == 'regression' else ''}"
            for cid in report.flaky_case_ids
        )
        print(f"  ⚠️ FLAKY ({len(report.flaky_case_ids)}): {items}")
    if report.failed_case_ids:
        print(f"  ❌ NEVER PASSED ({len(report.failed_case_ids)}): "
              f"{', '.join(report.failed_case_ids)}")
    print(f"  GATE[{verdict['gate']}]: {mark} — {verdict['reason']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="passk_eval — pass@k (capacidade) vs pass^k (regressão), k runs"
    )
    ap.add_argument("--agent", help="id do agente (lê agents/**/EVALS.yaml)")
    ap.add_argument("--all", action="store_true", help="todas as suites EVALS.yaml")
    ap.add_argument("--type", dest="agent_type", help="filtra por tipo (cargo|minds|...)")
    ap.add_argument("--suite", help="caminho explícito de uma EVALS.yaml")
    ap.add_argument("-k", type=int, default=DEFAULT_K, help=f"runs (default {DEFAULT_K})")
    ap.add_argument("--target", choices=["offline_replay", "http_agent"],
                    default="offline_replay", help="alvo (offline=spec · http_agent=LIVE)")
    ap.add_argument("--gate", choices=["capability", "regression", "both"],
                    default="capability", help="gate a aplicar (default capability)")
    ap.add_argument("--passk-threshold", type=float, default=CAPACITY_THRESHOLD,
                    help=f"limiar pass@k (default {CAPACITY_THRESHOLD})")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)

    if a.self_test:
        return _self_test()

    if not _FRAMEWORK_OK:
        print(f"passk_eval: framework de evals indisponível ({_FRAMEWORK_ERR})",
              file=sys.stderr)
        return 2
    if a.k < 1:
        print("passk_eval: -k deve ser >= 1", file=sys.stderr)
        return 2

    try:
        suites = _resolve_suites(a)
    except UsageError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    all_passed = True
    payloads = []
    for suite in suites:
        target_fn, target_name = _resolve_target(a.target, suite.agent)
        report, agent, tname, category = run_passk(
            suite, target_fn, k=a.k, target_name=target_name
        )
        verdict = evaluate_gate(report, gate=a.gate, passk_threshold=a.passk_threshold)
        all_passed = all_passed and verdict["passed"]
        if a.json:
            payloads.append({"agent": agent, "target": tname, **report.to_dict(),
                             "verdict": verdict})
        else:
            _print_human(report, agent, tname, verdict, category)

    if a.json:
        print(json.dumps(payloads[0] if len(payloads) == 1 else payloads,
                         ensure_ascii=False, indent=2))
    return 0 if all_passed else 1


# --------------------------------------------------------------------------- #
# Self-test — testa o que é DESTE CLI: a lógica de --gate sobre um PassKReport
# canônico + os guards do run_passk. A MATEMÁTICA pass@k/pass^k é do scorer
# canônico e é testada em tests/python/test_evals/test_pass_k.py (não re-testar).
# --------------------------------------------------------------------------- #
def _self_test() -> int:
    if not _FRAMEWORK_OK:
        # TIER OPCIONAL (docstring do módulo): fora do repo-de-origem o import do
        # framework canônico falha por design — isso não é falha do kit instalado
        # (a matemática pass@k/pass^k é testada lá, não aqui). Degrada para exit 0
        # (self-test "ok em modo degradado"), não 2 — senão todo smoke-test deste
        # kit fora do repo-de-origem reportaria falha por um tier que é opcional.
        print(f"self-test OK (degradado — framework de evals indisponível: {_FRAMEWORK_ERR}) — "
              f"a matemática é testada em tests/python/test_evals/test_pass_k.py",
              file=sys.stderr)
        return 0

    # Gate logic sobre um PassKReport canônico (exemplo loop-passk: 19/20 pass@k, 17/20 pass^k).
    rep = PassKReport(
        k=3, n_cases=20, pass_at_k=0.95, pass_caret_k=0.85,
        flaky_case_ids=["flk0", "flk1"], failed_case_ids=["hole"],
    )
    cap = evaluate_gate(rep, gate="capability")          # 0.95 >= 0.90 → pass
    assert cap["passed"] is True, cap
    reg = evaluate_gate(rep, gate="regression")          # 0.85 < 1.00 → fail
    assert reg["passed"] is False, reg
    assert evaluate_gate(rep, gate="both")["passed"] is False

    perfect = PassKReport(k=3, n_cases=3, pass_at_k=1.0, pass_caret_k=1.0)
    assert evaluate_gate(perfect, gate="regression")["passed"] is True
    assert evaluate_gate(perfect, gate="both")["passed"] is True

    try:
        evaluate_gate(rep, gate="bogus")
        raise AssertionError("gate inválido deveria levantar ValueError")
    except ValueError:
        pass

    # Guards do run_passk (sem rodar a suite — disparam antes do runner).
    class _C:
        def __init__(self, cid: str) -> None:
            self.id = cid

    class _S:
        agent = "stub"

        def __init__(self, cases: list) -> None:
            self.cases = cases

    try:
        run_passk(_S([_C("dup"), _C("dup")]), lambda s: None, k=1)  # type: ignore[arg-type]
        raise AssertionError("case_id duplicado deveria levantar ValueError")
    except ValueError:
        pass
    try:
        run_passk(_S([_C("a")]), lambda s: None, k=0)  # type: ignore[arg-type]
        raise AssertionError("k<1 deveria levantar ValueError")
    except ValueError:
        pass

    json.dumps(rep.to_dict())  # serializável

    print("self-test OK (gate logic + guards; matemática no scorer canônico)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
