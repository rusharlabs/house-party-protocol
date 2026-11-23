#!/usr/bin/env python3
"""
done_gate (Operator Kit) -- programmatic, config-driven Definition-of-Done.

Programmatic and config-driven Definition-of-Done: besides taking loose
criteria (argv/stdin), it accepts `--profile <type>` and reads the commands
from `verification.done_criteria[<type>]` in operator-profile.yaml. It's the
deterministic gate between "I think I'm done" and "it's verified": exit 0 ONLY
if ALL criteria pass (AND). Empty list = NOT-done (never passes by omission).

Usage:
    python done_gate.py "python -m pytest -q" "ruff check ."      # loose criteria
    python done_gate.py --profile py                              # reads from the profile (type 'py')
    python done_gate.py --profile py --json                       # JSON output for the loop
    echo '{"criteria":["pytest -q"]}' | python done_gate.py --stdin
    python done_gate.py "python -m hpp evidence run --id e2e-login --artifact \"pw-out/**/trace.zip\" -- npx playwright test tests/login.spec.ts"
        # an end-to-end criterion recorded by the HPP core (`python -m hpp`): done_gate keeps only a
        # short output tail; the durable proof is the .hpp/evidence/e2e-login-<UTC>.json record.
        # Double quotes inside the criterion: it runs through the OS shell, and cmd.exe keeps
        # single quotes as literal characters.
    python done_gate.py --self-test

THREE STATES, and only one is forbidden (v1.1.0):

    DONE                all criteria passed AND nobody declared pending work.  exit 0
    PARCIAL-DECLARADO   whoever ran it SAID what is missing (--declare-partial or the
                        `partial` field from stdin). Not green -- exit 1 -- but it's
                        an honest, machine-readable state, with the list of what
                        is missing. The declaration BEATS the green: all criteria
                        passing + declaration = PARCIAL, because whoever ran it
                        knows more than the criteria.                           exit 1
    NOT-DONE            failed and nobody declared anything. It's the state this
                        kit calls "silent partial" -- the only one FORBIDDEN. The
                        gate can't prevent the silence, but it NAMES it in the
                        output and says what to do.                             exit 1

    python done_gate.py "pytest -q" --declare-partial "missing the edge-case tests: X, Y"
    echo '{"criteria":["pytest -q"],"partial":{"missing":["X","Y"],"reason":"..."}}' \
        | python done_gate.py --stdin

    # Why: a binary gate pushes toward one of two errors -- the agent paints green over what wasn't
    # finished, or the loop gets stuck on a NOT-DONE without knowing what's missing. The third state
    # is the honest output: "I'm not done, and THIS is the gap". Downstream (handoff, ledger, the
    # loop itself) reads `partial: true` + `declared.missing` and knows where to resume. Exit stays 1
    # in both non-green cases: nothing downstream can treat partial as done. The distinction lives in the payload.

Exit: 0 = DONE -- 1 = PARCIAL-DECLARADO or NOT-DONE -- 2 = invalid usage.
stdlib + PyYAML (only in --profile mode). Cross-platform (shell=True respects the OS).

v1.1.0 -- 2026-09-20 (three states) -- v1.0.0 -- 2026-06-19 (Operator Kit -- Tier 1)
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
except Exception:  # noqa: BLE001 -- without the loader, --profile mode is unavailable but the rest works
    load_profile = None  # type: ignore[assignment]
    get = None  # type: ignore[assignment]


def run_criterion(cmd: str, cwd: str | None = None, timeout: int = 600) -> dict:
    """Runs a criterion command. Returns {cmd, passed, exit_code, tail}. Never crashes."""
    try:
        r = subprocess.run(
            cmd, shell=True, cwd=cwd,
            capture_output=True, text=True, timeout=timeout,
        )
        tail = ((r.stdout or "") + (r.stderr or "")).strip()[-400:]
        return {"cmd": cmd, "passed": r.returncode == 0, "exit_code": r.returncode, "tail": tail}
    except subprocess.TimeoutExpired:
        return {"cmd": cmd, "passed": False, "exit_code": 124, "tail": f"timeout {timeout}s"}
    except Exception as e:  # noqa: BLE001 -- gate never crashes; failure = not-done
        return {"cmd": cmd, "passed": False, "exit_code": 1, "tail": f"error: {e}"}


# Why: `cwd` keeps the kit configurable for external consumers; the local flow uses the default.
def gate(criteria, cwd: str | None = None, timeout: int = 600):
    """Runs all criteria (AND). Returns (all_passed, results). Empty list = not-done."""
    results = [run_criterion(c, cwd=cwd, timeout=timeout) for c in criteria if str(c).strip()]
    return (bool(results) and all(r["passed"] for r in results)), results


def criteria_from_profile(task_type: str) -> list[str]:
    """Reads verification.done_criteria[<task_type>] from operator-profile.yaml. [] if absent."""
    if load_profile is None or get is None:
        return []
    prof = load_profile()
    crit = get(prof, f"verification.done_criteria.{task_type}", [])
    return [str(c) for c in crit] if isinstance(crit, list) else []


DONE = "DONE"
PARCIAL = "PARCIAL-DECLARADO"
NOT_DONE = "NOT-DONE"


def parse_declaration(raw) -> dict | None:
    """Normalizes the pending-work declaration. None = nothing declared.

    Accepts free text ("X and Y are missing") or dict {"missing": [...], "reason": "..."}.
    An EMPTY declaration isn't a declaration -- it becomes None, and the state falls to NOT-DONE.
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
    """The third state. The declaration BEATS the green."""
    if declared is not None:
        return PARCIAL
    return DONE if all_passed else NOT_DONE


def _self_test() -> None:
    # Why: plain `python` doesn't exist on macOS (only python3) and the self-test used to fail
    # with exit 127. The right interpreter is the one running THIS; quoted because shell=True and
    # the path may have a space.
    py = f'"{sys.executable}"'
    ok, res = gate([f'{py} -c "import sys; sys.exit(0)"'])
    assert ok and res[0]["passed"], "exit 0 should pass"
    assert gate([f'{py} -c "import sys; sys.exit(3)"'])[0] is False, "exit 3 should fail"
    assert gate([f'{py} -c "pass"', f'{py} -c "raise SystemExit(1)"'])[0] is False, "AND: one failure sinks it"
    assert gate([])[0] is False, "empty list = not-done"

    # the three states
    assert decide(True, None) == DONE
    assert decide(False, None) == NOT_DONE
    assert decide(False, {"missing": ["x"], "reason": ""}) == PARCIAL
    assert decide(True, {"missing": ["x"], "reason": ""}) == PARCIAL, \
        "the DECLARATION BEATS the green: whoever ran it knows more than the criteria"

    # an empty declaration isn't a declaration
    assert parse_declaration("") is None
    assert parse_declaration("   ") is None
    assert parse_declaration({}) is None
    assert parse_declaration({"missing": [], "reason": ""}) is None
    assert parse_declaration("X and Y are missing") == {"missing": ["X and Y are missing"], "reason": ""}
    d = parse_declaration({"missing": ["X", " Y "], "reason": "no access to staging"})
    assert d == {"missing": ["X", "Y"], "reason": "no access to staging"}, d
    assert parse_declaration({"reason": "reason only"}) == {"missing": ["reason only"], "reason": "reason only"}

    # the instrument discriminates: the three states are reachable and distinct
    assert len({decide(True, None), decide(False, None), decide(False, {"missing": ["x"], "reason": ""})}) == 3
    print("self-test OK")


def main(argv) -> int:
    if argv and argv[0] in ("--self-test", "-t"):
        _self_test()
        return 0
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]

    # --declare-partial "<text>" may come at any position
    declared_raw = None
    if "--declare-partial" in argv:
        i = argv.index("--declare-partial")
        if i + 1 >= len(argv):
            print("usage: --declare-partial \"<what is missing and why>\"", file=sys.stderr)
            return 2
        declared_raw = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]

    if argv and argv[0] == "--profile":
        if len(argv) < 2:
            print("usage: done_gate.py --profile <type>   (type = key under verification.done_criteria)", file=sys.stderr)
            return 2
        task_type = argv[1]
        criteria = criteria_from_profile(task_type)
        if not criteria:
            print(f"done_gate: no criterion for type '{task_type}' in operator-profile.yaml "
                  "(or profile/PyYAML missing)", file=sys.stderr)
            return 2
    elif argv and argv[0] == "--stdin":
        try:
            payload = json.loads(sys.stdin.read() or "{}")
            criteria = payload.get("criteria", [])
            if declared_raw is None and "partial" in payload:
                declared_raw = payload.get("partial")
        except Exception:
            print("done_gate: invalid stdin JSON", file=sys.stderr)
            return 2
    else:
        criteria = argv

    if not criteria:
        print('usage: done_gate.py "<cmd1>" [...]  |  --profile <type>  |  --stdin', file=sys.stderr)
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
        print(f"\nDONE-GATE: {state} ({passed}/{len(results)} criteria)")
        if state == PARCIAL:
            for m in declared["missing"]:
                print(f"  missing: {m}")
            if declared["reason"]:
                print(f"  because: {declared['reason']}")
            if all_passed:
                print("  (all criteria green — the declaration won: whoever ran it knows more)")
        elif state == NOT_DONE:
            print("  no pending-work declaration. If this is PARTIAL, declare what is missing")
            print("  (--declare-partial \"...\"); if it is a FAILURE, fix it. Silence is not a state.")
    return 0 if state == DONE else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
