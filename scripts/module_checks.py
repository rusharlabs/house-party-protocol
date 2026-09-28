#!/usr/bin/env python3
"""Run every shipped module's self-tests and evals the way a user on this machine would.

Self-tests go through the kit doctor's smoke stage (every `.py` that answers `--self-test`, the
house contract), in plan mode: nothing is installed and nothing is registered. Evals are the
`evals/*.sh` of each module, run from the module directory with the bash you name.

    python scripts/module_checks.py
    python scripts/module_checks.py --bash /bin/bash --without-python   # a stock Mac: bash 3.2,
                                                                         # BSD tools, no `python`

`--without-python` (macOS and Linux) puts a shim directory first on PATH: `python3` runs this
interpreter and a bare `python` fails with "command not found" (exit 127), so a module that still
calls a bare `python` fails here instead of on the first Mac that runs it. Every other tool stays
where it was.

In the source tree there are no modules (they exist only in the emitted copy); the script says
so and exits 0. A module `marketplace.json` declares and the copy does not carry is an error, never
one module fewer to run. Exit: 0 all green - 1 a self-test or an eval failed - 3 error.

Standard library only. Writes only to a temporary directory it removes.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from shell_portability import MissingModules, module_dirs  # noqa: E402  (one reading of marketplace.json)

EVAL_TIMEOUT_S = 900


def _without_python_env(shim_dir: Path) -> dict[str, str]:
    """PATH as it was, with a shim directory first: `python3` runs this interpreter, and a bare `python`
    fails the way it does on a host that has none (command not found, exit 127).

    Why: the first version removed every PATH entry that held a `python`. On a Linux runner that is
    /usr/bin, and with it grep, rm, seq, dirname and git, so every eval and half the self-tests failed
    on the tools before reaching the question this option asks. Shadowing leaves every other tool where
    it was."""
    python3 = shim_dir / "python3"
    python3.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
    missing = shim_dir / "python"
    missing.write_text('#!/bin/sh\necho "python: command not found (module_checks --without-python: this host '
                       'has only python3)" >&2\nexit 127\n', encoding="utf-8")
    for script in (python3, missing):
        script.chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([str(shim_dir), os.environ.get("PATH", "")])
    return env


def _declares_self_test(module: Path) -> bool:
    return any("--self-test" in p.read_text(encoding="utf-8", errors="replace")
               for p in module.rglob("*.py") if "__pycache__" not in p.parts)


def run_self_tests(module: Path, kit_doctor: Path, target: Path, env: dict[str, str]) -> dict:
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(kit_doctor), "install", "--kit", str(module),
         "--target", str(target), "--no-register"],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
        errors="replace", env=env, timeout=1800,
    )
    try:
        stages = {s["stage"]: s for s in json.loads(proc.stdout).get("stages", [])}
    except (json.JSONDecodeError, AttributeError):
        return {"ok": 0, "failed": [f"kit_doctor exit {proc.returncode}: {(proc.stderr or proc.stdout)[-300:]}"]}
    results = stages.get("smoke", {}).get("results", [])
    ok = sum(1 for r in results if r["status"] == "ok")
    failed = [f"{r['file']}: {r['status']}" for r in results if r["status"] in ("fail", "timeout", "error")]
    if ok == 0 and _declares_self_test(module):
        # LC-1b: a module whose scripts answer --self-test cannot pass with zero self-tests run
        failed.append("scripts declare --self-test but the smoke stage ran none")
    return {"ok": ok, "failed": failed}


def run_evals(module: Path, bash: str, env: dict[str, str]) -> list[dict]:
    rows = []
    for script in sorted((module / "evals").glob("*.sh")):
        started = time.monotonic()
        try:
            proc = subprocess.run([bash, f"evals/{script.name}"], cwd=module, env=env,
                                  stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=EVAL_TIMEOUT_S)
            code, out = proc.returncode, (proc.stdout + proc.stderr)
        except subprocess.TimeoutExpired:
            code, out = 124, f"no answer in {EVAL_TIMEOUT_S}s"
        lines = [line for line in out.splitlines() if line.strip()]
        rows.append({"eval": script.name, "exit": code, "seconds": round(time.monotonic() - started),
                     "last": lines[-1] if lines else "", "output": out if code else ""})
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bash", default=shutil.which("bash") or "bash")
    parser.add_argument("--without-python", action="store_true")
    parser.add_argument("--skip-evals", action="store_true")
    parser.add_argument("--root", type=Path, default=Path(os.environ.get("HPP_EMITTED_COPY") or ROOT),
                        help="the emitted copy to check (default: this checkout)")
    args = parser.parse_args(argv)

    try:
        modules = module_dirs(args.root)
    except MissingModules as exc:
        print(f"module_checks: {exc}", file=sys.stderr)
        return 3
    if not modules:
        print("module_checks: no marketplace.json with modules here (source tree); nothing to run")
        return 0
    forge = [m for m in modules if m.name.startswith("kit-forge-")]
    if not forge or not (forge[0] / "kit_doctor.py").is_file():
        print("module_checks: kit-forge/kit_doctor.py not found among the modules", file=sys.stderr)
        return 3
    if args.without_python and os.name == "nt":
        print("module_checks: --without-python is for macOS and Linux (Windows names it `python`)",
              file=sys.stderr)
        return 3

    failures = 0
    with tempfile.TemporaryDirectory(prefix="hpp-module-checks-") as tmp:
        tmp_path = Path(tmp)
        env = dict(os.environ)
        if args.without_python:
            shim = tmp_path / "shim"
            shim.mkdir()
            env = _without_python_env(shim)
        print(f"bash: {args.bash} · python: {sys.executable}"
              + (" · PATH without `python`" if args.without_python else ""))
        for module in modules:
            target = tmp_path / "target" / module.name
            target.mkdir(parents=True)
            smoke = run_self_tests(module, forge[0] / "kit_doctor.py", target, env)
            evals = [] if args.skip_evals else run_evals(module, args.bash, env)
            bad_evals = [e for e in evals if e["exit"] != 0]
            failures += len(smoke["failed"]) + len(bad_evals)
            status = "FAIL" if smoke["failed"] or bad_evals else "ok"
            print(f"{status:4}  {module.parent.name}/{module.name}: {smoke['ok']} self-test(s), "
                  f"{len(evals) - len(bad_evals)}/{len(evals)} eval(s)")
            for item in smoke["failed"]:
                print(f"        self-test  {item}")
            for e in evals:
                mark = "ok" if e["exit"] == 0 else f"exit {e['exit']}"
                print(f"        eval  {e['eval']}  {mark}  {e['seconds']}s  {e['last'][:120]}")
                if e["exit"]:
                    print("\n".join(f"          | {line}" for line in e["output"].splitlines()[-25:]))
    print(f"module_checks: {len(modules)} module(s), {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
