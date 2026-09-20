"""Standalone pass@k and pass^k evaluation runner using only the stdlib."""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


class EvalError(ValueError):
    """A suite is invalid or unsafe to run."""


def load_suite(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    try:
        suite = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvalError(f"invalid suite JSON: {exc}") from exc
    if not isinstance(suite, dict) or not isinstance(suite.get("version"), str):
        raise EvalError("suite needs a string version")
    cases = suite.get("cases")
    if not isinstance(cases, list) or not cases:
        raise EvalError("suite needs non-empty cases")
    identifiers = [case.get("id") for case in cases if isinstance(case, dict)]
    if len(identifiers) != len(cases) or any(not isinstance(item, str) or not item for item in identifiers):
        raise EvalError("every case needs an id")
    if len(set(identifiers)) != len(identifiers):
        raise EvalError("case ids must be unique")
    return suite, hashlib.sha256(raw).hexdigest()


def _outcome(case: dict[str, Any], run_index: int) -> bool:
    runner = case.get("runner")
    if runner == "hpp-control":
        from hpp.controls import run_control
        try:
            return run_control(case.get("id", ""))
        except ValueError as exc:
            raise EvalError(str(exc)) from exc
    if runner == "replay":
        outcomes = case.get("outcomes")
        if not isinstance(outcomes, list) or not outcomes or not all(isinstance(item, bool) for item in outcomes):
            raise EvalError(f"replay case {case.get('id')} needs boolean outcomes")
        return outcomes[run_index % len(outcomes)]
    if runner == "command":
        command = case.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
            raise EvalError(f"command case {case.get('id')} needs a non-empty argv array")
        try:
            result = subprocess.run(command, shell=False, capture_output=True, text=True, timeout=case.get("timeout", 20))
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False
        return result.returncode == 0
    raise EvalError(f"case {case.get('id')} has unsupported runner: {runner}")


def run_suite(path: Path, k: int, gate: str) -> dict[str, Any]:
    if k < 1:
        raise EvalError("k must be >= 1")
    if gate not in {"capability", "regression", "both"}:
        raise EvalError("gate must be capability, regression, or both")
    suite, suite_hash = load_suite(path)
    cases: list[dict[str, Any]] = []
    for case in suite["cases"]:
        outcomes = [_outcome(case, index) for index in range(k)]
        cases.append({"id": case["id"], "outcomes": outcomes, "pass_at_k": any(outcomes), "pass_caret_k": all(outcomes)})
    total = len(cases)
    pass_at_k = sum(case["pass_at_k"] for case in cases) / total
    pass_caret_k = sum(case["pass_caret_k"] for case in cases) / total
    flaky = sum(case["pass_at_k"] and not case["pass_caret_k"] for case in cases) / total
    capability_ok = pass_at_k >= 0.90
    regression_ok = pass_caret_k == 1.0
    passed = capability_ok if gate == "capability" else regression_ok if gate == "regression" else capability_ok and regression_ok
    return {
        "suite": {"name": suite.get("name", path.stem), "version": suite["version"], "sha256": suite_hash},
        "platform": {"python": sys.version.split()[0], "system": platform.system()}, "k": k,
        "cases": cases, "metrics": {"pass_at_k": pass_at_k, "pass_caret_k": pass_caret_k, "flaky": flaky},
        "gate": {"name": gate, "capability_ok": capability_ok, "regression_ok": regression_ok, "passed": passed},
    }


def exit_for(report: dict[str, Any]) -> int:
    return 0 if report["gate"]["passed"] else 1
