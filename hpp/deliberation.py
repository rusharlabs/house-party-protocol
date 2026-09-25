"""House Session: deliberation between pinned deciders, recorded so it can be verified and measured.

The harness calls no model, and neither does this module. Seats answer somewhere else (a lane, a
CLI, a person); this module defines what a panel, a turn and a finished session must look like to
be recorded, decides when a session stops, and turns a finished session into one `hpp.decision/v1`
record, so the whole panel is measured by the ruler that already measures a single decider
(`hpp decide eval`).

Four rules carry the design:

- **Diversity is declared, not assumed.** A panel names every seat's pinned model and family; it
  needs two families among the participants, a judge outside the participants' lanes, and the
  roles its session type requires (a review without a dissenting seat does not start).
- **The first round is blind, and that is checkable.** Every turn lists the turns it had seen;
  a first-round turn that lists any is refused, and a later turn may only have seen earlier rounds.
- **A seat that did not answer is not judged.** It is never counted as a vote against, and it
  blocks the verdict: a panel with a dead seat is an instrument failure, not a decision.
- **The record seals itself.** `record_sha256` covers everything except the human decision, and
  `verify` re-derives the tally, the stop and the verdict from the turns and the judge it holds,
  so an edit to anything derived fails even when the hash was recomputed. The seal is not a
  signature: a consistent rewrite of a turn or of the judge's record, resealed, verifies. What
  anchors those inputs is outside the record — the verbatim text and the judge's raw response,
  whose hashes the record carries.

Turns carry hashes of the verbatim text, never the text: the text stays with the host, beside the
record, the same way a decision record keeps only the hash of the raw response.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Optional

from hpp.decision import (
    ABSTAIN,
    MODEL_METHODS,
    SCHEMA as DECISION_SCHEMA,
    DecisionError,
    is_alias,
    normalise_question,
    validate as validate_decision,
)

PANEL_SCHEMA = "hpp.panel/v1"
TURN_SCHEMA = "hpp.turn/v1"
SCHEMA = "hpp.deliberation/v1"
TALLY_SCHEMA = "hpp.deliberation-tally/v1"
ROLES = ("proponent", "dissent", "examiner", "judge")
CLAIM_KINDS = ("fact", "inference", "opinion")
MAX_ROUNDS = 10
# Minimum participants per role for each kind of question, and the round ceiling where the kind
# has one. "options" means one proponent per option of the question.
# Why (incident): two blind diagnoses already disagree or agree independently; a contrarian seat
# would slow the restore, and a second reply rarely adds evidence the first did not.
SESSION_TYPES: dict[str, dict[str, Any]] = {
    "plan": {"roles": {"proponent": 2, "dissent": 1, "examiner": 1}},
    "review": {"roles": {"examiner": 2, "dissent": 1}},
    "release-gate": {"roles": {"examiner": 1, "dissent": 1}},
    "incident": {"roles": {"proponent": 2}, "max_rounds": 2},
    "design": {"roles": {"proponent": "options", "dissent": 1}},
}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_DERIVED_PANEL_KEYS = ("sha256", "judge", "judge_independence", "families")


class DeliberationError(ValueError):
    """A panel, turn or deliberation record does not satisfy the contract."""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _hex(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        raise DeliberationError(f"{label} must be a 64-character lowercase sha256")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DeliberationError(f"{label} must be non-empty text")
    return value


# --------------------------------------------------------------------------- the panel

def _seat(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise DeliberationError("every seat must be an object")
    seat_id = _text(raw.get("id"), "seat id")
    role = raw.get("role")
    if role not in ROLES:
        raise DeliberationError(f"seat {seat_id}: role must be one of {', '.join(ROLES)}")
    model = _text(raw.get("model_served"), f"seat {seat_id}: model_served")
    if is_alias(model):
        raise DeliberationError(f"seat {seat_id}: model_served {model!r} is a moving alias; name the pinned version")
    return {"id": seat_id, "role": role, "provider": _text(raw.get("provider"), f"seat {seat_id}: provider"),
            "model_served": model, "family": _text(raw.get("family"), f"seat {seat_id}: family"),
            "lane": _text(raw.get("lane"), f"seat {seat_id}: lane")}


def normalise_panel(panel: Any) -> dict[str, Any]:
    """Return the normalised panel with its hash, or raise DeliberationError naming the first broken rule."""
    if not isinstance(panel, dict):
        raise DeliberationError("a panel must be an object")
    if panel.get("schema") != PANEL_SCHEMA:
        raise DeliberationError(f"schema must be {PANEL_SCHEMA}")
    panel_id = _text(panel.get("id"), "panel id")
    session_type = panel.get("session_type")
    if session_type not in SESSION_TYPES:
        raise DeliberationError(f"session_type must be one of {', '.join(SESSION_TYPES)}")
    try:
        question = normalise_question(panel.get("question"))
    except DecisionError as exc:
        raise DeliberationError(f"question: {exc}") from exc
    state = _hex(panel.get("state_sha256"), "state_sha256")
    raw_seats = panel.get("seats")
    if not isinstance(raw_seats, list) or not raw_seats:
        raise DeliberationError("a panel needs seats")
    seats = [_seat(item) for item in raw_seats]
    ids = [seat["id"] for seat in seats]
    if len(set(ids)) != len(ids):
        raise DeliberationError("seat ids must be unique")
    families_of: dict[str, str] = {}
    for seat in seats:
        # Why (review 2026-09-25): the family is declared, so two seats of the same pinned model
        # under two family names would pass the two-family rule while being one model.
        known = families_of.setdefault(seat["model_served"], seat["family"])
        if known != seat["family"]:
            raise DeliberationError(f"the same model {seat['model_served']!r} is declared under two families "
                                    f"({known!r} and {seat['family']!r}); one pinned model is one family")
    judges = [seat for seat in seats if seat["role"] == "judge"]
    if len(judges) != 1:
        raise DeliberationError(f"a panel needs exactly one judge seat, found {len(judges)}")
    judge = judges[0]
    participants = [seat for seat in seats if seat["role"] != "judge"]
    lanes = [seat["lane"] for seat in participants]
    if len(set(lanes)) != len(lanes):
        raise DeliberationError("every participant answers from its own lane; two seats share one")
    if judge["lane"] in lanes:
        raise DeliberationError("the judge sits outside the participants: its lane is a participant's lane")
    families = sorted({seat["family"] for seat in participants})
    if len(families) < 2:
        raise DeliberationError("the participants must come from at least two model families; "
                                "one family arguing with itself is ceremony, not diversity")
    rules = SESSION_TYPES[session_type]
    for role, minimum in rules["roles"].items():
        needed = len(question["options"]) if minimum == "options" else minimum
        present = sum(1 for seat in participants if seat["role"] == role)
        if present < needed:
            if minimum == "options":
                raise DeliberationError(f"a {session_type} session needs one proponent per option "
                                        f"({needed}), found {present}")
            raise DeliberationError(f"a {session_type} session needs at least {needed} {role} seat(s), found {present}")
    budget = panel.get("budget")
    if not isinstance(budget, dict):
        raise DeliberationError("a panel declares its budget: max_rounds and max_chars")
    max_rounds = budget.get("max_rounds")
    ceiling = rules.get("max_rounds", MAX_ROUNDS)
    if isinstance(max_rounds, bool) or not isinstance(max_rounds, int) or not 1 <= max_rounds <= MAX_ROUNDS:
        raise DeliberationError(f"budget.max_rounds must be a whole number from 1 to {MAX_ROUNDS}")
    if max_rounds > ceiling:
        raise DeliberationError(f"an {session_type} session allows at most {ceiling} rounds (one reply)")
    max_chars = budget.get("max_chars")
    if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars < 1:
        raise DeliberationError("budget.max_chars must be a positive whole number of characters")
    body = {"schema": PANEL_SCHEMA, "id": panel_id, "session_type": session_type, "question": question,
            "state_sha256": state, "seats": seats, "budget": {"max_rounds": max_rounds, "max_chars": max_chars}}
    computed = _hash(body)
    if "sha256" in panel and panel["sha256"] != computed:
        raise DeliberationError("panel sha256 does not match its content; the panel was edited after hashing")
    return {**body, "sha256": computed, "judge": judge["id"], "families": families,
            "judge_independence": "partial" if judge["family"] in families else "full"}


def _participants(panel: dict[str, Any]) -> list[str]:
    return [seat["id"] for seat in panel["seats"] if seat["role"] != "judge"]


# --------------------------------------------------------------------------- turns

def normalise_turn(turn: Any, panel: dict[str, Any]) -> dict[str, Any]:
    """Return the normalised turn with its hash. `panel` is a normalised panel."""
    if not isinstance(turn, dict):
        raise DeliberationError("a turn must be an object")
    if turn.get("schema") != TURN_SCHEMA:
        raise DeliberationError(f"turn schema must be {TURN_SCHEMA}")
    if turn.get("panel_sha256") != panel["sha256"]:
        raise DeliberationError("the turn belongs to a different panel (panel_sha256 does not match)")
    seat = turn.get("seat")
    if seat not in _participants(panel):
        raise DeliberationError(f"seat {seat!r} is not a participant of this panel (the judge takes no turns)")
    round_ = turn.get("round")
    if isinstance(round_, bool) or not isinstance(round_, int) or not 1 <= round_ <= panel["budget"]["max_rounds"]:
        raise DeliberationError(f"turn round must be from 1 to {panel['budget']['max_rounds']}")
    position = turn.get("position")
    if position != ABSTAIN and position not in panel["question"]["options"]:
        raise DeliberationError(f"position {position!r} is neither an option nor '{ABSTAIN}'")
    confidence = turn.get("confidence")
    if confidence is not None and (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                                   or not 0.0 <= float(confidence) <= 1.0):
        raise DeliberationError("confidence must be a number between 0 and 1, or null")
    raw_claims = turn.get("claims", [])
    if not isinstance(raw_claims, list):
        raise DeliberationError("claims must be a list")
    claims = []
    for claim in raw_claims:
        if not isinstance(claim, dict) or claim.get("kind") not in CLAIM_KINDS:
            raise DeliberationError(f"claim kind must be one of {', '.join(CLAIM_KINDS)}")
        refs = claim.get("refs", [])
        if not isinstance(refs, list) or not all(isinstance(ref, str) and ref for ref in refs) or len(set(refs)) != len(refs):
            raise DeliberationError("claim refs must be a list of unique, non-empty ids")
        claims.append({"kind": claim["kind"], "refs": list(refs)})
    text = _hex(turn.get("text_sha256"), "text_sha256")
    chars = turn.get("chars")
    if isinstance(chars, bool) or not isinstance(chars, int) or chars < 0:
        raise DeliberationError("chars must be the length of the verbatim text, a whole number >= 0")
    seen = turn.get("seen_turns")
    if not isinstance(seen, list) or not all(isinstance(item, str) and _HEX64.fullmatch(item) for item in seen) \
            or len(set(seen)) != len(seen):
        raise DeliberationError("seen_turns must list the hashes of the turns this seat had read")
    if round_ == 1 and seen:
        raise DeliberationError("the first round is blind: a round-1 turn cannot have seen other turns")
    body = {"schema": TURN_SCHEMA, "panel_sha256": panel["sha256"], "seat": seat, "round": round_,
            "position": position, "confidence": None if confidence is None else float(confidence),
            "claims": claims, "text_sha256": text, "chars": chars, "seen_turns": list(seen)}
    computed = _hash(body)
    if "sha256" in turn and turn["sha256"] != computed:
        raise DeliberationError("turn sha256 does not match its content; the turn was edited after hashing")
    return {**body, "sha256": computed}


def _grounded(turn: dict[str, Any]) -> bool:
    # F1: a position is grounded when the turn states at least one fact with a reference.
    return any(claim["kind"] == "fact" and claim["refs"] for claim in turn["claims"])


def _refs(turn: dict[str, Any]) -> set[str]:
    return {ref for claim in turn["claims"] for ref in claim["refs"]}


def _session(panel: Any, turns: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    normalised_panel = normalise_panel(panel)
    if not isinstance(turns, list):
        raise DeliberationError("turns must be a list")
    normalised = [normalise_turn(turn, normalised_panel) for turn in turns]
    order = {seat: index for index, seat in enumerate(_participants(normalised_panel))}
    normalised.sort(key=lambda turn: (turn["round"], order[turn["seat"]]))
    seen_pairs: set[tuple[str, int]] = set()
    round_of = {turn["sha256"]: turn["round"] for turn in normalised}
    for turn in normalised:
        pair = (turn["seat"], turn["round"])
        if pair in seen_pairs:
            raise DeliberationError(f"seat {turn['seat']} spoke twice in round {turn['round']}")
        seen_pairs.add(pair)
        for item in turn["seen_turns"]:
            if item not in round_of:
                raise DeliberationError(f"seat {turn['seat']} (round {turn['round']}) lists a seen turn that is not in this session")
            if round_of[item] >= turn["round"]:
                raise DeliberationError(f"seat {turn['seat']} (round {turn['round']}) can only have seen turns of an earlier round")
    rounds = sorted({turn["round"] for turn in normalised})
    if rounds and rounds != list(range(1, rounds[-1] + 1)):
        raise DeliberationError(f"rounds must run without gaps from 1; found {rounds}")
    return normalised_panel, normalised


# --------------------------------------------------------------------------- the count

def _tally(panel: dict[str, Any], turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    participants = _participants(panel)
    options = panel["question"]["options"]
    last = max((turn["round"] for turn in turns), default=0)
    tallies = []
    earlier_refs: set[str] = set()
    by_seat_refs: dict[str, set[str]] = {seat: set() for seat in participants}
    previous: dict[str, str] = {}
    for round_ in range(1, last + 1):
        current = {turn["seat"]: turn for turn in turns if turn["round"] == round_}
        votes = {option: {"grounded": 0, "ungrounded": 0} for option in options}
        abstained, not_judged = [], []
        for seat in participants:
            turn = current.get(seat)
            if turn is None:
                not_judged.append(seat)
            elif turn["position"] == ABSTAIN:
                abstained.append(seat)
            else:
                votes[turn["position"]]["grounded" if _grounded(turn) else "ungrounded"] += 1
        best = max((votes[option]["grounded"] for option in options), default=0)
        top = [option for option in options if votes[option]["grounded"] == best]
        leading = top[0] if best > 0 and len(top) == 1 else None
        answered = [current[seat] for seat in participants if seat in current]
        convergence = (not not_judged and not abstained and leading is not None
                       and all(turn["position"] == leading and _grounded(turn) for turn in answered))
        dissent = [turn["seat"] for turn in answered if leading is not None and _grounded(turn)
                   and turn["position"] not in (leading, ABSTAIN)]
        moved = [seat for seat, turn in current.items() if seat in previous and previous[seat] != turn["position"]]
        flips = [seat for seat in moved if not (_refs(current[seat]) - by_seat_refs[seat])]
        round_refs = set().union(*(_refs(turn) for turn in answered)) if answered else set()
        tallies.append({
            "round": round_, "votes": votes, "abstained": abstained, "not_judged": not_judged,
            "leading": leading, "grounded_convergence": convergence, "dissent": dissent,
            "moved": sorted(moved, key=participants.index),
            "flips_without_new_evidence": sorted(flips, key=participants.index),
            "new_refs": sorted(round_refs - earlier_refs),
            "chars": sum(turn["chars"] for turn in answered),
        })
        earlier_refs |= round_refs
        for seat, turn in current.items():
            by_seat_refs[seat] |= _refs(turn)
            previous[seat] = turn["position"]
    return tallies


def _checked(panel: Any, turns: Any) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    normalised_panel, normalised = _session(panel, turns)
    tallies = _tally(normalised_panel, normalised)
    # Why (review 2026-09-25): the stop was computed over the whole list only, so a round played
    # after a rule had fired decided the session - three flips could overturn a blind consensus,
    # and a seat absent from the blind round could vote after reading everyone. A session ends at
    # the first round where a rule holds; turns after it are refused, not counted.
    for index in range(len(tallies) - 1):
        stop = _stop(normalised_panel, tallies[:index + 1])
        if stop["decision"] == "stop":
            raise DeliberationError(f"the session stopped at round {index + 1} ({stop['reason']}); "
                                    f"turns of later rounds are not part of it")
    return normalised_panel, normalised, tallies


def tally(panel: Any, turns: Any) -> list[dict[str, Any]]:
    """Per-round count: grounded and ungrounded votes per option, abstentions, and seats not judged."""
    return _checked(panel, turns)[2]


def _stop(panel: dict[str, Any], tallies: list[dict[str, Any]]) -> dict[str, Any]:
    if not tallies:
        return {"decision": "continue", "next_round": 1, "reason": "no-turns-yet", "escalate": False}
    last = tallies[-1]
    round_ = last["round"]
    used = sum(item["chars"] for item in tallies)
    reason = None
    if last["not_judged"]:
        reason = "not-judged"
    elif last["grounded_convergence"]:
        reason = "grounded-convergence"
    elif used >= panel["budget"]["max_chars"]:
        reason = "paused-budget"
    elif round_ >= 2 and not last["new_refs"] and not last["moved"]:
        reason = "no-new-evidence"
    elif round_ >= panel["budget"]["max_rounds"]:
        reason = "max-rounds"
    if reason is None:
        return {"decision": "continue", "next_round": round_ + 1, "reason": "not-converged", "escalate": False}
    # Grounded dissent that survives to the end is not resolved by the panel: it goes to the human
    # as options, with the dissent preserved in the record.
    # Why (review 2026-09-25): reading `dissent` missed a grounded split with no leader (1-1-1),
    # where dissent is empty by construction. Two grounded positions standing is the condition.
    grounded_positions = [option for option, votes in last["votes"].items() if votes["grounded"]]
    escalate = reason in ("no-new-evidence", "max-rounds", "paused-budget") and len(grounded_positions) > 1
    return {"decision": "stop", "reason": reason, "round": round_, "escalate": escalate}


def decide_stop(panel: Any, turns: Any) -> dict[str, Any]:
    """`continue` with the next round, or `stop` with the rule that stopped the session."""
    normalised_panel, _, tallies = _checked(panel, turns)
    return _stop(normalised_panel, tallies)


# --------------------------------------------------------------------------- the record

def _agreement(tally_round: dict[str, Any]) -> Optional[float]:
    counts = [sum(item.values()) for item in tally_round["votes"].values()]
    voters = sum(counts)
    return (max(counts) / voters) if voters else None


def _judge(panel: dict[str, Any], judge: Any) -> dict[str, Any]:
    try:
        record = validate_decision(judge)
    except DecisionError as exc:
        raise DeliberationError(f"judge record: {exc}") from exc
    if record["question"]["sha256"] != panel["question"]["sha256"]:
        raise DeliberationError("the judge answered a different question than the panel's")
    if record["state_sha256"] != panel["state_sha256"]:
        raise DeliberationError("the judge judged a different state than the panel's")
    seat = next(item for item in panel["seats"] if item["id"] == panel["judge"])
    # Why (review 2026-09-25): the pin was checked only for model methods, so a judge record with
    # method `human`, `replay` or `lexical` passed with any provider, and the panel's decision then
    # named the seat's pinned model as the one that answered. The judge seat pins a model; its
    # record must come from that model and that provider.
    if record["method"] not in MODEL_METHODS:
        raise DeliberationError(f"the judge seat pins a model, so the judge record must come from it "
                                f"(method {' or '.join(MODEL_METHODS)}), not {record['method']!r}")
    if record["provider"]["id"] != seat["provider"]:
        raise DeliberationError(f"the judge record names provider {record['provider']['id']!r}, "
                                f"not the judge seat's {seat['provider']!r}")
    if record["provider"]["model_served"] != seat["model_served"]:
        raise DeliberationError(f"the judge record was served by {record['provider']['model_served']!r}, "
                                f"not by the judge seat's pinned model {seat['model_served']!r}")
    return record


def _body(panel_raw: Any, turns_raw: Any, judge_raw: Any) -> dict[str, Any]:
    panel, turns, tallies = _checked(panel_raw, turns_raw)
    stop = _stop(panel, tallies)
    if stop["decision"] != "stop":
        raise DeliberationError(f"the session has not stopped (next round {stop['next_round']}); run it or stop it first")
    final = tallies[-1]
    judge = None
    if stop["reason"] == "not-judged":
        verdict: dict[str, Any] = {"status": "blocked", "value": None,
                                   "reason": f"not judged: {', '.join(final['not_judged'])}"}
    else:
        if judge_raw is None:
            raise DeliberationError("a verdict needs the judge's decision record (hpp.decision/v1)")
        judge = _judge(panel, judge_raw)
        outcome = judge["outcome"]
        verdict = {"status": outcome["status"], "value": outcome["value"], "reason": "judge"}
        if outcome["status"] == "instrument-failure":
            verdict["error"] = outcome["error"]
    last_turns = [turn for turn in turns if turn["round"] == final["round"]]
    dissent = []
    if verdict["value"] is not None:
        dissent = [{"seat": turn["seat"], "position": turn["position"], "grounded": True}
                   for turn in last_turns if _grounded(turn) and turn["position"] not in (verdict["value"], ABSTAIN)]
    all_votes = [count for item in tallies for votes in item["votes"].values() for count in votes.items()]
    total_votes = sum(value for _, value in all_votes)
    ungrounded = sum(value for key, value in all_votes if key == "ungrounded")
    metrics = {
        "blind_agreement": _agreement(tallies[0]),
        "final_agreement": _agreement(final),
        "flips_without_new_evidence": sum(len(item["flips_without_new_evidence"]) for item in tallies),
        "ungrounded_share": (ungrounded / total_votes) if total_votes else None,
        "families": len(panel["families"]),
    }
    usage = {"rounds": final["round"], "chars": sum(item["chars"] for item in tallies),
             "max_rounds": panel["budget"]["max_rounds"], "max_chars": panel["budget"]["max_chars"]}
    return {"schema": SCHEMA, "panel": panel, "turns": turns, "tally": tallies, "stop": stop, "usage": usage,
            "judge": judge, "verdict": verdict, "dissent": dissent, "metrics": metrics,
            "judge_independence": panel["judge_independence"]}


def build_record(panel: Any, turns: Any, judge: Any = None) -> dict[str, Any]:
    """Assemble and seal an `hpp.deliberation/v1` record. The human decision is added later, outside the seal."""
    body = _body(panel, turns, judge)
    return {**body, "record_sha256": _hash(body), "human_decision": None}


def _check_human(record: dict[str, Any]) -> None:
    human = record.get("human_decision")
    if human is None:
        return
    panel = record.get("panel")
    question = panel.get("question") if isinstance(panel, dict) else None
    options = question.get("options") if isinstance(question, dict) else None
    if not isinstance(options, list):
        raise DeliberationError("the record has no question options to check human_decision against")
    if not isinstance(human, dict) or human.get("value") not in options \
            or not isinstance(human.get("by"), str) or not human["by"].strip() \
            or not isinstance(human.get("note", ""), str):
        raise DeliberationError("human_decision must be null or {value: an option, by: who decided, note?: text}")


def verify_record(record: Any) -> dict[str, Any]:
    """`intact` when the seal holds AND the record re-derives from its own turns and judge; else `broken`."""
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        return {"status": "broken", "reason": f"schema must be {SCHEMA}"}
    try:
        _check_human(record)
    except DeliberationError as exc:
        return {"status": "broken", "reason": str(exc)}
    body = {key: value for key, value in record.items() if key not in ("record_sha256", "human_decision")}
    if record.get("record_sha256") != _hash(body):
        return {"status": "broken", "reason": "record_sha256 does not match: the record was edited after it was sealed"}
    try:
        rebuilt = _body(record.get("panel"), record.get("turns"), record.get("judge"))
    except DeliberationError as exc:
        return {"status": "broken", "reason": f"the record does not re-derive: {exc}"}
    for key in rebuilt:
        if _canonical(rebuilt[key]) != _canonical(body.get(key)):
            return {"status": "broken",
                    "reason": f"the record does not re-derive from its own turns and judge: '{key}' differs"}
    extra = sorted(set(body) - set(rebuilt))
    if extra:
        return {"status": "broken", "reason": f"the record carries fields the contract does not define: {extra}"}
    return {"status": "intact", "record_sha256": record["record_sha256"], "verdict": record["verdict"],
            "stop": record["stop"]}


def as_decision(record: dict[str, Any]) -> dict[str, Any]:
    """The whole panel as ONE `hpp.decision/v1` record, so `hpp decide eval` measures it like any decider."""
    panel = record["panel"]
    verdict = record["verdict"]
    if verdict["status"] == "blocked":
        outcome: dict[str, Any] = {"status": "instrument-failure", "value": None, "confidence": None,
                                   "error": f"panel blocked: {verdict['reason']}"}
    elif verdict["status"] == "instrument-failure":
        outcome = {"status": "instrument-failure", "value": None, "confidence": None,
                   "error": f"judge failed: {verdict.get('error', 'unknown')}"}
    else:
        outcome = {"status": verdict["status"], "value": verdict["value"], "confidence": None}
    judge_seat = next(item for item in panel["seats"] if item["id"] == panel["judge"])
    judge = record.get("judge") or {}
    decision = {"schema": DECISION_SCHEMA, "question": panel["question"], "state_sha256": panel["state_sha256"],
                "method": "panel", "provider": {"id": panel["id"], "model_served": judge_seat["model_served"]},
                "outcome": outcome, "authority": "advisory",
                "direction": judge.get("direction", "informational"),
                "raw_response_sha256": record["record_sha256"]}
    if judge.get("declared") is not None:
        decision["declared"] = judge["declared"]
    return decision


def exit_for_record(record: dict[str, Any]) -> int:
    """0 when the panel reached the judge; 1 when the verdict is blocked or the judge failed."""
    return 0 if record["verdict"]["status"] in ("recommendation", "abstention") else 1
