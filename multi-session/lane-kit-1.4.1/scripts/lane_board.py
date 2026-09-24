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
        CHECKPOINT-READY|VERIFIED -> NOT-SELECTED (terminal; written only by `select`)
        any state of an undecided candidate -> WITHDRAWN (terminal; written only by `withdraw`)

Competitions (best-of-N): N lanes attempt the same task independently, each on its own item. `compete`
declares which items are candidates for one task; `select` records the one winner, chosen by a reviewer
from ANOTHER lane AND ANOTHER model family than every candidate's builders, once every candidate is
CHECKPOINT-READY with evidence (or VERIFIED). The losers become NOT-SELECTED and can no longer move; a
candidate cannot be MERGED while its task has no winner. An unavailable reviewer records DEFERRED for
the competition, never a winner. The choice is an append-only event on the board, like every verdict.
A candidate whose lane died is taken out with `withdraw` (a competition event with the item and the
reason; the item becomes WITHDRAWN and its lane is owed the news): it stops counting for readiness and
for selection, so the remaining candidates can still be compared. At least one candidate always stays.

Usage:
    python lane_board.py claim <item_id> --lane <id> --role <role> --model <model> [--tag green|red]
    python lane_board.py set <item_id> <state> --lane <id> --role <role> --model <model>
                          [--evidence "..."] [--evidence-record <record.json>]
                          [--verdict-by-lane <id>] [--verdict-by-model <m>]
                          [--checker-unavailable] [--human-approved]
        --evidence-record (CHECKPOINT-READY only) attaches an `hpp.evidence/v1` record, verified through
        the optional HPP core (`python -m hpp`): accepted only when the core reports `valid` (an intact
        record of a passed run); the event stores {path, record_sha256, id}. Without the core: exit 2.
    python lane_board.py compete --task <task_id> --items A,B[,C...] --lane <id> --model <model>
    python lane_board.py select --task <task_id> --winner <item_id> --lane <reviewer> --model <m>
                          [--reason "..."]
    python lane_board.py select --task <task_id> --checker-unavailable --lane <reviewer> --model <m>
    python lane_board.py withdraw --task <task_id> --item <item_id> --lane <coordinator> --model <m>
                          --reason "..."
    python lane_board.py status [<item_id>]
    python lane_board.py render
    python lane_board.py --self-test

Exit: 0 ok - 1 invalid transition/enforcement refused - 2 invalid usage/lock not acquired.
stdlib only. v1.0.0 -- 2026-07-10 (lane-kit) · compete/select -- 2026-09-24 (lane-kit 1.4.0)
· withdraw -- 2026-09-24 (lane-kit 1.4.1)
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
_VERDICTS_WITH_EFFECT = ("VERIFIED", "NEEDS-FIX", "DEFERRED", "NOT-SELECTED", "WITHDRAWN")
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
    # Terminal, and no row above lists it as a target: `set` can never write it. Only `select`
    # does, for the candidates that lost — so a losing attempt cannot drift on to MERGED.
    "NOT-SELECTED": set(),
    # Terminal too, and written only by `withdraw`: a candidate taken out of its competition.
    "WITHDRAWN": set(),
}

# A competition lives on the same board as the items, as events with `kind: competition` and a
# `task_id` instead of an `item_id`. Its own states: DECLARED -> SELECTED | DEFERRED,
# DEFERRED -> SELECTED | DEFERRED, SELECTED terminal. WITHDRAWN events (one per candidate taken
# out, key `item`, never `item_id`) can sit between them and do not change that standing.
_COMPETITION = "competition"
# The states an EXECUTOR writes while building. A reviewer's verdict event carries the reviewer's
# model, so reading "who built this" off every event would count the checker as a builder.
_BUILDER_STATES = ("CLAIMED", "BUILDING", "CHECKPOINT-READY")
_READY_FOR_SELECTION = ("CHECKPOINT-READY", "VERIFIED")


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


def _append_events(events: list) -> None:
    """Several lines in ONE write: a selection and the losers it marks land together or not at all
    as far as a reader of the board can tell (a crash between two writes would leave a decided
    competition whose losers can still move)."""
    BOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BOARD_PATH, "a", encoding="utf-8") as f:
        f.write("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events))


def _is_competition(event: dict) -> bool:
    return event.get("kind") == _COMPETITION


def _competitions() -> dict:
    """task_id -> the competition's events, in board order (the first one is the DECLARED)."""
    found: dict = {}
    for e in _read_events():
        if _is_competition(e):
            found.setdefault(e.get("task_id", ""), []).append(e)
    return found


def _candidates(events: list) -> list:
    """Every item ever declared for the task, withdrawn ones included."""
    return list(events[0].get("candidates", [])) if events else []


def _withdrawn(events: list) -> list:
    """The candidates taken out with `withdraw`, in the order they were withdrawn."""
    return [e.get("item", "") for e in events if e.get("state") == "WITHDRAWN"]


def _active_candidates(events: list) -> list:
    """The candidates that still count for readiness and for selection."""
    gone = set(_withdrawn(events))
    return [item for item in _candidates(events) if item not in gone]


def _decided(events: list) -> dict | None:
    """The SELECTED event of the competition, or None while it has no winner."""
    return next((e for e in events if e.get("state") == "SELECTED"), None)


def _standing(events: list) -> str:
    """DECLARED, DEFERRED or SELECTED: a WITHDRAWN event does not change where the task stands."""
    if _decided(events):
        return "SELECTED"
    standing = [e.get("state") for e in events if e.get("state") != "WITHDRAWN"]
    return standing[-1] if standing else ""


def _competition_of(item_id: str) -> tuple | None:
    """(task_id, events) of the competition this item is a candidate of, or None."""
    for task_id, events in _competitions().items():
        if item_id in _candidates(events):
            return task_id, events
    return None


def _builders(item_id: str) -> list:
    """(lane, model) of every event an executor wrote while building the item."""
    return [(e.get("lane_id", ""), e.get("model", ""))
            for e in _read_events(item_id) if e.get("state") in _BUILDER_STATES]


def _checkpoint_evidence(item_id: str) -> str:
    """Evidence of the item's most recent CHECKPOINT-READY (a VERIFIED item keeps the one it had)."""
    last = next((e for e in reversed(_read_events(item_id)) if e.get("state") == "CHECKPOINT-READY"), None)
    return (last or {}).get("evidence", "")


def _checkpoint_record(item_id: str) -> dict:
    """The verified evidence record attached to the item's most recent CHECKPOINT-READY, if any."""
    last = next((e for e in reversed(_read_events(item_id)) if e.get("state") == "CHECKPOINT-READY"), None)
    return (last or {}).get("evidence_record") or {}


class EvidenceCoreMissing(Exception):
    """`--evidence-record` was given and the HPP core (`hpp.evidence`) is not importable."""


def _load_evidence_verifier() -> tuple:
    # Why: the kit stays stdlib-only and standalone; only this flag needs the HPP core, so the import
    # happens here and a missing core is a refusal (exit 2), never a silent fall back to free text.
    try:
        from hpp.evidence import EvidenceError, verify_evidence
    except ImportError as exc:
        raise EvidenceCoreMissing(str(exc)) from exc
    return verify_evidence, EvidenceError


def verify_evidence_record(record_path: str) -> tuple:
    """Verifies an `hpp.evidence/v1` record through the HPP core. Returns (ok, attachment_or_reason).

    Only status `valid` (an intact record of a PASSED run) is accepted; `not-evidence` and `blocked`
    are refused with the core's own problems. The attachment `{path, record_sha256, id}` is what the
    board stores, and the board never re-hashes it later. Raises EvidenceCoreMissing when the core is
    not importable. A relative path is read from the project root, which is also the root the
    record's artifacts are resolved against.
    """
    verify, evidence_error = _load_evidence_verifier()
    path = Path(record_path)
    if not path.is_absolute():
        path = _PROJECT_ROOT / path
    try:
        before = path.read_bytes()
        report = verify(path, root=_PROJECT_ROOT)
        after = path.read_bytes()
    except evidence_error as exc:
        return False, f"evidence record {record_path} refused by the HPP core: {exc}"
    except OSError as exc:
        return False, f"evidence record not readable: {record_path} ({exc.strerror or exc})"
    status = report.get("status")
    if status != "valid":
        problems = "; ".join(report.get("problems") or []) or "no detail"
        return False, (f"evidence record {record_path} is {status}, not valid — {problems} "
                       f"(only an intact record of a passed run is accepted)")
    # Why: the stored hash is read from the same bytes the core verified; a record rewritten between
    # the two reads would otherwise attach a hash nobody checked.
    if after != before:
        return False, f"evidence record {record_path} changed while it was being verified"
    record = json.loads(before.decode("utf-8"))
    return True, {"path": record_path, "record_sha256": record.get("record_sha256", ""), "id": record.get("id", "")}


def _validate_transition(item_id: str, new_state: str, lane_id: str, role: str, model: str,
                          evidence: str = "", verdict_by_lane: str = "", verdict_by_model: str = "",
                          checker_unavailable: bool = False, human_approved: bool = False, tag: str = "green",
                          evidence_record: dict | None = None) -> str | None:
    """Returns None if valid, or the error message."""
    current = _latest_state(item_id)
    cur_state = current["state"] if current else None

    allowed = _TRANSITIONS.get(cur_state, set())
    if new_state not in allowed:
        return f"invalid transition: {cur_state} -> {new_state} (allowed: {sorted(allowed)})"

    if new_state == "CLAIMED" and current and cur_state not in (None,):
        if cur_state in ("MERGED",):
            return "item already MERGED — cannot be reopened with CLAIMED"

    if new_state in ("BUILDING", "CHECKPOINT-READY"):
        competition = _competition_of(item_id)
        if competition:
            for other in _candidates(competition[1]):
                if other != item_id and lane_id in {lane for lane, _model in _builders(other)}:
                    return (f"lane {lane_id} is a builder of candidate {other} of task {competition[0]}; "
                            f"building {item_id} too would make two attempts one")

    if new_state == "CHECKPOINT-READY":
        builder = current  # the most recent BUILDING/CLAIMED event is the "owner"
        if role != "executor":
            return f"CHECKPOINT-READY only with role=executor (got: {role})"
        if not builder or builder.get("lane_id") != lane_id:
            return f"CHECKPOINT-READY only from the lane that claimed the item (owner: {builder.get('lane_id') if builder else '?'}, got: {lane_id})"
        if not evidence and not evidence_record:
            return "CHECKPOINT-READY requires non-empty evidence (pasted hash/exit code, never 'I ran it')"

    if new_state in ("VERIFIED", "NEEDS-FIX"):
        if role != "reviewer":
            return f"{new_state} only with role=reviewer (got: {role})"
        # find the original builder (CLAIMED event)
        claimed = next((e for e in reversed(_read_events(item_id)) if e["state"] == "CLAIMED"), None)
        builder_lane = claimed.get("lane_id") if claimed else None
        builder_model = claimed.get("model") if claimed else None
        if checker_unavailable:
            return f"checker unavailable — only DEFERRED is accepted, not {new_state}"
        # Why: the two maker≠checker guards below compare the reviewer against the builder, and with
        # the flags OMITTED they compared None against a real value — so neither could ever fire and
        # an item reached VERIFIED, then MERGED, recording no reviewer at all. The guard existed and
        # could not reach. Requiring both identities is what makes the two comparisons mean anything.
        if not verdict_by_lane or not verdict_by_model:
            faltando = " and ".join(
                f"--verdict-by-{k}" for k, v in (("lane", verdict_by_lane), ("model", verdict_by_model)) if not v)
            return (f"{new_state} requires the reviewer's identity: {faltando} missing. Without it the "
                    f"maker≠checker check compares against nothing and the verdict records no reviewer.")
        if verdict_by_lane == builder_lane:
            return f"maker≠checker violated: reviewer ({verdict_by_lane}) is the SAME lane as the builder ({builder_lane})"
        # Why: in convergence mode a second lane also builds the item; only the claiming lane was
        # compared, so that second lane could verify its own work.
        if verdict_by_lane in {lane for lane, _model in _builders(item_id)}:
            return (f"maker≠checker violated: reviewer ({verdict_by_lane}) is the SAME lane as a builder of "
                    f"{item_id}")
        if _model_family(verdict_by_model) == _model_family(builder_model):
            return f"maker≠checker violated: reviewer and builder are from the SAME model family ({_model_family(verdict_by_model)})"

    if new_state == "DEFERRED" and not checker_unavailable:
        return "DEFERRED only with --checker-unavailable"

    if new_state == "MERGED":
        verified = next((e for e in reversed(_read_events(item_id)) if e["state"] == "VERIFIED"), None)
        if not verified:
            return "MERGED requires a previous VERIFIED in the item history"
        # Why: without this a candidate could be verified on its own and merged before the other
        # attempts were compared — the competition would be decided by whoever finished first.
        competition = _competition_of(item_id)
        if competition and not _decided(competition[1]):
            return (f"MERGED refused: {item_id} is a candidate of task {competition[0]}, which has no winner "
                    f"yet — run `select` before merging (a candidate merged first skips the comparison)")
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
            if kwargs.get("evidence_record"):
                event["evidence_record"] = kwargs["evidence_record"]
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


def _shared_builder_lane(items: list) -> str | None:
    """The refusal when two candidates share a builder lane, or None."""
    lanes_of = {item: {lane for lane, _model in _builders(item) if lane} for item in items}
    for index, first in enumerate(items):
        for second in items[index + 1:]:
            shared = sorted(lanes_of[first] & lanes_of[second])
            if shared:
                return (f"candidates {first} and {second} share builder lane {shared[0]} — best-of-N needs "
                        f"independent attempts, one lane per candidate")
    return None


def _validate_compete(task_id: str, items: list, lane_id: str, model: str) -> str | None:
    """Returns None if the declaration is valid, or the error message."""
    if not task_id:
        return "compete requires --task <task_id>"
    if not lane_id or not model:
        return "compete requires the declaring lane's identity: --lane and --model"
    distinct = list(dict.fromkeys(items))
    if len(distinct) < 2:
        return (f"compete needs at least 2 distinct candidate items for task {task_id} "
                f"(got: {', '.join(items) or 'none'})")
    if len(distinct) != len(items):
        repeated = next(i for i in distinct if items.count(i) > 1)
        return f"item {repeated} is listed more than once — each candidate is one independent attempt"
    competitions = _competitions()
    if task_id in competitions:
        return (f"task {task_id} already has a competition (candidates: "
                f"{', '.join(_candidates(competitions[task_id]))}) — the board is append-only; "
                f"declare a new task id")
    for item in items:
        latest = _latest_state(item)
        if latest is None:
            return f"candidate {item} has never been claimed on this board — claim it before it can compete"
        if latest.get("state") in ("MERGED", "NOT-SELECTED", "WITHDRAWN"):
            return f"candidate {item} is {latest['state']} — a finished item cannot compete"
        for other_task, events in competitions.items():
            if item in _candidates(events):
                return f"item {item} is already a candidate of task {other_task} — one item, one competition"
    # Why: the convergence mode lets a second lane build on an item, so "one lane per candidate"
    # compares every builder lane of each candidate, not only the one that claimed it.
    return _shared_builder_lane(items)


def compete(task_id: str, items: list, lane_id: str, model: str) -> tuple:
    """Declares `items` as candidates for the same task. Returns (ok, event_or_error)."""
    try:
        with _Lock(_LANES_DIR):
            err = _validate_compete(task_id, items, lane_id, model)
            if err:
                return False, err
            event = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "kind": _COMPETITION,
                "task_id": task_id,
                "state": "DECLARED",
                "candidates": list(items),
                "lane_id": lane_id,
                "role": "coordinator",
                "model": model,
            }
            _append_event(event)
            return True, event
    except LockError as e:
        return False, str(e)


def _validate_select(task_id: str, events: list, winner: str, lane_id: str, model: str,
                     checker_unavailable: bool) -> str | None:
    """Returns None if the selection (or the DEFERRED) is valid, or the error message."""
    if not events:
        return f"no competition declared for task {task_id} — run `compete` first"
    decided = _decided(events)
    if decided:
        return (f"task {task_id} is already decided (winner: {decided.get('winner')}) — a selection is "
                f"not re-taken; the board is append-only")
    if not lane_id or not model:
        return "select requires the reviewer's identity: --lane and --model"
    candidates = _active_candidates(events)
    if checker_unavailable:
        if winner:
            return "checker unavailable — only DEFERRED is recorded for a competition, never a winner"
    elif not winner:
        return "select requires --winner <item_id> (or --checker-unavailable to record DEFERRED)"
    elif winner in _withdrawn(events):
        return f"winner {winner} was withdrawn from task {task_id} — only a remaining candidate can win"
    elif winner not in candidates:
        return f"winner {winner} is not a candidate of task {task_id} (candidates: {', '.join(candidates)})"
    for item in candidates:
        latest = _latest_state(item) or {}
        state = latest.get("state")
        if state == "CHECKPOINT-READY" and not (latest.get("evidence") or latest.get("evidence_record")):
            return (f"candidate {item} is CHECKPOINT-READY without evidence — a comparison needs every "
                    f"candidate's pasted proof")
        if state not in _READY_FOR_SELECTION:
            return (f"candidate {item} is {state} — every candidate must be CHECKPOINT-READY with evidence, "
                    f"or VERIFIED, before a winner is chosen")
    shared = _shared_builder_lane(candidates)
    if shared:
        return shared
    reviewer_family = _model_family(model)
    # Why: the lane rule reads EVERY candidate, withdrawn ones included — a lane that attempted the task
    # never judges it. The family rule reads only the attempts being compared.
    for item in _candidates(events):
        for builder_lane, builder_model in _builders(item):
            if lane_id == builder_lane:
                return (f"maker≠checker violated: reviewer ({lane_id}) is the SAME lane as the builder of "
                        f"candidate {item} ({builder_lane})")
            if checker_unavailable or item not in candidates:
                continue  # a DEFERRED records that no review happened; only the lane is checked
            if reviewer_family == _model_family(builder_model):
                return (f"maker≠checker violated: reviewer and the builder of candidate {item} are from the "
                        f"SAME model family ({reviewer_family})")
    return None


def select(task_id: str, winner: str, lane_id: str, model: str, reason: str = "",
           checker_unavailable: bool = False) -> tuple:
    """Records the winner of a competition (or DEFERRED). Returns (ok, event_or_error).

    The competition event names the winner, the losers, the reviewer and the evidence that was
    compared; each loser also gets its own NOT-SELECTED item event, which owes its lane the news
    through the same effect ledger as any verdict.
    """
    try:
        with _Lock(_LANES_DIR):
            events = _competitions().get(task_id, [])
            err = _validate_select(task_id, events, winner, lane_id, model, checker_unavailable)
            if err:
                return False, err
            ts = time.strftime("%Y-%m-%dT%H:%M:%S")
            candidates = _active_candidates(events)
            event = {
                "ts": ts,
                "kind": _COMPETITION,
                "task_id": task_id,
                "state": "DEFERRED" if checker_unavailable else "SELECTED",
                "candidates": candidates,
                "lane_id": lane_id,
                "role": "reviewer",
                "model": model,
            }
            if checker_unavailable:
                event["checker_unavailable"] = True
                if reason:
                    event["reason"] = reason
                _append_event(event)
                return True, event
            losers = [item for item in candidates if item != winner]
            event["winner"] = winner
            event["not_selected"] = losers
            if _withdrawn(events):
                event["withdrawn"] = _withdrawn(events)
            event["verdict_by"] = {"lane": lane_id, "model": model}
            event["compared"] = {
                item: {"state": (_latest_state(item) or {}).get("state", ""), "evidence": _checkpoint_evidence(item)}
                for item in candidates
            }
            for item in candidates:
                record = _checkpoint_record(item)
                if record:
                    event["compared"][item]["evidence_record"] = record
            if reason:
                event["reason"] = reason
            lines = [event]
            for loser in losers:
                marked = {
                    "ts": ts,
                    "item_id": loser,
                    "state": "NOT-SELECTED",
                    "lane_id": lane_id,
                    "role": "reviewer",
                    "model": model,
                    "verdict_by": {"lane": lane_id, "model": model},
                    "task_id": task_id,
                    "winner": winner,
                }
                reservation = _reserve_effect(loser, "NOT-SELECTED")
                if reservation:
                    marked["reservation_id"] = reservation
                lines.append(marked)
            _append_events(lines)
            return True, event
    except LockError as e:
        return False, str(e)


def _validate_withdraw(task_id: str, events: list, item: str, lane_id: str, model: str,
                       reason: str) -> str | None:
    """Returns None if the withdrawal is valid, or the error message."""
    if not events:
        return f"no competition declared for task {task_id} — run `compete` first"
    decided = _decided(events)
    if decided:
        return (f"task {task_id} is already decided (winner: {decided.get('winner')}) — a decided "
                f"competition is not re-opened; the board is append-only")
    if not lane_id or not model:
        return "withdraw requires the coordinator's identity: --lane and --model"
    if not reason.strip():
        return "withdraw requires --reason — a candidate taken out without a recorded why is a silent exclusion"
    if item in _withdrawn(events):
        return f"item {item} was already withdrawn from task {task_id}"
    remaining = _active_candidates(events)
    if item not in remaining:
        return f"item {item} is not a candidate of task {task_id} (candidates: {', '.join(remaining)})"
    if len(remaining) <= 1:
        return (f"task {task_id} needs at least 1 candidate — {item} is the last one; select it, or leave "
                f"the task open")
    # Why: a lane that built a rival could otherwise knock its competitor out of the comparison.
    for other in remaining:
        if other != item and lane_id in {lane for lane, _model in _builders(other)}:
            return (f"lane {lane_id} is a builder of candidate {other} of task {task_id}; it cannot withdraw "
                    f"a rival")
    return None


def withdraw(task_id: str, item: str, lane_id: str, model: str, reason: str) -> tuple:
    """Takes one candidate out of an undecided competition. Returns (ok, event_or_error).

    The competition event (state WITHDRAWN, `item`, `reason`) is what readiness and selection read;
    the item's own WITHDRAWN event makes it terminal and owes its lane the news through the same
    effect ledger as NOT-SELECTED.
    """
    try:
        with _Lock(_LANES_DIR):
            events = _competitions().get(task_id, [])
            err = _validate_withdraw(task_id, events, item, lane_id, model, reason)
            if err:
                return False, err
            ts = time.strftime("%Y-%m-%dT%H:%M:%S")
            event = {
                "ts": ts,
                "kind": _COMPETITION,
                "task_id": task_id,
                "state": "WITHDRAWN",
                "item": item,
                "reason": reason,
                "remaining": [c for c in _active_candidates(events) if c != item],
                "lane_id": lane_id,
                "role": "coordinator",
                "model": model,
            }
            marked = {
                "ts": ts,
                "item_id": item,
                "state": "WITHDRAWN",
                "lane_id": lane_id,
                "role": "coordinator",
                "model": model,
                "task_id": task_id,
                "reason": reason,
            }
            reservation = _reserve_effect(item, "WITHDRAWN")
            if reservation:
                marked["reservation_id"] = reservation
            _append_events([event, marked])
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


def _render_competitions(competitions: dict) -> list:
    lines = ["## COMPETITIONS (one task, N candidate items, one winner)"]
    for task_id, events in sorted(competitions.items()):
        decided = _decided(events)
        standing = _standing(events)
        candidates = ", ".join(_active_candidates(events))
        withdrawn = (f" · withdrawn: {', '.join(_withdrawn(events))}" if _withdrawn(events) else "")
        if decided:
            lines.append(f"### {task_id} — SELECTED · winner: {decided.get('winner')} · "
                         f"not selected: {', '.join(decided.get('not_selected', [])) or 'none'}{withdrawn}")
        else:
            waiting = " (checker unavailable)" if standing == "DEFERRED" else ""
            lines.append(f"### {task_id} — {standing} · no winner yet{waiting} · candidates: {candidates}"
                         f"{withdrawn}")
        for e in events:
            detail = ""
            if e.get("state") == "DECLARED":
                detail = f" · candidates: {', '.join(e.get('candidates', []))}"
            elif e.get("state") == "SELECTED":
                detail = (f" · winner: {e.get('winner')} · not selected: {', '.join(e.get('not_selected', []))}"
                          f" · verdict_by: {e.get('verdict_by')}")
            elif e.get("state") == "DEFERRED":
                detail = " · checker unavailable"
            elif e.get("state") == "WITHDRAWN":
                detail = f" · item: {e.get('item')}"
            reason = f" · reason: {e['reason']}" if e.get("reason") else ""
            lines.append(f"- {e.get('ts')} · {e.get('state')}{detail} · lane={e.get('lane_id')} "
                         f"role={e.get('role')}{reason}")
    lines.append("")
    return lines


def render() -> str:
    items: dict = {}
    competitions: dict = {}
    for e in _read_events():
        if _is_competition(e):
            competitions.setdefault(e.get("task_id", ""), []).append(e)
        elif "item_id" in e and "state" in e:
            items.setdefault(e["item_id"], []).append(e)
    lines = ["# LANE-BOARD.md (generated by lane_board.py render — do not edit by hand)", ""]
    for item_id, events in sorted(items.items()):
        last = events[-1]
        lines.append(f"## {item_id} — {last['state']}")
        for e in events:
            evid = f" · evidence: {e['evidence']}" if e.get("evidence") else ""
            # Why: render reads what was stored when the core verified the record; re-hashing here
            # would make a read path depend on files that may have moved since the checkpoint.
            stored = e.get("evidence_record") if isinstance(e.get("evidence_record"), dict) else {}
            record = (f" · record: {stored.get('id')} sha256:{str(stored.get('record_sha256', ''))[:12]}"
                      if stored else "")
            verdict = f" · verdict_by: {e['verdict_by']}" if e.get("verdict_by") else ""
            task = (f" · task: {e['task_id']}" + (f" · winner: {e['winner']}" if e.get("winner") else "")
                    if e.get("task_id") else "")
            reason = f" · reason: {e['reason']}" if e.get("reason") else ""
            lines.append(f"- {e['ts']} · {e['state']} · lane={e['lane_id']} role={e['role']}{evid}{record}{verdict}"
                         f"{task}{reason}")
        lines.append("")
    if competitions:
        lines.extend(_render_competitions(competitions))
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
        ok15, r15 = set_state("ITEM-3", "VERIFIED", "exec-a", "reviewer", "claude-opus-4-8", checker_unavailable=True, verdict_by_lane="rev-a", verdict_by_model="gpt-5.6")
        assert not ok15 and "DEFERRED" in r15, f"an unavailable checker only accepts DEFERRED: {r15}"
        ok16, r16 = set_state("ITEM-3", "DEFERRED", "exec-a", "reviewer", "claude-opus-4-8", checker_unavailable=True)
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


def _run_cli(argv: list) -> tuple:
    """Runs `main(argv)` the way a shell would and returns (exit code, stdout, stderr)."""
    import contextlib
    import io

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(argv)
        except SystemExit as exc:  # argparse rejects an unknown command or flag with exit 2
            code = exc.code if isinstance(exc.code, int) else 2
    return code, out.getvalue(), err.getvalue()


def _self_test_compete() -> int:
    """Competitions (`compete` / `select`) through the CLI: every refusal, and the CONTROL that a
    valid selection is accepted and recorded. Each check is counted, so a run reports N of M."""
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="lane_board_compete_"))
    global _PROJECT_ROOT, _LANES_DIR, BOARD_PATH, RENDER_PATH
    orig = (_PROJECT_ROOT, _LANES_DIR, BOARD_PATH, RENDER_PATH)
    orig_fx = None
    if lane_effects is not None:
        orig_fx = (lane_effects._PROJECT_ROOT, lane_effects._LANES_DIR, lane_effects.EFFECTS_PATH)
    results: list = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        results.append((name, bool(condition), detail))

    def refused(name: str, argv: list, needle: str) -> None:
        code, _out, err = _run_cli(argv)
        check(name, code == 1 and needle in err,
              f"expected exit 1 containing {needle!r}; got exit {code}: {err.strip()[:240]}")

    def accepted(name: str, argv: list) -> dict:
        code, out, err = _run_cli(argv)
        check(name, code == 0, f"expected exit 0; got exit {code}: {err.strip()[:240]}")
        try:
            return json.loads(out) if code == 0 else {}
        except ValueError:
            return {}

    def to_checkpoint(item: str, lane: str, model: str) -> None:
        steps = (("CLAIMED", ""), ("BUILDING", ""), ("CHECKPOINT-READY", f"pytest -q: 12 passed ({item})"))
        for state, evidence in steps:
            ok, why = set_state(item, state, lane, "executor", model, evidence=evidence)
            check(f"setup {item} -> {state}", ok, str(why))

    task = ["--lane", "coord", "--model", "claude-opus-4-8"]
    try:
        _PROJECT_ROOT = tmp
        _LANES_DIR = tmp / ".claude" / "lanes"
        BOARD_PATH = _LANES_DIR / "board.jsonl"
        RENDER_PATH = tmp / "LANE-BOARD.md"
        if lane_effects is not None:
            lane_effects._PROJECT_ROOT = tmp
            lane_effects._LANES_DIR = _LANES_DIR
            lane_effects.EFFECTS_PATH = _LANES_DIR / "effects.json"

        to_checkpoint("ITEM-A", "exec-a", "claude-opus-4-8")
        for state in ("CLAIMED", "BUILDING"):  # B is still being built when the task is declared
            ok, why = set_state("ITEM-B", state, "exec-b", "executor", "claude-sonnet-5")
            check(f"setup ITEM-B -> {state}", ok, str(why))
        set_state("ITEM-SAME-LANE", "CLAIMED", "exec-a", "executor", "claude-opus-4-8")
        set_state("ITEM-LONE", "CLAIMED", "exec-d", "executor", "gpt-5.6")

        # --- compete: refusals, then the CONTROL that a valid declaration is accepted ---
        refused("compete with one item", ["compete", "--task", "TASK-1", "--items", "ITEM-A", *task],
                "at least 2")
        refused("compete with an item listed twice",
                ["compete", "--task", "TASK-1", "--items", "ITEM-A,ITEM-A", *task], "at least 2")
        refused("compete with an item never claimed",
                ["compete", "--task", "TASK-1", "--items", "ITEM-A,ITEM-GHOST", *task], "never been claimed")
        refused("compete with two candidates from the same lane",
                ["compete", "--task", "TASK-1", "--items", "ITEM-A,ITEM-SAME-LANE", *task], "share builder lane")
        declared = accepted("CONTROL compete with 2 independent candidates",
                            ["compete", "--task", "TASK-1", "--items", "ITEM-A,ITEM-B", *task])
        check("compete records the candidates", declared.get("candidates") == ["ITEM-A", "ITEM-B"], str(declared))
        refused("compete re-declaring the same task",
                ["compete", "--task", "TASK-1", "--items", "ITEM-A,ITEM-B", *task], "already has a competition")
        refused("compete with an item that already competes",
                ["compete", "--task", "TASK-2", "--items", "ITEM-B,ITEM-LONE", *task], "already a candidate")

        # --- select: refusals ---
        reviewer = ["--lane", "rev-x", "--model", "gpt-5.6"]
        refused("select on a task never declared",
                ["select", "--task", "TASK-9", "--winner", "ITEM-A", *reviewer], "no competition declared")
        refused("select while a candidate has no checkpoint evidence",
                ["select", "--task", "TASK-1", "--winner", "ITEM-A", *reviewer], "must be CHECKPOINT-READY with evidence")
        ok, why = set_state("ITEM-B", "CHECKPOINT-READY", "exec-b", "executor", "claude-sonnet-5",
                            evidence="pytest -q: 12 passed (ITEM-B)")
        check("setup ITEM-B -> CHECKPOINT-READY", ok, str(why))

        # A hand-edited or legacy board can hold a checkpoint with no evidence; the board itself
        # never writes one, so this line is forged on purpose to reach that branch.
        to_checkpoint("ITEM-F1", "exec-f", "claude-opus-4-8")
        to_checkpoint("ITEM-F2", "exec-g", "claude-opus-4-8")
        _append_event({"ts": "2026-01-01T00:00:00", "item_id": "ITEM-F2", "state": "CHECKPOINT-READY",
                       "lane_id": "exec-g", "role": "executor", "model": "claude-opus-4-8"})
        accepted("setup compete TASK-3", ["compete", "--task", "TASK-3", "--items", "ITEM-F1,ITEM-F2", *task])
        refused("select while a CHECKPOINT-READY candidate carries no evidence",
                ["select", "--task", "TASK-3", "--winner", "ITEM-F1", *reviewer], "without evidence")

        refused("select by a reviewer on a candidate's lane",
                ["select", "--task", "TASK-1", "--winner", "ITEM-A", "--lane", "exec-b", "--model", "gpt-5.6"],
                "SAME lane")
        refused("select by a reviewer of a candidate's model family",
                ["select", "--task", "TASK-1", "--winner", "ITEM-A", "--lane", "rev-x", "--model", "claude-haiku-4"],
                "SAME model family")
        refused("select of a winner that is not a candidate",
                ["select", "--task", "TASK-1", "--winner", "ITEM-LONE", *reviewer], "not a candidate")
        refused("select without --winner", ["select", "--task", "TASK-1", *reviewer], "requires --winner")
        refused("select naming a winner while the checker is unavailable",
                ["select", "--task", "TASK-1", "--winner", "ITEM-A", "--checker-unavailable", *reviewer],
                "only DEFERRED")
        refused("DEFERRED recorded by a candidate's own lane",
                ["select", "--task", "TASK-1", "--checker-unavailable", "--lane", "exec-b", "--model", "gpt-5.6"],
                "SAME lane")
        code, out, _err = _run_cli(["status", "TASK-1"])
        try:
            shown = json.loads(out) if code == 0 else []
        except ValueError:
            shown = []
        check("status <task> shows the competition", bool(shown) and all(e.get("task_id") == "TASK-1" for e in shown),
              out[:240])

        # after the declaration, one lane must not become the builder of a second candidate
        to_checkpoint("ITEM-C", "exec-c", "claude-opus-4-8")
        set_state("ITEM-D", "CLAIMED", "exec-h", "executor", "gpt-5.6")
        accepted("setup compete TASK-4", ["compete", "--task", "TASK-4", "--items", "ITEM-C,ITEM-D", *task])
        refused("a candidate built by another candidate's lane",
                ["set", "ITEM-D", "BUILDING", "--lane", "exec-c", "--role", "executor", "--model", "claude-opus-4-8"],
                "builder of candidate")
        # A board edited by hand can still carry that event; the selection must catch it too.
        for state in ("BUILDING", "CHECKPOINT-READY"):
            _append_event({"ts": "2026-01-01T00:00:00", "item_id": "ITEM-D", "state": state, "lane_id": "exec-c",
                           "role": "executor", "model": "claude-opus-4-8", "evidence": "exit=0"})
        refused("select when one lane built two candidates",
                ["select", "--task", "TASK-4", "--winner", "ITEM-C", "--lane", "rev-y", "--model", "gemini-3"],
                "share builder lane")

        # convergence mode: a second lane that built the item cannot verify it either
        set_state("ITEM-V", "CLAIMED", "exec-v", "executor", "claude-opus-4-8")
        _append_event({"ts": "2026-01-01T00:00:00", "item_id": "ITEM-V", "state": "BUILDING", "lane_id": "exec-w",
                       "role": "executor", "model": "gpt-5.6"})
        set_state("ITEM-V", "CHECKPOINT-READY", "exec-w", "executor", "gpt-5.6", evidence="exit=0")
        set_state("ITEM-V", "UNDER-REVIEW", "exec-w", "executor", "gpt-5.6")
        refused("VERIFIED by a lane that built the item in convergence mode",
                ["set", "ITEM-V", "VERIFIED", "--lane", "exec-w", "--role", "reviewer", "--model", "gemini-3",
                 "--verdict-by-lane", "exec-w", "--verdict-by-model", "gemini-3"], "SAME lane")

        # a candidate cannot be merged before the comparison, even after its own review
        for state, extra in (("UNDER-REVIEW", {}),
                             ("VERIFIED", {"verdict_by_lane": "rev-a", "verdict_by_model": "gpt-5.6"})):
            ok, why = set_state("ITEM-A", state, "exec-a", "reviewer" if extra else "executor",
                                "gpt-5.6" if extra else "claude-opus-4-8", **extra)
            check(f"setup ITEM-A -> {state}", ok, str(why))
        refused("MERGED of a candidate before any winner",
                ["set", "ITEM-A", "MERGED", "--lane", "rev-a", "--role", "reviewer", "--model", "gpt-5.6"],
                "no winner yet")

        deferred = accepted("select with the checker unavailable records DEFERRED",
                            ["select", "--task", "TASK-1", "--checker-unavailable", *reviewer])
        check("the DEFERRED is a competition event", deferred.get("state") == "DEFERRED", str(deferred))
        refused("MERGED of a candidate while the competition is DEFERRED",
                ["set", "ITEM-A", "MERGED", "--lane", "rev-a", "--role", "reviewer", "--model", "gpt-5.6"],
                "no winner yet")
        refused("`set` cannot forge NOT-SELECTED",
                ["set", "ITEM-B", "NOT-SELECTED", "--lane", "rev-x", "--role", "reviewer", "--model", "gpt-5.6"],
                "invalid transition")

        # --- CONTROL: a valid selection is accepted, and it is evidence on the board ---
        chosen = accepted("CONTROL select by another lane of another family",
                          ["select", "--task", "TASK-1", "--winner", "ITEM-A", *reviewer,
                           "--reason", "same tests, half the diff"])
        check("select records the winner", chosen.get("winner") == "ITEM-A", str(chosen))
        check("select records who was not selected", chosen.get("not_selected") == ["ITEM-B"], str(chosen))
        check("select records the reviewer", chosen.get("verdict_by") == {"lane": "rev-x", "model": "gpt-5.6"},
              str(chosen))
        check("select records the evidence it compared",
              sorted((chosen.get("compared") or {}).keys()) == ["ITEM-A", "ITEM-B"], str(chosen))
        loser = _latest_state("ITEM-B") or {}
        check("the losing candidate is NOT-SELECTED", loser.get("state") == "NOT-SELECTED", str(loser))
        check("the winner keeps its own state", (_latest_state("ITEM-A") or {}).get("state") == "VERIFIED",
              str(_latest_state("ITEM-A")))
        refused("select again on a decided task",
                ["select", "--task", "TASK-1", "--winner", "ITEM-B", *reviewer], "already decided")
        refused("the loser cannot move on",
                ["set", "ITEM-B", "UNDER-REVIEW", "--lane", "exec-b", "--role", "executor", "--model", "claude-sonnet-5"],
                "invalid transition")
        accepted("the winner merges after the selection",
                 ["set", "ITEM-A", "MERGED", "--lane", "rev-a", "--role", "reviewer", "--model", "gpt-5.6"])
        if lane_effects is not None:
            owed = [(r["item_id"], r["decision"], r["target"]) for r in lane_effects.pending_effects()]
            check("the losing lane is owed the news", ("ITEM-B", "NOT-SELECTED", "exec-b") in owed, str(owed))

        rendered = render()
        for needle in ("TASK-1", "SELECTED", "winner: ITEM-A", "not selected: ITEM-B", "NOT-SELECTED", "TASK-3"):
            check(f"render shows {needle!r}", needle in rendered, rendered[-600:])
    finally:
        _PROJECT_ROOT, _LANES_DIR, BOARD_PATH, RENDER_PATH = orig
        if orig_fx is not None:
            lane_effects._PROJECT_ROOT, lane_effects._LANES_DIR, lane_effects.EFFECTS_PATH = orig_fx
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [(name, detail) for name, ok, detail in results if not ok]
    if failed:
        print(f"self-test FAILED (competitions) — {len(results) - len(failed)} of {len(results)} checks passed",
              file=sys.stderr)
        for name, detail in failed:
            print(f"  FAIL {name}: {detail}", file=sys.stderr)
        return 1
    print(f"self-test OK (competitions) — {len(results)} of {len(results)} checks: compete refuses one item, "
          "a repeated item, an unclaimed item, a shared lane, a re-declared task and a double entry; select "
          "refuses an undeclared task, a candidate without evidence, a reviewer on a candidate's lane or "
          "model family, a winner outside the candidates, a missing winner and a winner with the checker "
          "unavailable (DEFERRED instead); a candidate cannot merge before the winner; the CONTROL selection "
          "lands, the loser is NOT-SELECTED and owed the news, render shows the outcome")
    return 0


def _self_test_withdraw() -> int:
    """`withdraw` through the CLI: a candidate whose lane died leaves the competition, so the others
    can still be compared and merged. Every refusal, and the CONTROL that a withdrawal lands and
    unblocks the selection. Each check is counted, so a run reports N of M."""
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="lane_board_withdraw_"))
    global _PROJECT_ROOT, _LANES_DIR, BOARD_PATH, RENDER_PATH
    orig = (_PROJECT_ROOT, _LANES_DIR, BOARD_PATH, RENDER_PATH)
    orig_fx = None
    if lane_effects is not None:
        orig_fx = (lane_effects._PROJECT_ROOT, lane_effects._LANES_DIR, lane_effects.EFFECTS_PATH)
    results: list = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        results.append((name, bool(condition), detail))

    def run(argv: list) -> tuple:
        code, out, err = _run_cli(argv)
        try:
            parsed = json.loads(out) if code == 0 else {}
        except ValueError:
            parsed = {}
        return code, parsed, err

    def refused(name: str, argv: list, needle: str) -> None:
        code, _out, err = run(argv)
        check(name, code == 1 and needle in err,
              f"expected exit 1 containing {needle!r}; got exit {code}: {err.strip()[:240]}")

    def accepted(name: str, argv: list):
        code, parsed, err = run(argv)
        check(name, code == 0, f"expected exit 0; got exit {code}: {err.strip()[:240]}")
        return parsed

    def to_state(item: str, lane: str, model: str, last: str) -> None:
        for state in ("CLAIMED", "BUILDING", "CHECKPOINT-READY"):
            evidence = f"pytest -q: 12 passed ({item})" if state == "CHECKPOINT-READY" else ""
            ok, why = set_state(item, state, lane, "executor", model, evidence=evidence)
            check(f"setup {item} -> {state}", ok, str(why))
            if state == last:
                return

    coord = ["--lane", "coord", "--model", "claude-opus-4-8"]
    try:
        _PROJECT_ROOT = tmp
        _LANES_DIR = tmp / ".claude" / "lanes"
        BOARD_PATH = _LANES_DIR / "board.jsonl"
        RENDER_PATH = tmp / "LANE-BOARD.md"
        if lane_effects is not None:
            lane_effects._PROJECT_ROOT = tmp
            lane_effects._LANES_DIR = _LANES_DIR
            lane_effects.EFFECTS_PATH = _LANES_DIR / "effects.json"

        to_state("W-A", "exec-a", "claude-opus-4-8", "CHECKPOINT-READY")
        to_state("W-B", "exec-b", "claude-sonnet-5", "CHECKPOINT-READY")
        to_state("W-C", "exec-c", "gpt-5.6", "BUILDING")  # its lane dies here
        set_state("W-OUT", "CLAIMED", "exec-o", "executor", "gemini-3")
        accepted("setup compete TASK-W", ["compete", "--task", "TASK-W", "--items", "W-A,W-B,W-C", *coord])
        reviewer = ["--lane", "rev-x", "--model", "gemini-3"]

        # the defect: one dead candidate keeps the task undecidable, even for a DEFERRED
        refused("before any withdrawal the dead candidate blocks select",
                ["select", "--task", "TASK-W", "--winner", "W-A", *reviewer], "W-C is BUILDING")
        refused("before any withdrawal the dead candidate blocks DEFERRED",
                ["select", "--task", "TASK-W", "--checker-unavailable", *reviewer], "W-C is BUILDING")

        # --- withdraw: refusals ---
        why = ["--reason", "lane exec-c died mid-build"]
        refused("withdraw on a task never declared",
                ["withdraw", "--task", "TASK-NONE", "--item", "W-C", *coord, *why], "no competition declared")
        refused("withdraw an item that is not a candidate",
                ["withdraw", "--task", "TASK-W", "--item", "W-OUT", *coord, *why], "not a candidate")
        refused("withdraw without a reason",
                ["withdraw", "--task", "TASK-W", "--item", "W-C", *coord, "--reason", "  "], "requires --reason")
        refused("withdraw by the lane of a rival candidate",
                ["withdraw", "--task", "TASK-W", "--item", "W-C", "--lane", "exec-a", "--model", "claude-opus-4-8",
                 *why], "builder of candidate W-A")

        # --- CONTROL: a valid withdrawal is accepted and recorded ---
        event = accepted("CONTROL withdraw the dead candidate",
                         ["withdraw", "--task", "TASK-W", "--item", "W-C", *coord, *why])
        check("the withdrawal is a competition event",
              event.get("kind") == "competition" and event.get("state") == "WITHDRAWN"
              and event.get("task_id") == "TASK-W", str(event))
        check("the withdrawal names the item and the reason",
              event.get("item") == "W-C" and event.get("reason") == "lane exec-c died mid-build", str(event))
        check("the withdrawal event is not read as an event of the item",
              all(e.get("kind") != "competition" for e in _read_events("W-C")), str(_read_events("W-C")))
        check("the withdrawn item is WITHDRAWN", (_latest_state("W-C") or {}).get("state") == "WITHDRAWN",
              str(_latest_state("W-C")))
        refused("a withdrawn item cannot move on",
                ["set", "W-C", "CHECKPOINT-READY", "--lane", "exec-c", "--role", "executor", "--model", "gpt-5.6",
                 "--evidence", "exit=0"], "invalid transition")
        refused("`set` cannot forge WITHDRAWN",
                ["set", "W-B", "WITHDRAWN", "--lane", "coord", "--role", "coordinator", "--model", "gpt-5.6"],
                "invalid transition")
        refused("withdraw the same item twice",
                ["withdraw", "--task", "TASK-W", "--item", "W-C", *coord, *why], "already withdrawn")
        if lane_effects is not None:
            owed = [(r["item_id"], r["decision"], r["target"]) for r in lane_effects.pending_effects()]
            check("the withdrawn lane is owed the news", ("W-C", "WITHDRAWN", "exec-c") in owed, str(owed))

        code, shown, _err = _run_cli(["status", "TASK-W"])
        check("status <task> shows the withdrawal", code == 0 and '"WITHDRAWN"' in shown and '"W-C"' in shown,
              shown[:240])
        code, shown, _err = _run_cli(["status", "W-C"])
        check("status <item> shows the withdrawal", code == 0 and '"WITHDRAWN"' in shown, shown[:240])
        rendered = render()
        for needle in ("withdrawn: W-C", "WITHDRAWN · item: W-C", "reason: lane exec-c died mid-build",
                       "## W-C — WITHDRAWN"):
            check(f"render shows {needle!r}", needle in rendered, rendered[-600:])

        # --- the withdrawn item stops counting for readiness and for selection ---
        deferred = accepted("after the withdrawal DEFERRED is recorded",
                            ["select", "--task", "TASK-W", "--checker-unavailable", *reviewer])
        check("the DEFERRED lists only the remaining candidates", deferred.get("candidates") == ["W-A", "W-B"],
              str(deferred))
        refused("a withdrawn item cannot be the winner",
                ["select", "--task", "TASK-W", "--winner", "W-C", *reviewer], "was withdrawn")
        refused("the withdrawn lane still cannot select the task it attempted",
                ["select", "--task", "TASK-W", "--winner", "W-A", "--lane", "exec-c", "--model", "gemini-3"],
                "SAME lane")

        accepted("withdraw a second candidate, leaving one",
                 ["withdraw", "--task", "TASK-W", "--item", "W-B", *coord, "--reason", "lane exec-b went silent"])
        refused("withdraw the last remaining candidate",
                ["withdraw", "--task", "TASK-W", "--item", "W-A", *coord, "--reason", "no reason is enough"],
                "at least 1 candidate")
        chosen = accepted("CONTROL select the one remaining candidate (another family than it; the withdrawn "
                          "gpt attempt no longer counts)",
                          ["select", "--task", "TASK-W", "--winner", "W-A", "--lane", "rev-g", "--model", "gpt-5.6"])
        check("the selection compares only the remaining candidate",
              chosen.get("winner") == "W-A" and chosen.get("not_selected") == []
              and sorted((chosen.get("compared") or {}).keys()) == ["W-A"], str(chosen))
        check("the selection lists the withdrawn items", chosen.get("withdrawn") == ["W-C", "W-B"], str(chosen))
        refused("withdraw from a decided task",
                ["withdraw", "--task", "TASK-W", "--item", "W-A", *coord, "--reason", "too late"], "already decided")
        for state, extra in (("UNDER-REVIEW", {}),
                             ("VERIFIED", {"verdict_by_lane": "rev-a", "verdict_by_model": "gpt-5.6"})):
            ok, detail = set_state("W-A", state, "exec-a", "reviewer" if extra else "executor",
                                   "gpt-5.6" if extra else "claude-opus-4-8", **extra)
            check(f"setup W-A -> {state}", ok, str(detail))
        accepted("the winner merges after the selection",
                 ["set", "W-A", "MERGED", "--lane", "rev-a", "--role", "reviewer", "--model", "gpt-5.6"])
    finally:
        _PROJECT_ROOT, _LANES_DIR, BOARD_PATH, RENDER_PATH = orig
        if orig_fx is not None:
            lane_effects._PROJECT_ROOT, lane_effects._LANES_DIR, lane_effects.EFFECTS_PATH = orig_fx
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [(name, detail) for name, ok, detail in results if not ok]
    if failed:
        print(f"self-test FAILED (withdraw) — {len(results) - len(failed)} of {len(results)} checks passed",
              file=sys.stderr)
        for name, detail in failed:
            print(f"  FAIL {name}: {detail}", file=sys.stderr)
        return 1
    print(f"self-test OK (withdraw) — {len(results)} of {len(results)} checks: a dead candidate blocks select "
          "and DEFERRED until withdrawn; withdraw refuses an undeclared task, a non-candidate, an empty reason, "
          "a rival candidate's lane, a second withdrawal, the last candidate and a decided task; the CONTROL "
          "withdrawal lands as a competition event, the item is WITHDRAWN and owed the news, status and render "
          "show it, and the one remaining candidate is selected and merged")
    return 0


def _self_test_evidence_record() -> int:
    """`set <item> CHECKPOINT-READY --evidence-record` through the CLI. The fail-closed branch (the
    HPP core absent) always runs, by hiding the core from the import system; the branch that verifies
    real records runs only when the core is importable, and the summary says which branches ran."""
    import importlib
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="lane_board_record_"))
    global _PROJECT_ROOT, _LANES_DIR, BOARD_PATH, RENDER_PATH
    orig = (_PROJECT_ROOT, _LANES_DIR, BOARD_PATH, RENDER_PATH)
    orig_fx = None
    if lane_effects is not None:
        orig_fx = (lane_effects._PROJECT_ROOT, lane_effects._LANES_DIR, lane_effects.EFFECTS_PATH)
    results: list = []
    missing = object()
    hidden = ("hpp", "hpp.evidence")

    def check(name: str, condition: bool, detail: str = "") -> None:
        results.append((name, bool(condition), detail))

    def to_building(item: str, lane: str, model: str = "claude-opus-4-8") -> None:
        for state in ("CLAIMED", "BUILDING"):
            ok, why = set_state(item, state, lane, "executor", model)
            check(f"setup {item} -> {state}", ok, str(why))

    def state_of(item: str) -> str:
        return (_latest_state(item) or {}).get("state", "")

    ex = ["--lane", "exec-a", "--role", "executor", "--model", "claude-opus-4-8"]
    try:
        core = importlib.import_module("hpp.evidence")
    except ImportError:
        core = None
    try:
        _PROJECT_ROOT = tmp
        _LANES_DIR = tmp / ".claude" / "lanes"
        BOARD_PATH = _LANES_DIR / "board.jsonl"
        RENDER_PATH = tmp / "LANE-BOARD.md"
        if lane_effects is not None:
            lane_effects._PROJECT_ROOT = tmp
            lane_effects._LANES_DIR = _LANES_DIR
            lane_effects.EFFECTS_PATH = _LANES_DIR / "effects.json"

        # --- the usage docstring names only commands the parser has ---
        parser = build_parser()
        commands = {name for action in parser._actions if isinstance(action, argparse._SubParsersAction)
                    for name in action.choices}
        named = re.findall(r"python lane_board\.py (\S+)", __doc__ or "")
        stale = [word for word in named if word not in commands and word != "--self-test"]
        check("usage docstring names only real subcommands", named and not stale, f"not a subcommand: {stale}")
        check("usage docstring documents --evidence-record", "--evidence-record" in (__doc__ or ""))

        # --- the HPP core absent: the flag fails closed (exit 2), nothing is written ---
        saved = {name: sys.modules.get(name, missing) for name in hidden}
        try:
            for name in hidden:
                sys.modules[name] = None  # type: ignore[assignment] -- makes `import hpp.evidence` raise ImportError
            to_building("ITEM-R1", "exec-a")
            code, _out, err = _run_cli(["set", "ITEM-R1", "CHECKPOINT-READY", "--evidence-record",
                                        ".hpp/evidence/any.json", *ex])
            check("--evidence-record without the HPP core exits 2 naming the core",
                  code == 2 and "HPP core" in err, f"exit {code}: {err.strip()[:240]}")
            code, _out, err = _run_cli(["set", "ITEM-R1", "CHECKPOINT-READY", "--evidence", "pytest -q: 3 passed",
                                        "--evidence-record", ".hpp/evidence/any.json", *ex])
            check("without the core the free text does not stand in for the record (no silent downgrade)",
                  code == 2 and "HPP core" in err, f"exit {code}: {err.strip()[:240]}")
            check("a fail-closed refusal writes nothing", state_of("ITEM-R1") == "BUILDING", state_of("ITEM-R1"))
            code, _out, err = _run_cli(["set", "ITEM-R1", "BUILDING", "--evidence-record",
                                        ".hpp/evidence/any.json", *ex])
            check("--evidence-record on a state other than CHECKPOINT-READY is a usage error",
                  code == 2 and "CHECKPOINT-READY" in err, f"exit {code}: {err.strip()[:240]}")
            # CONTROL: without the flag nothing imports the core, and the free-text path is unchanged
            code, out, err = _run_cli(["set", "ITEM-R1", "CHECKPOINT-READY", "--evidence", "pytest -q: 3 passed", *ex])
            event = json.loads(out) if code == 0 else {}
            check("CONTROL free-text --evidence still lands with the core absent", code == 0,
                  f"exit {code}: {err.strip()[:240]}")
            check("CONTROL the free-text event has exactly the keys it always had",
                  sorted(event) == ["evidence", "item_id", "lane_id", "model", "role", "state", "tag", "ts"],
                  str(sorted(event)))
        finally:
            for name, module in saved.items():
                if module is missing:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module

        # --- render shows the stored id + sha256 prefix and never re-hashes (the file is absent) ---
        stored = {"path": ".hpp/evidence/gone.json", "record_sha256": "0123456789abcdef" * 4, "id": "e2e-gone"}
        to_building("ITEM-R2", "exec-r")
        _append_event({"ts": "2026-01-01T00:00:00", "item_id": "ITEM-R2", "state": "CHECKPOINT-READY",
                       "lane_id": "exec-r", "role": "executor", "model": "claude-opus-4-8",
                       "evidence_record": stored})
        rendered = render()
        check("render shows the record id and a sha256 prefix",
              "record: e2e-gone sha256:0123456789ab" in rendered, rendered[-400:])
        check("render prints a prefix, never the whole stored hash", stored["record_sha256"] not in rendered)

        # --- select compares a checkpoint whose only evidence is a record (forged: the board writes
        # one only after the core verified it) ---
        to_building("ITEM-R3", "exec-s", "claude-sonnet-5")
        ok, why = set_state("ITEM-R3", "CHECKPOINT-READY", "exec-s", "executor", "claude-sonnet-5",
                            evidence="pytest -q: 3 passed (ITEM-R3)")
        check("setup ITEM-R3 -> CHECKPOINT-READY", ok, str(why))
        code, _out, err = _run_cli(["compete", "--task", "TASK-R", "--items", "ITEM-R2,ITEM-R3",
                                    "--lane", "coord", "--model", "claude-opus-4-8"])
        check("setup compete TASK-R", code == 0, err.strip()[:240])
        code, out, err = _run_cli(["select", "--task", "TASK-R", "--winner", "ITEM-R2",
                                   "--lane", "rev-x", "--model", "gpt-5.6"])
        chosen = json.loads(out) if code == 0 else {}
        check("select accepts a candidate whose checkpoint carries a record instead of free text", code == 0,
              f"exit {code}: {err.strip()[:240]}")
        check("select records the compared record",
              ((chosen.get("compared") or {}).get("ITEM-R2") or {}).get("evidence_record") == stored, str(chosen))

        # --- the HPP core present: only `valid` is accepted, and the event keeps {path, record_sha256, id} ---
        if core is not None:
            write = [sys.executable, "-c", "import sys; open(sys.argv[1], 'w').write('ok')"]
            good = core.run_evidence("rec-ok", [*write, "out.txt"], ["out.txt"], root=tmp)
            to_building("ITEM-P1", "exec-a")
            code, out, err = _run_cli(["set", "ITEM-P1", "CHECKPOINT-READY", "--evidence-record",
                                       good["record_path"], *ex])
            event = json.loads(out) if code == 0 else {}
            check("a valid record is accepted on its own", code == 0, f"exit {code}: {err.strip()[:240]}")
            check("the event stores {path, record_sha256, id}",
                  event.get("evidence_record") == {"path": good["record_path"],
                                                   "record_sha256": good["record_sha256"], "id": "rec-ok"},
                  str(event))
            check("render shows the verified record",
                  f"record: rec-ok sha256:{good['record_sha256'][:12]}" in render(), render()[-400:])

            failed = core.run_evidence("rec-fail", [sys.executable, "-c", "import sys; sys.exit(3)"], [], root=tmp)
            edited_path = tmp / ".hpp" / "evidence" / "rec-edited.json"
            edited = json.loads((tmp / good["record_path"]).read_text(encoding="utf-8"))
            edited["duration_s"] = 0.0 if edited.get("duration_s") else 1.0
            edited_path.write_text(json.dumps(edited), encoding="utf-8")
            changed = core.run_evidence("rec-art", [*write, "out2.txt"], ["out2.txt"], root=tmp)
            (tmp / "out2.txt").write_text("changed after the run", encoding="utf-8")
            for index, (name, path, needle) in enumerate((
                    ("a not-evidence record (the run failed) is refused", failed["record_path"], "not-evidence"),
                    ("an edited record is refused as blocked", ".hpp/evidence/rec-edited.json", "blocked"),
                    ("a record whose artifact changed is refused as blocked", changed["record_path"], "blocked"),
                    ("a record that does not exist is refused", ".hpp/evidence/nope.json", "not readable"))):
                item = f"ITEM-N{index}"
                to_building(item, "exec-a")
                code, _out, err = _run_cli(["set", item, "CHECKPOINT-READY", "--evidence-record", path, *ex])
                check(name, code == 1 and "refused" in err and needle in err, f"exit {code}: {err.strip()[:240]}")
                check(f"{name}: nothing written", state_of(item) == "BUILDING", state_of(item))
    finally:
        _PROJECT_ROOT, _LANES_DIR, BOARD_PATH, RENDER_PATH = orig
        if orig_fx is not None:
            lane_effects._PROJECT_ROOT, lane_effects._LANES_DIR, lane_effects.EFFECTS_PATH = orig_fx
        shutil.rmtree(tmp, ignore_errors=True)

    failed_checks = [(name, detail) for name, ok, detail in results if not ok]
    branch = ("HPP core importable: the valid / not-evidence / blocked branch ran" if core is not None else
              "HPP core NOT importable: the valid / not-evidence / blocked branch did NOT run "
              "(put the core on PYTHONPATH to include it)")
    if failed_checks:
        print(f"self-test FAILED (evidence record) — {len(results) - len(failed_checks)} of {len(results)} "
              f"checks passed; {branch}", file=sys.stderr)
        for name, detail in failed_checks:
            print(f"  FAIL {name}: {detail}", file=sys.stderr)
        return 1
    print(f"self-test OK (evidence record) — {len(results)} of {len(results)} checks; {branch}. Always: the "
          "usage docstring names real subcommands, --evidence-record without the core exits 2 and writes "
          "nothing, the free-text path is unchanged (CONTROL), render shows a stored id + sha256 prefix "
          "without re-hashing, select compares a record-only checkpoint")
    return 0


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
    s.add_argument("--evidence-record", default="",
                   help="CHECKPOINT-READY only: an hpp.evidence/v1 record, verified through the HPP core")
    s.add_argument("--verdict-by-lane", default="")
    s.add_argument("--verdict-by-model", default="")
    s.add_argument("--checker-unavailable", action="store_true")
    s.add_argument("--human-approved", action="store_true")
    s.add_argument("--tag", default="green", choices=["green", "red"])

    co = sub.add_parser("compete", help="declare 2+ claimed items as candidates for the same task")
    co.add_argument("--task", required=True)
    co.add_argument("--items", required=True, help="comma-separated item ids, at least 2, one lane each")
    co.add_argument("--lane", required=True, help="the lane declaring the competition")
    co.add_argument("--model", required=True)

    se = sub.add_parser("select", help="record the winner of a competition (reviewer: another lane AND family)")
    se.add_argument("--task", required=True)
    se.add_argument("--winner", default="")
    se.add_argument("--lane", required=True, help="the reviewer's lane")
    se.add_argument("--model", required=True, help="the reviewer's model")
    se.add_argument("--reason", default="")
    se.add_argument("--checker-unavailable", action="store_true",
                    help="no reviewer available: record DEFERRED, never a winner")

    wd = sub.add_parser("withdraw", help="take one candidate out of an undecided competition (its lane died)")
    wd.add_argument("--task", required=True)
    wd.add_argument("--item", required=True, help="the candidate to take out")
    wd.add_argument("--lane", required=True, help="the coordinator's lane")
    wd.add_argument("--model", required=True)
    wd.add_argument("--reason", required=True, help="why the candidate leaves the competition")

    st = sub.add_parser("status")
    st.add_argument("item_id", nargs="?")

    sub.add_parser("render")
    p.add_argument("--self-test", action="store_true")
    return p


def main(argv) -> int:
    args = build_parser().parse_args(argv)

    if args.self_test:
        return _self_test() or _self_test_compete() or _self_test_withdraw() or _self_test_evidence_record()

    if args.cmd == "claim":
        ok, result = set_state(args.item_id, "CLAIMED", args.lane, args.role, args.model, tag=args.tag)
    elif args.cmd == "set":
        record = None
        if args.evidence_record:
            if args.state != "CHECKPOINT-READY":
                print(f"lane_board: --evidence-record applies only to CHECKPOINT-READY (got: {args.state})",
                      file=sys.stderr)
                return 2
            # Why: verified before the board lock is taken — hashing a large trace under the lock
            # would make every other lane's write time out.
            try:
                accepted, record = verify_evidence_record(args.evidence_record)
            except EvidenceCoreMissing as exc:
                print(f"lane_board: --evidence-record needs the HPP core (`python -m hpp`), which is not "
                      f"importable here ({exc}) — nothing was written; install the core or put it on "
                      f"PYTHONPATH (free-text --evidence does not need it)", file=sys.stderr)
                return 2
            if not accepted:
                print(f"lane_board: refused — {record}", file=sys.stderr)
                return 1
        ok, result = set_state(
            args.item_id, args.state, args.lane, args.role, args.model,
            evidence=args.evidence, verdict_by_lane=args.verdict_by_lane, verdict_by_model=args.verdict_by_model,
            checker_unavailable=args.checker_unavailable, human_approved=args.human_approved, tag=args.tag,
            evidence_record=record,
        )
    elif args.cmd == "compete":
        items = [item.strip() for item in args.items.split(",") if item.strip()]
        ok, result = compete(args.task, items, args.lane, args.model)
    elif args.cmd == "select":
        ok, result = select(args.task, args.winner, args.lane, args.model, reason=args.reason,
                            checker_unavailable=args.checker_unavailable)
    elif args.cmd == "withdraw":
        ok, result = withdraw(args.task, args.item, args.lane, args.model, args.reason)
    elif args.cmd == "status":
        events = _read_events(args.item_id)
        if args.item_id and not events:
            events = _competitions().get(args.item_id, [])
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
        print("usage: claim|set|compete|select|withdraw|status|render [...] or --self-test", file=sys.stderr)
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
