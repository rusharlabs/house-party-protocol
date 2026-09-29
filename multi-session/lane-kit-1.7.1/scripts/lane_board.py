#!/usr/bin/env python3
"""
lane_board -- whiteboard with a state machine for N sessions (lanes) without collision.

Sole writer of board.jsonl (append-only, per-directory lock). Enforcement IN CODE
(not textual discipline): CHECKPOINT-READY only by whoever claimed it + evidence; VERIFIED/NEEDS-FIX
only by a reviewer from ANOTHER lane AND ANOTHER model family than every lane that built the item
(maker!=checker); an unavailable checker -> only DEFERRED; MERGED requires a prior VERIFIED (+ the human
gate for a red item: `--human-approved`, or an approval recorded by `approve`; the tag belongs to the
item, so red stays red whatever a later --tag says).

States: CLAIMED -> BUILDING -> CHECKPOINT-READY -> UNDER-REVIEW -> VERIFIED|NEEDS-FIX -> MERGED
                                                                  -> DEFERRED (checker unavailable)
        NEEDS-FIX -> FIX-QUEUED -> BUILDING (only by the lane named; written only by `release-fix`)
        VERIFIED -> APPROVED -> MERGED (a red item; APPROVED written only by `approve`)
        CHECKPOINT-READY|VERIFIED -> NOT-SELECTED (terminal; written only by `select`)
        any state of an undecided candidate -> WITHDRAWN (terminal; written only by `withdraw`)

Operator hand-offs (what the Lane Dashboard calls; no agent is started by this file): `release-fix`
routes a NEEDS-FIX to a registered, live executor that the board would let build it, and
`start-review` opens a review for a registered, live reviewer that is not a builder of the item. Both
write a `## To:` kickoff to the mailbox (the directory lanes.yaml names) and ring the Codex doorbell
of the target lane like a verdict does. `approve` records the operator's approval of a red VERIFIED
item as APPROVED — never as MERGED: MERGED stays the record of an integration that happened.

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
                          [--branch <branch>]
    python lane_board.py set <item_id> <state> --lane <id> --role <role> --model <model>
                          [--evidence "..."] [--evidence-record <record.json>]
                          [--verdict-by-lane <id>] [--verdict-by-model <m>]
                          [--checker-unavailable] [--human-approved] [--branch <branch>]
        --evidence-record (CHECKPOINT-READY only) attaches an `hpp.evidence/v1` record, verified through
        the optional HPP core (`python -m hpp`): accepted only when the core reports `valid` (an intact
        record of a passed run); the event stores {path, record_sha256, id}. Without the core: exit 2.
        --branch (CLAIMED, BUILDING, CHECKPOINT-READY only) records the branch the builder works on,
        so a reader can ask git about the builder's work and never about a reviewer's checkout.
    python lane_board.py compete --task <task_id> --items A,B[,C...] --lane <id> --model <model>
    python lane_board.py select --task <task_id> --winner <item_id> --lane <reviewer> --model <m>
                          [--reason "..."]
    python lane_board.py select --task <task_id> --checker-unavailable --lane <reviewer> --model <m>
    python lane_board.py withdraw --task <task_id> --item <item_id> --lane <coordinator> --model <m>
                          --reason "..."
    python lane_board.py release-fix <item_id> --target-lane <executor> [--operator <name>]
    python lane_board.py start-review <item_id> --target-lane <reviewer> [--operator <name>]
    python lane_board.py approve <item_id> [--operator <name>]
    python lane_board.py status [<item_id>]
    python lane_board.py render
    python lane_board.py --self-test

Delivery (default ON; `mailbox.notify_on_verdict: false` in `.claude/lanes/lanes.yaml` turns it off):
the board itself writes the mailbox message a verdict owes the builder lane (`## To: <lane>`, item,
verdict, reason, evidence, round) and marks the reservation `delivered` with the message path as
evidence — idempotent by `reservation_id`: a retry writes no second message, a new round writes its
own. With the flag false nothing is written and the reservation stays `pending`.

Exit: 0 ok - 1 invalid transition/enforcement refused - 2 invalid usage/lock not acquired.
stdlib only. v1.0.0 -- 2026-07-10 (lane-kit) · compete/select -- 2026-09-24 (lane-kit 1.4.0)
· withdraw -- 2026-09-24 (lane-kit 1.4.1) · notify_on_verdict -- lane-kit 1.6.x
· release-fix/start-review/approve -- Lane Dashboard, contributed by @kleinelizeu (PR #18)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
try:
    import lane_effects  # noqa: E402 — same kit, same directory
except ImportError:  # pragma: no cover — a partial copy install still runs the board
    lane_effects = None  # type: ignore[assignment]
try:
    import _lane_io  # noqa: E402 — same kit, sibling directory: the lanes.yaml loader
except ImportError:  # pragma: no cover — a copy install that took only scripts/ keeps today's behaviour
    _lane_io = None  # type: ignore[assignment]

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
# The start of every lock refusal; main() maps it to exit 2, as the docstring and the lane-coordinator
# skill promise (busy, try again), apart from a refused transition (exit 1).
_LOCK_REFUSED = "lock not acquired within"

_TRANSITIONS = {
    None: {"CLAIMED"},
    "CLAIMED": {"BUILDING", "CLAIMED"},
    "BUILDING": {"CHECKPOINT-READY", "BUILDING"},
    "CHECKPOINT-READY": {"UNDER-REVIEW"},
    "UNDER-REVIEW": {"VERIFIED", "NEEDS-FIX", "DEFERRED"},
    # A NEEDS-FIX is resumed by a builder directly, or routed by the operator to a named executor.
    # FIX-QUEUED is written only by `release-fix`, and only the lane it names may leave it.
    "NEEDS-FIX": {"BUILDING", "FIX-QUEUED"},
    "FIX-QUEUED": {"BUILDING"},
    # APPROVED is the operator's approval of a red item, written only by `approve`; it is not a merge,
    # so it still leads to MERGED, which only the integration itself should record.
    "VERIFIED": {"MERGED", "APPROVED"},
    "APPROVED": {"MERGED"},
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
            # Why: on Windows a lock directory another writer is removing stays "delete pending" for an
            # instant, and mkdir on it answers access denied, not "exists". That is a busy lock: it
            # escaped as a crash, and the write (a concurrent claim) was lost with a traceback.
            except (FileExistsError, PermissionError) as exc:
                if time.monotonic() > deadline:
                    reason = f" (last answer: {exc})" if isinstance(exc, PermissionError) else ""
                    raise LockError(f"{_LOCK_REFUSED} {self.timeout}s: {self.path}{reason}")
                time.sleep(0.01)

    def __exit__(self, *exc):
        if self._acquired:
            try:
                os.rmdir(self.path)
            except OSError:
                pass


# Why (review of PR #18, DASH-MODEL-IDENTITY): the family is the alphabetic prefix of the id, and one
# vendor answers to several prefixes. A builder on `gpt-5.6-sol` and a reviewer recorded as `codex-mini`
# or `o3` counted as two families although both are OpenAI models, so an OpenAI checker passed on OpenAI
# work. The aliases fold into `gpt`; `o` counts only before a digit, so `olmo-2` stays its own family.
# Why (DASH-CURSOR-FAMILY): the same held for Anthropic. Cursor Agent names its models by tier
# (`sonnet-4-thinking`, `opus-4.1`), hosted ids carry a vendor prefix (`anthropic/claude-...`,
# `us.anthropic.claude-...`), and each of those read as a family apart from `claude` -- so a Sonnet
# reviewer passed on Claude work. Every alias of a vendor folds into ONE name, the one the kit records.
# A word that names no model (`auto`, `default`: the CLI chooses) has no family: "" -- and a verdict from
# a model of no nameable family is refused, because a family nobody can name is not a family anybody checked.
_FAMILY_ALIASES = {
    "gpt": ("gpt", "codex", "openai", "chatgpt"),
    "claude": ("claude", "anthropic", "sonnet", "opus", "haiku", "fable"),
    "gemini": ("gemini", "google"),
}
_ALIAS_TO_FAMILY = {alias: family for family, aliases in _FAMILY_ALIASES.items() for alias in aliases}
_UNRESOLVED_MODELS = ("auto", "default")


def _model_family(model: str) -> str:
    """The family of a model id, canonical (heuristic): 'claude-opus-5-5', 'sonnet-4-thinking' and
    'anthropic/claude-3' -> 'claude'; 'codex-*', 'openai/*', 'chatgpt-*', the o-series 'o3' -> 'gpt';
    'google/gemini-3' -> 'gemini'. A vendor the table does not know keeps its own prefix ('grok-4' ->
    'grok'). '' when no family can be named: an empty id, an id that does not start with a letter, or a
    word that lets the CLI choose ('auto', 'default')."""
    text = (model or "").strip().lower()
    if not text or text in _UNRESOLVED_MODELS:
        return ""
    # vendor and region prefixes: `anthropic/claude-...`, `us.anthropic.claude-...`, `openai/gpt-...`
    for token in re.split(r"[/.]", text):
        word = re.match(r"^([a-z]+)", token)
        if word and word.group(1) in _ALIAS_TO_FAMILY:
            return _ALIAS_TO_FAMILY[word.group(1)]
        if re.match(r"^o\d", token):
            return "gpt"
    m = re.match(r"^([a-z]+)", text.rsplit("/", 1)[-1])
    return m.group(1) if m else ""


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


def _item_tag(item_id: str) -> str:
    """red once any event of the item said red. The tag belongs to the item, not to a command line:
    reading it from `--tag` let a caller who omitted the flag (default green) merge a red item
    without the human gate, and record it as green on the way. (Found by @kleinelizeu, PR #18.)"""
    return "red" if any(e.get("tag") == "red" for e in _read_events(item_id)) else "green"


def _approved(item_id: str) -> bool:
    """True once `approve` recorded the operator's approval of the item (an APPROVED event)."""
    return any(e.get("state") == "APPROVED" for e in _read_events(item_id))


def _building_refusal(item_id: str, lane_id: str) -> str | None:
    """Why `lane_id` may not build `item_id`, or None. One rule, read by the transition itself and by
    `release-fix` before it names an executor: a fix queued for a lane that can never write BUILDING
    would sit in FIX-QUEUED with no legal move left (review of PR #18, BOARD-FIX-DEAD-END)."""
    competition = _competition_of(item_id)
    if competition:
        for other in _candidates(competition[1]):
            if other != item_id and lane_id in {lane for lane, _model in _builders(other)}:
                return (f"lane {lane_id} is a builder of candidate {other} of task {competition[0]}; "
                        f"building {item_id} too would make two attempts one")
    return None


def _checkpoint_evidence(item_id: str) -> str:
    """Evidence of the item's most recent CHECKPOINT-READY (a VERIFIED item keeps the one it had)."""
    last = next((e for e in reversed(_read_events(item_id)) if e.get("state") == "CHECKPOINT-READY"), None)
    return (last or {}).get("evidence", "")


def _checkpoint_record(item_id: str) -> dict:
    """The verified evidence record attached to the item's most recent CHECKPOINT-READY, if any."""
    last = next((e for e in reversed(_read_events(item_id)) if e.get("state") == "CHECKPOINT-READY"), None)
    return (last or {}).get("evidence_record") or {}


def _checkpoint_summary(item_id: str) -> str:
    """What a kickoff says about the item's checkpoint: its pasted evidence, its verified record (id, path
    and a sha256 prefix), or both -- '' only when the checkpoint carries neither.

    Why (BOARD-KICKOFF-RECORD): the kickoffs read the textual evidence alone, so a checkpoint whose only
    evidence was a verified record was announced to its reviewer as "No checkpoint evidence on the
    board" -- a false absence, with the record's id and path a field away."""
    parts = []
    evidence = _checkpoint_evidence(item_id)
    if evidence:
        parts.append(evidence)
    record = _checkpoint_record(item_id)
    if record:
        digest = str(record.get("record_sha256") or "")
        parts.append(f"Evidence record: {record.get('id') or '?'} at {record.get('path') or '?'}"
                     + (f" (sha256 {digest[:12]})" if digest else ""))
    return "\n".join(parts)


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

    if new_state == "FIX-QUEUED":
        return "FIX-QUEUED is written only by `release-fix`: the operator routes a fix to a named executor"

    if new_state == "APPROVED":
        return "APPROVED is written only by `approve`: the operator's approval of a red VERIFIED item"

    if new_state == "BUILDING" and cur_state == "FIX-QUEUED" and current.get("target_lane") != lane_id:
        return f"fix released to {current.get('target_lane')}, not to {lane_id}"

    if new_state in ("BUILDING", "CHECKPOINT-READY"):
        refusal = _building_refusal(item_id, lane_id)
        if refusal:
            return refusal

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
        # Why (PR #18, found by @kleinelizeu): a NEEDS-FIX can be rebuilt by an executor of another
        # family (directly, or routed by `release-fix`); comparing only with the claiming model let that
        # executor's own family verify the fix it built. The family rule now reads every builder, as the
        # lane rule above already did.
        if not _model_family(verdict_by_model):
            return (f"cannot tell the family of the reviewer's model '{verdict_by_model}' (an id starts with its "
                    f"family's name; `auto` lets the CLI choose): a family nobody can name is not a family anybody checked")
        builder_families = {_model_family(builder_model)} | {_model_family(m) for _lane, m in _builders(item_id) if m}
        if _model_family(verdict_by_model) in builder_families:
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
        if tag == "red" and not human_approved and not _approved(item_id):
            return ("item 🔴 (tag=red) requires --human-approved for MERGED (human gate), or an approval "
                    "recorded with `approve`")

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
    # Why: `release-fix` routes a fix to another executor, and the verdict on that fix is owed to
    # the lane that built it. Read off the CLAIMED event, it went to the lane the fix was routed away
    # from — often a lane that had stopped, so a message nobody reads was recorded as delivered.
    built = next((e for e in reversed(events) if e["state"] in _BUILDER_STATES and e.get("lane_id")), None)
    target = (built or {}).get("lane_id", "")
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


# ---------------------------------------------------------------------------
# delivery: the mailbox message a verdict owes, written by the board itself
# ---------------------------------------------------------------------------
# Why: the board reserved an effect for every verdict and nothing in the kit ever wrote the mailbox,
# so every delivery was by hand and UNDELIVERED was the steady state. Now the board writes the
# message (routed with the same `## To:` line lane_register.py reads) and marks the reservation
# delivered with the message path as evidence — unless lanes.yaml says `notify_on_verdict: false`.

_MAILBOX_DIR_DEFAULT = ".claude/lanes/mailbox"
_DOORBELL_TIMEOUT_SECONDS = 5
# Why: the registry does not record the host a lane runs on. A `host` field is honoured when an
# entry carries one; otherwise the model family decides — a lane whose model is OpenAI's runs under
# Codex CLI, the one host of this kit with a native way to nudge a running session (`codex queue`).
_OPENAI_FAMILIES = ("gpt", "codex", "openai", "o")

_VERDICT_MESSAGE = """# VERDICT — {item_id} is {state}

> Written by `lane_board.py` (`mailbox.notify_on_verdict` in lanes.yaml). The `## To:` line is the
> literal `lane_register.py` matches to route this message to its lane — keep it exactly as written.

## To: {target}
## From: {sender}
## When: {when}
## Affected item(s): {item_id}

### Verdict
{verdict}

### Why
{reason}

### Evidence
{evidence}

### Round / reservation
round {round_key} · reservation `{reservation_id}` (`lane_effects.py show {reservation_id}`)

---
*Consumption: read this file, act on the verdict, and archive it by moving it to
`{archive}` — never edit it in place; the mailbox is write-once, read-and-archive.*
"""


def _truthy(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "on", "1")
    return bool(value)


def _mailbox_setting() -> dict:
    """What lanes.yaml says about delivery: `notify` (default ON), `doorbell` (default ON), `dir`."""
    if _lane_io is None or lane_effects is None:
        return {"notify": False, "doorbell": False, "dir": None}
    cfg = _lane_io.load_config()
    mailbox_dir = Path(str(_lane_io.get(cfg, "mailbox.dir", _MAILBOX_DIR_DEFAULT)))
    if not mailbox_dir.is_absolute():
        mailbox_dir = _PROJECT_ROOT / mailbox_dir
    return {
        "notify": _truthy(_lane_io.get(cfg, "mailbox.notify_on_verdict", None), True),
        "doorbell": _truthy(_lane_io.get(cfg, "mailbox.native_doorbell", None), True),
        "dir": mailbox_dir,
    }


def _message_name(item_id: str, state: str, reservation_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", item_id) or "item"
    return f"{safe}-{state}-{reservation_id}.md"


def _render_message(record: dict, event: dict, rel: str) -> str:
    verdict_by = event.get("verdict_by") or {}
    if verdict_by:
        sender = f"{verdict_by.get('lane')} ({event.get('role', 'reviewer')}, {verdict_by.get('model')})"
    else:
        sender = f"{event.get('lane_id', '?')} ({event.get('role', '?')}, {event.get('model', '?')})"
    verdict = record["decision"]
    if event.get("task_id"):
        verdict += f" · task {event['task_id']}"
        if event.get("winner"):
            verdict += f" · winner {event['winner']}"
    stored = event.get("evidence_record") if isinstance(event.get("evidence_record"), dict) else {}
    evidence = event.get("evidence") or (f"record {stored.get('id')} at {stored.get('path')}" if stored else "")
    if not evidence:
        evidence = f"(none recorded on this board event — `lane_board.py status {record['item_id']}` has the history)"
    head, _sep, tail = rel.rpartition("/")
    archive = f"{head}/_read/{tail}" if head else f"_read/{tail}"
    return _VERDICT_MESSAGE.format(
        item_id=record["item_id"], state=record["decision"], target=record["target"], sender=sender,
        when=event.get("ts", ""), verdict=verdict,
        reason=event.get("reason") or "(no reason recorded on the board event)", evidence=evidence,
        round_key=record.get("round_key") or "0", reservation_id=record["reservation_id"], archive=archive)


def _lane_runs_on_codex(entry: dict) -> bool:
    host = str(entry.get("host") or "").strip().lower()
    if host:
        return host == "codex"
    return _model_family(str(entry.get("model") or "")) in _OPENAI_FAMILIES


def _ring_doorbell(target: str, text: str) -> str:
    """Nudge a Codex CLI lane that a message is waiting: `codex queue --thread <session> --message <text>`.

    Returns the one-line outcome recorded beside the delivery evidence. Bounded by
    `_DOORBELL_TIMEOUT_SECONDS`, no retry, never raises: the mailbox file IS the delivery, the
    doorbell only shortens the wait for it, so every failure is a note, never a refusal. A Claude
    Code lane gets no doorbell — the host has no CLI equivalent of `codex queue`.
    """
    import shutil
    import subprocess

    try:
        entry = (_lane_io._read_registry().get("lanes") or {}).get(target) if _lane_io is not None else None
    except Exception:  # noqa: BLE001 -- Why: an unreadable registry is a doorbell outcome, not a delivery failure
        entry = None
    if not entry:
        return "none (lane not in the registry)"
    if not _lane_runs_on_codex(entry):
        return "none (claude-code lane: no CLI equivalent of codex queue)"
    exe = shutil.which("codex")
    if not exe:
        return "skipped (codex not on PATH)"
    session = str(entry.get("session_id") or "").strip()
    if not session:
        return "failed (no session id recorded for the lane)"
    try:
        run = subprocess.run([exe, "queue", "--thread", session, "--message", text],
                             capture_output=True, text=True, timeout=_DOORBELL_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return f"failed (timeout after {_DOORBELL_TIMEOUT_SECONDS}s)"
    except OSError as exc:
        return f"failed ({exc.strerror or exc})"
    if run.returncode != 0:
        detail = (run.stderr or run.stdout or "").strip().splitlines()
        return f"failed (exit {run.returncode}{': ' + detail[0][:120] if detail else ''})"
    return f"sent (codex queue --thread {session})"


def _notify_mailbox(reservation_id: str, event: dict, settings: dict | None = None) -> tuple:
    """Write the mailbox message a reservation owes and mark it delivered. Idempotent by reservation_id.

    Returns (ok, message_path_or_reason). A reservation already delivered is left alone — the first
    message and its evidence stand; a message file already on disk is not rewritten; the doorbell
    rings once per delivery and its outcome is recorded beside the evidence. Never raises.
    """
    try:
        settings = settings or _mailbox_setting()
        mailbox_dir = settings.get("dir")
        if lane_effects is None or mailbox_dir is None:
            return False, "no effect ledger or no mailbox directory"
        record = lane_effects.get(reservation_id)
        if record is None:
            return False, f"unknown reservation {reservation_id}"
        if record.get("effect_state") == "delivered":
            return True, record.get("evidence", "")
        mailbox_dir.mkdir(parents=True, exist_ok=True)
        name = _message_name(record["item_id"], record["decision"], reservation_id)
        path = mailbox_dir / name
        try:
            rel = path.relative_to(_PROJECT_ROOT).as_posix()
        except ValueError:
            rel = path.as_posix()
        if not path.exists():
            # `.md.tmp` never matches the mailbox glob, so a half-written message is never routed.
            tmp = path.with_name(name + ".tmp")
            tmp.write_bytes(_render_message(record, event, rel).encode("utf-8"))
            os.replace(tmp, path)
        doorbell = ""
        if settings.get("doorbell"):
            doorbell = _ring_doorbell(record["target"], f"lane-kit mailbox {rel}: {record['item_id']} is "
                                                        f"{record['decision']} (reservation {reservation_id})")
        ok, result = lane_effects.deliver(reservation_id, evidence=rel, doorbell=doorbell)
        if not ok:
            return False, str(result)
        return True, rel
    except Exception as exc:  # noqa: BLE001 -- Why: the verdict is already on the board when this runs;
        # a mailbox that cannot be written must leave the reservation PENDING (visible under
        # UNDELIVERED) instead of failing the write that recorded the verdict.
        return False, str(exc)


def _deliver(owed: list) -> None:
    """After the board lines are appended AND the board lock is released: write the message each
    reservation owes, if delivery is on.

    Outside the lock on purpose: the doorbell may wait its whole timeout on a silent daemon, and the
    board lock spins for only 2s — held that long it would refuse another lane's claim. Reports on
    stderr, never raises, never changes the exit code — the verdict is already recorded, and an
    undelivered one stays visible under UNDELIVERED.
    """
    if not owed:
        return
    try:
        settings = _mailbox_setting()
    except Exception:  # noqa: BLE001 -- Why: an unreadable lanes.yaml must not turn a recorded verdict into a crash
        return
    if not settings.get("notify"):
        return
    for reservation_id, event in owed:
        ok, where = _notify_mailbox(reservation_id, event, settings)
        record = lane_effects.get(reservation_id) or {}
        target = record.get("target", "?")
        if ok:
            bell = f" · doorbell: {record['doorbell']}" if record.get("doorbell") else ""
            print(f"[lane_board] mailbox: {where} -> {target} (reservation {reservation_id} delivered{bell})",
                  file=sys.stderr)
        else:
            print(f"[lane_board] mailbox: reservation {reservation_id} -> {target} NOT delivered ({where}); it "
                  f"stays pending — see `lane_effects.py pending`", file=sys.stderr)


def set_state(item_id: str, new_state: str, lane_id: str, role: str, model: str, **kwargs) -> tuple:
    """Returns (ok, message_or_error). Writes under lock; the mailbox delivery runs AFTER the lock is
    released — a doorbell waiting on its timeout must never hold the board against another lane."""
    branch = kwargs.pop("branch", "")
    try:
        with _Lock(_LANES_DIR):
            if _item_tag(item_id) == "red":
                kwargs["tag"] = "red"  # the tag belongs to the item: a later --tag cannot make it green
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
            if branch and new_state in _BUILDER_STATES:
                event["branch"] = branch
            reservation = _reserve_effect(item_id, new_state)
            if reservation:
                event["reservation_id"] = reservation
            _append_event(event)
    except LockError as e:
        return False, str(e)
    if reservation:
        _deliver([(reservation, event)])
    return True, event


# ---------------------------------------------------------------------------
# operator hand-offs: release-fix, start-review, approve
# ---------------------------------------------------------------------------
# Contributed by @kleinelizeu with the Lane Dashboard (PR #18). The dashboard calls these; a person
# calls them from a terminal the same way. None of them starts an agent.

_KICKOFF_MESSAGE = """# {title} — {item_id}

> Written by `lane_board.py {command}`. The `## To:` line is the literal `lane_register.py` matches to
> route this message to its lane — keep it exactly as written.

## To: {target}
## From: {operator} (operator)
## When: {when}
## Affected item(s): {item_id}

{body}
---
*Consumption: read this file, act on it, and archive it by moving it to `{archive}` — never edit it in
place; the mailbox is write-once, read-and-archive.*
"""


def _lane_liveness(entry: dict) -> str:
    """alive / suspect / dead, by the same rule and config the lane registry uses."""
    if _lane_io is not None:
        return _lane_io.liveness(entry)
    # A copy install that took only scripts/: the registry's default thresholds, heartbeats in UTC.
    try:
        beat = datetime.fromisoformat(str(entry.get("heartbeat_at", "")))
    except ValueError:
        return "dead"
    beat = beat if beat.tzinfo else beat.replace(tzinfo=timezone.utc)
    minutes = (datetime.now(timezone.utc) - beat).total_seconds() / 60
    return "alive" if minutes < 10 else "suspect" if minutes < 30 else "dead"


def _live_lane(lane_id: str, role: str) -> tuple:
    """(registry entry, None) when `lane_id` is a registered, live lane with `role`; else (None, why)."""
    try:
        registry = json.loads((_LANES_DIR / "registry.json").read_text(encoding="utf-8"))
        entry = registry.get("lanes", {}).get(lane_id)
    except (OSError, json.JSONDecodeError, AttributeError):
        return None, "lane registry unavailable (.claude/lanes/registry.json)"
    if not isinstance(entry, dict) or entry.get("role") != role:
        return None, f"target lane is not a registered {role}: {lane_id}"
    state = _lane_liveness(entry)
    if state != "alive":
        return None, f"target lane is not alive ({state}): {lane_id}"
    return entry, None


def _write_kickoff(command: str, item_id: str, target_lane: str, operator: str, body: str) -> str:
    """A write-once mailbox message, in the directory lanes.yaml names (the one `lane_register.py` scans),
    routed with `## To:`. Written under the board lock, BEFORE the event that names it: a hand-off is
    never on the board without its kickoff on disk. `.md.tmp` never matches the mailbox glob. Returns
    the message path, relative to the project when it lies inside it."""
    settings = _mailbox_setting()
    mailbox_dir = settings.get("dir") or (_LANES_DIR / "mailbox")
    kind = "fix" if command == "release-fix" else "review"
    safe_item = re.sub(r"[^A-Za-z0-9._-]+", "-", item_id).strip(".-") or "item"
    name = f"{kind}-{int(time.time() * 1000)}-{safe_item}.md"
    path = mailbox_dir / name
    try:
        rel = path.relative_to(_PROJECT_ROOT).as_posix()
    except ValueError:
        rel = path.as_posix()
    head, _sep, tail = rel.rpartition("/")
    text = _KICKOFF_MESSAGE.format(
        title="FIX KICKOFF" if kind == "fix" else "REVIEW KICKOFF", command=command, item_id=item_id,
        target=target_lane, operator=operator, when=time.strftime("%Y-%m-%dT%H:%M:%S"), body=body,
        archive=f"{head}/_read/{tail}" if head else f"_read/{tail}")
    mailbox_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(name + ".tmp")
    tmp.write_bytes(text.encode("utf-8"))
    os.replace(tmp, path)
    return rel


def _ring_kickoff(event: dict) -> None:
    """After the board lock is released: nudge a Codex target lane that its kickoff is waiting, the same
    doorbell a verdict rings (`mailbox.native_doorbell`), and say on stderr what happened. The kickoff
    file is the delivery; the doorbell only shortens the wait for it, so nothing here can fail the call."""
    try:
        settings = _mailbox_setting()
        target, kickoff = event.get("target_lane", ""), event.get("kickoff", "")
        bell = ""
        if settings.get("doorbell"):
            bell = _ring_doorbell(target, f"lane-kit mailbox {kickoff}: {event.get('item_id')} is "
                                          f"{event.get('state')} for {target}")
        print(f"[lane_board] mailbox: {kickoff} -> {target} (kickoff{' · doorbell: ' + bell if bell else ''})",
              file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 -- Why: the hand-off is already on the board with its kickoff on
        # disk; a registry or config that cannot be read must cost the doorbell, never the recorded hand-off.
        print(f"[lane_board] mailbox: the doorbell could not be rung ({exc})", file=sys.stderr)


def release_fix(item_id: str, target_lane: str, operator: str = "operator") -> tuple:
    """Route a NEEDS-FIX to a named, live executor: FIX-QUEUED + a kickoff. No agent is started here.

    The target must be registered, alive, of role executor, and a lane the board would let build the
    item — a builder of a rival candidate never could, and its FIX-QUEUED would have no way out.
    Reroute valve: a fix already queued can be released again, to ANOTHER lane, only when the lane it
    was queued for is no longer alive; a live lane's fix is not taken from it. The event carries
    `reroute` with the abandoned lane and the measured reason.
    """
    try:
        with _Lock(_LANES_DIR):
            current = _latest_state(item_id)
            current_state = current.get("state") if current else "absent"
            reroute_from, reroute_reason = "", ""
            if current_state == "FIX-QUEUED":
                reroute_from = current.get("target_lane", "")
                if reroute_from == target_lane:
                    return False, f"fix already released to {target_lane} — a reroute needs another lane"
                _entry, reroute_reason = _live_lane(reroute_from, "executor")
                if not reroute_reason:
                    return False, f"fix in progress with {reroute_from}, which is alive — only an abandoned release reroutes"
            elif current_state != "NEEDS-FIX":
                return False, f"release-fix needs an item in NEEDS-FIX (current: {current_state})"
            target, target_error = _live_lane(target_lane, "executor")
            if target_error:
                return False, target_error
            refusal = _building_refusal(item_id, target_lane)
            if refusal:
                return False, f"{target_lane} could never take this fix: {refusal}"
            review = next((e for e in reversed(_read_events(item_id)) if e.get("state") == "NEEDS-FIX"), {})
            checkpoint = _checkpoint_summary(item_id)
            body = (f"### What changed\nA reviewer recorded `NEEDS-FIX`. You run the next attempt.\n\n"
                    f"### Direction of the fix\n{review.get('evidence') or 'The reviewer left no evidence on the board.'}\n\n"
                    f"### Previous checkpoint\n{checkpoint or 'No checkpoint evidence on the board.'}\n\n"
                    f"### What the target lane must do\n"
                    f"- [ ] Take the fix: `lane_board.py set {item_id} BUILDING --lane {target_lane} --role executor "
                    f"--model <the model you run> --branch <your branch>`\n"
                    f"- [ ] Fix the blocker and run the applicable gates.\n"
                    f"- [ ] Record `CHECKPOINT-READY` only with objective evidence.\n"
                    f"- [ ] Never review this attempt yourself.\n")
            try:
                kickoff = _write_kickoff("release-fix", item_id, target_lane, operator, body)
            except OSError as error:
                return False, f"kickoff not delivered: {error}"
            event = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "item_id": item_id,
                "state": "FIX-QUEUED",
                "lane_id": operator,
                "role": "operator",
                "model": "human",
                "target_lane": target_lane,
                "target_model": target.get("model", "unknown"),
                "kickoff": kickoff,
                "tag": _item_tag(item_id),
            }
            if reroute_from:
                event["reroute"] = {"from": reroute_from, "reason": reroute_reason}
            _append_event(event)
    except LockError as error:
        return False, str(error)
    _ring_kickoff(event)
    return True, event


def start_review(item_id: str, target_lane: str, operator: str = "operator") -> tuple:
    """Open a review for a named, live reviewer: UNDER-REVIEW + a kickoff.

    The lane is checked here (a builder lane cannot be sent its own work); the model FAMILY is checked
    where the verdict is recorded, as for every review — opening a review is cheap and reversible,
    and refusing it by family would make DEFERRED unreachable when no other family is at hand.
    """
    try:
        with _Lock(_LANES_DIR):
            checkpoint = _latest_state(item_id)
            current_state = checkpoint.get("state") if checkpoint else "absent"
            if current_state not in ("CHECKPOINT-READY", "DEFERRED"):
                return False, f"start-review needs an item in CHECKPOINT-READY or DEFERRED (current: {current_state})"
            builder_lanes = {lane for lane, _model in _builders(item_id)}
            if target_lane in builder_lanes:
                return False, f"maker≠checker violated: {target_lane} built {item_id} and cannot review it"
            target, target_error = _live_lane(target_lane, "reviewer")
            if target_error:
                return False, target_error
            body = (f"### Checkpoint evidence\n{_checkpoint_summary(item_id) or 'No checkpoint evidence on the board.'}\n\n"
                    f"### What the target lane must do\n"
                    f"- [ ] Review the attempt independently and run the applicable gates.\n"
                    f"- [ ] Record `VERIFIED` or `NEEDS-FIX` with evidence and `--verdict-by-lane {target_lane}`.\n"
                    f"- [ ] If you cannot check it, record `DEFERRED --checker-unavailable` — never a verdict.\n"
                    f"- [ ] Do not merge.\n")
            try:
                kickoff = _write_kickoff("start-review", item_id, target_lane, operator, body)
            except OSError as error:
                return False, f"kickoff not delivered: {error}"
            event = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "item_id": item_id,
                "state": "UNDER-REVIEW",
                "lane_id": operator,
                "role": "operator",
                "model": "human",
                "target_lane": target_lane,
                "target_model": target.get("model", "unknown"),
                "kickoff": kickoff,
                "tag": _item_tag(item_id),
            }
            _append_event(event)
    except LockError as error:
        return False, str(error)
    _ring_kickoff(event)
    return True, event


def approve(item_id: str, operator: str = "operator") -> tuple:
    """Record the operator's approval of a red VERIFIED item as APPROVED — never as MERGED.

    Why (review of PR #18, DASH-PREMATURE-MERGED): the dashboard's "approve" wrote MERGED, so an item
    whose branch was still unmerged read as integrated. The approval is the human gate; MERGED is the
    record that the integration happened, written afterwards by whoever integrates (no second
    `--human-approved` is needed once the approval is on the board).
    """
    try:
        with _Lock(_LANES_DIR):
            current = _latest_state(item_id)
            current_state = current.get("state") if current else "absent"
            if current_state != "VERIFIED":
                return False, f"approve needs a VERIFIED item (current: {current_state})"
            if _item_tag(item_id) != "red":
                return False, (f"{item_id} is green: it has no human gate to approve — record MERGED once its "
                               f"work is integrated")
            competition = _competition_of(item_id)
            if competition and not _decided(competition[1]):
                return False, (f"{item_id} is a candidate of task {competition[0]}, which has no winner yet — "
                               f"run `select` before approving")
            event = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "item_id": item_id,
                "state": "APPROVED",
                "lane_id": operator,
                "role": "operator",
                "model": "human",
                "human_approved": True,
                "tag": "red",
            }
            _append_event(event)
            return True, event
    except LockError as error:
        return False, str(error)


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
    if not reviewer_family and not checker_unavailable:
        return (f"cannot tell the family of the reviewer's model '{model}' (an id starts with its family's name; "
                f"`auto` lets the CLI choose): a family nobody can name is not a family anybody checked")
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


def deliberated_choice(task_id: str, record_path: str) -> tuple:
    """(ok, (winner, judge_lane, judge_model, record_sha256) or error) from a sealed design session.

    The session must verify (HPP core), be a `design` session whose options are exactly the task's
    remaining candidates, and have chosen one. Its judge becomes the reviewer of record, so the
    board's own lane and family rules then apply to the judge unchanged.
    """
    try:
        from hpp.deliberation import verify_record
    except ImportError as exc:
        raise EvidenceCoreMissing(str(exc)) from exc
    try:
        record = json.loads(Path(record_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"cannot read the deliberation record: {exc}"
    report = verify_record(record)
    if report["status"] != "intact":
        return False, f"the deliberation record does not verify: {report['reason']}"
    panel = record["panel"]
    if panel["session_type"] != "design":
        return False, f"a competition is decided by a design session, this is a {panel['session_type']} session"
    candidates = _active_candidates(_competitions().get(task_id, []))
    if sorted(panel["question"]["options"]) != sorted(candidates):
        return False, (f"the session's options {sorted(panel['question']['options'])} are not the task's "
                       f"remaining candidates {sorted(candidates)}")
    verdict = record["verdict"]
    if verdict["status"] != "recommendation":
        return False, f"the session did not choose (verdict: {verdict['status']}) — record DEFERRED instead"
    judge = next(seat for seat in panel["seats"] if seat["id"] == panel["judge"])
    return True, (verdict["value"], judge["lane"], judge["model_served"], record["record_sha256"])


def select(task_id: str, winner: str, lane_id: str, model: str, reason: str = "",
           checker_unavailable: bool = False, deliberation: str = "") -> tuple:
    """Records the winner of a competition (or DEFERRED). Returns (ok, event_or_error).

    The competition event names the winner, the losers, the reviewer and the evidence that was
    compared; each loser also gets its own NOT-SELECTED item event, which owes its lane the news
    through the same effect ledger as any verdict. Delivery runs after the lock is released.
    """
    owed: list = []
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
            if deliberation:
                event["deliberation"] = deliberation
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
                    owed.append((reservation, dict(marked, reason=reason)))
                lines.append(marked)
            _append_events(lines)
    except LockError as e:
        return False, str(e)
    _deliver(owed)
    return True, event


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
    except LockError as e:
        return False, str(e)
    if reservation:
        _deliver([(reservation, marked)])
    return True, event


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
            # Why (PR #18): a fix or a review handed to a lane that then died was invisible here; the target
            # lane and any reroute are what the operator needs to see to unstick it.
            target = f" · target: {e['target_lane']}" if e.get("target_lane") else ""
            reroute = e.get("reroute") if isinstance(e.get("reroute"), dict) else {}
            rerouted = f" · rerouted from {reroute.get('from')} ({reroute.get('reason')})" if reroute else ""
            branch = f" · branch: {e['branch']}" if e.get("branch") else ""
            lines.append(f"- {e['ts']} · {e['state']} · lane={e['lane_id']} role={e['role']}{evid}{record}{verdict}"
                         f"{task}{reason}{target}{rerouted}{branch}")
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


def _config_off():
    """Until `_config_restore`: the board reads lanes.yaml as `notify_on_verdict: false` and
    `native_doorbell: false`.

    The self-tests of the state machine measure transitions, not delivery, and must not depend on
    the config of the repository they happen to run in. Returns what to restore.
    """
    if _lane_io is None:
        return None
    orig = _lane_io.load_config
    # Why: a kickoff rings the doorbell outside the notify flag, and a self-test must never reach a real
    # `codex` on the machine that runs it — the doorbell has its own self-test, with fakes.
    _lane_io.load_config = lambda: {"mailbox": {"notify_on_verdict": False, "native_doorbell": False}}
    return orig


def _config_restore(orig) -> None:
    if _lane_io is not None and orig is not None:
        _lane_io.load_config = orig


def _self_test() -> int:
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="lane_board_selftest_"))
    global _PROJECT_ROOT, _LANES_DIR, BOARD_PATH, RENDER_PATH
    orig = (_PROJECT_ROOT, _LANES_DIR, BOARD_PATH, RENDER_PATH)
    orig_fx = None
    if lane_effects is not None:
        orig_fx = (lane_effects._PROJECT_ROOT, lane_effects._LANES_DIR, lane_effects.EFFECTS_PATH)
    orig_cfg = _config_off()
    try:
        _PROJECT_ROOT = tmp
        _LANES_DIR = tmp / ".claude" / "lanes"
        BOARD_PATH = _LANES_DIR / "board.jsonl"
        RENDER_PATH = tmp / "LANE-BOARD.md"
        if lane_effects is not None:
            lane_effects._PROJECT_ROOT = tmp
            lane_effects._LANES_DIR = _LANES_DIR
            lane_effects.EFFECTS_PATH = _LANES_DIR / "effects.json"

        ok1, r1 = set_state("ITEM-1", "CLAIMED", "exec-a", "executor", "claude-opus-5-5")
        assert ok1, f"CLAIMED should pass: {r1}"

        ok2, r2 = set_state("ITEM-1", "BUILDING", "exec-a", "executor", "claude-opus-5-5")
        assert ok2, f"BUILDING should pass: {r2}"

        ok3, r3 = set_state("ITEM-1", "CHECKPOINT-READY", "exec-b", "executor", "claude-opus-5-5", evidence="exit=0")
        assert not ok3 and "owner" in r3, f"CHECKPOINT-READY from the wrong lane should be refused: {r3}"

        ok4, r4 = set_state("ITEM-1", "CHECKPOINT-READY", "exec-a", "executor", "claude-opus-5-5")
        assert not ok4 and "evidence" in r4, f"CHECKPOINT-READY without evidence should be refused: {r4}"

        ok5, r5 = set_state("ITEM-1", "CHECKPOINT-READY", "exec-a", "executor", "claude-opus-5-5", evidence="exit=0 sha=abc")
        assert ok5, f"a valid CHECKPOINT-READY should pass: {r5}"

        ok6, r6 = set_state("ITEM-1", "UNDER-REVIEW", "exec-a", "executor", "claude-opus-5-5")
        assert ok6, f"UNDER-REVIEW should pass: {r6}"

        ok7, r7 = set_state("ITEM-1", "VERIFIED", "exec-a", "reviewer", "claude-opus-5-5", verdict_by_lane="exec-a", verdict_by_model="claude-opus-5-5")
        assert not ok7 and "SAME lane" in r7, f"maker=checker (same lane) should be refused: {r7}"

        ok8, r8 = set_state("ITEM-1", "VERIFIED", "exec-a", "reviewer", "claude-opus-5-5", verdict_by_lane="rev-a", verdict_by_model="claude-opus-5-5")
        assert not ok8 and "SAME model family" in r8, f"maker=checker (same model family) should be refused: {r8}"

        ok9, r9 = set_state("ITEM-1", "VERIFIED", "exec-a", "reviewer", "claude-opus-5-5", verdict_by_lane="rev-a", verdict_by_model="gpt-5.6-sol")
        assert ok9, f"a reviewer on another lane + another family should pass: {r9}"

        # the verdict owes an effect: decided (accepted) and NOT yet delivered
        if lane_effects is not None:
            rid = r9.get("reservation_id")
            assert rid, f"a verdict must reserve an effect: {r9}"
            fx = lane_effects.get(rid)
            assert fx["state"] == "accepted" and fx["effect_state"] == "pending", fx
            assert fx["target"] == "exec-a", f"the effect must aim at the builder lane: {fx}"
            assert [r["item_id"] for r in lane_effects.pending_effects()] == ["ITEM-1"], lane_effects.pending_effects()
            # CONTROL: with `notify_on_verdict: false` the board writes nothing — delivery is by hand, as before
            assert not (_LANES_DIR / "mailbox").exists(), "notify_on_verdict false must not write a mailbox"
            assert sorted(r9) == ["item_id", "lane_id", "model", "reservation_id", "role", "state", "ts", "verdict_by"], r9
            lane_effects.deliver(rid, evidence="mailbox/proof.md")
            assert lane_effects.pending_effects() == [], "delivering did not clear the outstanding list"

        ok10, r10 = set_state("ITEM-1", "MERGED", "rev-a", "reviewer", "gpt-5.6-sol")
        assert ok10, f"MERGED after VERIFIED (default green tag) should pass: {r10}"

        ok11, r11 = set_state("ITEM-2", "CLAIMED", "exec-a", "executor", "claude-opus-5-5", tag="red")
        set_state("ITEM-2", "BUILDING", "exec-a", "executor", "claude-opus-5-5")
        set_state("ITEM-2", "CHECKPOINT-READY", "exec-a", "executor", "claude-opus-5-5", evidence="exit=0")
        set_state("ITEM-2", "UNDER-REVIEW", "exec-a", "executor", "claude-opus-5-5")
        set_state("ITEM-2", "VERIFIED", "exec-a", "reviewer", "gpt-5.6-sol", verdict_by_lane="rev-a", verdict_by_model="gpt-5.6-sol")
        ok12, r12 = set_state("ITEM-2", "MERGED", "rev-a", "reviewer", "gpt-5.6-sol", tag="red")
        assert not ok12 and "human gate" in r12, f"a red item without --human-approved should be refused MERGED: {r12}"
        ok13, r13 = set_state("ITEM-2", "MERGED", "rev-a", "reviewer", "gpt-5.6-sol", tag="red", human_approved=True)
        assert ok13, f"a red item with --human-approved should pass: {r13}"

        ok14, r14 = set_state("ITEM-3", "CLAIMED", "exec-a", "executor", "claude-opus-5-5")
        set_state("ITEM-3", "BUILDING", "exec-a", "executor", "claude-opus-5-5")
        set_state("ITEM-3", "CHECKPOINT-READY", "exec-a", "executor", "claude-opus-5-5", evidence="x")
        set_state("ITEM-3", "UNDER-REVIEW", "exec-a", "executor", "claude-opus-5-5")
        ok15, r15 = set_state("ITEM-3", "VERIFIED", "exec-a", "reviewer", "claude-opus-5-5", checker_unavailable=True, verdict_by_lane="rev-a", verdict_by_model="gpt-5.6-sol")
        assert not ok15 and "DEFERRED" in r15, f"an unavailable checker only accepts DEFERRED: {r15}"
        ok16, r16 = set_state("ITEM-3", "DEFERRED", "exec-a", "reviewer", "claude-opus-5-5", checker_unavailable=True)
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
              "an unavailable checker only accepts DEFERRED, with notify_on_verdict false (CONTROL) a "
              "verdict reserves an accepted-but-undelivered effect, writes no mailbox and delivering by "
              "hand clears it, render ok, dual write of the board path")
        return 0
    finally:
        _PROJECT_ROOT, _LANES_DIR, BOARD_PATH, RENDER_PATH = orig
        if orig_fx is not None:
            lane_effects._PROJECT_ROOT, lane_effects._LANES_DIR, lane_effects.EFFECTS_PATH = orig_fx
        _config_restore(orig_cfg)
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
    orig_cfg = _config_off()
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

    task = ["--lane", "coord", "--model", "claude-opus-5-5"]
    try:
        _PROJECT_ROOT = tmp
        _LANES_DIR = tmp / ".claude" / "lanes"
        BOARD_PATH = _LANES_DIR / "board.jsonl"
        RENDER_PATH = tmp / "LANE-BOARD.md"
        if lane_effects is not None:
            lane_effects._PROJECT_ROOT = tmp
            lane_effects._LANES_DIR = _LANES_DIR
            lane_effects.EFFECTS_PATH = _LANES_DIR / "effects.json"

        to_checkpoint("ITEM-A", "exec-a", "claude-opus-5-5")
        for state in ("CLAIMED", "BUILDING"):  # B is still being built when the task is declared
            ok, why = set_state("ITEM-B", state, "exec-b", "executor", "claude-sonnet-5")
            check(f"setup ITEM-B -> {state}", ok, str(why))
        set_state("ITEM-SAME-LANE", "CLAIMED", "exec-a", "executor", "claude-opus-5-5")
        set_state("ITEM-LONE", "CLAIMED", "exec-d", "executor", "gpt-5.6-sol")

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
        reviewer = ["--lane", "rev-x", "--model", "gpt-5.6-sol"]
        refused("select on a task never declared",
                ["select", "--task", "TASK-9", "--winner", "ITEM-A", *reviewer], "no competition declared")
        refused("select while a candidate has no checkpoint evidence",
                ["select", "--task", "TASK-1", "--winner", "ITEM-A", *reviewer], "must be CHECKPOINT-READY with evidence")
        ok, why = set_state("ITEM-B", "CHECKPOINT-READY", "exec-b", "executor", "claude-sonnet-5",
                            evidence="pytest -q: 12 passed (ITEM-B)")
        check("setup ITEM-B -> CHECKPOINT-READY", ok, str(why))

        # A hand-edited or legacy board can hold a checkpoint with no evidence; the board itself
        # never writes one, so this line is forged on purpose to reach that branch.
        to_checkpoint("ITEM-F1", "exec-f", "claude-opus-5-5")
        to_checkpoint("ITEM-F2", "exec-g", "claude-opus-5-5")
        _append_event({"ts": "2026-01-01T00:00:00", "item_id": "ITEM-F2", "state": "CHECKPOINT-READY",
                       "lane_id": "exec-g", "role": "executor", "model": "claude-opus-5-5"})
        accepted("setup compete TASK-3", ["compete", "--task", "TASK-3", "--items", "ITEM-F1,ITEM-F2", *task])
        refused("select while a CHECKPOINT-READY candidate carries no evidence",
                ["select", "--task", "TASK-3", "--winner", "ITEM-F1", *reviewer], "without evidence")

        refused("select by a reviewer on a candidate's lane",
                ["select", "--task", "TASK-1", "--winner", "ITEM-A", "--lane", "exec-b", "--model", "gpt-5.6-sol"],
                "SAME lane")
        refused("select by a reviewer of a candidate's model family",
                ["select", "--task", "TASK-1", "--winner", "ITEM-A", "--lane", "rev-x", "--model", "claude-haiku-4-5-20251001"],
                "SAME model family")
        refused("select of a winner that is not a candidate",
                ["select", "--task", "TASK-1", "--winner", "ITEM-LONE", *reviewer], "not a candidate")
        refused("select without --winner", ["select", "--task", "TASK-1", *reviewer], "requires --winner")
        refused("select naming a winner while the checker is unavailable",
                ["select", "--task", "TASK-1", "--winner", "ITEM-A", "--checker-unavailable", *reviewer],
                "only DEFERRED")
        refused("DEFERRED recorded by a candidate's own lane",
                ["select", "--task", "TASK-1", "--checker-unavailable", "--lane", "exec-b", "--model", "gpt-5.6-sol"],
                "SAME lane")
        code, out, _err = _run_cli(["status", "TASK-1"])
        try:
            shown = json.loads(out) if code == 0 else []
        except ValueError:
            shown = []
        check("status <task> shows the competition", bool(shown) and all(e.get("task_id") == "TASK-1" for e in shown),
              out[:240])

        # after the declaration, one lane must not become the builder of a second candidate
        to_checkpoint("ITEM-C", "exec-c", "claude-opus-5-5")
        set_state("ITEM-D", "CLAIMED", "exec-h", "executor", "gpt-5.6-sol")
        accepted("setup compete TASK-4", ["compete", "--task", "TASK-4", "--items", "ITEM-C,ITEM-D", *task])
        refused("a candidate built by another candidate's lane",
                ["set", "ITEM-D", "BUILDING", "--lane", "exec-c", "--role", "executor", "--model", "claude-opus-5-5"],
                "builder of candidate")
        # A board edited by hand can still carry that event; the selection must catch it too.
        for state in ("BUILDING", "CHECKPOINT-READY"):
            _append_event({"ts": "2026-01-01T00:00:00", "item_id": "ITEM-D", "state": state, "lane_id": "exec-c",
                           "role": "executor", "model": "claude-opus-5-5", "evidence": "exit=0"})
        refused("select when one lane built two candidates",
                ["select", "--task", "TASK-4", "--winner", "ITEM-C", "--lane", "rev-y", "--model", "gemini-3"],
                "share builder lane")

        # convergence mode: a second lane that built the item cannot verify it either
        set_state("ITEM-V", "CLAIMED", "exec-v", "executor", "claude-opus-5-5")
        _append_event({"ts": "2026-01-01T00:00:00", "item_id": "ITEM-V", "state": "BUILDING", "lane_id": "exec-w",
                       "role": "executor", "model": "gpt-5.6-sol"})
        set_state("ITEM-V", "CHECKPOINT-READY", "exec-w", "executor", "gpt-5.6-sol", evidence="exit=0")
        set_state("ITEM-V", "UNDER-REVIEW", "exec-w", "executor", "gpt-5.6-sol")
        refused("VERIFIED by a lane that built the item in convergence mode",
                ["set", "ITEM-V", "VERIFIED", "--lane", "exec-w", "--role", "reviewer", "--model", "gemini-3",
                 "--verdict-by-lane", "exec-w", "--verdict-by-model", "gemini-3"], "SAME lane")

        # a candidate cannot be merged before the comparison, even after its own review
        for state, extra in (("UNDER-REVIEW", {}),
                             ("VERIFIED", {"verdict_by_lane": "rev-a", "verdict_by_model": "gpt-5.6-sol"})):
            ok, why = set_state("ITEM-A", state, "exec-a", "reviewer" if extra else "executor",
                                "gpt-5.6-sol" if extra else "claude-opus-5-5", **extra)
            check(f"setup ITEM-A -> {state}", ok, str(why))
        refused("MERGED of a candidate before any winner",
                ["set", "ITEM-A", "MERGED", "--lane", "rev-a", "--role", "reviewer", "--model", "gpt-5.6-sol"],
                "no winner yet")

        deferred = accepted("select with the checker unavailable records DEFERRED",
                            ["select", "--task", "TASK-1", "--checker-unavailable", *reviewer])
        check("the DEFERRED is a competition event", deferred.get("state") == "DEFERRED", str(deferred))
        refused("MERGED of a candidate while the competition is DEFERRED",
                ["set", "ITEM-A", "MERGED", "--lane", "rev-a", "--role", "reviewer", "--model", "gpt-5.6-sol"],
                "no winner yet")
        refused("`set` cannot forge NOT-SELECTED",
                ["set", "ITEM-B", "NOT-SELECTED", "--lane", "rev-x", "--role", "reviewer", "--model", "gpt-5.6-sol"],
                "invalid transition")

        # --- CONTROL: a valid selection is accepted, and it is evidence on the board ---
        chosen = accepted("CONTROL select by another lane of another family",
                          ["select", "--task", "TASK-1", "--winner", "ITEM-A", *reviewer,
                           "--reason", "same tests, half the diff"])
        check("select records the winner", chosen.get("winner") == "ITEM-A", str(chosen))
        check("select records who was not selected", chosen.get("not_selected") == ["ITEM-B"], str(chosen))
        check("select records the reviewer", chosen.get("verdict_by") == {"lane": "rev-x", "model": "gpt-5.6-sol"},
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
                 ["set", "ITEM-A", "MERGED", "--lane", "rev-a", "--role", "reviewer", "--model", "gpt-5.6-sol"])
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
        _config_restore(orig_cfg)
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
    orig_cfg = _config_off()
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

    coord = ["--lane", "coord", "--model", "claude-opus-5-5"]
    try:
        _PROJECT_ROOT = tmp
        _LANES_DIR = tmp / ".claude" / "lanes"
        BOARD_PATH = _LANES_DIR / "board.jsonl"
        RENDER_PATH = tmp / "LANE-BOARD.md"
        if lane_effects is not None:
            lane_effects._PROJECT_ROOT = tmp
            lane_effects._LANES_DIR = _LANES_DIR
            lane_effects.EFFECTS_PATH = _LANES_DIR / "effects.json"

        to_state("W-A", "exec-a", "claude-opus-5-5", "CHECKPOINT-READY")
        to_state("W-B", "exec-b", "claude-sonnet-5", "CHECKPOINT-READY")
        to_state("W-C", "exec-c", "gpt-5.6-sol", "BUILDING")  # its lane dies here
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
                ["withdraw", "--task", "TASK-W", "--item", "W-C", "--lane", "exec-a", "--model", "claude-opus-5-5",
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
                ["set", "W-C", "CHECKPOINT-READY", "--lane", "exec-c", "--role", "executor", "--model", "gpt-5.6-sol",
                 "--evidence", "exit=0"], "invalid transition")
        refused("`set` cannot forge WITHDRAWN",
                ["set", "W-B", "WITHDRAWN", "--lane", "coord", "--role", "coordinator", "--model", "gpt-5.6-sol"],
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
                          ["select", "--task", "TASK-W", "--winner", "W-A", "--lane", "rev-g", "--model", "gpt-5.6-sol"])
        check("the selection compares only the remaining candidate",
              chosen.get("winner") == "W-A" and chosen.get("not_selected") == []
              and sorted((chosen.get("compared") or {}).keys()) == ["W-A"], str(chosen))
        check("the selection lists the withdrawn items", chosen.get("withdrawn") == ["W-C", "W-B"], str(chosen))
        refused("withdraw from a decided task",
                ["withdraw", "--task", "TASK-W", "--item", "W-A", *coord, "--reason", "too late"], "already decided")
        for state, extra in (("UNDER-REVIEW", {}),
                             ("VERIFIED", {"verdict_by_lane": "rev-a", "verdict_by_model": "gpt-5.6-sol"})):
            ok, detail = set_state("W-A", state, "exec-a", "reviewer" if extra else "executor",
                                   "gpt-5.6-sol" if extra else "claude-opus-5-5", **extra)
            check(f"setup W-A -> {state}", ok, str(detail))
        accepted("the winner merges after the selection",
                 ["set", "W-A", "MERGED", "--lane", "rev-a", "--role", "reviewer", "--model", "gpt-5.6-sol"])
    finally:
        _PROJECT_ROOT, _LANES_DIR, BOARD_PATH, RENDER_PATH = orig
        if orig_fx is not None:
            lane_effects._PROJECT_ROOT, lane_effects._LANES_DIR, lane_effects.EFFECTS_PATH = orig_fx
        _config_restore(orig_cfg)
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


def _self_test_release() -> int:
    """`release-fix`, `start-review`, `approve` and the item-owned red tag through the CLI: every refusal,
    the reroute valve, the executor that could never build the fix, and the CONTROL that each hand-off
    lands with its `## To:` kickoff. Contributed with the Lane Dashboard (PR #18). Counted, N of M."""
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="lane_board_release_"))
    global _PROJECT_ROOT, _LANES_DIR, BOARD_PATH, RENDER_PATH
    orig = (_PROJECT_ROOT, _LANES_DIR, BOARD_PATH, RENDER_PATH)
    orig_fx = None
    if lane_effects is not None:
        orig_fx = (lane_effects._PROJECT_ROOT, lane_effects._LANES_DIR, lane_effects.EFFECTS_PATH)
    orig_cfg = _config_off()
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

    def accepted(name: str, argv: list) -> dict:
        code, parsed, err = run(argv)
        check(name, code == 0, f"expected exit 0; got exit {code}: {err.strip()[:240]}")
        return parsed

    def register(lanes: dict) -> None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        registry = {"lanes": {lane: {"role": role, "model": model, "heartbeat_at": beat or now}
                              for lane, (role, model, beat) in lanes.items()}}
        _LANES_DIR.mkdir(parents=True, exist_ok=True)
        (_LANES_DIR / "registry.json").write_text(json.dumps(registry), encoding="utf-8")

    def to_needs_fix(item: str, tag: str = "green") -> None:
        for state in ("CLAIMED", "BUILDING", "CHECKPOINT-READY"):
            ok, why = set_state(item, state, "exec-a", "executor", "claude-opus-5-5", tag=tag,
                                evidence="pytest -q: 3 passed" if state == "CHECKPOINT-READY" else "")
            check(f"setup {item} -> {state}", ok, str(why))
        ok, why = set_state(item, "UNDER-REVIEW", "rev-x", "reviewer", "gpt-5.6-sol")
        check(f"setup {item} -> UNDER-REVIEW", ok, str(why))
        ok, why = set_state(item, "NEEDS-FIX", "rev-x", "reviewer", "gpt-5.6-sol", verdict_by_lane="rev-x",
                            verdict_by_model="gpt-5.6-sol", evidence="the token is never refreshed")
        check(f"setup {item} -> NEEDS-FIX", ok, str(why))

    def kickoff_text(event: dict) -> str:
        path = _PROJECT_ROOT / event.get("kickoff", "missing")
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    lanes = {"exec-b": ("executor", "gemini-3", ""), "exec-c": ("executor", "claude-haiku-4-5-20251001", ""),
             "rev-y": ("reviewer", "gemini-3", ""), "exec-a": ("reviewer", "gpt-5.6-sol", "")}
    try:
        _PROJECT_ROOT = tmp
        _LANES_DIR = tmp / ".claude" / "lanes"
        BOARD_PATH = _LANES_DIR / "board.jsonl"
        RENDER_PATH = tmp / "LANE-BOARD.md"
        if lane_effects is not None:
            lane_effects._PROJECT_ROOT = tmp
            lane_effects._LANES_DIR = _LANES_DIR
            lane_effects.EFFECTS_PATH = _LANES_DIR / "effects.json"
        register(lanes)

        to_needs_fix("F1")
        refused("set cannot write FIX-QUEUED",
                ["set", "F1", "FIX-QUEUED", "--lane", "exec-b", "--role", "executor", "--model", "gemini-3"],
                "release-fix")
        refused("release-fix to a reviewer", ["release-fix", "F1", "--target-lane", "rev-y"], "executor")
        refused("release-fix to an unregistered lane", ["release-fix", "F1", "--target-lane", "nobody"], "nobody")
        queued = accepted("CONTROL release-fix lands", ["release-fix", "F1", "--target-lane", "exec-b"])
        text = kickoff_text(queued)
        check("the fix kickoff routes by `## To:` and carries the direction",
              "\n## To: exec-b\n" in text and "## Para:" not in text and "never refreshed" in text, text[:200])
        refused("another lane cannot take a queued fix",
                ["set", "F1", "BUILDING", "--lane", "exec-c", "--role", "executor", "--model", "claude-haiku-4-5-20251001"],
                "exec-b")
        refused("a live release is not rerouted", ["release-fix", "F1", "--target-lane", "exec-c"], "alive")
        register({**lanes, "exec-b": ("executor", "gemini-3", "2000-01-01T00:00:00")})
        rerouted = accepted("an abandoned release reroutes", ["release-fix", "F1", "--target-lane", "exec-c"])
        check("the reroute names the abandoned lane", rerouted.get("reroute", {}).get("from") == "exec-b", str(rerouted))
        accepted("the named lane takes the fix",
                 ["set", "F1", "BUILDING", "--lane", "exec-c", "--role", "executor", "--model",
                  "claude-haiku-4-5-20251001", "--branch", "fix/f1"])
        code, rendered, _err = _run_cli(["render"])
        check("render names the target lane, the reroute and the builder's branch",
              code == 0 and "target: exec-c" in rendered and "rerouted from exec-b" in rendered
              and "branch: fix/f1" in rendered, rendered[-300:])
        set_state("F1", "CHECKPOINT-READY", "exec-c", "executor", "claude-haiku-4-5-20251001",
                  evidence="pytest -q: 4 passed")
        set_state("F1", "UNDER-REVIEW", "rev-x", "reviewer", "gpt-5.6-sol")
        set_state("F1", "VERIFIED", "rev-x", "reviewer", "gpt-5.6-sol", verdict_by_lane="rev-x",
                  verdict_by_model="gpt-5.6-sol")
        owed = [(r["decision"], r["target"]) for r in lane_effects.pending_effects() if r["item_id"] == "F1"]
        check("the verdict on the routed fix is owed to the lane that built it; the first verdict to the claimer",
              ("VERIFIED", "exec-c") in owed and ("NEEDS-FIX", "exec-a") in owed, str(owed))
        register(lanes)

        # an executor that could never build the item is refused BEFORE a kickoff exists
        for state in ("CLAIMED", "BUILDING", "CHECKPOINT-READY"):
            set_state("C1", state, "exec-a", "executor", "claude-opus-5-5",
                      evidence="pytest -q: 2 passed" if state == "CHECKPOINT-READY" else "")
        set_state("C2", "CLAIMED", "exec-b", "executor", "gemini-3")
        accepted("setup compete TASK-R", ["compete", "--task", "TASK-R", "--items", "C1,C2", "--lane", "coord",
                                          "--model", "claude-opus-5-5"])
        set_state("C1", "UNDER-REVIEW", "rev-x", "reviewer", "gpt-5.6-sol")
        set_state("C1", "NEEDS-FIX", "rev-x", "reviewer", "gpt-5.6-sol", verdict_by_lane="rev-x",
                  verdict_by_model="gpt-5.6-sol", evidence="off by one")
        refused("release-fix to the builder of a rival candidate", ["release-fix", "C1", "--target-lane", "exec-b"],
                "candidate")
        check("the refused release left the item in NEEDS-FIX", (_latest_state("C1") or {}).get("state") == "NEEDS-FIX",
              str(_latest_state("C1")))

        for state in ("CLAIMED", "BUILDING", "CHECKPOINT-READY"):
            set_state("V1", state, "exec-a", "executor", "claude-opus-5-5",
                      evidence="pytest -q: 5 passed" if state == "CHECKPOINT-READY" else "")
        refused("start-review for a builder lane", ["start-review", "V1", "--target-lane", "exec-a"], "maker")
        refused("start-review for an executor", ["start-review", "V1", "--target-lane", "exec-c"], "reviewer")
        opened = accepted("CONTROL start-review lands", ["start-review", "V1", "--target-lane", "rev-y"])
        text = kickoff_text(opened)
        check("the review kickoff routes by `## To:` and carries the checkpoint evidence",
              "\n## To: rev-y\n" in text and "pytest -q: 5 passed" in text, text[:200])
        refused("start-review needs a checkpoint", ["start-review", "V1", "--target-lane", "rev-y"], "CHECKPOINT-READY")

        for state, extra in (("CLAIMED", {}), ("BUILDING", {}), ("CHECKPOINT-READY", {"evidence": "ok"})):
            set_state("R1", state, "exec-a", "executor", "claude-opus-5-5", tag="red", **extra)
        set_state("R1", "UNDER-REVIEW", "rev-y", "reviewer", "gemini-3")
        set_state("R1", "VERIFIED", "rev-y", "reviewer", "gemini-3", verdict_by_lane="rev-y", verdict_by_model="gemini-3")
        refused("a red item omitting --tag still needs the human gate",
                ["set", "R1", "MERGED", "--lane", "exec-a", "--role", "executor", "--model", "claude-opus-5-5"],
                "human-approved")
        refused("set cannot write APPROVED",
                ["set", "R1", "APPROVED", "--lane", "max", "--role", "operator", "--model", "human"], "approve")
        approval = accepted("CONTROL approve records APPROVED", ["approve", "R1", "--operator", "max"])
        check("the approval is APPROVED, not MERGED, and stays red",
              approval.get("state") == "APPROVED" and approval.get("tag") == "red", str(approval))
        merged = accepted("after the approval MERGED needs no second flag",
                          ["set", "R1", "MERGED", "--lane", "exec-a", "--role", "executor", "--model", "claude-opus-5-5",
                           "--evidence", "git cherry HEAD feat/r1: every commit contained"])
        check("the merged red item stays red", merged.get("tag") == "red", str(merged))
        code, _out, err = _run_cli(["set", "R1", "MERGED", "--lane", "x", "--role", "operator", "--model", "human",
                                    "--branch", "main"])
        check("--branch on a state that does not build is a usage error (exit 2)",
              code == 2 and "--branch" in err, f"exit {code}: {err.strip()[:200]}")
    finally:
        _PROJECT_ROOT, _LANES_DIR, BOARD_PATH, RENDER_PATH = orig
        if orig_fx is not None:
            lane_effects._PROJECT_ROOT, lane_effects._LANES_DIR, lane_effects.EFFECTS_PATH = orig_fx
        _config_restore(orig_cfg)
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [(name, detail) for name, ok, detail in results if not ok]
    if failed:
        print(f"self-test FAILED (release) — {len(results) - len(failed)} of {len(results)} checks passed",
              file=sys.stderr)
        for name, detail in failed:
            print(f"  FAIL {name}: {detail}", file=sys.stderr)
        return 1
    print(f"self-test OK (release) — {len(results)} of {len(results)} checks: release-fix refuses set, a reviewer, "
          "an unregistered lane, a live reroute and the builder of a rival candidate; only the named lane takes a "
          "queued fix; an abandoned release reroutes and render shows it with the builder's branch; the verdict on "
          "the routed fix is owed to the lane that built it; start-review "
          "refuses a builder lane, an executor and a missing checkpoint; each kickoff is routed with `## To:`; a red "
          "item keeps its human gate when --tag is omitted; approve records APPROVED (never MERGED) and set cannot "
          "forge it; --branch outside a build state is a usage error")
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
    orig_cfg = _config_off()
    results: list = []
    missing = object()
    hidden = ("hpp", "hpp.evidence")

    def check(name: str, condition: bool, detail: str = "") -> None:
        results.append((name, bool(condition), detail))

    def to_building(item: str, lane: str, model: str = "claude-opus-5-5") -> None:
        for state in ("CLAIMED", "BUILDING"):
            ok, why = set_state(item, state, lane, "executor", model)
            check(f"setup {item} -> {state}", ok, str(why))

    def state_of(item: str) -> str:
        return (_latest_state(item) or {}).get("state", "")

    ex = ["--lane", "exec-a", "--role", "executor", "--model", "claude-opus-5-5"]
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
                       "lane_id": "exec-r", "role": "executor", "model": "claude-opus-5-5",
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
                                    "--lane", "coord", "--model", "claude-opus-5-5"])
        check("setup compete TASK-R", code == 0, err.strip()[:240])
        code, out, err = _run_cli(["select", "--task", "TASK-R", "--winner", "ITEM-R2",
                                   "--lane", "rev-x", "--model", "gpt-5.6-sol"])
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
        _config_restore(orig_cfg)
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


def _self_test_mailbox() -> int:
    """Delivery of a verdict to the mailbox (`mailbox.notify_on_verdict`, default ON) and the Codex
    doorbell (`mailbox.native_doorbell`, default ON) with fake `codex` executables on PATH — never a
    live daemon. The CONTROL: `notify_on_verdict: false` restores the by-hand behaviour. Each check is
    counted, so a run reports N of M."""
    import contextlib
    import io
    import shutil
    import tempfile

    if lane_effects is None or _lane_io is None:
        print("self-test SKIPPED (mailbox) — lane_effects.py or hooks/_lane_io.py is not importable beside "
              "this file, so the board delivers nothing here")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="lane_board_mailbox_"))
    global _PROJECT_ROOT, _LANES_DIR, BOARD_PATH, RENDER_PATH, _DOORBELL_TIMEOUT_SECONDS
    orig = (_PROJECT_ROOT, _LANES_DIR, BOARD_PATH, RENDER_PATH, _DOORBELL_TIMEOUT_SECONDS)
    orig_fx = (lane_effects._PROJECT_ROOT, lane_effects._LANES_DIR, lane_effects.EFFECTS_PATH)
    orig_io = (_lane_io._PROJECT_ROOT, _lane_io._LANES_DIR, _lane_io.REGISTRY_PATH, _lane_io.CONFIG_PATH)
    orig_load = _lane_io.load_config
    orig_path = os.environ.get("PATH", "")
    results: list = []
    stderr = io.StringIO()
    event_keys = ["item_id", "lane_id", "model", "reservation_id", "role", "state", "ts", "verdict_by"]

    def check(name: str, condition: bool, detail: str = "") -> None:
        results.append((name, bool(condition), detail))

    def config(cfg: dict) -> None:
        _lane_io.load_config = lambda: dict(cfg)

    def messages() -> list:
        d = _LANES_DIR / "mailbox"
        return sorted(d.glob("*.md")) if d.is_dir() else []

    def to_review(item: str, lane: str = "exec-a", model: str = "claude-opus-5-5") -> None:
        for state, extra in (("CLAIMED", {}), ("BUILDING", {}),
                             ("CHECKPOINT-READY", {"evidence": f"pytest -q: 3 passed ({item})"}), ("UNDER-REVIEW", {})):
            ok, why = set_state(item, state, lane, "executor", model, **extra)
            check(f"setup {item} -> {state}", ok, str(why))

    def verdict(item: str, state: str, reviewer: str = "rev-a", model: str = "gpt-5.6-sol") -> dict:
        ok, event = set_state(item, state, reviewer, "reviewer", model, verdict_by_lane=reviewer, verdict_by_model=model)
        check(f"verdict {item} -> {state} is accepted", ok, str(event))
        return event if ok else {}

    def record_of(event: dict) -> dict:
        return lane_effects.get(event.get("reservation_id", "")) or {}

    def fake_codex(behaviour: str, args_file: Path) -> None:
        """A `codex` on PATH that records its argv (ok), fails (exit 3) or hangs (4s).

        Why the two timeouts below: a fresh `.bat` on a loaded Windows box takes ~2s just to start
        (measured: the 1s timeout this test first used reported `failed (timeout after 1s)` for the
        `ok` and `fail` fakes, whose delivery was fine). The cases that must prove the fake RAN get a
        generous 15s; only the hang case shrinks the timeout to 1s, against a fake that sleeps 4s.
        """
        bindir = tmp / "bin" / behaviour
        bindir.mkdir(parents=True, exist_ok=True)
        py = sys.executable
        if os.name == "nt":
            body = {"ok": f'@echo off\r\necho %* > "{args_file}"\r\nexit /b 0\r\n',
                    "fail": "@echo off\r\necho boom: no daemon 1>&2\r\nexit /b 3\r\n",
                    "hang": f'@echo off\r\n"{py}" -c "import time; time.sleep(4)"\r\nexit /b 0\r\n'}[behaviour]
            (bindir / "codex.bat").write_bytes(body.encode("utf-8"))
        else:
            body = {"ok": f'#!/bin/sh\necho "$@" > "{args_file}"\nexit 0\n',
                    "fail": '#!/bin/sh\necho "boom: no daemon" 1>&2\nexit 3\n',
                    "hang": f'#!/bin/sh\n"{py}" -c "import time; time.sleep(4)"\nexit 0\n'}[behaviour]
            exe = bindir / "codex"
            exe.write_bytes(body.encode("utf-8"))
            exe.chmod(0o755)
        os.environ["PATH"] = str(bindir) + os.pathsep + orig_path

    try:
        _PROJECT_ROOT = tmp
        _LANES_DIR = tmp / ".claude" / "lanes"
        BOARD_PATH = _LANES_DIR / "board.jsonl"
        RENDER_PATH = tmp / "LANE-BOARD.md"
        lane_effects._PROJECT_ROOT, lane_effects._LANES_DIR = tmp, _LANES_DIR
        lane_effects.EFFECTS_PATH = _LANES_DIR / "effects.json"
        _lane_io._PROJECT_ROOT, _lane_io._LANES_DIR = tmp, _LANES_DIR
        _lane_io.REGISTRY_PATH, _lane_io.CONFIG_PATH = _LANES_DIR / "registry.json", _LANES_DIR / "lanes.yaml"
        (tmp / "bin" / "empty").mkdir(parents=True)
        os.environ["PATH"] = str(tmp / "bin" / "empty")  # no codex anywhere until a fake is installed
        _DOORBELL_TIMEOUT_SECONDS = 15  # see fake_codex: generous for the fakes that must run to completion
        _lane_io.register("exec-a", "executor", "sess-a", "claude-opus-5-5")   # a Claude Code lane
        _lane_io.register("exec-g", "executor", "sess-g", "gpt-5.6-sol")       # a Codex CLI lane (OpenAI family)

        with contextlib.redirect_stderr(stderr):
            # --- the default, with no config at all: a verdict is delivered ---
            config({})
            to_review("ITEM-1")
            event = verdict("ITEM-1", "NEEDS-FIX")
            files = messages()
            check("default ON: one message is written", len(files) == 1, str(files))
            text = files[0].read_text(encoding="utf-8") if files else ""
            check("the message routes to the builder lane with `## To:`", "\n## To: exec-a\n" in text, text[:200])
            for needle in ("ITEM-1", "NEEDS-FIX", "rev-a", event.get("reservation_id", "?"), "round "):
                check(f"the message carries {needle!r}", needle in text, text[:400])
            check("the message is written with LF", bool(files) and b"\r" not in files[0].read_bytes())
            rec = record_of(event)
            check("the reservation is delivered", rec.get("effect_state") == "delivered", str(rec))
            check("the evidence is the message path", bool(files) and rec.get("evidence") == files[0].relative_to(tmp).as_posix(),
                  str(rec))
            check("a Claude Code lane gets no doorbell, and the ledger says why",
                  str(rec.get("doorbell", "")).startswith("none (claude-code lane"), str(rec))
            check("nothing is left pending", lane_effects.pending_effects() == [], str(lane_effects.pending_effects()))
            check("render shows no UNDELIVERED", "UNDELIVERED" not in render())
            check("the board event keeps its shape", sorted(event) == event_keys, str(sorted(event)))

            # --- a retry of the same reservation writes nothing new ---
            ok_retry, where = _notify_mailbox(event.get("reservation_id", ""), event)
            check("a retry is accepted", ok_retry, str(where))
            check("a retry writes no second message", messages() == files, str(messages()))
            again = record_of(event)
            check("a retry keeps the first delivery", again.get("delivered_at") == rec.get("delivered_at")
                  and again.get("evidence") == rec.get("evidence"), str(again))

            # --- a new round writes its own message ---
            for state, extra in (("BUILDING", {}), ("CHECKPOINT-READY", {"evidence": "pytest -q: 4 passed"}), ("UNDER-REVIEW", {})):
                ok, why = set_state("ITEM-1", state, "exec-a", "executor", "claude-opus-5-5", **extra)
                check(f"setup round 2 -> {state}", ok, str(why))
            second = verdict("ITEM-1", "VERIFIED")
            check("a new round is a new reservation", bool(second.get("reservation_id"))
                  and second.get("reservation_id") != event.get("reservation_id"), str(second))
            check("a new round writes a second message", len(messages()) == 2, str(messages()))
            check("both rounds are delivered", lane_effects.pending_effects() == [], str(lane_effects.pending_effects()))

            # --- CONTROL: `notify_on_verdict: false` restores the by-hand behaviour ---
            config({"mailbox": {"notify_on_verdict": False}})
            before = messages()
            seen = len(stderr.getvalue())
            to_review("ITEM-OFF")
            off = verdict("ITEM-OFF", "NEEDS-FIX")
            rec_off = record_of(off)
            check("CONTROL off: no message is written", messages() == before, str(messages()))
            check("CONTROL off: the reservation stays pending, empty evidence, no doorbell note",
                  rec_off.get("effect_state") == "pending" and rec_off.get("evidence") == "" and "doorbell" not in rec_off,
                  str(rec_off))
            check("CONTROL off: render shows UNDELIVERED", "UNDELIVERED" in render())
            check("CONTROL off: the event keeps its shape", sorted(off) == event_keys, str(sorted(off)))
            check("CONTROL off: nothing was printed on stderr", "[lane_board] mailbox" not in stderr.getvalue()[seen:],
                  stderr.getvalue()[seen:][-300:])

            # --- the doorbell, with fake codex executables on PATH ---
            config({})
            args_file = tmp / "codex-args.txt"
            fake_codex("ok", args_file)
            to_review("ITEM-G1", "exec-g", "gpt-5.6-sol")
            g1 = record_of(verdict("ITEM-G1", "NEEDS-FIX", reviewer="rev-c", model="claude-opus-5-5"))
            check("doorbell: a Codex lane is rung and the ledger records `sent`",
                  g1.get("doorbell") == "sent (codex queue --thread sess-g)", str(g1))
            args = args_file.read_text(encoding="utf-8", errors="replace") if args_file.exists() else ""
            check("doorbell: codex queue got the lane's session, the message path and the verdict",
                  "--thread" in args and "sess-g" in args and "--message" in args and "ITEM-G1" in args
                  and "NEEDS-FIX" in args and ".md" in args, args)
            check("doorbell: the file is still the delivery", g1.get("effect_state") == "delivered"
                  and str(g1.get("evidence", "")).endswith(".md"), str(g1))

            fake_codex("fail", args_file)
            to_review("ITEM-G2", "exec-g", "gpt-5.6-sol")
            g2 = record_of(verdict("ITEM-G2", "NEEDS-FIX", reviewer="rev-c", model="claude-opus-5-5"))
            check("doorbell: a non-zero codex exit is recorded as failed, with the exit code",
                  str(g2.get("doorbell", "")).startswith("failed (exit 3"), str(g2))
            check("doorbell: a failed ring never undoes the delivery", g2.get("effect_state") == "delivered", str(g2))

            fake_codex("hang", args_file)
            _DOORBELL_TIMEOUT_SECONDS = 1  # only here: the fake sleeps 4s, so the cut is certain
            to_review("ITEM-G3", "exec-g", "gpt-5.6-sol")
            g3 = record_of(verdict("ITEM-G3", "NEEDS-FIX", reviewer="rev-c", model="claude-opus-5-5"))
            _DOORBELL_TIMEOUT_SECONDS = 15
            check("doorbell: a hanging codex is cut by the timeout and recorded as failed",
                  g3.get("doorbell") == "failed (timeout after 1s)", str(g3))
            check("doorbell: a timed-out ring never undoes the delivery", g3.get("effect_state") == "delivered", str(g3))

            os.environ["PATH"] = str(tmp / "bin" / "empty")
            to_review("ITEM-G4", "exec-g", "gpt-5.6-sol")
            g4 = record_of(verdict("ITEM-G4", "NEEDS-FIX", reviewer="rev-c", model="claude-opus-5-5"))
            check("doorbell: without codex on PATH it is skipped and the delivery stands",
                  g4.get("doorbell") == "skipped (codex not on PATH)" and g4.get("effect_state") == "delivered", str(g4))

            config({"mailbox": {"native_doorbell": False}})
            fake_codex("ok", args_file)
            if args_file.exists():
                args_file.unlink()
            to_review("ITEM-G5", "exec-g", "gpt-5.6-sol")
            g5 = record_of(verdict("ITEM-G5", "NEEDS-FIX", reviewer="rev-c", model="claude-opus-5-5"))
            check("doorbell: native_doorbell false delivers, rings nothing, records no note",
                  g5.get("effect_state") == "delivered" and "doorbell" not in g5 and not args_file.exists(), str(g5))

            config({})
            reg = _lane_io._read_registry()
            reg["lanes"]["exec-h"] = dict(reg["lanes"]["exec-a"], host="codex", session_id="sess-h")
            _lane_io._write_registry(reg)
            to_review("ITEM-H1", "exec-h")
            h1 = record_of(verdict("ITEM-H1", "NEEDS-FIX"))
            check("doorbell: a registry `host: codex` wins over the model family",
                  h1.get("doorbell") == "sent (codex queue --thread sess-h)", str(h1))
            to_review("ITEM-U1", "exec-unknown")
            u1 = record_of(verdict("ITEM-U1", "NEEDS-FIX"))
            check("doorbell: a lane absent from the registry is delivered with `none`",
                  u1.get("effect_state") == "delivered" and str(u1.get("doorbell", "")).startswith("none (lane not in the registry"),
                  str(u1))

            # --- select and withdraw deliver their news too ---
            config({"mailbox": {"native_doorbell": False}})
            for item, lane, model in (("C-A", "exec-a", "claude-opus-5-5"), ("C-B", "exec-b", "claude-sonnet-5"),
                                      ("C-C", "exec-c", "claude-haiku-5")):
                for state, extra in (("CLAIMED", {}), ("BUILDING", {}), ("CHECKPOINT-READY", {"evidence": f"ok {item}"})):
                    ok, why = set_state(item, state, lane, "executor", model, **extra)
                    check(f"setup {item} -> {state}", ok, str(why))
            ok, why = compete("TASK-C", ["C-A", "C-B", "C-C"], "coord", "claude-opus-5-5")
            check("setup compete TASK-C", ok, str(why))
            ok, why = withdraw("TASK-C", "C-C", "coord", "claude-opus-5-5", "lane exec-c died")
            check("setup withdraw C-C", ok, str(why))
            ok, why = select("TASK-C", "C-A", "rev-x", "gpt-5.6-sol", reason="half the diff")
            check("setup select C-A", ok, str(why))
            texts = [f.read_text(encoding="utf-8") for f in messages()]
            check("withdraw delivers WITHDRAWN to the withdrawn lane, with the reason",
                  any("\n## To: exec-c\n" in t and "WITHDRAWN" in t and "lane exec-c died" in t for t in texts))
            check("select delivers NOT-SELECTED to the losing lane, with the winner and the reason",
                  any("\n## To: exec-b\n" in t and "NOT-SELECTED" in t and "winner C-A" in t and "half the diff" in t
                      for t in texts))
            check("after select and withdraw only the CONTROL-off reservation is still pending",
                  [r["item_id"] for r in lane_effects.pending_effects()] == ["ITEM-OFF"],
                  str(lane_effects.pending_effects()))

            # --- a mailbox that cannot be written: the verdict stays on the board, the debt stays visible ---
            config({"mailbox": {"dir": ".claude/lanes/blocked", "native_doorbell": False}})
            (_LANES_DIR / "blocked").write_text("a file where the directory should be", encoding="utf-8")
            to_review("ITEM-X")
            x = verdict("ITEM-X", "NEEDS-FIX")
            check("an unwritable mailbox leaves the verdict on the board",
                  (_latest_state("ITEM-X") or {}).get("state") == "NEEDS-FIX", str(_latest_state("ITEM-X")))
            check("an unwritable mailbox leaves the reservation pending (visible under UNDELIVERED)",
                  record_of(x).get("effect_state") == "pending" and "UNDELIVERED" in render(), str(record_of(x)))
            check("an unwritable mailbox is reported on stderr, not raised",
                  "NOT delivered" in stderr.getvalue(), stderr.getvalue()[-300:])
    finally:
        os.environ["PATH"] = orig_path
        _lane_io.load_config = orig_load
        _lane_io._PROJECT_ROOT, _lane_io._LANES_DIR, _lane_io.REGISTRY_PATH, _lane_io.CONFIG_PATH = orig_io
        lane_effects._PROJECT_ROOT, lane_effects._LANES_DIR, lane_effects.EFFECTS_PATH = orig_fx
        _PROJECT_ROOT, _LANES_DIR, BOARD_PATH, RENDER_PATH, _DOORBELL_TIMEOUT_SECONDS = orig
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [(name, detail) for name, ok, detail in results if not ok]
    if failed:
        print(f"self-test FAILED (mailbox) — {len(results) - len(failed)} of {len(results)} checks passed",
              file=sys.stderr)
        for name, detail in failed:
            print(f"  FAIL {name}: {detail}", file=sys.stderr)
        return 1
    print(f"self-test OK (mailbox) — {len(results)} of {len(results)} checks: by default a verdict writes ONE "
          "`## To:` message to the builder lane and marks the reservation delivered with that path; a retry "
          "writes nothing new, a new round writes its own; notify_on_verdict false (CONTROL) writes nothing "
          "and keeps the reservation pending; the Codex doorbell records sent / failed (exit, timeout) / "
          "skipped (no codex) / none (Claude Code lane) beside the evidence and never undoes a delivery; "
          "select and withdraw deliver too; an unwritable mailbox keeps the verdict and the debt visible")
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
    c.add_argument("--branch", default="", help="the branch this builder works on, recorded on the event")

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
    s.add_argument("--branch", default="",
                   help="CLAIMED, BUILDING or CHECKPOINT-READY only: the branch this builder works on")

    co = sub.add_parser("compete", help="declare 2+ claimed items as candidates for the same task")
    co.add_argument("--task", required=True)
    co.add_argument("--items", required=True, help="comma-separated item ids, at least 2, one lane each")
    co.add_argument("--lane", required=True, help="the lane declaring the competition")
    co.add_argument("--model", required=True)

    se = sub.add_parser("select", help="record the winner of a competition (reviewer: another lane AND family)")
    se.add_argument("--task", required=True)
    se.add_argument("--winner", default="")
    se.add_argument("--lane", default="", help="the reviewer's lane (not with --deliberation: the judge is)")
    se.add_argument("--model", default="", help="the reviewer's model (not with --deliberation: the judge is)")
    se.add_argument("--deliberation", default="",
                    help="a sealed design session (hpp.deliberation/v2) whose options are the candidates; "
                         "its judge is the reviewer of record")
    se.add_argument("--reason", default="")
    se.add_argument("--checker-unavailable", action="store_true",
                    help="no reviewer available: record DEFERRED, never a winner")

    wd = sub.add_parser("withdraw", help="take one candidate out of an undecided competition (its lane died)")
    wd.add_argument("--task", required=True)
    wd.add_argument("--item", required=True, help="the candidate to take out")
    wd.add_argument("--lane", required=True, help="the coordinator's lane")
    wd.add_argument("--model", required=True)
    wd.add_argument("--reason", required=True, help="why the candidate leaves the competition")

    rf = sub.add_parser("release-fix", help="route a NEEDS-FIX to a named live executor (FIX-QUEUED + kickoff)")
    rf.add_argument("item_id")
    rf.add_argument("--target-lane", required=True, help="a registered, live lane with role executor")
    rf.add_argument("--operator", default="operator", help="who released it, recorded on the event")

    sr = sub.add_parser("start-review", help="open a review for a named live reviewer (UNDER-REVIEW + kickoff)")
    sr.add_argument("item_id")
    sr.add_argument("--target-lane", required=True, help="a registered, live lane with role reviewer")
    sr.add_argument("--operator", default="operator", help="who opened it, recorded on the event")

    ap = sub.add_parser("approve", help="record the operator's approval of a red VERIFIED item (APPROVED, not MERGED)")
    ap.add_argument("item_id")
    ap.add_argument("--operator", default="operator", help="who approved it, recorded on the event")

    st = sub.add_parser("status")
    st.add_argument("item_id", nargs="?")

    sub.add_parser("render")
    p.add_argument("--self-test", action="store_true")
    return p


def main(argv) -> int:
    args = build_parser().parse_args(argv)

    if args.self_test:
        return (_self_test() or _self_test_compete() or _self_test_withdraw() or _self_test_release()
                or _self_test_evidence_record() or _self_test_mailbox())

    if args.cmd == "claim":
        ok, result = set_state(args.item_id, "CLAIMED", args.lane, args.role, args.model, tag=args.tag,
                               branch=args.branch)
    elif args.cmd == "set":
        if args.branch and args.state not in _BUILDER_STATES:
            print(f"lane_board: --branch applies only to {', '.join(_BUILDER_STATES)} — the branch is the "
                  f"builder's, and a {args.state} event is not a build (got: {args.state})", file=sys.stderr)
            return 2
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
            evidence_record=record, branch=args.branch,
        )
    elif args.cmd == "compete":
        items = [item.strip() for item in args.items.split(",") if item.strip()]
        ok, result = compete(args.task, items, args.lane, args.model)
    elif args.cmd == "select":
        if args.deliberation:
            if args.winner or args.lane or args.model or args.checker_unavailable:
                print("lane_board: --deliberation names the winner and the reviewer; do not pass --winner, "
                      "--lane, --model or --checker-unavailable with it", file=sys.stderr)
                return 2
            try:
                chosen, detail = deliberated_choice(args.task, args.deliberation)
            except EvidenceCoreMissing as exc:
                print(f"lane_board: --deliberation needs the HPP core (`python -m hpp`), which is not importable "
                      f"here ({exc}) — nothing was written", file=sys.stderr)
                return 2
            if not chosen:
                print(f"lane_board: refused — {detail}", file=sys.stderr)
                return 1
            winner, lane, model, sha = detail
            ok, result = select(args.task, winner, lane, model, reason=args.reason or f"deliberation {sha[:12]}",
                                deliberation=sha)
        else:
            ok, result = select(args.task, args.winner, args.lane, args.model, reason=args.reason,
                                checker_unavailable=args.checker_unavailable)
    elif args.cmd == "withdraw":
        ok, result = withdraw(args.task, args.item, args.lane, args.model, args.reason)
    elif args.cmd == "release-fix":
        ok, result = release_fix(args.item_id, args.target_lane, args.operator)
    elif args.cmd == "start-review":
        ok, result = start_review(args.item_id, args.target_lane, args.operator)
    elif args.cmd == "approve":
        ok, result = approve(args.item_id, args.operator)
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
        print("usage: claim|set|compete|select|withdraw|release-fix|start-review|approve|status|render [...] "
              "or --self-test", file=sys.stderr)
        return 2

    if ok:
        print(json.dumps(result, ensure_ascii=False))
        return 0
    print(f"lane_board: refused — {result}", file=sys.stderr)
    # Why: a busy lock and a refused transition both reached this line and both exited 1, while the
    # docstring and the skill promise 2 for the lock -- a script could not tell "retry" from "refused".
    return 2 if isinstance(result, str) and result.startswith(_LOCK_REFUSED) else 1


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
