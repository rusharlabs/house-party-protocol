#!/usr/bin/env python3
"""
determinism_harness (Operator Kit) -- flaky hunter: runs a validator N times and
requires ONE single stdout hash. Output that changes between runs = non-deterministic test
(flaky) = FAIL. Deterministic validator = all runs with the same hash = PASS.

Why it exists: a verification gate is only worth it if it's stable. A flaky test
"passes" sometimes and creates a false green. Here we measure the stability of the output
(stdout hash) across N runs -- N comes from verification.determinism_runs (default 5).

Negative control (Monte-Carlo of the gate itself): --negative takes a command that
MUST fail (exit != 0). If that command "passes" (exit 0), the gate is broken/
too permissive and the harness reports FAIL. It's the test-of-the-test: it proves the
gate still knows how to fail things.

PASS verdict requires: (a) a validator with a single hash across all runs AND exit 0 in all;
(b) if there is --negative, it MUST have failed (exit != 0). Any violation => FAIL.

Usage:
    python determinism_harness.py "python -m pytest -q"
    python determinism_harness.py "<validator>" --negative "<cmd-that-must-fail>"
    python determinism_harness.py "<validator>" --runs 8 --json
    python determinism_harness.py --self-test

Exit: 0 = PASS (deterministic + control ok) -- 1 = FAIL (flaky/error/negative passed)
      -- 2 = invalid usage.
stdlib + PyYAML (via loader, only to read the default runs). Cross-platform (shell=True).

v1.0.0 -- 2026-06-19 (Operator Kit -- Tier 1)
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

# import the shared kit loader (.../operator-kit/_lib/profile_loader.py)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from _lib.profile_loader import load_profile, get
except Exception:  # noqa: BLE001 -- without the loader, uses the default runs; the rest works
    load_profile = None  # type: ignore[assignment]
    get = None  # type: ignore[assignment]

DEFAULT_RUNS = 5


def _hash(texto: str) -> str:
    """SHA-256 (12 chars) of the normalized stdout (unified newlines)."""
    norm = (texto or "").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(norm.encode("utf-8", "replace")).hexdigest()[:12]


def run_once(cmd: str, cwd: str | None = None, timeout: int = 600) -> dict:
    """Runs the command once. Returns {exit_code, stdout_hash, tail}. Never crashes."""
    try:
        r = subprocess.run(
            cmd, shell=True, cwd=cwd,
            capture_output=True, text=True, timeout=timeout,
        )
        return {"exit_code": r.returncode, "stdout_hash": _hash(r.stdout or ""),
                "tail": ((r.stdout or "") + (r.stderr or "")).strip()[-300:]}
    except subprocess.TimeoutExpired:
        return {"exit_code": 124, "stdout_hash": "TIMEOUT", "tail": f"timeout {timeout}s"}
    except Exception as e:  # noqa: BLE001 -- the harness never crashes; error = failed run
        return {"exit_code": 1, "stdout_hash": "ERRO", "tail": f"erro: {e}"}


# Why: `cwd` keeps the kit configurable for external consumers; the local flow uses the default.
def harness(validador: str, runs: int = DEFAULT_RUNS, negative: str | None = None,
            cwd: str | None = None, timeout: int = 600) -> dict:
    """Runs the whole protocol. Returns a structured report with the verdict.

    - Runs `validador` `runs` times; collects hashes and exit codes.
    - deterministic = a single hash across all runs.
    - all_exit_zero = all runs with exit 0.
    - If `negative`: runs it once; negative_ok = exit != 0 (MUST fail).
    - passed = deterministic AND all_exit_zero AND (negative_ok if there is a negative).
    """
    runs = max(1, int(runs))
    resultados = [run_once(validador, cwd=cwd, timeout=timeout) for _ in range(runs)]
    hashes = [r["stdout_hash"] for r in resultados]
    hashes_unicos = sorted(set(hashes))
    deterministic = len(hashes_unicos) == 1
    all_exit_zero = all(r["exit_code"] == 0 for r in resultados)

    razao = []
    if not deterministic:
        razao.append(f"flaky: {len(hashes_unicos)} hashes distintos em {runs} runs ({hashes_unicos})")
    if not all_exit_zero:
        codes = sorted({r["exit_code"] for r in resultados})
        razao.append(f"validador nao saiu 0 em todos os runs (exit codes: {codes})")

    negative_result = None
    negative_ok = True
    if negative is not None and str(negative).strip():
        negative_result = run_once(negative, cwd=cwd, timeout=timeout)
        negative_ok = negative_result["exit_code"] != 0
        if not negative_ok:
            razao.append("CONTROLE NEGATIVO PASSOU (exit 0) — gate quebrado/permissivo demais")

    passed = deterministic and all_exit_zero and negative_ok
    return {
        "passed": passed,
        "runs": runs,
        "deterministic": deterministic,
        "all_exit_zero": all_exit_zero,
        "hashes_unicos": hashes_unicos,
        "hashes": hashes,
        "results": resultados,
        "negative": negative,
        "negative_ok": negative_ok,
        "negative_result": negative_result,
        "razao": razao,
    }


def runs_from_profile() -> int:
    """Reads verification.determinism_runs from the profile. Default 5 if absent/invalid."""
    if load_profile is None or get is None:
        return DEFAULT_RUNS
    prof = load_profile()
    val = get(prof, "verification.determinism_runs", DEFAULT_RUNS)
    try:
        return max(1, int(val))
    except (TypeError, ValueError):
        return DEFAULT_RUNS


def _render(report: dict) -> str:
    linhas = []
    det = "SIM" if report["deterministic"] else "NAO"
    z = "SIM" if report["all_exit_zero"] else "NAO"
    linhas.append(f"  runs={report['runs']}  deterministico={det}  exit0_em_todos={z}")
    linhas.append(f"  hashes unicos: {report['hashes_unicos']}")
    if report["negative"] is not None:
        ok = "OK (falhou como esperado)" if report["negative_ok"] else "FALHA (passou!)"
        linhas.append(f"  controle negativo: {ok}  -> {report['negative']}")
    veredito = "PASS" if report["passed"] else "FAIL"
    linhas.append(f"\nDETERMINISM: {veredito}")
    if report["razao"]:
        linhas.append("  motivo: " + "; ".join(report["razao"]))
    return "\n".join(linhas)


def _self_test() -> None:
    # Cross-platform deterministic commands via 'python -c' (no network, no profile).
    _py = f'"{sys.executable}"'  # Why: plain `python` doesn't exist on macOS -- the fixture uses the same interpreter running the self-test.
    determ = f'{_py} -c "print(42)"'                    # same output always
    flaky = f'{_py} -c "import random; print(random.random())"'  # output changes
    falha = f'{_py} -c "import sys; sys.exit(1)"'        # exit != 0 (good negative)
    passa = f'{_py} -c "import sys; sys.exit(0)"'        # exit 0 (BAD negative)

    # 1) Deterministic validator => PASS.
    r1 = harness(determ, runs=4)
    assert r1["deterministic"] is True and r1["passed"] is True, "deterministico deveria passar"
    assert len(r1["hashes_unicos"]) == 1

    # 2) Flaky validator => FAIL (more than 1 hash). >1 run to detect the variation.
    r2 = harness(flaky, runs=6)
    assert r2["deterministic"] is False and r2["passed"] is False, "flaky deveria falhar"
    assert len(r2["hashes_unicos"]) > 1

    # 3) Negative that fails (exit 1) => negative_ok True, doesn't sink PASS.
    r3 = harness(determ, runs=3, negative=falha)
    assert r3["negative_ok"] is True and r3["passed"] is True, "negativo que falha = controle ok"

    # 4) Negative that PASSES (exit 0) => broken gate => FAIL.
    r4 = harness(determ, runs=3, negative=passa)
    assert r4["negative_ok"] is False and r4["passed"] is False, "negativo que passa = gate quebrado"

    # 5) Deterministic validator but with exit != 0 => FAIL.
    r5 = harness(falha, runs=3)
    assert r5["deterministic"] is True and r5["all_exit_zero"] is False and r5["passed"] is False

    print("self-test OK")


def main(argv) -> int:
    if argv and argv[0] in ("--self-test", "-t"):
        _self_test()
        return 0

    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]

    # simple flag parsing (--negative VAL, --runs N) + positional (validador)
    validador = None
    negative = None
    runs = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--negative":
            if i + 1 >= len(argv):
                print("determinism_harness: --negative requer um comando", file=sys.stderr)
                return 2
            negative = argv[i + 1]
            i += 2
        elif a == "--runs":
            if i + 1 >= len(argv):
                print("determinism_harness: --runs requer um numero", file=sys.stderr)
                return 2
            try:
                runs = max(1, int(argv[i + 1]))
            except ValueError:
                print("determinism_harness: --runs deve ser inteiro", file=sys.stderr)
                return 2
            i += 2
        elif validador is None:
            validador = a
            i += 1
        else:
            print(f"determinism_harness: argumento inesperado '{a}'", file=sys.stderr)
            return 2

    if not validador:
        print('uso: determinism_harness.py "<validador>" [--negative "<cmd-que-deve-falhar>"] '
              '[--runs N] [--json]', file=sys.stderr)
        return 2

    if runs is None:
        runs = runs_from_profile()

    report = harness(validador, runs=runs, negative=negative)
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
