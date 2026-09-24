"""A lexical decider: the baseline any model-backed decider has to beat.

Reads {"question": ..., "state": ...} on stdin (what `hpp decide eval` sends) and prints one
`hpp.decision/v1` record. It abstains when no family matches or when two families tie, and it
never claims a confidence: a keyword count is not a probability.

    python -m hpp decide eval examples/typed-decisions/gotcha-family-suite.json \
        --decider-command '["python", "examples/typed-decisions/baseline_decider.py"]'
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

try:
    _HAS_DECISIONS = importlib.util.find_spec("hpp.decision") is not None
except ModuleNotFoundError:
    _HAS_DECISIONS = False
if not _HAS_DECISIONS:
    # Why: run as `python examples/typed-decisions/<script>.py` from a checkout, the script's own
    # directory is on sys.path and the checkout root is not; and an older installed hpp without
    # `hpp.decision` must not win over the checkout beside the script.
    sys.modules.pop("hpp", None)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hpp.decision import SCHEMA, digest, normalise_question

KEYWORDS = {
    "instrument": ("broken pipe", "unexpected end of file", "not in sorted order", "sigpipe"),
    "lock": ("lock", "locked", "index.lock", "resource busy"),
    "ratelimit": ("429", "rate limit", "too many requests", "quota"),
    "transient": ("timed out", "timeout", "connection reset", "temporarily unavailable", "503"),
    "state": ("already exists", "not a git repository", "detached head", "conflict", "no such file"),
    "config": ("permission denied", "not found in path", "invalid option", "unknown option", "missing required"),
    "dependency": ("modulenotfounderror", "no module named", "cannot find module", "could not resolve dependencies"),
    "fatal": ("segmentation fault", "out of memory", "killed", "core dumped"),
}


def decide(request: dict) -> dict:
    question = normalise_question(request["question"])
    state = request["state"]
    text = state.lower()
    hits = sorted(family for family, words in KEYWORDS.items()
                  if family in question["options"] and any(word in text for word in words))
    outcome = {"status": "abstention", "value": None, "confidence": None}
    if len(hits) == 1:
        outcome = {"status": "recommendation", "value": hits[0], "confidence": None}
    return {"schema": SCHEMA, "question": question, "state_sha256": digest(state), "method": "lexical",
            "outcome": outcome, "authority": "advisory", "direction": "informational"}


def main() -> int:
    request = json.loads(sys.stdin.read())
    print(json.dumps(decide(request), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
