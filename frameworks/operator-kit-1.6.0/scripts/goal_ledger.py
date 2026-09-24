#!/usr/bin/env python3
"""
goal_ledger -- reader/writer for the _GOAL-LEDGER (autonomous /goal loop -- 2026-06-27).

SSoT for the project's goals: docs/plans/_GOAL-LEDGER.md (markdown table
goal<->tier<->PRD<->status<->criterion<->review). It works at the
GOAL level (not batch): reports the NEXT repo-safe (🟢) not-done goal, the progress
summary, and -- optionally -- writes the status of a goal (--set, surgical edit
of the Status cell). It's the piece the loop uses to know "which objective to tackle now"
and to mark progress without drift.

Usage:
    python scripts/goal_ledger.py                 # next goal + summary
    python scripts/goal_ledger.py --json
    python scripts/goal_ledger.py --next          # just the id of the next goal
    python scripts/goal_ledger.py --set G-A "✅ done (LIVE 2026-06-27)"
    python scripts/goal_ledger.py --readiness G-A R2 --evidence "done_gate exit=0 (3/3 criteria)"
    python scripts/goal_ledger.py --readiness G-A R2 --evidence ".hpp/evidence/e2e-login-<UTC>.json"
        # an hpp evidence record is verified through the HPP core (`python -m hpp`): it must be
        # `valid` (intact AND passed); without the core, R2 with a record is refused (fail closed)
    python scripts/goal_ledger.py --self-test
Exit: 0 = ok -- 1 = --set did not find the goal -- 2 = ledger missing/invalid usage.
stdlib-only. Reading does NOT mutate; --set does a surgical edit of only the Status cell.

v1.0.0 -- 2026-06-27 (initial release: goal driver for the /goal loop)
v1.1.0 -- 2026-07-10 (Operator Kit -- Tier 2 -- embedded in operator-kit -- root resolved via
         CLAUDE_PROJECT_DIR/${CLAUDE_PLUGIN_ROOT}/searching for .git, no longer a fixed parents[N]:
         the file's depth changes when the kit is installed in another project -- the same
         off-by-one that already bit the dual-report-builder. Parsing/ledger logic intact.)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

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


_ROOT = _resolve_root()
LEDGER = _ROOT / "docs" / "plans" / "_GOAL-LEDGER.md"


# ───────────────────────── parsing (pure) ──────────────────────────
def _split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(bool(c) and set(c) <= set("-: ") for c in cells)


def parse(text: str) -> dict:
    """Parses the 1st markdown table with Goal+Status columns. Returns {col, goals}."""
    header = None
    col: dict[str, int] = {}
    goals: list[dict] = []
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = _split_row(line)
        if _is_separator(cells):
            continue
        low = [c.lower() for c in cells]
        if header is None:
            if any("goal" in c for c in low) and any("status" in c for c in low):
                header = cells
                for i, c in enumerate(low):
                    if c == "#":
                        col["id"] = i
                    elif "goal" in c:
                        col["name"] = i
                    elif "tier" in c:
                        col["tier"] = i
                    elif "prd" in c:
                        col["prd"] = i
                    elif "status" in c:
                        col["status"] = i
                    elif "crit" in c or "done" in c:
                        col["done_when"] = i
                    elif "review" in c:
                        col["review"] = i
                    elif "readiness" in c:
                        col["readiness"] = i
                col.setdefault("id", 0)
            continue
        gid = cells[col["id"]] if col["id"] < len(cells) else ""
        if not gid or gid.startswith("#"):
            continue

        def g(key: str) -> str:
            i = col.get(key)
            return cells[i] if i is not None and i < len(cells) else ""

        goals.append({
            "id": gid, "name": g("name"), "tier": g("tier"), "prd": g("prd"),
            "status": g("status"), "done_when": g("done_when"), "review": g("review"),
            "readiness": g("readiness"),
        })
    return {"col": col, "goals": goals}


def status_kind(status: str) -> str:
    s = status.lower()
    if "✅" in status or "done" in s or "pass" in s:
        return "done"
    if ("🔄" in status or "em-curso" in s or "em curso" in s or "in_progress" in s
            or "in-progress" in s or "andamento" in s):
        return "in_progress"
    return "pending"


def tier_kind(tier: str) -> set[str]:
    k: set[str] = set()
    if "🟢" in tier:
        k.add("repo")
    if "🟠" in tier:
        k.add("vm")
    if "🔴" in tier:
        k.add("gate")
    return k


def actionable(goal: dict) -> bool:
    """Repo-safe (🟢) and still not-done = the loop can tackle it autonomously (LC-2)."""
    return "repo" in tier_kind(goal["tier"]) and status_kind(goal["status"]) != "done"


def next_goal(goals: list[dict]):
    return next((g for g in goals if actionable(g)), None)


def summary(goals: list[dict]) -> dict:
    done = [g for g in goals if status_kind(g["status"]) == "done"]
    repo_pending = [g for g in goals if actionable(g)]
    gates = [g for g in goals
             if "gate" in tier_kind(g["tier"]) and status_kind(g["status"]) != "done"]
    nxt = next_goal(goals)
    return {
        "total": len(goals), "done": len(done),
        "repo_pending": len(repo_pending), "gates": len(gates),
        "next": ({"id": nxt["id"], "name": nxt["name"], "prd": nxt["prd"],
                  "done_when": nxt["done_when"]} if nxt else None),
        "pct": round(100 * len(done) / max(1, len(goals)), 1),
    }


def set_column(text: str, goal_id: str, column_key: str, new_value: str) -> tuple[str, bool]:
    """Generic surgical edit: swaps ONLY the cell for `column_key` (e.g. 'status',
    'readiness') on the row whose id == goal_id. Generalizes set_status()."""
    p = parse(text)
    ci = p["col"].get(column_key)
    ii = p["col"].get("id", 0)
    if ci is None:
        raise ValueError(f"column '{column_key}' not found in the ledger")
    out: list[str] = []
    changed = False
    for line in text.splitlines():
        if line.lstrip().startswith("|"):
            cells = _split_row(line)
            if (not _is_separator(cells) and ii < len(cells)
                    and cells[ii] == goal_id and ci < len(cells)):
                cells[ci] = new_value
                line = "| " + " | ".join(cells) + " |"
                changed = True
        out.append(line)
    tail = "\n" if text.endswith("\n") else ""
    return "\n".join(out) + tail, changed


def set_status(text: str, goal_id: str, new_status: str) -> tuple[str, bool]:
    """Surgical edit: swaps ONLY the Status cell on the row whose id == goal_id."""
    return set_column(text, goal_id, "status", new_status)


# ───────────────────────── R0->R4 readiness ladder ──────────────────────────
_READINESS_LEVELS = ("R0", "R1", "R2", "R3", "R4")

_READINESS_EVIDENCE_RE = {
    # R0 (Declared) does not require evidence -- it's the maker's word.
    "R1": re.compile(r"(?i)(self-test|pytest|test).{0,40}(ok|pass|exit\s*=?\s*0|passed)"),
    "R2": re.compile(r"(?i)done_gate.{0,40}(exit\s*=?\s*0|DONE)"),
    "R3": re.compile(r"(?i)REVIEW-[\w\-]+\.md"),
    "R4": re.compile(r"(?i)verdict_by\s*[:=]?\s*operator"),
}

# R2 may also name an `hpp evidence` record; it is verified, never read as text.
_EVIDENCE_RECORD_RE = re.compile(r"(?<![\w./\\-])(?:\./)?(\.hpp[/\\]evidence[/\\][A-Za-z0-9][A-Za-z0-9._-]*\.json)")
# Any token that names a record, whatever path leads to it: used to refuse the forms above does not verify.
_ANY_RECORD_RE = re.compile(r"[^\s'\"()\[\]{}<>]*\.hpp[/\\]evidence[/\\][A-Za-z0-9][A-Za-z0-9._-]*\.json")


def _record_paths(evidence: str) -> list[str]:
    return [m.group(1).replace("\\", "/") for m in _EVIDENCE_RECORD_RE.finditer(evidence or "")]


def _verify_records(paths: list[str], root: Path) -> str | None:
    """None when every named record verifies `valid`; else the refusal. No HPP core = refused (fail closed)."""
    try:
        from hpp.evidence import EvidenceError, verify_evidence
    except ImportError:
        return ("R2 refused — the evidence names an hpp evidence record, but the HPP core is not importable "
                "(`python -m hpp`); install it so the record can be verified")
    for rel in paths:
        try:
            report = verify_evidence(Path(root) / rel, root=Path(root))
        except EvidenceError as exc:
            return f"R2 refused — {rel}: {exc}"
        if report.get("status") != "valid":
            return (f"R2 refused — {rel}: hpp evidence verify says {report.get('status')!r} "
                    f"(needs 'valid'): {'; '.join(report.get('problems') or [])}")
    return None


def validate_readiness(level: str, evidence: str, root: Path | None = None) -> str | None:
    """Returns None if the evidence satisfies the level, or the refusal message (exit 2).

    Hard rule (A.2): nobody declares a readiness higher than the evidence.
    """
    if level not in _READINESS_LEVELS:
        return f"invalid level: {level!r} (valid: {_READINESS_LEVELS})"
    if level == "R0":
        return None
    if level == "R2":
        # Why: a record named by an absolute or nested path was not recognised, so R2 fell back to
        # the textual receipt and the record was never verified. It is refused instead.
        stray = [token for token in _ANY_RECORD_RE.findall(evidence or "")
                 if not _EVIDENCE_RECORD_RE.fullmatch(token)]
        if stray:
            return (f"R2 refused — name the record relative to the project root "
                    f"(.hpp/evidence/<name>.json), so it can be verified: {stray[0]}")
    records = _record_paths(evidence) if level == "R2" else []
    if records:
        return _verify_records(records, _ROOT if root is None else root)
    pattern = _READINESS_EVIDENCE_RE[level]
    if not evidence or not pattern.search(evidence):
        hints = {
            "R1": "evidence must reference a self-test/pytest with exit 0/passed",
            "R2": "evidence must reference a done_gate receipt (e.g. 'done_gate exit=0')",
            "R3": "evidence must reference a REVIEW-*.md (goal_review.py from another family)",
            "R4": "evidence must contain 'verdict_by: operator' (only the human declares R4)",
        }
        return f"{level} refused — {hints[level]} (evidence received: {evidence!r})"
    return None


def set_readiness(text: str, goal_id: str, level: str, evidence: str) -> tuple[str, bool, str | None]:
    """Returns (new_text, changed, error). error != None = refused, text unchanged."""
    err = validate_readiness(level, evidence)
    if err:
        return text, False, err
    cell = f"{level} ({evidence[:60]})" if evidence else level
    try:
        new_text, changed = set_column(text, goal_id, "readiness", cell)
    except ValueError as e:
        return text, False, str(e)
    if not changed:
        return text, False, f"goal '{goal_id}' not found in the ledger"
    return new_text, True, None


# ───────────────────────── self-test ──────────────────────────
_SAMPLE = (
    "| # | Goal | Tier | PRD-source | Status | Criterion-of-DONE (LIVE) | Review |\n"
    "|---|------|------|------------|--------|--------------------------|--------|\n"
    "| G-A | foo | 🟢 | PRD-X | ⬜ pending | crit a | rev a |\n"
    "| G-B | bar | 🔴 gate | PRD-Y | ⬜ gate | crit b | rev b |\n"
    "| G-C | baz | 🟢 | PRD-Z | ✅ done | crit c | rev c |\n"
)


def _self_test() -> None:
    p = parse(_SAMPLE)
    assert len(p["goals"]) == 3, p["goals"]
    assert status_kind("✅ done") == "done"
    assert status_kind("🔄 in-progress (x)") == "in_progress"
    assert status_kind("⬜ pending") == "pending"
    assert tier_kind("🟢→deploy") == {"repo"}
    assert tier_kind("🟢(mirror)+🔴(release)") == {"repo", "gate"}
    nxt = next_goal(p["goals"])
    assert nxt and nxt["id"] == "G-A", nxt  # G-A repo+pending; G-B gate; G-C done
    s = summary(p["goals"])
    assert s["done"] == 1 and s["repo_pending"] == 1 and s["gates"] == 1, s
    new, changed = set_status(_SAMPLE, "G-A", "🔄 in-progress")
    assert changed and "🔄 in-progress" in new, "set_status failed"
    assert "| G-B | bar |" in new.replace("  ", " ") or "G-B" in new, "other rows intact"
    assert parse(new)["goals"][0]["status"] == "🔄 in-progress", "the new status did not persist"

    # R0->R4 ladder (A.2)
    sample_r = _SAMPLE.replace(
        "| # | Goal | Tier | PRD-source | Status | Criterion-of-DONE (LIVE) | Review |",
        "| # | Goal | Tier | PRD-source | Status | Criterion-of-DONE (LIVE) | Review | Readiness |",
    ).replace(
        "|---|------|------|------------|--------|--------------------------|--------|",
        "|---|------|------|------------|--------|--------------------------|--------|-----------|",
    )
    # add a Readiness cell (R0) to each data row (goals G-A/G-B/G-C)
    lines_r = []
    for ln in sample_r.splitlines():
        if ln.startswith("| G-"):
            ln = ln.rstrip()[:-1].rstrip() + " | R0 |"
        lines_r.append(ln)
    sample_r = "\n".join(lines_r) + "\n"

    assert validate_readiness("R0", "") is None, "R0 should not require evidence"
    assert validate_readiness("R2", "I just ran it and it looked fine") is not None, "R2 without a receipt should refuse"
    assert validate_readiness("R2", "done_gate exit=0 (3/3 criteria)") is None, "R2 with a receipt should accept"
    assert validate_readiness("R3", "I reviewed it and liked it") is not None, "R3 without a REVIEW-*.md should refuse"
    assert validate_readiness("R3", "see REVIEW-G-A-20260710.md") is None, "R3 with a REVIEW-*.md should accept"
    assert validate_readiness("R4", "I approved it") is not None, "R4 without verdict_by:operator should refuse"
    assert validate_readiness("R4", "verdict_by: operator") is None, "R4 with verdict_by:operator should accept"

    new_r, ok_r, err_r = set_readiness(sample_r, "G-A", "R2", "done_gate exit=0 (2/2 criteria)")
    assert ok_r and err_r is None, f"R2 with a receipt should write: {err_r}"
    assert "R2 (done_gate exit=0" in new_r

    _, ok_r2, err_r2 = set_readiness(sample_r, "G-A", "R4", "no formal evidence")
    assert not ok_r2 and err_r2 and "verdict_by" in err_r2, f"R4 without evidence should refuse: {err_r2}"

    _, ok_r3, err_r3 = set_readiness(_SAMPLE, "G-A", "R1", "self-test ok")
    assert not ok_r3 and "readiness" in (err_r3 or ""), "a ledger without a readiness column should refuse with a clear error"

    # R2 through an hpp evidence record (.hpp/evidence/<name>.json): verified by the optional
    # HPP core, never trusted as text; without the core it fails closed.
    rec = ".hpp/evidence/e2e-login-20260924T000000Z.json"
    assert _record_paths(f"see {rec}") == [rec], "a record path in the evidence must be recognised"
    for elsewhere in (f"C:/x/{rec}", f"sub/{rec}", f"/abs/{rec}"):
        err_e = validate_readiness("R2", f"done_gate exit=0 {elsewhere}")
        assert err_e and "relative" in err_e, \
            f"a record named by another path must refuse, never fall back to the textual receipt: {err_e}"
    saved = {name: sys.modules.get(name) for name in ("hpp", "hpp.evidence")}
    sys.modules["hpp"] = None  # type: ignore[assignment]  # simulate an absent core
    sys.modules["hpp.evidence"] = None  # type: ignore[assignment]
    try:
        err_h = validate_readiness("R2", f"done_gate exit=0 · record {rec}")
        assert err_h and "HPP core" in err_h, f"a record without the HPP core must refuse R2 (fail closed): {err_h}"
        assert validate_readiness("R2", "done_gate exit=0 (3/3 criteria)") is None, \
            "CONTROL: the textual done_gate receipt keeps working without the HPP core"
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
    try:
        import hpp.evidence as hpp_evidence  # optional core: this branch runs only when it is importable
    except ImportError:
        hpp_evidence = None
    if hpp_evidence is not None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            good = hpp_evidence.run_evidence(
                "ok", [sys.executable, "-c", "open('out.txt', 'w').write('x')"], ["out.txt"], root=root)
            bad = hpp_evidence.run_evidence("bad", [sys.executable, "-c", "raise SystemExit(3)"], [], root=root)
            assert validate_readiness("R2", good["record_path"], root=root) is None, "a valid record must satisfy R2"
            err_nf = validate_readiness("R2", bad["record_path"], root=root) or ""
            assert "not-evidence" in err_nf, f"a record of a failed run must refuse R2: {err_nf}"
            (root / "out.txt").write_text("changed", encoding="utf-8")
            err_bl = validate_readiness("R2", f"done_gate exit=0 {good['record_path']}", root=root) or ""
            assert "blocked" in err_bl, f"a changed artifact must refuse R2, even next to a textual receipt: {err_bl}"

    print("self-test OK")


# ───────────────────────── CLI ──────────────────────────
def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="goal_ledger — goal driver for the /goal loop")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--next", action="store_true", help="prints only the id of the next repo-safe goal")
    ap.add_argument("--set", nargs=2, metavar=("GOAL", "STATUS"))
    ap.add_argument("--readiness", nargs=2, metavar=("GOAL", "LEVEL"), help="R0-R4 (readiness ladder); requires --evidence for R1+")
    ap.add_argument("--evidence", default="", help="textual evidence for --readiness (receipt/REVIEW-*.md/verdict_by:operator), "
                    "or an .hpp/evidence/<name>.json record path for R2, verified through the HPP core")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)

    if a.self_test:
        _self_test()
        return 0

    if not LEDGER.exists():
        print(f"goal_ledger: ledger missing: {LEDGER}", file=sys.stderr)
        return 2
    text = LEDGER.read_text(encoding="utf-8", errors="replace")

    if a.readiness:
        gid, level = a.readiness
        new, ok, err = set_readiness(text, gid, level, a.evidence)
        if not ok:
            print(f"goal_ledger: readiness refused — {err}", file=sys.stderr)
            return 2
        LEDGER.write_text(new, encoding="utf-8")
        print(f"goal_ledger: {gid} -> Readiness = '{level}' (evidence: {a.evidence[:60]!r})")
        return 0

    if a.set:
        gid, new_status = a.set
        new, changed = set_status(text, gid, new_status)
        if not changed:
            print(f"goal_ledger: goal '{gid}' not found in the ledger", file=sys.stderr)
            return 1
        LEDGER.write_text(new, encoding="utf-8")
        print(f"goal_ledger: {gid} → Status = '{new_status}' ✅")
        return 0

    p = parse(text)
    s = summary(p["goals"])
    if a.next:
        print(s["next"]["id"] if s["next"] else "")
        return 0
    if a.json:
        print(json.dumps({**s, "goals": p["goals"]}, ensure_ascii=False, indent=2))
        return 0
    print(f"GOAL-LEDGER — {s['done']}/{s['total']} done ({s['pct']}%) · "
          f"{s['repo_pending']} repo-safe pending · {s['gates']} gate(s)")
    if s["next"]:
        print(f"NEXT (repo-safe): {s['next']['id']} — {s['next']['name']} "
              f"[{s['next']['prd']}]")
        print(f"  done-when: {s['next']['done_when']}")
    else:
        print("NEXT: (no repo-safe item pending — only 🔴/human gates left)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
