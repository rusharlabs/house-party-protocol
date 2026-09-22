#!/usr/bin/env python3
"""
verify_ladder (Operator Kit) -- 6-level verification ladder, portable and config-driven.

6-level verification ladder, project-agnostic: reads the
`verification.ladder` ladder from operator-profile.yaml (dict level->command)
and runs each level that HAS a command. The 6 canonical levels are:
    lint - test - build - visual - staging - security

Anti-false-green principle: a level with an EMPTY/absent command does not "pass" -- it
is SKIPPED and doesn't count toward the score. The score is X/N where N = number of levels
with a real command (SKIPPED levels inflate neither the denominator nor the numerator).

Overall PASS/FAIL:
    FAIL if ANY mandatory level (verification.ladder_required) failed,
    OR if the score (levels that passed) < verification.ladder_min_score.
    Otherwise PASS. (A mandatory level without a command = SKIPPED = not satisfied = FAIL.)

Usage:
    python verify_ladder.py                 # reads the ladder from operator-profile.yaml
    python verify_ladder.py --json          # structured JSON output
    python verify_ladder.py --self-test

Exit: 0 = PASS -- 1 = FAIL -- 2 = invalid usage/config (no usable ladder).
stdlib + PyYAML (via loader). Cross-platform (shell=True respects the OS). Degrades
to safe defaults without a profile: no ladder -> nothing to verify -> FAIL (never a false green).

v1.0.0 -- 2026-06-19 (Operator Kit -- Tier 1 -- generalizes verify-6-levels)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# import the shared kit loader (.../operator-kit/_lib/profile_loader.py)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from _lib.profile_loader import load_profile, get
except Exception:  # noqa: BLE001 -- without the loader, profile mode is unavailable; the rest works
    load_profile = None  # type: ignore[assignment]
    get = None  # type: ignore[assignment]

# Canonical order of the 6 levels.
CANONICAL_LEVELS = ["lint", "test", "build", "visual", "staging", "security"]


def run_level(level: str, cmd: str, cwd: str | None = None, timeout: int = 600) -> dict:
    """Runs one ladder level. No command -> SKIPPED status (never a false green).

    Returns dict {level, cmd, status, passed, exit_code, tail}.
    status in {"PASS", "FAIL", "SKIPPED"}. SKIPPED never counts as passed.
    """
    cmd = (cmd or "").strip()
    if not cmd:
        return {"level": level, "cmd": "", "status": "SKIPPED",
                "passed": False, "exit_code": None, "tail": "sem comando configurado"}
    try:
        r = subprocess.run(
            cmd, shell=True, cwd=cwd,
            capture_output=True, text=True, timeout=timeout,
        )
        tail = ((r.stdout or "") + (r.stderr or "")).strip()[-400:]
        passed = r.returncode == 0
        return {"level": level, "cmd": cmd, "status": "PASS" if passed else "FAIL",
                "passed": passed, "exit_code": r.returncode, "tail": tail}
    except subprocess.TimeoutExpired:
        return {"level": level, "cmd": cmd, "status": "FAIL",
                "passed": False, "exit_code": 124, "tail": f"timeout {timeout}s"}
    except Exception as e:  # noqa: BLE001 -- the ladder never crashes; error = failed level
        return {"level": level, "cmd": cmd, "status": "FAIL",
                "passed": False, "exit_code": 1, "tail": f"erro: {e}"}


def evaluate(ladder: dict, obrigatorios=None, score_minimo: int = 1,
             cwd: str | None = None, timeout: int = 600) -> dict:
    """Runs the whole ladder and evaluates overall PASS/FAIL.

    ladder: dict {level: comando}. Levels follow CANONICAL_LEVELS when present,
            extras (if any) run at the end in alphabetical order.
    obrigatorios: list of levels that MUST pass (default []).
    score_minimo: minimum number of PASS levels to not fail on score.

    Returns dict with results, score, total (levels with a command), pass/fail and razao.
    """
    obrigatorios = list(obrigatorios or [])
    # Sorts: canonical first (in the fixed order), then alphabetical extras.
    keys = [n for n in CANONICAL_LEVELS if n in ladder]
    keys += sorted(k for k in ladder if k not in CANONICAL_LEVELS)

    results = [run_level(n, ladder.get(n, ""), cwd=cwd, timeout=timeout) for n in keys]

    with_command = [r for r in results if r["status"] != "SKIPPED"]
    total = len(with_command)                                  # N = levels with a real command
    score = sum(1 for r in with_command if r["passed"])        # X = levels that passed

    # A mandatory level is satisfied ONLY if status == PASS (SKIPPED or FAIL don't count).
    status_by_level = {r["level"]: r["status"] for r in results}
    obrig_falhos = [n for n in obrigatorios if status_by_level.get(n) != "PASS"]

    ok = (not obrig_falhos) and (score >= score_minimo)
    razao = []
    if obrig_falhos:
        razao.append(f"mandatory level(s) not satisfied: {', '.join(obrig_falhos)}")
    if score < score_minimo:
        razao.append(f"score {score} < minimum {score_minimo}")
    if total == 0:
        razao.append("no level has a command configured (nothing verified)")

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
    """Reads verification.ladder / ladder_required / ladder_min_score from the profile.

    Returns (ladder_dict, obrigatorios_list, score_minimo_int). Safe defaults if absent.
    """
    if load_profile is None or get is None:
        return {}, [], 1
    prof = load_profile()
    ladder = get(prof, "verification.ladder", {}) or {}
    if not isinstance(ladder, dict):
        ladder = {}
    required = get(prof, "verification.ladder_required", []) or []
    required = [str(x) for x in required] if isinstance(required, list) else []
    minimum = get(prof, "verification.ladder_min_score", 1)
    try:
        minimum = int(minimum)
    except (TypeError, ValueError):
        minimum = 1
    return {k: str(v or "") for k, v in ladder.items()}, required, minimum


def _render(report: dict) -> str:
    """Renders the human report (text). Shows the tail per level, score and verdict."""
    lines = []
    for r in report["results"]:
        mark = {"PASS": "OK  ", "FAIL": "FAIL", "SKIPPED": "SKIP"}[r["status"]]
        ec = "" if r["exit_code"] is None else f" exit {r['exit_code']}"
        lines.append(f"  [{mark}] {r['level']:<9}{ec}  {r['cmd'] or '(no command)'}")
        if r["status"] == "FAIL" and r["tail"]:
            lines.append(f"          ^ {r['tail'][-200:]}")
    verdict = "PASS" if report["passed"] else "FAIL"
    lines.append(f"\nLADDER: {verdict}  (score {report['score']}/{report['total']}, "
                  f"minimum {report['score_minimo']})")
    if report["razao"]:
        lines.append("  reason: " + "; ".join(report["razao"]))
    return "\n".join(lines)


def _self_test() -> None:
    # fake inline ladder -- no profile, no network; deterministic cross-platform commands.
    ok_cmd = f'"{sys.executable}" -c "import sys; sys.exit(0)"'
    fail_cmd = f'"{sys.executable}" -c "import sys; sys.exit(1)"'

    # 1) Level without a command => SKIPPED, doesn't count towards the total.
    rep = evaluate({"lint": "", "test": ok_cmd}, obrigatorios=["test"], score_minimo=1)
    assert rep["total"] == 1, f"SKIPPED should not count towards the total: {rep['total']}"
    assert rep["score"] == 1, f"score should be 1: {rep['score']}"
    assert rep["passed"] is True, "mandatory test passed and score>=min => PASS"
    skip = next(r for r in rep["results"] if r["level"] == "lint")
    assert skip["status"] == "SKIPPED", "lint without a command must be SKIPPED"

    # 2) A mandatory level that fails => overall FAIL even with another level ok.
    rep2 = evaluate({"test": fail_cmd, "build": ok_cmd}, obrigatorios=["test"], score_minimo=1)
    assert rep2["passed"] is False, "mandatory test failed => FAIL"
    assert "test" in rep2["obrigatorios_falhos"]

    # 3) Score below the minimum => FAIL.
    rep3 = evaluate({"test": ok_cmd}, obrigatorios=[], score_minimo=2)
    assert rep3["passed"] is False, "score 1 < minimum 2 => FAIL"

    # 4) A mandatory level WITHOUT a command (SKIPPED) does NOT satisfy => FAIL (anti-false-green).
    rep4 = evaluate({"security": ""}, obrigatorios=["security"], score_minimo=0)
    assert rep4["passed"] is False, "a SKIPPED mandatory level does not satisfy"
    assert "security" in rep4["obrigatorios_falhos"]

    # 5) Empty ladder => total 0, nothing verified => FAIL.
    rep5 = evaluate({}, obrigatorios=[], score_minimo=1)
    assert rep5["total"] == 0 and rep5["passed"] is False, "an empty ladder never passes"

    # 6) Canonical order respected when present.
    rep6 = evaluate({"security": ok_cmd, "lint": ok_cmd}, obrigatorios=[], score_minimo=1)
    order = [r["level"] for r in rep6["results"]]
    assert order == ["lint", "security"], f"wrong canonical order: {order}"

    print("self-test OK")


def main(argv) -> int:
    if argv and argv[0] in ("--self-test", "-t"):
        _self_test()
        return 0
    as_json = "--json" in argv

    ladder, required, minimum = ladder_from_profile()
    if not ladder:
        msg = "verify_ladder: no ladder in verification.ladder of operator-profile.yaml " \
              "(or profile/PyYAML missing) — nothing to verify"
        if as_json:
            print(json.dumps({"passed": False, "score": 0, "total": 0,
                              "razao": [msg]}, ensure_ascii=False, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 2

    report = evaluate(ladder, obrigatorios=required, score_minimo=minimum)
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
