#!/usr/bin/env python3
"""
instinct_promote -- instinct candidates from /ralph-gate FAILs; only a human promotes.

Pattern inspired by the "instinct + confidence-scoring" idea in ECC (continuous-learning-v2,
github.com/affaan-m/ECC, MIT, (c) 2026 Affaan Mustafa) -- see NOTICE-ECC.md alongside. NOT A
SINGLE line of ECC code was copied (their CLI runs ~2000 lines, XDG dirs, remote fetch,
promote/prune/evolve across projects); this is a minimal, new reimplementation of the PATTERN:
recurring failure = candidate; confidence = recurrence count; promotion is ALWAYS a human
act (never automatic -- same spirit as partial-autonomy-slider: propose, do not auto-execute
on something that persists/teaches the team).

Flow:
  --scan  : reads .claude/handoff/HANDOFF-LEDGER.jsonl ("gate-failed" events from ralph_gate.py,
            field failed_cmds), groups by the command that failed, increments the count in
            .claude/evolve/instincts.jsonl (creates a new candidate if not seen yet).
  --list  : lists candidates (status=candidate) sorted by count desc.
  --promote <id> --to <file.md> : appends a formatted block to the file (LEARNINGS.md style) and
            marks the candidate as promoted (a later --scan will not resurface it).

Usage:
    python instinct_promote.py --scan
    python instinct_promote.py --list
    python instinct_promote.py --promote inst-ab12cd --to LEARNINGS.md
    python instinct_promote.py --self-test

Exit: 0 ok - 2 invalid usage.
stdlib only. v1.0.0 — 2026-07-10 (Operator Kit · Tier 3 · operator-kit/evolve)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())


def _ledger_path() -> Path:
    return _PROJECT_ROOT / ".claude" / "handoff" / "HANDOFF-LEDGER.jsonl"


def _store_path() -> Path:
    return _PROJECT_ROOT / ".claude" / "evolve" / "instincts.jsonl"


def _signature(cmd: str) -> str:
    """Stable, short key per command that failed (same command = same candidate)."""
    return "inst-" + hashlib.sha256(cmd.strip().encode("utf-8")).hexdigest()[:10]


def _read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _load_store(store_path: Path) -> dict:
    """Returns {id: candidate} from the store (the last occurrence of each id wins)."""
    by_id = {}
    for row in _read_jsonl(store_path):
        cid = row.get("id")
        if cid:
            by_id[cid] = row
    return by_id


def _write_store(store_path: Path, by_id: dict) -> None:
    store_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(by_id[k], ensure_ascii=False) for k in sorted(by_id)]
    store_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _cursor_path(store_path: Path) -> Path:
    return store_path.with_suffix(store_path.suffix + ".cursor")


def _read_cursor(store_path: Path) -> int:
    p = _cursor_path(store_path)
    if not p.exists():
        return 0
    try:
        return int(p.read_text(encoding="utf-8").strip() or "0")
    except ValueError:
        return 0


def _write_cursor(store_path: Path, n: int) -> None:
    _cursor_path(store_path).parent.mkdir(parents=True, exist_ok=True)
    _cursor_path(store_path).write_text(str(n), encoding="utf-8")


def scan(ledger_path: Path, store_path: Path) -> dict:
    """Reads ONLY the new lines of the ledger (since the cursor) looking for gate-failed, groups
    by cmd and increments the count in the store. Idempotent: re-scan with no new line = no effect.
    Returns {"eventos_lidos": N, "candidatos_novos": N, "candidatos_atualizados": N}."""
    by_id = _load_store(store_path)
    events = 0
    new_candidates = 0
    updated_candidates = 0
    now = time.strftime("%Y-%m-%dT%H:%M:%S")

    all_lines = ledger_path.read_text(encoding="utf-8").splitlines() if ledger_path.exists() else []
    cursor = _read_cursor(store_path)
    new_lines = all_lines[cursor:]

    for raw in new_lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if row.get("event") != "gate-failed":
            continue
        events += 1
        for cmd in row.get("failed_cmds", []) or []:
            cid = _signature(cmd)
            if cid in by_id:
                if by_id[cid].get("status") == "promoted":
                    continue  # already promoted -- does not resurface
                by_id[cid]["count"] = by_id[cid].get("count", 1) + 1
                by_id[cid]["last_seen"] = now
                updated_candidates += 1
            else:
                by_id[cid] = {
                    "id": cid,
                    "cmd": cmd,
                    "count": 1,
                    "first_seen": now,
                    "last_seen": now,
                    "status": "candidate",
                }
                new_candidates += 1

    _write_store(store_path, by_id)
    _write_cursor(store_path, len(all_lines))
    return {"eventos_lidos": events, "candidatos_novos": new_candidates, "candidatos_atualizados": updated_candidates}


def list_candidates(store_path: Path) -> list:
    by_id = _load_store(store_path)
    cands = [c for c in by_id.values() if c.get("status") == "candidate"]
    return sorted(cands, key=lambda c: (-c.get("count", 0), c.get("id", "")))


def promote(store_path: Path, cid: str, to_path: Path) -> tuple[bool, str]:
    by_id = _load_store(store_path)
    cand = by_id.get(cid)
    if cand is None:
        return False, f"candidate {cid} not found"
    if cand.get("status") == "promoted":
        return False, f"candidate {cid} already promoted"

    entry = (
        f"\n### [{time.strftime('%Y-%m-%d')}] — instinct promoted ({cid})\n"
        f"**Command that failed {cand['count']}x:** `{cand['cmd']}`\n"
        f"**First seen:** {cand['first_seen']} · **last:** {cand['last_seen']}\n"
        f"**Suggested action:** review why this command keeps failing in /ralph-gate "
        f"and fix the root cause (or adjust the done criterion, if it is the one that is wrong).\n"
    )
    to_path.parent.mkdir(parents=True, exist_ok=True)
    with open(to_path, "a", encoding="utf-8") as f:
        f.write(entry)

    cand["status"] = "promoted"
    cand["promoted_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    cand["promoted_to"] = str(to_path)
    by_id[cid] = cand
    _write_store(store_path, by_id)
    return True, f"promoted to {to_path}"


def _self_test() -> int:
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="instinct_promote_selftest_"))
    try:
        ledger = tmp / ".claude" / "handoff" / "HANDOFF-LEDGER.jsonl"
        ledger.parent.mkdir(parents=True)
        store = tmp / ".claude" / "evolve" / "instincts.jsonl"

        events = [
            {"event": "gate-failed", "failed_cmds": ["python -m pytest -q"]},
            {"event": "gate-passed"},
            {"event": "gate-failed", "failed_cmds": ["python -m pytest -q", "python lint.py"]},
            {"event": "gate-failed", "failed_cmds": ["python -m pytest -q"]},
        ]
        ledger.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")

        r1 = scan(ledger, store)
        assert r1["eventos_lidos"] == 3, f"should count 3 gate-failed: {r1}"
        assert r1["candidatos_novos"] == 2, f"2 distinct commands should be new: {r1}"
        assert r1["candidatos_atualizados"] == 2, f"pytest seen 3x = 1 new + 2 updates (2nd and 3rd occurrence): {r1}"

        cands = list_candidates(store)
        assert len(cands) == 2, f"2 candidates expected: {cands}"
        top = cands[0]
        assert top["cmd"] == "python -m pytest -q" and top["count"] == 3, f"pytest should have count=3 (top): {top}"

        # re-scan with no new line (cursor already at the end) should not inflate the count or recount
        r2 = scan(ledger, store)
        assert r2 == {"eventos_lidos": 0, "candidatos_novos": 0, "candidatos_atualizados": 0}, \
            f"idempotent re-scan (cursor) should read zero new events: {r2}"
        cands_after_rescan = list_candidates(store)
        assert next(c for c in cands_after_rescan if c["id"] == top["id"])["count"] == 3, \
            "re-scan should not change the count (cursor prevents reprocessing a line already seen)"

        # promote
        to_file = tmp / "LEARNINGS.md"
        ok, msg = promote(store, top["id"], to_file)
        assert ok, msg
        text = to_file.read_text(encoding="utf-8")
        assert "python -m pytest -q" in text and "3x" in text, f"malformed entry: {text}"

        # a promoted candidate does not resurface in list nor in re-scan
        cands2 = list_candidates(store)
        assert all(c["id"] != top["id"] for c in cands2), "promoted candidate should not appear in --list"

        ledger.write_text(ledger.read_text(encoding="utf-8") + json.dumps(
            {"event": "gate-failed", "failed_cmds": ["python -m pytest -q"]}) + "\n", encoding="utf-8")
        scan(ledger, store)
        by_id = _load_store(store)
        assert by_id[top["id"]]["status"] == "promoted", "gate-failed after promotion should not reopen the candidate"

        # promote of a nonexistent id -> clean failure
        ok2, msg2 = promote(store, "inst-naoexiste", to_file)
        assert not ok2, "promote of a nonexistent id should fail"

        print("self-test OK — scan groups by cmd (confidence=count), list sorts by count, "
              "promote appends+marks promoted, promoted never resurfaces, re-scan is idempotent for repeated events")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="instinct_promote.py")
    p.add_argument("--scan", action="store_true")
    p.add_argument("--list", action="store_true")
    p.add_argument("--promote", metavar="ID")
    p.add_argument("--to", metavar="FILE", help="destination of --promote (e.g. LEARNINGS.md)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--self-test", action="store_true")
    return p


def main(argv) -> int:
    args = build_parser().parse_args(argv)
    if args.self_test:
        return _self_test()

    ledger_path = _ledger_path()
    store_path = _store_path()

    if args.scan:
        result = scan(ledger_path, store_path)
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else
              f"instinct_promote: {result['eventos_lidos']} events · "
              f"{result['candidatos_novos']} new candidates · {result['candidatos_atualizados']} updated")
        return 0

    if args.list:
        cands = list_candidates(store_path)
        if args.json:
            print(json.dumps(cands, ensure_ascii=False, indent=2))
        else:
            if not cands:
                print("instinct_promote: no pending candidates")
            for c in cands:
                print(f"  {c['id']}  count={c['count']:<3}  {c['cmd']}")
        return 0

    if args.promote:
        if not args.to:
            print("usage: instinct_promote.py --promote <id> --to <file.md>", file=sys.stderr)
            return 2
        ok, msg = promote(store_path, args.promote, Path(args.to))
        print(msg)
        return 0 if ok else 1

    print("usage: instinct_promote.py --scan | --list | --promote <id> --to <file> | --self-test", file=sys.stderr)
    return 2


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
