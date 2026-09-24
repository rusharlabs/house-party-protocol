"""Small, explicit policy classifier; it never executes a command."""
from __future__ import annotations

import re
from typing import Any


_RECURSIVE_DELETE_REASON = "recursive deletion requires an explicit recovery plan"
_RM_COMMAND = re.compile(r"(?:.*[\\/])?rm", re.I)


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


def assess(command: str) -> dict[str, Any]:
    text = command.strip()
    if not text:
        return {"action": "ALLOW", "rule": "empty", "reason": "no command supplied"}
    if _rm_recursive_force(text):
        return {"action": "BLOCK", "rule": "recursive-delete", "reason": _RECURSIVE_DELETE_REASON}
    for rule, pattern, reason in _BLOCK_RULES:
        if pattern.search(text):
            return {"action": "BLOCK", "rule": rule, "reason": reason}
    for rule, pattern, reason in _MANUAL_RULES:
        if pattern.search(text):
            return {"action": "MANUAL", "rule": rule, "reason": reason}
    return {"action": "ALLOW", "rule": "allow", "reason": "no configured policy rule matched"}


def exit_for(verdict: dict[str, Any], mode: str) -> int:
    if mode == "audit":
        return 0
    if verdict["action"] == "BLOCK":
        return 2
    if verdict["action"] == "MANUAL":
        return 1
    return 0
