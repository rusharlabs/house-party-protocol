#!/usr/bin/env python3
"""
lane_effects — a decision and the effect of that decision are two facts, and they are tracked apart.

The board records that a reviewer said VERIFIED or NEEDS-FIX. It does not record whether the lane
that has to act on it was ever told. Collapse the two and you get both failures from one cause:

  * a restart NEVER notifies — the decision is written down, so it looks handled;
  * a retry notifies TWICE — nothing on disk says the effect already went out.

Two axes, never one:

    state         pending -> accepted     the DECISION (a reviewer said it, the board took it)
    effect_state  pending -> delivered    the EFFECT (the mailbox message, webhook, post went out)

And `reservation_id` — deterministic over (item, decision, target, effect, round) — is what makes a
retry RECONCILE instead of re-send. Reserving the same decision twice returns the SAME reservation.
Delivering twice is a no-op that keeps the FIRST `delivered_at` and the first evidence.

`pending_effects()` is the durable replacement for a watermark in a process variable: after a crash
it is still on disk, and it is exactly the list a restart has to work through.

Usage:
    python lane_effects.py reserve <item_id> <decision> --target <lane> [--effect mailbox] [--round K]
    python lane_effects.py accept  <reservation_id>
    python lane_effects.py deliver <reservation_id> [--evidence "<path or id>"]
    python lane_effects.py pending
    python lane_effects.py show <reservation_id>

Exit: 0 ok · 1 refused (unknown reservation, effect before acceptance) · 2 invalid usage.

stdlib only. Adapted from saltbo/agent-kanban (FSL-1.1-ALv2) — concept only, nothing copied.
v1.0.0 — 2026-09-22 (lane-kit)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
_LANES_DIR = _PROJECT_ROOT / ".claude" / "lanes"
EFFECTS_PATH = _LANES_DIR / "effects.json"

# Its own lock file: lane_board.py holds `.lock` while it validates a transition, and the board
# reserves an effect from inside that critical section.
_LOCK_NAME = ".effects.lock"
_LOCK_SPIN_SECONDS = 2.0

STATES = ("pending", "accepted")
EFFECT_STATES = ("pending", "delivered")


class LockError(Exception):
    pass


class _Lock:
    def __init__(self, lanes_dir: Path, timeout: float = _LOCK_SPIN_SECONDS):
        self.path = lanes_dir / _LOCK_NAME
        self.timeout = timeout
        self._acquired = False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                os.mkdir(self.path)
                self._acquired = True
                return self
            except FileExistsError:
                if time.monotonic() > deadline:
                    raise LockError(f"effects lock not acquired within {self.timeout}s: {self.path}")
                time.sleep(0.01)

    def __exit__(self, *exc):
        if self._acquired:
            try:
                os.rmdir(self.path)
            except OSError:
                pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def reservation_id(item_id: str, decision: str, target: str, effect: str = "mailbox",
                   round_key: str = "") -> str:
    """Deterministic and unique: the same decision to the same target is the same reservation.

    `round_key` is what separates a legitimately repeated decision (a second NEEDS-FIX after a new
    build) from a retry of the same one. Without it a second round would silently reconcile against
    the first and never be delivered.
    """
    raw = "|".join([item_id, decision, target, effect, round_key])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _read() -> dict:
    if not EFFECTS_PATH.exists():
        return {"schema_version": "1.0", "effects": {}}
    try:
        data = json.loads(EFFECTS_PATH.read_text(encoding="utf-8"))
    except ValueError:
        # A corrupt ledger must not take the caller down; it is rebuilt from the next reservation.
        return {"schema_version": "1.0", "effects": {}}
    data.setdefault("effects", {})
    return data


def _write(data: dict) -> None:
    EFFECTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = EFFECTS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, EFFECTS_PATH)


def reserve(item_id: str, decision: str, target: str, effect: str = "mailbox",
            round_key: str = "", payload: dict | None = None) -> tuple:
    """Reserve the effect of a decision. Idempotent: a retry returns the EXISTING reservation."""
    rid = reservation_id(item_id, decision, target, effect, round_key)
    try:
        with _Lock(_LANES_DIR):
            data = _read()
            existing = data["effects"].get(rid)
            if existing is not None:
                return True, dict(existing, reused=True)
            record = {
                "reservation_id": rid,
                "item_id": item_id,
                "decision": decision,
                "target": target,
                "effect": effect,
                "round_key": round_key,
                "state": "pending",
                "effect_state": "pending",
                "reserved_at": _now_iso(),
                "accepted_at": None,
                "delivered_at": None,
                "evidence": "",
                "payload": payload or {},
            }
            data["effects"][rid] = record
            _write(data)
            return True, dict(record, reused=False)
    except LockError as exc:
        return False, str(exc)


def accept(rid: str) -> tuple:
    """Mark the DECISION as taken. Says nothing about the effect. Idempotent."""
    try:
        with _Lock(_LANES_DIR):
            data = _read()
            record = data["effects"].get(rid)
            if record is None:
                return False, f"unknown reservation: {rid}"
            if record["state"] != "accepted":
                record["state"] = "accepted"
                record["accepted_at"] = _now_iso()
                _write(data)
            return True, dict(record)
    except LockError as exc:
        return False, str(exc)


def deliver(rid: str, evidence: str = "") -> tuple:
    """Mark the EFFECT as delivered. Refuses before acceptance; a second call never re-sends."""
    try:
        with _Lock(_LANES_DIR):
            data = _read()
            record = data["effects"].get(rid)
            if record is None:
                return False, f"unknown reservation: {rid}"
            if record["state"] != "accepted":
                return False, (f"refused: the decision was never accepted (state={record['state']}) — "
                               f"accept it before delivering its effect")
            if record["effect_state"] == "delivered":
                # The whole point: a retry reconciles. The first delivery stands.
                return True, dict(record, already=True)
            record["effect_state"] = "delivered"
            record["delivered_at"] = _now_iso()
            record["evidence"] = evidence
            _write(data)
            return True, dict(record, already=False)
    except LockError as exc:
        return False, str(exc)


def get(rid: str):
    return _read()["effects"].get(rid)


def all_effects() -> list:
    return sorted(_read()["effects"].values(), key=lambda r: (r["reserved_at"], r["reservation_id"]))


def pending_effects() -> list:
    """Everything decided and not yet delivered — what a restart has to work through."""
    return [r for r in all_effects() if r["effect_state"] != "delivered"]


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------

def _self_test() -> int:
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="lane_effects_selftest_"))
    global _PROJECT_ROOT, _LANES_DIR, EFFECTS_PATH
    orig = (_PROJECT_ROOT, _LANES_DIR, EFFECTS_PATH)
    try:
        _PROJECT_ROOT = tmp
        _LANES_DIR = tmp / ".claude" / "lanes"
        EFFECTS_PATH = _LANES_DIR / "effects.json"

        ok, rec = reserve("ITEM-1", "NEEDS-FIX", "exec-a")
        assert ok and rec["state"] == "pending" and rec["effect_state"] == "pending", rec
        assert rec["reused"] is False and rec["delivered_at"] is None, rec

        _, again = reserve("ITEM-1", "NEEDS-FIX", "exec-a")
        assert again["reservation_id"] == rec["reservation_id"] and again["reused"] is True, again
        assert len(all_effects()) == 1, "a retry must not create a second reservation"

        # CONTROL: a new round must NOT reconcile against the first one
        _, round2 = reserve("ITEM-1", "NEEDS-FIX", "exec-a", round_key="2")
        assert round2["reservation_id"] != rec["reservation_id"], "rounds collapsed into one reservation"
        assert len(all_effects()) == 2, all_effects()

        bad, why = deliver(rec["reservation_id"])
        assert bad is False and "accept" in why, f"an effect before acceptance must be refused: {why}"
        assert get(rec["reservation_id"])["effect_state"] == "pending", "it was delivered anyway"

        _, accepted = accept(rec["reservation_id"])
        assert accepted["state"] == "accepted" and accepted["effect_state"] == "pending", accepted
        first_accept = accepted["accepted_at"]
        _, accepted_again = accept(rec["reservation_id"])
        assert accepted_again["accepted_at"] == first_accept, "accept is not idempotent"

        ok1, delivered = deliver(rec["reservation_id"], evidence="mailbox/msg-1.md")
        assert ok1 and delivered["effect_state"] == "delivered" and delivered["delivered_at"], delivered
        ok2, twice = deliver(rec["reservation_id"], evidence="mailbox/msg-2.md")
        assert ok2 and twice["already"] is True, twice
        assert twice["delivered_at"] == delivered["delivered_at"], "delivered_at moved on a retry"
        assert twice["evidence"] == "mailbox/msg-1.md", "the first evidence was overwritten"

        assert [r["reservation_id"] for r in pending_effects()] == [round2["reservation_id"]], pending_effects()
        assert deliver("nope")[0] is False, "an unknown reservation must be refused"

        # a corrupt ledger degrades instead of taking the caller down
        EFFECTS_PATH.write_text("{not json", encoding="utf-8")
        assert pending_effects() == [], "a corrupt ledger should read as empty, not raise"
        assert reserve("ITEM-9", "VERIFIED", "exec-z")[0] is True, "a corrupt ledger should be rebuilt"

        print("self-test OK — both axes start pending, a retry reuses the reservation, a new round "
              "does not (control), effect before acceptance refused, delivering twice keeps the first "
              "delivered_at and evidence, pending_effects reads from disk, corrupt ledger degrades")
        return 0
    finally:
        _PROJECT_ROOT, _LANES_DIR, EFFECTS_PATH = orig
        shutil.rmtree(tmp, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lane_effects.py")
    sub = p.add_subparsers(dest="cmd")

    r = sub.add_parser("reserve")
    r.add_argument("item_id")
    r.add_argument("decision")
    r.add_argument("--target", required=True)
    r.add_argument("--effect", default="mailbox")
    r.add_argument("--round", dest="round_key", default="")

    a = sub.add_parser("accept")
    a.add_argument("reservation_id")

    d = sub.add_parser("deliver")
    d.add_argument("reservation_id")
    d.add_argument("--evidence", default="")

    sub.add_parser("pending")

    s = sub.add_parser("show")
    s.add_argument("reservation_id")

    p.add_argument("--self-test", action="store_true")
    return p


def main(argv) -> int:
    args = build_parser().parse_args(argv)
    if args.self_test:
        return _self_test()

    if args.cmd == "reserve":
        ok, result = reserve(args.item_id, args.decision, args.target, args.effect, args.round_key)
    elif args.cmd == "accept":
        ok, result = accept(args.reservation_id)
    elif args.cmd == "deliver":
        ok, result = deliver(args.reservation_id, evidence=args.evidence)
    elif args.cmd == "pending":
        print(json.dumps(pending_effects(), ensure_ascii=False, indent=2))
        return 0
    elif args.cmd == "show":
        record = get(args.reservation_id)
        if record is None:
            print(f"lane_effects: unknown reservation {args.reservation_id}", file=sys.stderr)
            return 1
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0
    else:
        print("usage: reserve|accept|deliver|pending|show [...], or --self-test", file=sys.stderr)
        return 2

    if ok:
        print(json.dumps(result, ensure_ascii=False))
        return 0
    print(f"lane_effects: {result}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
