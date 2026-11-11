"""In-memory fuzz properties for the public policy and JSON contracts."""
from __future__ import annotations

import json
import re
from typing import Any

from hpp.policy import BUILT_IN_ACTIONS, PolicyError, assess, exit_for, validate_policy

_RANK = {"ALLOW": 0, "MANUAL": 1, "BLOCK": 2}
_FIELDS = {"action", "rule", "reason", "source"}
_MAX_INPUT = 4096


def _verdict(command: str, policy: dict[str, Any] | None) -> dict[str, Any]:
    first = assess(command, policy)
    assert first == assess(command, policy), "policy classification must be deterministic"
    assert set(first) == _FIELDS, "verdict fields differ from the public contract"
    assert first["action"] in _RANK, "verdict has an unknown action"
    assert all(isinstance(value, str) and value for value in first.values())
    assert json.loads(json.dumps(first, ensure_ascii=True)) == first
    assert exit_for(first, "audit") == 0
    assert exit_for(first, "enforce") == _RANK[first["action"]]
    return first


def _compiled(policy: dict[str, Any]) -> dict[str, Any]:
    assert set(policy) == {"schema", "rules", "raise"}
    assert policy["schema"] == "hpp.policy/v1"
    ids = [rule[0] for rule in policy["rules"]]
    assert len(ids) == len(set(ids)), "duplicate policy rule ids were accepted"
    assert not set(ids) & set(BUILT_IN_ACTIONS), "a project rule redefined a built-in id"
    assert all(rule[3] in {"MANUAL", "BLOCK"} for rule in policy["rules"]), "an invalid rule action was accepted"
    assert all(BUILT_IN_ACTIONS.get(name) == "MANUAL" and action == "BLOCK"
               for name, action in policy["raise"].items()), "a raise failed to strengthen a manual gate"
    return {
        "schema": policy["schema"],
        "raise": policy["raise"],
        "rules": [(name, expression.pattern, expression.flags, reason, action)
                  for name, expression, reason, action in policy["rules"]],
    }


def _check_generated(command: str, data: bytes) -> None:
    literal = re.escape(command[:24] or "fuzz")
    raises = {name: "BLOCK" for name, action in BUILT_IN_ACTIONS.items() if action == "MANUAL"}
    for action in ("MANUAL", "BLOCK"):
        raw = {
            "schema": "hpp.policy/v1",
            "rules": [{"id": "fuzz-rule", "action": action, "pattern": literal, "reason": "local fuzz rule"}],
            "raise": raises if data and data[0] & 1 else {},
        }
        before = json.dumps(raw, sort_keys=True)
        policy = validate_policy(raw)
        assert json.dumps(raw, sort_keys=True) == before, "validation mutated its input"
        assert _compiled(policy) == _compiled(validate_policy(json.loads(before)))
        for probe in (command, "git push origin review", "git push origin main"):
            baseline = _verdict(probe, None)
            custom = _verdict(probe, policy)
            assert _RANK[custom["action"]] >= _RANK[baseline["action"]], "a project policy softened a built-in gate"


def _check_json(data: bytes) -> None:
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return
    document = raw.get("policy", raw) if isinstance(raw, dict) else raw
    try:
        first = validate_policy(document)
    except PolicyError as original:
        try:
            validate_policy(document)
        except PolicyError as repeated:
            assert str(original) == str(repeated), "policy rejection must be deterministic"
            return
        raise AssertionError("a rejected policy became valid after JSON round-trip")
    assert isinstance(document, dict)
    assert set(document) <= {"schema", "rules", "raise"}, "unknown policy fields were accepted"
    before = json.dumps(document, ensure_ascii=True, sort_keys=True)
    assert _compiled(first) == _compiled(validate_policy(json.loads(before)))
    assert json.dumps(document, ensure_ascii=True, sort_keys=True) == before, "validation mutated the JSON document"
    # Fixed BLOCK probes short-circuit before arbitrary user regex searches. Generated
    # literal patterns exercise custom searches independently in _check_generated.
    for probe in ("git push origin main", "rm -rf local-scratch"):
        assert _verdict(probe, first)["action"] == "BLOCK", "a JSON policy softened a built-in block"


def check_input(data: bytes) -> None:
    """Exercise classifiers and validation; input bytes never become code, commands or paths."""
    data = data[:_MAX_INPUT]
    command = data.decode("utf-8", "replace")[:256]
    _check_generated(command, data)
    _check_json(data)

