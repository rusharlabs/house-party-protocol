"""Replays recorded House Sessions as ONE decider, so `hpp decide eval` measures the whole panel.

Reads {"question": ..., "state": ...} on stdin (what `hpp decide eval` sends), finds the session
recorded for that state in `sessions.json`, rebuilds its turns and the judge's record, seals the
deliberation with `hpp.deliberation`, verifies the seal, and prints the panel's verdict as one
`hpp.decision/v1` record. Nothing here calls a model: the sessions were recorded beforehand.

    python -m hpp decide eval examples/typed-decisions/gotcha-family-suite.json \
        --decider-command '["python", "examples/house-session/panel_decider.py"]'

A state with no recorded session, or a question other than the panel's, exits non-zero: the ruler
counts that as an instrument failure, never as an answer.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

try:
    _HAS_DELIBERATION = importlib.util.find_spec("hpp.deliberation") is not None
except ModuleNotFoundError:
    _HAS_DELIBERATION = False
if not _HAS_DELIBERATION:
    # Why: run as `python examples/house-session/<script>.py` from a checkout, the script's own
    # directory is on sys.path and the checkout root is not; and an older installed hpp without
    # `hpp.deliberation` must not win over the checkout beside the script.
    sys.modules.pop("hpp", None)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hpp.decision import SCHEMA as DECISION_SCHEMA, digest, normalise_question
from hpp.deliberation import TURN_SCHEMA, as_decision, build_record, normalise_panel, normalise_turn, verify_record

HERE = Path(__file__).resolve().parent


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def replay(request: dict, sessions: dict) -> dict:
    question = normalise_question(request["question"])
    state = digest(request["state"])
    template = sessions["panel"]
    if normalise_question(template["question"])["sha256"] != question["sha256"]:
        raise SystemExit("panel_decider: the suite asks a different question than the recorded panel")
    session = next((item for item in sessions["sessions"] if item["state_sha256"] == state), None)
    if session is None:
        raise SystemExit("panel_decider: no session was recorded for this state")
    panel = {**template, "id": f"{template['id']}-{session['case']}", "state_sha256": state}
    normalised = normalise_panel(panel)
    panel_sha = normalised["sha256"]
    hashes: dict[str, str] = {}
    turns = []
    for raw in sorted(session["turns"], key=lambda item: item["round"]):
        turn = {"schema": TURN_SCHEMA, "panel_sha256": panel_sha, "seat": raw["seat"], "round": raw["round"],
                "position": raw["position"], "confidence": None, "claims": raw["claims"],
                "text_sha256": _sha(raw["text"]), "chars": len(raw["text"]),
                "seen_turns": [hashes[key] for key in raw.get("seen", [])]}
        turns.append(turn)
        # Why: a later turn names what it read as "seat:round"; its hash is only known once that
        # turn is normalised, so hashes are filled in round order.
        hashes[f"{raw['seat']}:{raw['round']}"] = normalise_turn(turn, normalised)["sha256"]
    judge_seat = next(seat for seat in template["seats"] if seat["role"] == "judge")
    verdict = session["judge"]
    judge = {"schema": DECISION_SCHEMA, "question": question, "state_sha256": state, "method": "external-model",
             "provider": {"id": judge_seat["provider"], "model_served": judge_seat["model_served"]},
             "outcome": {"status": verdict["status"],
                         "value": verdict.get("value") if verdict["status"] == "recommendation" else None,
                         "confidence": None},
             "authority": "advisory", "direction": "informational",
             "raw_response_sha256": _sha(verdict["text"])}
    record = build_record(panel, turns, judge)
    report = verify_record(record)
    if report["status"] != "intact":
        raise SystemExit(f"panel_decider: the rebuilt record does not verify: {report['reason']}")
    return as_decision(record)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sessions", default=str(HERE / "sessions.json"))
    args = parser.parse_args()
    sessions = json.loads(Path(args.sessions).read_text(encoding="utf-8"))
    request = json.loads(sys.stdin.read())
    print(json.dumps(replay(request, sessions), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
