#!/usr/bin/env python3
"""
_handoff_io -- single IO lib for the handoff (write/read/render/consume/validate).

Handoff = 1 JSON artifact per lane (`HANDOFF-CURRENT-<lane_id>.json`) + 1 append-only ledger
(`HANDOFF-LEDGER.jsonl`). Materializes LC-1 (every number carries `re_derive_cmd`) and LC-4 (every
next step carries `verify_first_cmd` -- "restored context is a reference, not a queue").

Usage:
    echo '{...}' | python _handoff_io.py write --stdin
    python _handoff_io.py write --demo --lane solo
    python _handoff_io.py read --lane solo
    python _handoff_io.py read --last 5
    python _handoff_io.py render --lane solo
    python _handoff_io.py consume <handoff_id> --session <id>
    python _handoff_io.py --self-test

Exit: 0 ok - 1 validation failed (secret detected, required field missing, invalid
schema) - 2 invalid usage. stdlib + optional PyYAML (unused; pure JSON here).

v1.0.0 -- 2026-07-10 (continuity-kit - Tier 1 - derives from the formal design +
         LOVABLE-PROD-REVIEW/.claude/hooks/{session_start,stop_state_guard}.py -- method, not data)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
_HANDOFF_DIR = _PROJECT_ROOT / ".claude" / "handoff"
LEDGER_PATH = _HANDOFF_DIR / "HANDOFF-LEDGER.jsonl"

_MAX_BYTES = 65536
_REQUIRED_TOP = ("schema_version", "handoff_id", "created_at", "trigger", "quality", "session", "state", "git", "valid_until")
# The ONE place the accepted schema version is written — and the cross-model checker was right
# that the claim was overstated before: the validator and its message read it, but three
# WRITERS still spelled "2.0" by hand, one of them the degraded-handoff path that fires when
# a session dies without /pre-clear. They read it now, so a bump cannot make write() produce
# what validate() rejects. v1.1 is absent on purpose: it had zero files anywhere when it was
# renamed, so a compatibility read would be dead code the day it was born.
_ACCEPTED_SCHEMA_VERSIONS = ("2.0",)

# Secret patterns -- same spirit as ip_pii_linter.py (kit-forge), local copy: each kit
# in this marketplace is self-contained (C5 SKILL-CONTRACT), no cross-kit import.
_SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"sk-proj-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"xox[bap]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"AIza[A-Za-z0-9_\-]{20,}"),
    re.compile(r"sbp_[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*[\"'][A-Za-z0-9_\-]{16,}[\"']"),
]


def _now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%dT%H:%M:%S-03:00")


def _git(args: list) -> str:
    try:
        r = subprocess.run(["git", "-C", str(_PROJECT_ROOT)] + args, capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def git_block(checkpoint_ref: str = "", checkpoint_commit: str = "") -> dict:
    """The git evidence of the handoff. `checkpoint_*` name the turn checkpoint when one was taken.

    Why the checkpoint belongs here (turn_checkpoint.py): `porcelain` and every number derived
    from it read the index, and a shared index reports edits that did not happen and misses ones
    that did. The checkpoint ref is a content-addressed object — it is the half of this block
    that stays true regardless.
    """
    head = _git(["rev-parse", "--short", "HEAD"])
    branch = _git(["branch", "--show-current"])
    porcelain = _git(["status", "--porcelain"])
    untracked = sum(1 for ln in porcelain.splitlines() if ln.startswith("??"))
    block = {"head": head, "branch": branch, "dirty": bool(porcelain.strip()), "untracked": untracked, "porcelain": porcelain[:4000]}
    if checkpoint_ref:
        block["checkpoint_ref"] = checkpoint_ref
    if checkpoint_commit:
        block["checkpoint_commit"] = checkpoint_commit
    return block


def scan_secrets(text: str) -> list:
    hits = []
    for pat in _SECRET_PATTERNS:
        for m in pat.finditer(text):
            hits.append(m.group(0)[:8] + "...")
    return hits


def validate(data: dict) -> list:
    """Returns list of errors (empty = valid). LC-1/LC-4 rules built into the contract."""
    errors = []
    for field in _REQUIRED_TOP:
        if field not in data:
            errors.append(f"required field missing: {field}")
    if data.get("schema_version") not in _ACCEPTED_SCHEMA_VERSIONS:
        # Why: the check and the message used to be spelled separately, and the 2.0 rename
        # moved only the check — the message kept telling the reader to write '1.1', which
        # this very line then rejected. Deriving it means they cannot disagree again.
        wanted = " or ".join(repr(v) for v in _ACCEPTED_SCHEMA_VERSIONS)
        errors.append(f"schema_version must be {wanted} (got: {data.get('schema_version')!r})")

    session = data.get("session", {}) or {}
    if not session.get("session_id"):
        errors.append("session.session_id missing")
    if not session.get("lane_id"):
        errors.append("session.lane_id missing (default 'solo' when there is no lane)")

    git = data.get("git", {}) or {}
    for f in ("head", "branch", "dirty", "untracked"):
        if f not in git:
            errors.append(f"git.{f} missing (the git block is required — v1.1)")
    if data.get("quality") == "degraded-auto" and "porcelain" not in git:
        errors.append("quality=degraded-auto requires git.porcelain (v1.1 fix) — even when empty (clean tree), the KEY must exist")

    state = data.get("state", {}) or {}
    if not state.get("summary"):
        errors.append("state.summary missing")
    for i, n in enumerate(state.get("numbers", []) or []):
        if not n.get("re_derive_cmd"):
            errors.append(f"state.numbers[{i}] without re_derive_cmd (LC-1: every number needs a re-derivation command)")

    for i, p in enumerate(data.get("next_step", []) or []):
        if not p.get("verify_first_cmd"):
            errors.append(f"next_step[{i}] without verify_first_cmd (LC-4: next step without an idempotency check)")

    text_dump = json.dumps(data, ensure_ascii=False)
    secrets = scan_secrets(text_dump)
    if secrets:
        errors.append(f"secret detected in handoff ({len(secrets)} match(es), redacted: {secrets[:3]}) — REJECTED (no-secrets-in-memory)")

    size = len(text_dump.encode("utf-8"))
    if size > _MAX_BYTES:
        errors.append(f"handoff exceeds max_bytes ({size} > {_MAX_BYTES})")

    if not data.get("valid_until"):
        errors.append("valid_until missing")

    return errors


def append_ledger(event: str, handoff_id: str, lane_id: str = "solo", by_session: str = "", **details) -> None:
    _HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    entry = {"ts": _now_iso(), "event": event, "handoff_id": handoff_id, "lane_id": lane_id, "by_session": by_session, "details": details}
    with open(LEDGER_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def current_path(lane_id: str) -> Path:
    return _HANDOFF_DIR / f"HANDOFF-CURRENT-{lane_id}.json"


def write(data: dict) -> tuple:
    """Validates and writes atomically. Returns (ok, errors_or_path)."""
    errors = validate(data)
    if errors:
        return False, errors

    lane_id = data["session"]["lane_id"]
    _HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    target = current_path(lane_id)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, target)

    append_ledger("written", data["handoff_id"], lane_id=lane_id, by_session=data["session"].get("session_id", ""))
    return True, str(target)


def newest_handoff(lane_id: str | None = None) -> dict | None:
    if not _HANDOFF_DIR.is_dir():
        return None
    if lane_id:
        p = current_path(lane_id)
        candidates = [p] if p.exists() else []
    else:
        candidates = sorted(_HANDOFF_DIR.glob("HANDOFF-CURRENT-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in candidates:
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
    return None


def is_stale(h: dict) -> tuple:
    """(stale, reason). Checks valid_until AND stale_when.head_moved (v1.1 fix)."""
    valid_until = h.get("valid_until")
    if valid_until:
        try:
            vu = datetime.fromisoformat(valid_until)
            if datetime.now(vu.tzinfo or timezone.utc) > vu:
                return True, "valid_until expired"
        except ValueError:
            pass
    written_head = (h.get("git") or {}).get("head")
    current_head = _git(["rev-parse", "--short", "HEAD"])
    if written_head and current_head and written_head != current_head:
        return True, f"HEAD moved (was {written_head}, now {current_head}) — stale_when.head_moved"
    return False, ""


def render(h: dict, cap_bytes: int = 4096) -> str:
    stale, reason = is_stale(h)
    lines = ["⚠️ RESTORED CONTEXT = HISTORICAL REFERENCE, NOT A QUEUE (LC-4)"]
    lines.append(f"HANDOFF {h.get('handoff_id')} · {h.get('quality')} · lane={h.get('session', {}).get('lane_id')}")
    if stale:
        lines.append(f"⚠️ STALE ({reason}) — re-derive everything via re_derive_cmd; next_step is NOT actionable.")
    else:
        state = h.get("state", {})
        lines.append(f"STATE: {state.get('summary', '')}")
        for n in state.get("numbers", []) or []:
            lines.append(f"  · {n['metric']}={n['value']} (re-derive: {n['re_derive_cmd']})")
        ja = h.get("already_done", []) or []
        if ja:
            lines.append("ALREADY EXECUTED — NEVER REPEAT: " + "; ".join(j["action"] for j in ja))
        gates = h.get("open_gates", []) or []
        if gates:
            lines.append("OPEN GATES: " + "; ".join(g["description"] for g in gates))
        proib = h.get("prohibitions", []) or []
        if proib:
            lines.append("PROHIBITIONS: " + "; ".join(proib))
        passos = sorted(h.get("next_step", []) or [], key=lambda p: p.get("order", 0))
        if passos:
            p0 = passos[0]
            lines.append(f"NEXT STEP {p0.get('order')}: {p0.get('description')}")
            lines.append(f"  → BEFORE EXECUTING, RUN: {p0.get('verify_first_cmd')} (if already done: skip and record it)")
    lines.append(f"Full file: {current_path(h.get('session', {}).get('lane_id', 'solo'))}")
    text = "\n".join(lines)
    return text[:cap_bytes]


def consume(handoff_id: str, session_id: str, lane_id: str = "solo") -> None:
    append_ledger("consumed", handoff_id, lane_id=lane_id, by_session=session_id)


def degraded_auto_aggregate(lane_id: str = "solo", session_id: str = "",
                            checkpoint_ref: str = "", checkpoint_commit: str = "") -> dict:
    """Fallback for when the session dies without /pre-clear (used by handoff_guard.py)."""
    now = _now_iso()
    ts_id = datetime.now().strftime("%Y%m%d-%H%M")
    log = _git(["log", "--oneline", "-5"])
    return {
        "schema_version": _ACCEPTED_SCHEMA_VERSIONS[0],
        "handoff_id": f"HO-{ts_id}-{lane_id}",
        "created_at": now,
        "trigger": "degraded-auto",
        "quality": "degraded-auto",
        "session": {"session_id": session_id, "lane_id": lane_id},
        "state": {"summary": "Session ended without /pre-clear — degraded handoff, automatic aggregation.", "numbers": []},
        "git": git_block(checkpoint_ref=checkpoint_ref, checkpoint_commit=checkpoint_commit),
        "already_done": [],
        "next_step": [],
        "open_gates": [],
        "prohibitions": ["NEVER treat this degraded handoff as full coverage — reconfirm everything at the live source (LC-1)."],
        "evidence": [{"type": "cmd", "ref": "git log --oneline -5", "value": log}],
        "valid_until": (datetime.now(timezone(timedelta(hours=-3))) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S-03:00"),
        "boot_docs": [],
    }


def _demo_handoff(lane_id: str = "solo") -> dict:
    now = _now_iso()
    ts_id = datetime.now().strftime("%Y%m%d-%H%M")
    return {
        "schema_version": _ACCEPTED_SCHEMA_VERSIONS[0],
        "handoff_id": f"HO-{ts_id}-{lane_id}",
        "created_at": now,
        "trigger": "manual",
        "quality": "full",
        "session": {"session_id": "demo-session", "lane_id": lane_id, "role": "solo"},
        "state": {
            "summary": "Demo handoff generated by --demo.",
            "numbers": [{"metric": "example", "value": "1", "measured_at": now, "re_derive_cmd": "echo 1"}],
        },
        "git": git_block(),
        "already_done": [{"action": "generated the demo", "evidence": "this very file", "never_repeat": True}],
        "next_step": [{"order": 1, "description": "nothing — it is a demo", "verify_first_cmd": "echo verified"}],
        "open_gates": [],
        "prohibitions": [],
        "valid_until": (datetime.now(timezone(timedelta(hours=-3))) + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S-03:00"),
        "boot_docs": [],
    }


def _self_test() -> int:
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="handoff_io_selftest_"))
    global _HANDOFF_DIR, LEDGER_PATH, _PROJECT_ROOT
    orig_dir, orig_ledger, orig_root = _HANDOFF_DIR, LEDGER_PATH, _PROJECT_ROOT
    try:
        _PROJECT_ROOT = tmp
        _HANDOFF_DIR = tmp / ".claude" / "handoff"
        LEDGER_PATH = _HANDOFF_DIR / "HANDOFF-LEDGER.jsonl"

        good = {
            "schema_version": _ACCEPTED_SCHEMA_VERSIONS[0], "handoff_id": "HO-20260710-1500-solo",
            "created_at": "2026-07-10T15:00:00-03:00", "trigger": "manual", "quality": "full",
            "session": {"session_id": "s1", "lane_id": "solo"},
            "state": {"summary": "test", "numbers": [{"metric": "x", "value": "1", "measured_at": "2026-07-10T15:00:00-03:00", "re_derive_cmd": "echo 1"}]},
            "git": {"head": "abc123", "branch": "main", "dirty": False, "untracked": 0},
            "next_step": [{"order": 1, "description": "do x", "verify_first_cmd": "test -f x"}],
            "valid_until": "2099-01-01T00:00:00-03:00",
        }
        ok, result = write(good)
        assert ok, f"a valid handoff should be written: {result}"
        assert current_path("solo").exists(), "file was not created"

        ledger_lines = LEDGER_PATH.read_text(encoding="utf-8").splitlines()
        assert any(json.loads(l)["event"] == "written" for l in ledger_lines), "ledger has no written event"

        no_verify = dict(good, handoff_id="HO-20260710-1501-solo", next_step=[{"order": 1, "description": "no verify"}])
        ok2, errs2 = write(no_verify)
        assert not ok2 and any("verify_first_cmd" in e for e in errs2), f"should reject without verify_first_cmd: {errs2}"

        no_derive = dict(good, handoff_id="HO-20260710-1502-solo", state={"summary": "x", "numbers": [{"metric": "y", "value": "2", "measured_at": "2026-07-10T15:00:00-03:00"}]})
        ok3, errs3 = write(no_derive)
        assert not ok3 and any("re_derive_cmd" in e for e in errs3), f"should reject without re_derive_cmd: {errs3}"

        with_secret = dict(good, handoff_id="HO-20260710-1503-solo", state={"summary": "token = \"sk-ant-1234567890abcdef1234\"", "numbers": []})
        ok4, errs4 = write(with_secret)
        assert not ok4 and any("secret" in e for e in errs4), f"should reject with a secret: {errs4}"

        degraded_no_porcelain = dict(good, handoff_id="HO-20260710-1504-solo", quality="degraded-auto")
        ok5, errs5 = write(degraded_no_porcelain)
        assert not ok5 and any("porcelain" in e for e in errs5), f"degraded-auto without porcelain should fail: {errs5}"

        h = newest_handoff("solo")
        assert h is not None and h["handoff_id"] == "HO-20260710-1500-solo"

        text = render(h)
        assert "LC-4" in text and "NEXT STEP" in text, f"incomplete render: {text}"

        stale_h = dict(good, valid_until="2020-01-01T00:00:00-03:00")
        stale, reason = is_stale(stale_h)
        assert stale and "expired" in reason

        consume(h["handoff_id"], "session-x", "solo")
        ledger_lines2 = LEDGER_PATH.read_text(encoding="utf-8").splitlines()
        assert any(json.loads(l)["event"] == "consumed" for l in ledger_lines2), "ledger has no consumed event"

        degraded = degraded_auto_aggregate("solo", "s2")
        okd, resd = write(degraded)
        assert okd, f"degraded_auto_aggregate should be valid: {resd}"

        print("self-test OK — valid write+ledger, rejects without verify_first_cmd, rejects without re_derive_cmd, "
              "rejects secret, rejects degraded-auto without porcelain, render with LC-4, staleness, consume, degraded-auto")
        return 0
    finally:
        _HANDOFF_DIR, LEDGER_PATH, _PROJECT_ROOT = orig_dir, orig_ledger, orig_root
        shutil.rmtree(tmp, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="_handoff_io.py")
    sub = p.add_subparsers(dest="cmd")

    w = sub.add_parser("write")
    w.add_argument("--stdin", action="store_true")
    w.add_argument("--demo", action="store_true")
    w.add_argument("--lane", default="solo")

    r = sub.add_parser("read")
    r.add_argument("--lane", default=None)
    r.add_argument("--last", type=int, default=None)

    ren = sub.add_parser("render")
    ren.add_argument("--lane", default="solo")

    c = sub.add_parser("consume")
    c.add_argument("handoff_id")
    c.add_argument("--session", default="")
    c.add_argument("--lane", default="solo")

    p.add_argument("--self-test", action="store_true")
    return p


def main(argv) -> int:
    args = build_parser().parse_args(argv)

    if args.self_test:
        return _self_test()

    if args.cmd == "write":
        if args.demo:
            data = _demo_handoff(args.lane)
        elif args.stdin:
            try:
                data = json.loads(sys.stdin.read())
            except Exception as e:  # noqa: BLE001
                print(f"_handoff_io: invalid JSON on stdin: {e}", file=sys.stderr)
                return 2
        else:
            print("usage: write --stdin | write --demo [--lane X]", file=sys.stderr)
            return 2
        ok, result = write(data)
        if ok:
            print(f"_handoff_io: written to {result}")
            return 0
        for e in result:
            print(f"  [REJECTED] {e}", file=sys.stderr)
        return 1

    if args.cmd == "read":
        if args.last:
            if not LEDGER_PATH.exists():
                print("[]")
                return 0
            lines = LEDGER_PATH.read_text(encoding="utf-8").splitlines()[-args.last:]
            print(json.dumps([json.loads(l) for l in lines], ensure_ascii=False, indent=2))
            return 0
        h = newest_handoff(args.lane)
        print(json.dumps(h, ensure_ascii=False, indent=2) if h else "null")
        return 0

    if args.cmd == "render":
        h = newest_handoff(args.lane)
        if not h:
            print("_handoff_io: no handoff found", file=sys.stderr)
            return 1
        print(render(h))
        return 0

    if args.cmd == "consume":
        consume(args.handoff_id, args.session, args.lane)
        print(f"_handoff_io: consumed recorded for {args.handoff_id}")
        return 0

    print("usage: write|read|render|consume [...] or --self-test", file=sys.stderr)
    return 2


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
