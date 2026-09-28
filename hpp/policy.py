"""Small, explicit policy classifier; it never executes a command.

The built-in rules are fixed. A project may declare more in a policy file (`.hpp/policy.json`,
`hpp.policy/v1`): rules of its own that earn `BLOCK` or `MANUAL`, and built-in `MANUAL` rules raised
to `BLOCK`. A policy only hardens -- a rule with action `ALLOW`, a raise that keeps or lowers a
class, or a rule that reuses a built-in id is refused as a whole, so a project that asked for a
policy never silently gets the built-ins instead. `assess` itself reads nothing from disk: the
caller loads the policy and passes it in.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

POLICY_SCHEMA = "hpp.policy/v1"
DEFAULT_POLICY_PATH = Path(".hpp") / "policy.json"
# Ordered from the least to the most strict: a policy may only move a rule to the right.
ACTIONS = ("ALLOW", "MANUAL", "BLOCK")
_RULE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_RULE_KEYS = frozenset({"id", "action", "pattern", "reason"})
_POLICY_KEYS = frozenset({"schema", "rules", "raise"})

_RECURSIVE_DELETE_REASON = "recursive deletion requires an explicit recovery plan"
_RM_COMMAND = re.compile(r"(?:.*[\\/])?rm", re.I)


class PolicyError(ValueError):
    """A policy file cannot be applied truthfully; no command was classified."""


def _rm_recursive_force(text: str) -> bool:
    # Why: flag order and flag form vary (-rf, -fr, -r -f, --recursive --force), so the
    # check reads the option set of each rm invocation instead of matching one spelling.
    for segment in re.split(r"[|;&\n]+", text):
        tokens = [token.strip("\"'") for token in segment.split()]
        for index, token in enumerate(tokens):
            if not _RM_COMMAND.fullmatch(token):
                continue
            recursive = force = False
            for option in tokens[index + 1:]:
                if option == "--":
                    break
                if option.startswith("--"):
                    recursive = recursive or option == "--recursive"
                    force = force or option == "--force"
                elif option.startswith("-") and len(option) > 1:
                    letters = option[1:].lower()
                    recursive = recursive or "r" in letters
                    force = force or "f" in letters
            if recursive and force:
                return True
    return False


_BLOCK_RULES = (
    ("recursive-delete", re.compile(r"\brmdir\s+/s", re.I), _RECURSIVE_DELETE_REASON),
    ("force-push", re.compile(r"\bgit\s+push\b[^\n]*(?:--force|-f\b)", re.I), "force push rewrites shared history"),
    ("main-push", re.compile(r"\bgit\s+push\b[^\n]*\b(?:main|master)\b", re.I), "main branch must be merged through review"),
    # Why: `| sudo bash`, `| sudo -E sh` and `| zsh` are the same act as `| sh`; requiring the shell
    # right after the pipe let them through.
    ("pipe-to-shell", re.compile(r"\b(?:curl|wget)\b[^|\n]*\|\s*(?:sudo(?:\s+-\S+)*\s+)?(?:ba|z|da|k)?sh\b", re.I),
     "downloaded code must be inspected before execution"),
    ("destructive-sql", re.compile(r"\b(?:drop|truncate)\s+(?:table|database)\b", re.I), "destructive SQL needs an explicit backup gate"),
)
_MANUAL_RULES = (
    ("external-push", re.compile(r"\bgit\s+push\b", re.I), "external publication needs a human gate"),
    # Why: flags usually come before the URL (`curl -s https://...`); matching only a URL right
    # after the command let the ordinary shape through as ALLOW.
    ("external-send", re.compile(r"\b(?:curl|wget)\b[^|;&\n]*?\bhttps?://", re.I), "external transfer needs a human gate"),
    # Why: the shipped typed-decision adapter sends the judged text to an endpoint the person
    # declared; like curl to a URL, running it is an outbound transfer and needs a human gate.
    ("decision-advisor", re.compile(r"typed-decisions[\\/]decide\.py", re.I),
     "the example advisor sends text to an external decision endpoint"),
)
BUILT_IN_ACTIONS: dict[str, str] = {
    **{rule: "BLOCK" for rule, _, _ in _BLOCK_RULES},
    **{rule: "MANUAL" for rule, _, _ in _MANUAL_RULES},
}


def _verdict(action: str, rule: str, reason: str, source: str) -> dict[str, Any]:
    return {"action": action, "rule": rule, "reason": reason, "source": source}


def validate_policy(document: Any) -> dict[str, Any]:
    """Check a policy document against the contract and compile it; refuse anything that would exempt."""
    if not isinstance(document, dict):
        raise PolicyError("policy must be a JSON object")
    if document.get("schema") != POLICY_SCHEMA:
        raise PolicyError(f"policy schema must be {POLICY_SCHEMA}")
    unknown = sorted(set(document) - _POLICY_KEYS)
    if unknown:
        raise PolicyError(f"policy key(s) outside the contract: {', '.join(unknown)} "
                          "(a policy only hardens; there is no allow list)")
    rules = document.get("rules", [])
    if not isinstance(rules, list):
        raise PolicyError('"rules" must be a list of rule objects')
    compiled: list[tuple[str, re.Pattern[str], str, str]] = []
    seen: set[str] = set()
    for index, rule in enumerate(rules, 1):
        if not isinstance(rule, dict):
            raise PolicyError(f"rule {index} must be an object")
        extra = sorted(set(rule) - _RULE_KEYS)
        if extra:
            raise PolicyError(f"rule {index}: key(s) outside the contract: {', '.join(extra)}")
        missing = sorted(_RULE_KEYS - set(rule))
        if missing:
            raise PolicyError(f"rule {index}: missing {', '.join(missing)}")
        rule_id = rule["id"]
        if not isinstance(rule_id, str) or not _RULE_ID.fullmatch(rule_id):
            raise PolicyError(f"rule {index}: id must be lowercase letters, digits and '-' (up to 64 characters)")
        if rule_id in BUILT_IN_ACTIONS:
            raise PolicyError(f"rule {rule_id!r} is built in; a policy cannot redefine it (use \"raise\" to harden it)")
        if rule_id in seen:
            raise PolicyError(f"rule {rule_id!r} is declared twice")
        seen.add(rule_id)
        action = rule["action"]
        if action not in ("BLOCK", "MANUAL"):
            raise PolicyError(f"rule {rule_id!r}: action must be BLOCK or MANUAL, not {action!r}; a policy only hardens")
        pattern = rule["pattern"]
        if not isinstance(pattern, str) or not pattern:
            raise PolicyError(f"rule {rule_id!r}: pattern must be a non-empty regular expression")
        try:
            # Why: the built-in rules match case-insensitively; a user rule follows the same reading.
            expression = re.compile(pattern, re.I)
        except re.error as exc:
            raise PolicyError(f"rule {rule_id!r}: invalid pattern: {exc}") from exc
        reason = rule["reason"]
        if not isinstance(reason, str) or not reason.strip():
            raise PolicyError(f"rule {rule_id!r}: reason must be a non-empty string")
        compiled.append((rule_id, expression, reason.strip(), action))
    raises = document.get("raise", {})
    if not isinstance(raises, dict):
        raise PolicyError('"raise" must be an object mapping a built-in rule id to BLOCK')
    raised: dict[str, str] = {}
    for rule_id, action in raises.items():
        if rule_id not in BUILT_IN_ACTIONS:
            raise PolicyError(f"raise: {rule_id!r} is not a built-in rule (built in: {', '.join(BUILT_IN_ACTIONS)})")
        if action not in ACTIONS:
            raise PolicyError(f"raise: {rule_id!r}: action must be one of {', '.join(ACTIONS)}, not {action!r}")
        current = BUILT_IN_ACTIONS[rule_id]
        if ACTIONS.index(action) <= ACTIONS.index(current):
            verb = "lower" if ACTIONS.index(action) < ACTIONS.index(current) else "keep"
            raise PolicyError(f"raise: {rule_id!r} is {current} and {action} would {verb} it; a policy only hardens")
        raised[rule_id] = action
    return {"schema": POLICY_SCHEMA, "rules": compiled, "raise": raised}


def load_policy(path: Path) -> dict[str, Any]:
    source = Path(path)
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PolicyError(f"policy file not found: {source}") from exc
    except json.JSONDecodeError as exc:
        raise PolicyError(f"policy file is not JSON: {source}: {exc.msg}") from exc
    return validate_policy(document)


def policy_for_workspace(explicit: Optional[str], workspace: Path) -> tuple[Optional[dict[str, Any]], Optional[Path]]:
    """The policy a check applies: the file named, else the workspace's `.hpp/policy.json`, else none."""
    if explicit:
        path = Path(explicit)
        return load_policy(path), path
    candidate = Path(workspace) / DEFAULT_POLICY_PATH
    if candidate.is_file():
        return load_policy(candidate), candidate
    return None, None


def assess(command: str, policy: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    text = command.strip()
    if not text:
        return _verdict("ALLOW", "empty", "no command supplied", "built-in")
    raised = policy["raise"] if policy else {}
    user_rules = policy["rules"] if policy else []
    if _rm_recursive_force(text):
        return _verdict("BLOCK", "recursive-delete", _RECURSIVE_DELETE_REASON, "built-in")
    for rule, pattern, reason in _BLOCK_RULES:
        if pattern.search(text):
            return _verdict("BLOCK", rule, reason, "built-in")
    # Every BLOCK is tried before any MANUAL, whatever its origin: a policy cannot soften a built-in
    # BLOCK by declaring a MANUAL rule over the same command.
    for rule, pattern, reason in _MANUAL_RULES:
        if raised.get(rule) == "BLOCK" and pattern.search(text):
            return _verdict("BLOCK", rule, reason, "policy")
    for rule, pattern, reason, action in user_rules:
        if action == "BLOCK" and pattern.search(text):
            return _verdict("BLOCK", rule, reason, "policy")
    for rule, pattern, reason in _MANUAL_RULES:
        if pattern.search(text):
            return _verdict("MANUAL", rule, reason, "built-in")
    for rule, pattern, reason, action in user_rules:
        if action == "MANUAL" and pattern.search(text):
            return _verdict("MANUAL", rule, reason, "policy")
    return _verdict("ALLOW", "allow", "no configured policy rule matched", "built-in")


def exit_for(verdict: dict[str, Any], mode: str) -> int:
    if mode == "audit":
        return 0
    if verdict["action"] == "BLOCK":
        return 2
    if verdict["action"] == "MANUAL":
        return 1
    return 0
