"""House Session: a deliberation between pinned deciders, recorded so it can be measured.

The harness still calls no model. What this file pins down is the contract a deliberation run
OUTSIDE the harness must satisfy: who sits (`hpp.panel/v1`), what each seat said
(`hpp.turn/v1`) and what the session concluded (`hpp.deliberation/v1`). Each refusal below is a
case the contract exists to stop, written as a test that fails if the input is accepted; each
CONTROLE proves the validator is not refusing everything.

The four properties that make a panel more than one model talking to itself:

- the first round is BLIND, and that is checkable (`seen_turns` must be empty);
- a seat that never answered is NOT JUDGED, never a vote against, and it blocks the verdict;
- the session STOPS by rule (grounded convergence, no new evidence, budget, round ceiling);
- the record SEALS itself (a hash over everything but the human decision) and re-derives its
  own tally from its own turns, so an edited record fails `verify`.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from hpp import cli
from hpp.decision import digest, run_decision_suite, validate as validate_decision
from hpp.deliberation import (
    DeliberationError,
    as_decision,
    build_record,
    decide_stop,
    normalise_panel,
    normalise_turn,
    tally,
    verify_record,
)

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = PRODUCT_ROOT / "examples" / "house-session"
SUITE = PRODUCT_ROOT / "examples" / "typed-decisions" / "gotcha-family-suite.json"

QUESTION = {"id": "route.risk", "kind": "choice", "options": ["low", "medium", "high"], "ladder": True,
            "instructions": "How much damage could this change do if it is wrong?"}
STATE = "delete the migration that created the invoices table"


def _seat(seat_id, role, family, lane=None, model=None):
    return {"id": seat_id, "role": role, "provider": f"{family}-provider", "family": family,
            "model_served": model or f"{family}-model-2026-09-01", "lane": lane or f"lane-{seat_id}"}


def _panel(**overrides):
    panel = {
        "schema": "hpp.panel/v1",
        "id": "risk-review-001",
        "session_type": "review",
        "question": dict(QUESTION),
        "state_sha256": digest(STATE),
        "seats": [
            _seat("a", "examiner", "alpha"),
            _seat("b", "examiner", "beta"),
            _seat("c", "dissent", "gamma"),
            _seat("j", "judge", "delta"),
        ],
        "budget": {"max_rounds": 3, "max_chars": 20000},
    }
    for key, value in overrides.items():
        if value is None:
            panel.pop(key, None)
        else:
            panel[key] = value
    return panel


def _turn(panel, seat, round_, position, refs=("ctx-1",), kind="fact", seen=(), chars=400, text=None):
    claims = [{"kind": kind, "refs": list(refs)}] if refs is not None else []
    return {
        "schema": "hpp.turn/v1",
        "panel_sha256": normalise_panel(panel)["sha256"],
        "seat": seat, "round": round_, "position": position, "confidence": None,
        "claims": claims,
        "text_sha256": hashlib.sha256((text or f"{seat}:{round_}:{position}").encode()).hexdigest(),
        "chars": chars, "seen_turns": list(seen),
    }


def _sha(panel, turn):
    return normalise_turn(turn, normalise_panel(panel))["sha256"]


def _judge(panel, value="high", status="recommendation", model="delta-model-2026-09-01"):
    outcome = {"status": status, "value": value if status == "recommendation" else None, "confidence": None}
    if status == "instrument-failure":
        outcome["error"] = "judge timed out"
    return {"schema": "hpp.decision/v1", "question": dict(QUESTION), "state_sha256": digest(STATE),
            "method": "external-model", "provider": {"id": "delta-provider", "model_served": model},
            "outcome": outcome, "authority": "advisory", "direction": "informational",
            "raw_response_sha256": hashlib.sha256(b"judge").hexdigest()}


def _round_one(panel, positions=("high", "high", "high")):
    return [_turn(panel, seat, 1, pos) for seat, pos in zip("abc", positions)]


# =========================================================================== F0 · the panel

def test_CONTROLE_a_complete_panel_is_valid_and_hashed():
    panel = normalise_panel(_panel())
    assert len(panel["sha256"]) == 64
    assert panel["judge"] == "j"
    assert panel["judge_independence"] == "full"
    assert normalise_panel(_panel())["sha256"] == panel["sha256"], "the panel hash must be stable"


def test_a_seat_served_by_a_moving_alias_is_refused():
    seats = _panel()["seats"]
    seats[0]["model_served"] = "alpha-latest"
    with pytest.raises(DeliberationError, match="pinned"):
        normalise_panel(_panel(seats=seats))


def test_CONTROLE_the_same_seat_pinned_is_accepted():
    seats = _panel()["seats"]
    seats[0]["model_served"] = "alpha-2026-08-14"
    assert normalise_panel(_panel(seats=seats))["seats"][0]["model_served"] == "alpha-2026-08-14"


def test_a_judge_sitting_in_a_participant_lane_is_refused():
    seats = _panel()["seats"]
    seats[3]["lane"] = seats[0]["lane"]
    with pytest.raises(DeliberationError, match="judge sits outside"):
        normalise_panel(_panel(seats=seats))


def test_CONTROLE_a_judge_in_its_own_lane_is_accepted():
    assert normalise_panel(_panel())["judge"] == "j"


def test_a_panel_of_one_model_family_is_refused():
    seats = [_seat("a", "examiner", "alpha"), _seat("b", "examiner", "alpha"),
             _seat("c", "dissent", "alpha"), _seat("j", "judge", "delta")]
    with pytest.raises(DeliberationError, match="two model families"):
        normalise_panel(_panel(seats=seats))


def test_CONTROLE_two_families_are_enough():
    seats = [_seat("a", "examiner", "alpha"), _seat("b", "examiner", "alpha"),
             _seat("c", "dissent", "beta"), _seat("j", "judge", "delta")]
    assert len(normalise_panel(_panel(seats=seats))["families"]) == 2


def test_a_review_without_a_dissenting_seat_is_refused():
    seats = [_seat("a", "examiner", "alpha"), _seat("b", "examiner", "beta"),
             _seat("c", "examiner", "gamma"), _seat("j", "judge", "delta")]
    with pytest.raises(DeliberationError, match="dissent"):
        normalise_panel(_panel(seats=seats))


def test_CONTROLE_the_same_review_with_a_dissent_is_accepted():
    assert [seat["role"] for seat in normalise_panel(_panel())["seats"]].count("dissent") == 1


@pytest.mark.parametrize("mutation, fragment", [
    ({"schema": "hpp.panel/v0"}, "schema must be"),
    ({"session_type": "chat"}, "session_type"),
    ({"budget": None}, "budget"),
    ({"budget": {"max_rounds": 0, "max_chars": 100}}, "max_rounds"),
    ({"budget": {"max_rounds": 3, "max_chars": 0}}, "max_chars"),
    ({"state_sha256": "abc"}, "state_sha256"),
    ({"question": {"id": "q", "kind": "score", "options": ["a", "b"]}}, "choice"),
])
def test_the_panel_contract_refuses_each_malformed_panel(mutation, fragment):
    with pytest.raises(DeliberationError, match=fragment):
        normalise_panel(_panel(**mutation))


def test_a_panel_needs_exactly_one_judge():
    seats = _panel()["seats"] + [_seat("k", "judge", "epsilon")]
    with pytest.raises(DeliberationError, match="exactly one judge"):
        normalise_panel(_panel(seats=seats))
    with pytest.raises(DeliberationError, match="exactly one judge"):
        normalise_panel(_panel(seats=_panel()["seats"][:3]))


def test_two_participants_cannot_share_a_lane_or_an_id():
    seats = _panel()["seats"]
    seats[1]["lane"] = seats[0]["lane"]
    with pytest.raises(DeliberationError, match="own lane"):
        normalise_panel(_panel(seats=seats))
    seats = _panel()["seats"]
    seats[1]["id"] = "a"
    with pytest.raises(DeliberationError, match="unique"):
        normalise_panel(_panel(seats=seats))


def test_an_incident_allows_at_most_one_reply():
    seats = [_seat("a", "proponent", "alpha"), _seat("b", "proponent", "beta"), _seat("j", "judge", "delta")]
    with pytest.raises(DeliberationError, match="incident"):
        normalise_panel(_panel(session_type="incident", seats=seats, budget={"max_rounds": 3, "max_chars": 9000}))
    assert normalise_panel(_panel(session_type="incident", seats=seats,
                                  budget={"max_rounds": 2, "max_chars": 9000}))["session_type"] == "incident"


def test_a_design_session_needs_one_advocate_per_option():
    seats = [_seat("a", "proponent", "alpha"), _seat("b", "proponent", "beta"),
             _seat("c", "dissent", "gamma"), _seat("j", "judge", "delta")]
    with pytest.raises(DeliberationError, match="one proponent per option"):
        normalise_panel(_panel(session_type="design", seats=seats))
    seats.insert(2, _seat("p", "proponent", "gamma"))
    assert normalise_panel(_panel(session_type="design", seats=seats))["session_type"] == "design"


def test_a_judge_of_a_participant_family_is_declared_partial_not_hidden():
    seats = _panel()["seats"]
    seats[3]["family"] = "alpha"
    assert normalise_panel(_panel(seats=seats))["judge_independence"] == "partial"


# =========================================================================== F1 · blindness

def test_a_first_round_turn_that_saw_other_turns_is_refused():
    panel = _panel()
    seen_one = _sha(panel, _turn(panel, "b", 1, "high"))
    with pytest.raises(DeliberationError, match="blind"):
        normalise_turn(_turn(panel, "a", 1, "high", seen=[seen_one]), normalise_panel(panel))


def test_CONTROLE_a_first_round_turn_with_nothing_seen_is_accepted():
    panel = _panel()
    assert normalise_turn(_turn(panel, "a", 1, "high"), normalise_panel(panel))["round"] == 1


def test_a_turn_cannot_claim_to_have_seen_a_turn_of_its_own_round():
    panel = _panel()
    first = _round_one(panel, ("high", "medium", "low"))
    second_b = _turn(panel, "b", 2, "high", refs=("ctx-2",), seen=[_sha(panel, t) for t in first])
    cheating = _turn(panel, "a", 2, "high", seen=[_sha(panel, second_b)])
    with pytest.raises(DeliberationError, match="earlier round"):
        tally(panel, first + [second_b, cheating, _turn(panel, "c", 2, "low", seen=[])])


@pytest.mark.parametrize("mutation, fragment", [
    ({"seat": "zz"}, "not a participant"),
    ({"seat": "j"}, "not a participant"),
    ({"round": 4}, "round"),
    ({"position": "maybe"}, "position"),
    ({"panel_sha256": "0" * 64}, "different panel"),
    ({"claims": [{"kind": "rumour", "refs": []}]}, "claim kind"),
    ({"text_sha256": "not-a-hash"}, "text_sha256"),
    ({"chars": -1}, "chars"),
])
def test_the_turn_contract_refuses_each_malformed_turn(mutation, fragment):
    panel = _panel()
    turn = {**_turn(panel, "a", 1, "high"), **mutation}
    with pytest.raises(DeliberationError, match=fragment):
        normalise_turn(turn, normalise_panel(panel))


def test_one_turn_per_seat_per_round():
    panel = _panel()
    turns = _round_one(panel) + [_turn(panel, "a", 1, "low", text="again")]
    with pytest.raises(DeliberationError, match="twice"):
        tally(panel, turns)


# =========================================================================== F1 · the count

def test_a_seat_that_never_answered_is_not_judged_never_a_vote():
    panel = _panel()
    rounds = tally(panel, _round_one(panel)[:2])
    first = rounds[0]
    assert first["not_judged"] == ["c"]
    assert sum(sum(votes.values()) for votes in first["votes"].values()) == 2, "a dead seat must not be counted as a vote"


def test_an_ungrounded_position_is_counted_apart_from_a_grounded_one():
    panel = _panel()
    turns = [_turn(panel, "a", 1, "high"), _turn(panel, "b", 1, "high", refs=None),
             _turn(panel, "c", 1, "low", kind="opinion")]
    first = tally(panel, turns)[0]
    assert first["votes"]["high"] == {"grounded": 1, "ungrounded": 1}
    assert first["votes"]["low"] == {"grounded": 0, "ungrounded": 1}
    assert first["leading"] == "high"


def test_CONTROLE_three_grounded_votes_converge():
    panel = _panel()
    first = tally(panel, _round_one(panel))[0]
    assert first["grounded_convergence"] is True
    assert first["not_judged"] == [] and first["dissent"] == []


def test_a_change_of_position_without_new_evidence_is_marked():
    panel = _panel()
    first = _round_one(panel, ("high", "high", "low"))
    seen = [_sha(panel, t) for t in first]
    second = [_turn(panel, "a", 2, "high", seen=seen), _turn(panel, "b", 2, "high", seen=seen),
              _turn(panel, "c", 2, "high", refs=("ctx-1",), seen=seen)]
    assert tally(panel, first + second)[1]["flips_without_new_evidence"] == ["c"]


def test_CONTROLE_a_change_of_position_brought_by_a_new_reference_is_not_marked():
    panel = _panel()
    first = _round_one(panel, ("high", "high", "low"))
    seen = [_sha(panel, t) for t in first]
    second = [_turn(panel, "a", 2, "high", seen=seen), _turn(panel, "b", 2, "high", seen=seen),
              _turn(panel, "c", 2, "high", refs=("ctx-9",), seen=seen)]
    assert tally(panel, first + second)[1]["flips_without_new_evidence"] == []


# =========================================================================== F1 · stopping

def test_nothing_said_yet_means_run_the_first_round():
    assert decide_stop(_panel(), []) == {"decision": "continue", "next_round": 1, "reason": "no-turns-yet",
                                        "escalate": False}


def test_grounded_convergence_in_the_blind_round_stops_early():
    stop = decide_stop(_panel(), _round_one(_panel()))
    assert (stop["decision"], stop["reason"]) == ("stop", "grounded-convergence")


def test_a_round_that_brought_no_new_reference_and_moved_nobody_stops():
    panel = _panel()
    first = _round_one(panel, ("high", "high", "low"))
    seen = [_sha(panel, t) for t in first]
    second = [_turn(panel, s, 2, p, seen=seen) for s, p in zip("abc", ("high", "high", "low"))]
    stop = decide_stop(panel, first + second)
    assert (stop["decision"], stop["reason"]) == ("stop", "no-new-evidence")
    assert stop["escalate"] is True, "grounded dissent that survives a round goes to the human as A/B/C"


def test_CONTROLE_a_round_with_a_new_reference_continues():
    panel = _panel()
    first = _round_one(panel, ("high", "high", "low"))
    seen = [_sha(panel, t) for t in first]
    second = [_turn(panel, "a", 2, "high", seen=seen), _turn(panel, "b", 2, "high", seen=seen),
              _turn(panel, "c", 2, "low", refs=("ctx-7",), seen=seen)]
    stop = decide_stop(panel, first + second)
    assert (stop["decision"], stop["next_round"]) == ("continue", 3)


def test_the_character_budget_pauses_the_session():
    panel = _panel(budget={"max_rounds": 3, "max_chars": 1000})
    stop = decide_stop(panel, _round_one(panel, ("high", "medium", "low")))
    assert (stop["decision"], stop["reason"]) == ("stop", "paused-budget")


def test_the_round_ceiling_stops_the_session():
    panel = _panel(budget={"max_rounds": 1, "max_chars": 20000})
    stop = decide_stop(panel, _round_one(panel, ("high", "medium", "low")))
    assert (stop["decision"], stop["reason"]) == ("stop", "max-rounds")


def test_a_dead_seat_stops_the_session_as_not_judged():
    stop = decide_stop(_panel(), _round_one(_panel())[:2])
    assert (stop["decision"], stop["reason"]) == ("stop", "not-judged")


# =========================================================================== F1 · the record

def test_CONTROLE_a_live_panel_with_a_judge_produces_a_verdict():
    panel = _panel()
    record = build_record(panel, _round_one(panel), _judge(panel))
    assert record["verdict"] == {"status": "recommendation", "value": "high", "reason": "judge"}
    assert verify_record(record)["status"] == "intact"


def test_a_dead_seat_blocks_the_verdict_even_with_a_judge():
    panel = _panel()
    record = build_record(panel, _round_one(panel)[:2], _judge(panel))
    assert record["verdict"]["status"] == "blocked"
    assert "c" in record["verdict"]["reason"]
    decision = validate_decision(as_decision(record))
    assert decision["outcome"]["status"] == "instrument-failure", "a blocked panel is never a verdict"


def test_a_session_that_has_not_stopped_cannot_be_recorded():
    panel = _panel()
    first = _round_one(panel, ("high", "high", "low"))
    seen = [_sha(panel, t) for t in first]
    second = [_turn(panel, "a", 2, "high", seen=seen), _turn(panel, "b", 2, "high", seen=seen),
              _turn(panel, "c", 2, "low", refs=("ctx-7",), seen=seen)]
    with pytest.raises(DeliberationError, match="has not stopped"):
        build_record(panel, first + second, _judge(panel))


def test_a_verdict_needs_the_judge():
    with pytest.raises(DeliberationError, match="judge"):
        build_record(_panel(), _round_one(_panel()), None)


@pytest.mark.parametrize("judge_kwargs, fragment", [
    ({"model": "epsilon-model-2026-09-01"}, "judge seat"),
])
def test_a_judge_record_from_another_model_is_refused(judge_kwargs, fragment):
    panel = _panel()
    with pytest.raises(DeliberationError, match=fragment):
        build_record(panel, _round_one(panel), _judge(panel, **judge_kwargs))


def test_a_judge_that_answered_another_question_or_state_is_refused():
    panel = _panel()
    other_question = _judge(panel)
    other_question["question"] = {**QUESTION, "instructions": "something else"}
    with pytest.raises(DeliberationError, match="different question"):
        build_record(panel, _round_one(panel), other_question)
    other_state = _judge(panel)
    other_state["state_sha256"] = digest("another change")
    with pytest.raises(DeliberationError, match="different state"):
        build_record(panel, _round_one(panel), other_state)


def test_dissent_that_lost_is_preserved_in_the_record():
    panel = _panel()
    first = _round_one(panel, ("high", "high", "low"))
    seen = [_sha(panel, t) for t in first]
    second = [_turn(panel, s, 2, p, seen=seen) for s, p in zip("abc", ("high", "high", "low"))]
    record = build_record(panel, first + second, _judge(panel))
    assert record["dissent"] == [{"seat": "c", "position": "low", "grounded": True}]
    assert record["stop"]["escalate"] is True


def test_an_edited_record_fails_verify():
    panel = _panel()
    record = build_record(panel, _round_one(panel), _judge(panel))
    edited = copy.deepcopy(record)
    edited["verdict"]["value"] = "low"
    report = verify_record(edited)
    assert report["status"] == "broken"
    assert "record_sha256" in report["reason"]


def test_a_resealed_forgery_fails_because_the_tally_does_not_re_derive():
    panel = _panel()
    record = build_record(panel, _round_one(panel), _judge(panel))
    forged = copy.deepcopy(record)
    forged["tally"][0]["votes"]["low"]["grounded"] = 9
    body = {key: value for key, value in forged.items() if key not in ("record_sha256", "human_decision")}
    forged["record_sha256"] = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
                                                        ensure_ascii=False).encode()).hexdigest()
    report = verify_record(forged)
    assert report["status"] == "broken"
    assert "re-derive" in report["reason"]


def test_the_human_decision_is_recorded_outside_the_seal():
    panel = _panel()
    record = build_record(panel, _round_one(panel), _judge(panel))
    record["human_decision"] = {"value": "medium", "by": "maintainer", "note": "shipping behind a flag"}
    assert verify_record(record)["status"] == "intact"
    record["human_decision"] = {"value": "enormous", "by": "maintainer"}
    assert verify_record(record)["status"] == "broken"


def test_the_panel_projects_to_a_decision_the_ruler_already_reads():
    panel = _panel()
    record = build_record(panel, _round_one(panel), _judge(panel))
    decision = validate_decision(as_decision(record))
    assert decision["method"] == "panel"
    assert decision["outcome"]["value"] == "high"
    assert decision["outcome"]["confidence"] is None, "a panel publishes no confidence it did not measure"
    assert decision["raw_response_sha256"] == record["record_sha256"]


def test_a_panel_decision_cannot_claim_a_confidence():
    panel = _panel()
    projected = as_decision(build_record(panel, _round_one(panel), _judge(panel)))
    projected["outcome"]["confidence"] = 0.9
    with pytest.raises(ValueError, match="confidence"):
        validate_decision(projected)


# =========================================================================== F1 · measured as one decider

def _panel_decider(tmp_path, sessions=None):
    command = [sys.executable, str(EXAMPLE / "panel_decider.py")]
    if sessions is not None:
        path = tmp_path / "sessions.json"
        path.write_text(json.dumps(sessions), encoding="utf-8")
        command += ["--sessions", str(path)]
    return command


def test_CONTROLE_the_shipped_panel_replay_passes_the_ruler(tmp_path):
    report = run_decision_suite(SUITE, decider_command=_panel_decider(tmp_path), timeout=30)
    assert report["gate"]["passed"], report["gate"]["reason"]
    assert report["metrics"]["failed"] == 0


def test_a_wrong_panel_fails_the_same_ruler(tmp_path):
    sessions = json.loads((EXAMPLE / "sessions.json").read_text(encoding="utf-8"))
    for session in sessions["sessions"][:3]:
        if session["judge"]["status"] == "recommendation":
            session["judge"]["value"] = "fatal" if session["judge"]["value"] != "fatal" else "lock"
    report = run_decision_suite(SUITE, decider_command=_panel_decider(tmp_path, sessions), timeout=30)
    assert not report["gate"]["passed"]
    assert report["metrics"]["selective_accuracy"] < 0.9


def test_a_panel_with_a_dead_seat_is_an_instrument_failure_in_the_ruler(tmp_path):
    sessions = json.loads((EXAMPLE / "sessions.json").read_text(encoding="utf-8"))
    sessions["sessions"][0]["turns"] = sessions["sessions"][0]["turns"][:1]
    report = run_decision_suite(SUITE, decider_command=_panel_decider(tmp_path, sessions), timeout=30)
    assert report["metrics"]["failed"] == 1
    assert not report["gate"]["passed"]


# =========================================================================== the command line

def _write(tmp_path, name, value):
    path = tmp_path / name
    path.write_text(json.dumps(value), encoding="utf-8")
    return str(path)


def test_cli_deliberate_follows_the_exit_contract(tmp_path, capsys):
    panel = _panel()
    panel_path = _write(tmp_path, "panel.json", panel)
    turns_path = _write(tmp_path, "turns.json", _round_one(panel))
    judge_path = _write(tmp_path, "judge.json", _judge(panel))
    record_path = tmp_path / "record.json"

    assert cli.main(["deliberate", "plan", panel_path]) == 0
    assert cli.main(["deliberate", "validate", panel_path]) == 0
    bad = copy.deepcopy(panel)
    bad["seats"][0]["model_served"] = "alpha-latest"
    assert cli.main(["deliberate", "validate", _write(tmp_path, "bad.json", bad)]) == 2

    assert cli.main(["deliberate", "tally", "--panel", panel_path, "--turns", turns_path]) == 0
    capsys.readouterr()
    assert cli.main(["deliberate", "stop", "--panel", panel_path, "--turns", turns_path]) == 0
    assert json.loads(capsys.readouterr().out)["reason"] == "grounded-convergence"

    assert cli.main(["deliberate", "record", "--panel", panel_path, "--turns", turns_path,
                     "--judge", judge_path, "--out", str(record_path)]) == 0
    assert cli.main(["deliberate", "verify", str(record_path)]) == 0
    assert cli.main(["deliberate", "validate", str(record_path)]) == 0
    edited = json.loads(record_path.read_text(encoding="utf-8"))
    edited["verdict"]["value"] = "low"
    assert cli.main(["deliberate", "verify", _write(tmp_path, "edited.json", edited)]) == 2

    dead_turns = _write(tmp_path, "dead.json", _round_one(panel)[:2])
    assert cli.main(["deliberate", "record", "--panel", panel_path, "--turns", dead_turns,
                     "--out", str(tmp_path / "blocked.json")]) == 1, "a blocked verdict is recorded, and warns"


def test_the_documented_example_command_runs(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "hpp", "decide", "eval", str(SUITE),
         "--decider-command", json.dumps([sys.executable, str(EXAMPLE / "panel_decider.py")])],
        cwd=PRODUCT_ROOT, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["gate"]["passed"] is True


# =========================================================================== cross-model review, round 1
# Each test below reproduces a defect the checker found in the first version; each failed before
# its fix. The codes are the checker's.

@pytest.mark.parametrize("method, provider", [
    ("human", None),
    ("replay", {"id": "x", "model_served": "epsilon-model-2026-09-01"}),
    ("lexical", None),
])
def test_JUDGE_PIN_BYPASS_a_judge_that_is_not_the_seats_model_is_refused(method, provider):
    panel = _panel()
    judge = {**_judge(panel, value="low"), "method": method}
    if provider is None:
        judge.pop("provider")
        judge.pop("raw_response_sha256")
    else:
        judge["provider"] = provider
    with pytest.raises(DeliberationError, match="judge"):
        build_record(panel, _round_one(panel), judge)


def test_JUDGE_PROVIDER_ID_UNCHECKED_the_judge_provider_must_be_the_seats():
    panel = _panel()
    judge = _judge(panel)
    judge["provider"] = {"id": "someone-else", "model_served": "delta-model-2026-09-01"}
    with pytest.raises(DeliberationError, match="provider"):
        build_record(panel, _round_one(panel), judge)


def test_DEAD_SEAT_SKIPS_BLIND_ROUND_a_seat_absent_from_the_blind_round_cannot_vote_later():
    panel = _panel()
    first = _round_one(panel)[:2]
    seen = [_sha(panel, t) for t in first]
    second = [_turn(panel, s, 2, "high", seen=seen) for s in "abc"]
    with pytest.raises(DeliberationError, match="stopped at round 1"):
        build_record(panel, first + second, _judge(panel))


def test_STOP_NOT_ENFORCED_PER_ROUND_turns_after_a_stop_are_not_part_of_the_session():
    panel = _panel()
    first = _round_one(panel)
    seen = [_sha(panel, t) for t in first]
    second = [_turn(panel, s, 2, "low", seen=seen) for s in "abc"]
    with pytest.raises(DeliberationError, match="stopped at round 1 .grounded-convergence."):
        build_record(panel, first + second, _judge(panel, value="low"))
    with pytest.raises(DeliberationError, match="stopped at round 1"):
        decide_stop(panel, first + second)


def test_ESCALATE_MISSES_GROUNDED_TIE_a_grounded_split_with_no_leader_escalates():
    panel = _panel(budget={"max_rounds": 1, "max_chars": 20000})
    stop = decide_stop(panel, _round_one(panel, ("high", "low", "medium")))
    assert (stop["reason"], stop["escalate"]) == ("max-rounds", True)


def test_CONTROLE_one_grounded_position_and_abstentions_do_not_escalate():
    panel = _panel(budget={"max_rounds": 1, "max_chars": 20000})
    turns = [_turn(panel, "a", 1, "high"), _turn(panel, "b", 1, "abstain", kind="opinion"),
             _turn(panel, "c", 1, "high", refs=None)]
    stop = decide_stop(panel, turns)
    assert (stop["reason"], stop["escalate"]) == ("max-rounds", False)


def test_DOC_OVERCLAIM_SEAL_the_seal_proves_derivation_not_the_authenticity_of_its_inputs():
    """The documented limit: a consistent rewrite of the judge's record, resealed, verifies.

    What catches it is outside the record: the judge's raw response, whose hash no longer matches
    the rewritten record. `verify` is not an authentication, and the docs say so.
    """
    panel = _panel()
    record = build_record(panel, _round_one(panel), _judge(panel))
    forged = copy.deepcopy(record)
    forged["judge"]["outcome"]["value"] = "low"
    forged["verdict"]["value"] = "low"
    forged["dissent"] = [{"seat": seat, "position": "high", "grounded": True} for seat in "abc"]
    body = {key: value for key, value in forged.items() if key not in ("record_sha256", "human_decision")}
    forged["record_sha256"] = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
                                                        ensure_ascii=False).encode()).hexdigest()
    assert verify_record(forged)["status"] == "intact"
    assert forged["judge"]["raw_response_sha256"] == record["judge"]["raw_response_sha256"], \
        "the anchor that exposes the rewrite is the raw response kept outside the record"


def test_VERIFY_KEYERROR_EXIT3_a_malformed_record_is_broken_not_an_internal_error():
    report = verify_record({"schema": "hpp.deliberation/v1", "panel": {"question": {}},
                            "human_decision": {"value": "x", "by": "y"}})
    assert report["status"] == "broken"


def test_HEX_ACCEPTS_TRAILING_NEWLINE_a_hash_with_a_trailing_newline_is_refused():
    panel = _panel()
    turn = {**_turn(panel, "a", 1, "high"), "text_sha256": "a" * 64 + "\n"}
    with pytest.raises(DeliberationError, match="text_sha256"):
        normalise_turn(turn, normalise_panel(panel))
    with pytest.raises(ValueError, match="state_sha256"):
        validate_decision({**_judge(panel), "state_sha256": digest(STATE) + "\n"})


def test_FAMILY_DIVERSITY_SELF_DECLARED_one_pinned_model_cannot_be_two_families():
    seats = _panel()["seats"]
    seats[1]["model_served"] = seats[0]["model_served"]
    with pytest.raises(DeliberationError, match="same model"):
        normalise_panel(_panel(seats=seats))
