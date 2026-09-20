#!/usr/bin/env python3
"""Runner standalone de pass@k e pass^k para suites JSON reproduzíveis.

O runner não chama modelos nem depende do projeto em que o kit foi instalado. Cada
caso usa uma de duas fontes verificáveis:

- ``replay``: resultados booleanos declarados na fixture;
- ``command``: um argv executado sem shell, com exit/output esperados.

Exit codes: 0=gate aprovado, 2=gate bloqueou, 3=erro de uso/execução.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_K = 3
CAPACITY_THRESHOLD = 0.90


class SuiteError(ValueError):
    """Suite inválida ou impossível de executar."""


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    outcomes: list[bool]

    @property
    def pass_at_k(self) -> bool:
        return any(self.outcomes)

    @property
    def pass_caret_k(self) -> bool:
        return all(self.outcomes)


@dataclass(frozen=True)
class PassKReport:
    suite: str
    suite_version: str
    suite_sha256: str
    k: int
    n_cases: int
    pass_at_k: float
    pass_caret_k: float
    gap: float
    flaky_case_ids: list[str]
    failed_case_ids: list[str]
    cases: list[CaseResult]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["cases"] = [
            {
                **asdict(case),
                "pass_at_k": case.pass_at_k,
                "pass_caret_k": case.pass_caret_k,
            }
            for case in self.cases
        ]
        return payload


def _load_suite(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        suite = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SuiteError(f"suite ilegível: {path}: {exc}") from exc
    if not isinstance(suite, dict):
        raise SuiteError("suite deve ser um objeto JSON")
    if not isinstance(suite.get("suite"), str) or not suite["suite"].strip():
        raise SuiteError("suite requer nome não vazio em 'suite'")
    if not isinstance(suite.get("version"), str) or not suite["version"].strip():
        raise SuiteError("suite requer versão string em 'version'")
    cases = suite.get("cases")
    if not isinstance(cases, list) or not cases:
        raise SuiteError("suite requer lista não vazia em 'cases'")
    ids = [case.get("id") for case in cases if isinstance(case, dict)]
    if len(ids) != len(cases) or any(not isinstance(cid, str) or not cid for cid in ids):
        raise SuiteError("todo case requer id string não vazio")
    duplicated = sorted({cid for cid in ids if ids.count(cid) > 1})
    if duplicated:
        raise SuiteError(f"case id duplicado: {duplicated}")
    return suite, hashlib.sha256(raw).hexdigest()


def _replay(case: dict[str, Any], k: int) -> list[bool]:
    outcomes = case.get("outcomes")
    if not isinstance(outcomes, list) or len(outcomes) < k:
        raise SuiteError(f"{case['id']}: replay requer ao menos {k} outcomes")
    if any(type(value) is not bool for value in outcomes[:k]):
        raise SuiteError(f"{case['id']}: outcomes devem ser booleanos")
    return outcomes[:k]


def _command(case: dict[str, Any], k: int, cwd: Path) -> list[bool]:
    command = case.get("command")
    if not isinstance(command, list) or not command or any(not isinstance(x, str) for x in command):
        raise SuiteError(f"{case['id']}: command deve ser argv JSON não vazio")
    expected_exit = case.get("expect_exit", 0)
    if not isinstance(expected_exit, int):
        raise SuiteError(f"{case['id']}: expect_exit deve ser inteiro")
    timeout = case.get("timeout_seconds", 30)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise SuiteError(f"{case['id']}: timeout_seconds deve ser positivo")
    expected_out = case.get("expect_stdout_contains")
    expected_err = case.get("expect_stderr_contains")
    if expected_out is not None and not isinstance(expected_out, str):
        raise SuiteError(f"{case['id']}: expect_stdout_contains deve ser string")
    if expected_err is not None and not isinstance(expected_err, str):
        raise SuiteError(f"{case['id']}: expect_stderr_contains deve ser string")

    outcomes: list[bool] = []
    for _ in range(k):
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=float(timeout),
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SuiteError(f"{case['id']}: comando não executável: {exc}") from exc
        passed = result.returncode == expected_exit
        if expected_out is not None:
            passed = passed and expected_out in result.stdout
        if expected_err is not None:
            passed = passed and expected_err in result.stderr
        outcomes.append(passed)
    return outcomes


def run_suite(path: Path, *, k: int = DEFAULT_K) -> PassKReport:
    if k < 1:
        raise SuiteError("k deve ser >= 1")
    suite, digest = _load_suite(path)
    results: list[CaseResult] = []
    for case in suite["cases"]:
        runner = case.get("runner")
        if runner == "replay":
            outcomes = _replay(case, k)
        elif runner == "command":
            outcomes = _command(case, k, path.parent)
        else:
            raise SuiteError(f"{case['id']}: runner inválido: {runner!r}")
        results.append(CaseResult(case_id=case["id"], outcomes=outcomes))

    n_cases = len(results)
    pass_at = sum(case.pass_at_k for case in results) / n_cases
    pass_caret = sum(case.pass_caret_k for case in results) / n_cases
    return PassKReport(
        suite=suite["suite"],
        suite_version=suite["version"],
        suite_sha256=digest,
        k=k,
        n_cases=n_cases,
        pass_at_k=pass_at,
        pass_caret_k=pass_caret,
        gap=pass_at - pass_caret,
        flaky_case_ids=[case.case_id for case in results if case.pass_at_k and not case.pass_caret_k],
        failed_case_ids=[case.case_id for case in results if not case.pass_at_k],
        cases=results,
    )


def evaluate_gate(
    report: PassKReport,
    *,
    gate: str = "capability",
    passk_threshold: float = CAPACITY_THRESHOLD,
) -> dict[str, Any]:
    if not 0 <= passk_threshold <= 1:
        raise SuiteError("passk_threshold deve estar entre 0 e 1")
    capability_ok = report.pass_at_k >= passk_threshold
    regression_ok = report.pass_caret_k == 1.0
    if gate == "capability":
        passed = capability_ok
    elif gate == "regression":
        passed = regression_ok
    elif gate == "both":
        passed = capability_ok and regression_ok
    else:
        raise SuiteError("gate inválido; use capability, regression ou both")
    return {
        "gate": gate,
        "passed": passed,
        "capability_ok": capability_ok,
        "regression_ok": regression_ok,
        "passk_threshold": passk_threshold,
    }


def _payload(report: PassKReport, verdict: dict[str, Any]) -> dict[str, Any]:
    return {
        **report.to_dict(),
        "verdict": verdict,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def _print_human(report: PassKReport, verdict: dict[str, Any]) -> None:
    print(f"suite={report.suite} cases={report.n_cases} k={report.k}")
    print(f"pass@k={report.pass_at_k:.2%} pass^k={report.pass_caret_k:.2%} gap={report.gap:.2%}")
    if report.flaky_case_ids:
        print("flaky=" + ",".join(report.flaky_case_ids))
    if report.failed_case_ids:
        print("never-passed=" + ",".join(report.failed_case_ids))
    print(f"gate={verdict['gate']} result={'PASS' if verdict['passed'] else 'BLOCK'}")


def _self_test() -> int:
    always = CaseResult("always", [True, True, True])
    flaky = CaseResult("flaky", [True, False, True])
    never = CaseResult("never", [False, False, False])
    assert always.pass_at_k and always.pass_caret_k
    assert flaky.pass_at_k and not flaky.pass_caret_k
    assert not never.pass_at_k and not never.pass_caret_k
    report = PassKReport(
        suite="self-test",
        suite_version="1",
        suite_sha256="0" * 64,
        k=3,
        n_cases=3,
        pass_at_k=2 / 3,
        pass_caret_k=1 / 3,
        gap=1 / 3,
        flaky_case_ids=["flaky"],
        failed_case_ids=["never"],
        cases=[always, flaky, never],
    )
    assert not evaluate_gate(report, gate="capability")["passed"]
    assert not evaluate_gate(report, gate="regression")["passed"]
    perfect = PassKReport(
        suite="perfect",
        suite_version="1",
        suite_sha256="1" * 64,
        k=3,
        n_cases=1,
        pass_at_k=1.0,
        pass_caret_k=1.0,
        gap=0.0,
        flaky_case_ids=[],
        failed_case_ids=[],
        cases=[always],
    )
    assert evaluate_gate(perfect, gate="both")["passed"]
    print("self-test OK — runner standalone, replay, pass@k, pass^k e gates")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, help="suite JSON")
    parser.add_argument("-k", type=int, default=DEFAULT_K)
    parser.add_argument("--gate", choices=("capability", "regression", "both"), default="capability")
    parser.add_argument("--passk-threshold", type=float, default=CAPACITY_THRESHOLD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    if args.suite is None:
        parser.error("--suite é obrigatório")
    try:
        report = run_suite(args.suite, k=args.k)
        verdict = evaluate_gate(report, gate=args.gate, passk_threshold=args.passk_threshold)
    except SuiteError as exc:
        print(f"passk_eval: {exc}", file=sys.stderr)
        return 3
    if args.json:
        print(json.dumps(_payload(report, verdict), ensure_ascii=False, indent=2))
    else:
        _print_human(report, verdict)
    return 0 if verdict["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
