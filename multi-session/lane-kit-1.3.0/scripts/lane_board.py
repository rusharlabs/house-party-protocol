#!/usr/bin/env python3
"""
lane_board -- whiteboard with a state machine for N sessions (lanes) without collision.

Sole writer of board.jsonl (append-only, per-directory lock). Enforcement IN CODE
(not textual discipline): CHECKPOINT-READY only by whoever claimed it + evidence; VERIFIED/NEEDS-FIX
only by a reviewer from ANOTHER lane AND ANOTHER model family than the builder (maker!=checker); an
unavailable checker -> only DEFERRED; MERGED requires a prior VERIFIED (+ human gate for red items, via
--tag red requiring --human-approved).

States: CLAIMED -> BUILDING -> CHECKPOINT-READY -> UNDER-REVIEW -> VERIFIED|NEEDS-FIX -> MERGED
                                                                  -> DEFERRED (checker unavailable)

Usage:
    python lane_board.py claim <item_id> --lane <id> --role <role> --model <model> [--tag green|red]
    python lane_board.py --set <item_id> <state> --lane <id> --role <role> --model <model>
                          [--evidence "..."] [--verdict-by-lane <id>] [--verdict-by-model <m>]
                          [--checker-indisponivel] [--human-approved]
    python lane_board.py status [<item_id>]
    python lane_board.py render
    python lane_board.py --self-test

Exit: 0 ok - 1 invalid transition/enforcement refused - 2 invalid usage/lock not acquired.
stdlib only. v1.0.0 -- 2026-07-10 (lane-kit)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import lane_effects  # noqa: E402 — same kit, same directory
except ImportError:  # pragma: no cover — a partial copy install still runs the board
    lane_effects = None  # type: ignore[assignment]

_PROJECT_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
_LANES_DIR = _PROJECT_ROOT / ".claude" / "lanes"
BOARD_PATH = _LANES_DIR / "board.jsonl"

# A verdict is a DECISION that owes somebody an EFFECT: the lane that built the item has to be
# told. `lane_effects.py` holds the two apart, so a restart does not skip the telling and a retry
# does not tell twice.
_VERDICTS_WITH_EFFECT = ("VERIFIED", "NEEDS-FIX", "DEFERRED")
RENDER_PATH = _PROJECT_ROOT / "docs" / "plans" / "execution" / "LANE-BOARD.md"
# Why: the generated directory was renamed to English. A repo that already holds the old
# spelling keeps receiving the board there for one version, instead of getting a second
# directory alongside it — the notice on stderr says which one was used.
_LEGACY_RENDER_DIR = ("docs", "plans", "execucao")

_LOCK_SPIN_SECONDS = 2.0

_TRANSITIONS = {
    None: {"CLAIMED"},
    "CLAIMED": {"BUILDING", "CLAIMED"},
    "BUILDING": {"CHECKPOINT-READY", "BUILDING"},
    "CHECKPOINT-READY": {"UNDER-REVIEW"},
    "UNDER-REVIEW": {"VERIFIED", "NEEDS-FIX", "DEFERRED"},
    "NEEDS-FIX": {"BUILDING"},
    "VERIFIED": {"MERGED"},
    "DEFERRED": {"UNDER-REVIEW"},
    "MERGED": set(),
}


class LockError(Exception):
    pass


class _Lock:
    def __init__(self, lanes_dir: Path, timeout: float = _LOCK_SPIN_SECONDS):
        self.path = lanes_dir / ".lock"
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
                    raise LockError(f"lock not acquired within {self.timeout}s: {self.path}")
                time.sleep(0.01)

    def __exit__(self, *exc):
        if self._acquired:
            try:
                os.rmdir(self.path)
            except OSError:
                pass


def _model_family(model: str) -> str:
    """Extracts the family from a model id (heuristic): 'claude-opus-4-8' -> 'claude'."""
    if not model:
        return ""
    m = re.match(r"^([a-zA-Z]+)", model)
    return m.group(1).lower() if m else model.lower()


def _read_events(item_id: str | None = None) -> list:
    if not BOARD_PATH.exists():
        return []
    events = []
    for line in BOARD_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue  # corrupted line (should never happen with the lock) -- ignore, do not crash
        if item_id is None or e.get("item_id") == item_id:
            events.append(e)
    return events


def _latest_state(item_id: str) -> dict | None:
    events = _read_events(item_id)
    return events[-1] if events else None


def _append_event(event: dict) -> None:
    BOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BOARD_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _validate_transition(item_id: str, new_state: str, lane_id: str, role: str, model: str,
                          evidence: str = "", verdict_by_lane: str = "", verdict_by_model: str = "",
                          checker_indisponivel: bool = False, human_approved: bool = False, tag: str = "green") -> str | None:
    """Returns None if valid, or the error message."""
    current = _latest_state(item_id)
    cur_state = current["state"] if current else None

    allowed = _TRANSITIONS.get(cur_state, set())
    if new_state not in allowed:
        return f"invalid transition: {cur_state} -> {new_state} (allowed: {sorted(allowed)})"

    if new_state == "CLAIMED" and current and cur_state not in (None,):
        if cur_state in ("MERGED",):
            return "item already MERGED — cannot be reopened with CLAIMED"

    if new_state == "CHECKPOINT-READY":
        builder = current  # the most recent BUILDING/CLAIMED event is the "owner"
        if role != "executor":
            return f"CHECKPOINT-READY only with role=executor (got: {role})"
        if not builder or builder.get("lane_id") != lane_id:
            return f"CHECKPOINT-READY only from the lane that claimed the item (owner: {builder.get('lane_id') if builder else '?'}, got: {lane_id})"
        if not evidence:
            return "CHECKPOINT-READY requires non-empty evidence (pasted hash/exit code, never 'I ran it')"

    if new_state in ("VERIFIED", "NEEDS-FIX"):
        if role != "reviewer":
            return f"{new_state} only with role=reviewer (got: {role})"
        # find the original builder (CLAIMED event)
        claimed = next((e for e in reversed(_read_events(item_id)) if e["state"] == "CLAIMED"), None)
        builder_lane = claimed.get("lane_id") if claimed else None
        builder_model = claimed.get("model") if claimed else None
        if checker_indisponivel:
            return f"checker unavailable — only DEFERRED is accepted, not {new_state}"
        if verdict_by_lane == builder_lane:
            return f"maker≠checker violated: reviewer ({verdict_by_lane}) is the SAME lane as the builder ({builder_lane})"
        if _model_family(verdict_by_model) == _model_family(builder_model):
            return f"maker≠checker violated: reviewer and builder are from the SAME model family ({_model_family(verdict_by_model)})"

    if new_state == "DEFERRED" and not checker_indisponivel:
        return "DEFERRED only with --checker-indisponivel"

    if new_state == "MERGED":
        verified = next((e for e in reversed(_read_events(item_id)) if e["state"] == "VERIFIED"), None)
        if not verified:
            return "MERGED requires a previous VERIFIED in the item history"
        if tag == "red" and not human_approved:
            return "item 🔴 (tag=red) requires --human-approved for MERGED (human gate)"

    return None


def _reserve_effect(item_id: str, new_state: str) -> str:
    """Reserve the outward effect this verdict owes the builder lane. Returns the reservation id.

    The decision is ACCEPTED here (the board took it) and the effect stays PENDING — telling the
    lane is somebody else's call, and `lane_effects.py pending` is what a restart reads instead of
    a watermark it no longer has. The `round_key` is the number of prior events for this item, so a
    second NEEDS-FIX after a new build is a NEW reservation while a retried write reconciles.
    """
    if lane_effects is None or new_state not in _VERDICTS_WITH_EFFECT:
        return ""
    events = _read_events(item_id)
    claimed = next((e for e in reversed(events) if e["state"] == "CLAIMED"), None)
    target = (claimed or {}).get("lane_id", "")
    if not target:
        return ""
    round_key = str(sum(1 for e in events if e["state"] in _VERDICTS_WITH_EFFECT))
    try:
        ok, record = lane_effects.reserve(item_id, new_state, target, round_key=round_key)
        if not ok:
            return ""
        lane_effects.accept(record["reservation_id"])
        return record["reservation_id"]
    except Exception:  # noqa: BLE001 -- Why: the VERDICT is the primary record and the effect ledger is
        # derived from it; a locked or corrupt ledger must degrade to "no reservation id on this
        # event" — losing the verdict to save the ledger would invert what is evidence of what.
        return ""


def set_state(item_id: str, new_state: str, lane_id: str, role: str, model: str, **kwargs) -> tuple:
    """Returns (ok, message_or_error). Writes under lock."""
    try:
        with _Lock(_LANES_DIR):
            err = _validate_transition(item_id, new_state, lane_id, role, model, **kwargs)
            if err:
                return False, err
            event = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "item_id": item_id,
                "state": new_state,
                "lane_id": lane_id,
                "role": role,
                "model": model,
            }
            if kwargs.get("evidence"):
                event["evidence"] = kwargs["evidence"]
            if kwargs.get("verdict_by_lane"):
                event["verdict_by"] = {"lane": kwargs["verdict_by_lane"], "model": kwargs.get("verdict_by_model", "")}
            if kwargs.get("tag"):
                event["tag"] = kwargs["tag"]
            reservation = _reserve_effect(item_id, new_state)
            if reservation:
                event["reservation_id"] = reservation
            _append_event(event)
            return True, event
    except LockError as e:
        return False, str(e)


def _render_target() -> Path:
    """Dual write for one version: the English path wins; a repo that only has the legacy
    directory keeps its board there, with a deprecation notice on stderr."""
    legacy = _PROJECT_ROOT.joinpath(*_LEGACY_RENDER_DIR, RENDER_PATH.name)
    if RENDER_PATH.exists():
        # Why (adversarial review of 2.5.0): with a half-done manual rename BOTH boards can exist —
        # the English one wins, and the stale legacy board sits there looking current to whoever
        # opens it. The new one is still the answer; saying the old one is stale is the whole fix.
        if legacy.exists():
            print(f"[lane_board] stale board left behind: '{legacy}' is no longer written — "
                  f"delete it; the current board is '{RENDER_PATH}'.", file=sys.stderr)
        return RENDER_PATH
    if legacy.parent.is_dir() and not RENDER_PATH.parent.is_dir():
        print(
            f"[lane_board] deprecated: wrote '{'/'.join(_LEGACY_RENDER_DIR)}/{RENDER_PATH.name}'; "
            f"rename that directory to 'execution' — the old spelling is accepted for one version only.",
            file=sys.stderr,
        )
        return legacy
    return RENDER_PATH


def render() -> str:
    items: dict = {}
    for e in _read_events():
        items.setdefault(e["item_id"], []).append(e)
    lines = ["# LANE-BOARD.md (generated by lane_board.py render — do not edit by hand)", ""]
    for item_id, events in sorted(items.items()):
        last = events[-1]
        lines.append(f"## {item_id} — {last['state']}")
        for e in events:
            evid = f" · evidence: {e['evidence']}" if e.get("evidence") else ""
            verdict = f" · verdict_by: {e['verdict_by']}" if e.get("verdict_by") else ""
            lines.append(f"- {e['ts']} · {e['state']} · lane={e['lane_id']} role={e['role']}{evid}{verdict}")
        lines.append("")
    outstanding = []
    if lane_effects is not None:
        try:
            outstanding = lane_effects.pending_effects()
        except Exception:  # noqa: BLE001 -- Why: render() is a read path used by humans mid-incident; an
            # unreadable ledger must show an empty UNDELIVERED block, not a traceback in place of
            # the board.
            outstanding = []
    if outstanding:
        lines.append("## UNDELIVERED effects (decided, nobody was told yet)")
        for record in outstanding:
            lines.append(f"- {record['reservation_id']} · {record['item_id']} · {record['decision']} "
                          f"-> {record['target']} · state={record['state']} effect={record['effect_state']}")
        lines.append("")
    return "\n".join(lines)


def _self_test() -> int:
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="lane_board_selftest_"))
    global _PROJECT_ROOT, _LANES_DIR, BOARD_PATH, RENDER_PATH
    orig = (_PROJECT_ROOT, _LANES_DIR, BOARD_PATH, RENDER_PATH)
    orig_fx = None
    if lane_effects is not None:
        orig_fx = (lane_effects._PROJECT_ROOT, lane_effects._LANES_DIR, lane_effects.EFFECTS_PATH)
    try:
        _PROJECT_ROOT = tmp
        _LANES_DIR = tmp / ".claude" / "lanes"
        BOARD_PATH = _LANES_DIR / "board.jsonl"
        RENDER_PATH = tmp / "LANE-BOARD.md"
        if lane_effects is not None:
            lane_effects._PROJECT_ROOT = tmp
            lane_effects._LANES_DIR = _LANES_DIR
            lane_effects.EFFECTS_PATH = _LANES_DIR / "effects.json"

        ok1, r1 = set_state("ITEM-1", "CLAIMED", "exec-a", "executor", "claude-opus-4-8")
        assert ok1, f"CLAIMED should pass: {r1}"

        ok2, r2 = set_state("ITEM-1", "BUILDING", "exec-a", "executor", "claude-opus-4-8")
        assert ok2, f"BUILDING should pass: {r2}"

        ok3, r3 = set_state("ITEM-1", "CHECKPOINT-READY", "exec-b", "executor", "claude-opus-4-8", evidence="exit=0")
        assert not ok3 and "owner" in r3, f"CHECKPOINT-READY from the wrong lane should be refused: {r3}"

        ok4, r4 = set_state("ITEM-1", "CHECKPOINT-READY", "exec-a", "executor", "claude-opus-4-8")
        assert not ok4 and "evidence" in r4, f"CHECKPOINT-READY without evidence should be refused: {r4}"

        ok5, r5 = set_state("ITEM-1", "CHECKPOINT-READY", "exec-a", "executor", "claude-opus-4-8", evidence="exit=0 sha=abc")
        assert ok5, f"a valid CHECKPOINT-READY should pass: {r5}"

        ok6, r6 = set_state("ITEM-1", "UNDER-REVIEW", "exec-a", "executor", "claude-opus-4-8")
        assert ok6, f"UNDER-REVIEW should pass: {r6}"

        ok7, r7 = set_state("ITEM-1", "VERIFIED", "exec-a", "reviewer", "claude-opus-4-8", verdict_by_lane="exec-a", verdict_by_model="claude-opus-4-8")
        assert not ok7 and "SAME lane" in r7, f"maker=checker (same lane) should be refused: {r7}"

        ok8, r8 = set_state("ITEM-1", "VERIFIED", "exec-a", "reviewer", "claude-opus-4-8", verdict_by_lane="rev-a", verdict_by_model="claude-opus-4-8")
        assert not ok8 and "SAME model family" in r8, f"maker=checker (same model family) should be refused: {r8}"

        ok9, r9 = set_state("ITEM-1", "VERIFIED", "exec-a", "reviewer", "claude-opus-4-8", verdict_by_lane="rev-a", verdict_by_model="gpt-5.6")
        assert ok9, f"a reviewer on another lane + another family should pass: {r9}"

        # the verdict owes an effect: decided (accepted) and NOT yet delivered
        if lane_effects is not None:
            rid = r9.get("reservation_id")
            assert rid, f"a verdict must reserve an effect: {r9}"
            fx = lane_effects.get(rid)
            assert fx["state"] == "accepted" and fx["effect_state"] == "pending", fx
            assert fx["target"] == "exec-a", f"the effect must aim at the builder lane: {fx}"
            assert [r["item_id"] for r in lane_effects.pending_effects()] == ["ITEM-1"], lane_effects.pending_effects()
            lane_effects.deliver(rid, evidence="mailbox/proof.md")
            assert lane_effects.pending_effects() == [], "delivering did not clear the outstanding list"

        ok10, r10 = set_state("ITEM-1", "MERGED", "rev-a", "reviewer", "gpt-5.6")
        assert ok10, f"MERGED after VERIFIED (default green tag) should pass: {r10}"

        ok11, r11 = set_state("ITEM-2", "CLAIMED", "exec-a", "executor", "claude-opus-4-8", tag="red")
        set_state("ITEM-2", "BUILDING", "exec-a", "executor", "claude-opus-4-8")
        set_state("ITEM-2", "CHECKPOINT-READY", "exec-a", "executor", "claude-opus-4-8", evidence="exit=0")
        set_state("ITEM-2", "UNDER-REVIEW", "exec-a", "executor", "claude-opus-4-8")
        set_state("ITEM-2", "VERIFIED", "exec-a", "reviewer", "gpt-5.6", verdict_by_lane="rev-a", verdict_by_model="gpt-5.6")
        ok12, r12 = set_state("ITEM-2", "MERGED", "rev-a", "reviewer", "gpt-5.6", tag="red")
        assert not ok12 and "human gate" in r12, f"a red item without --human-approved should be refused MERGED: {r12}"
        ok13, r13 = set_state("ITEM-2", "MERGED", "rev-a", "reviewer", "gpt-5.6", tag="red", human_approved=True)
        assert ok13, f"a red item with --human-approved should pass: {r13}"

        ok14, r14 = set_state("ITEM-3", "CLAIMED", "exec-a", "executor", "claude-opus-4-8")
        set_state("ITEM-3", "BUILDING", "exec-a", "executor", "claude-opus-4-8")
        set_state("ITEM-3", "CHECKPOINT-READY", "exec-a", "executor", "claude-opus-4-8", evidence="x")
        set_state("ITEM-3", "UNDER-REVIEW", "exec-a", "executor", "claude-opus-4-8")
        ok15, r15 = set_state("ITEM-3", "VERIFIED", "exec-a", "reviewer", "claude-opus-4-8", checker_indisponivel=True, verdict_by_lane="rev-a", verdict_by_model="gpt-5.6")
        assert not ok15 and "DEFERRED" in r15, f"an unavailable checker only accepts DEFERRED: {r15}"
        ok16, r16 = set_state("ITEM-3", "DEFERRED", "exec-a", "reviewer", "claude-opus-4-8", checker_indisponivel=True)
        assert ok16, f"DEFERRED with an unavailable checker should pass: {r16}"

        rendered = render()
        assert "ITEM-1" in rendered and "MERGED" in rendered

        # dual write: the English path wins, a legacy-only repo keeps its board where it is
        RENDER_PATH = tmp / "docs" / "plans" / "execution" / "LANE-BOARD.md"
        assert _render_target() == RENDER_PATH, "a fresh repo must get the English path"
        tmp.joinpath(*_LEGACY_RENDER_DIR).mkdir(parents=True)
        assert _render_target().parent.name == "execucao", "a legacy-only repo must keep its directory"
        RENDER_PATH.parent.mkdir(parents=True)
        assert _render_target() == RENDER_PATH, "with both directories the English path wins"

        print("self-test OK — CLAIMED->BUILDING->CHECKPOINT-READY->UNDER-REVIEW->VERIFIED->MERGED, "
              "maker=checker refused (same lane / same family), tag=red requires --human-approved, "
              "an unavailable checker only accepts DEFERRED, a verdict reserves an accepted-but-"
              "undelivered effect that delivering clears, render ok, dual write of the board path")
        return 0
    finally:
        _PROJECT_ROOT, _LANES_DIR, BOARD_PATH, RENDER_PATH = orig
        if orig_fx is not None:
            lane_effects._PROJECT_ROOT, lane_effects._LANES_DIR, lane_effects.EFFECTS_PATH = orig_fx
        shutil.rmtree(tmp, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lane_board.py")
    sub = p.add_subparsers(dest="cmd")

    c = sub.add_parser("claim")
    c.add_argument("item_id")
    c.add_argument("--lane", required=True)
    c.add_argument("--role", default="executor")
    c.add_argument("--model", required=True)
    c.add_argument("--tag", default="green", choices=["green", "red"])

    s = sub.add_parser("set")
    s.add_argument("item_id")
    s.add_argument("state")
    s.add_argument("--lane", required=True)
    s.add_argument("--role", required=True)
    s.add_argument("--model", required=True)
    s.add_argument("--evidence", default="")
    s.add_argument("--verdict-by-lane", default="")
    s.add_argument("--verdict-by-model", default="")
    s.add_argument("--checker-indisponivel", action="store_true")
    s.add_argument("--human-approved", action="store_true")
    s.add_argument("--tag", default="green", choices=["green", "red"])

    st = sub.add_parser("status")
    st.add_argument("item_id", nargs="?")

    sub.add_parser("render")
    p.add_argument("--self-test", action="store_true")
    return p


def main(argv) -> int:
    args = build_parser().parse_args(argv)

    if args.self_test:
        return _self_test()

    if args.cmd == "claim":
        ok, result = set_state(args.item_id, "CLAIMED", args.lane, args.role, args.model, tag=args.tag)
    elif args.cmd == "set":
        ok, result = set_state(
            args.item_id, args.state, args.lane, args.role, args.model,
            evidence=args.evidence, verdict_by_lane=args.verdict_by_lane, verdict_by_model=args.verdict_by_model,
            checker_indisponivel=args.checker_indisponivel, human_approved=args.human_approved, tag=args.tag,
        )
    elif args.cmd == "status":
        events = _read_events(args.item_id)
        print(json.dumps(events, ensure_ascii=False, indent=2))
        return 0
    elif args.cmd == "render":
        text = render()
        target = _render_target()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        print(text)
        return 0
    else:
        print("usage: claim|set|status|render [...] or --self-test", file=sys.stderr)
        return 2

    if ok:
        print(json.dumps(result, ensure_ascii=False))
        return 0
    print(f"lane_board: refused — {result}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
