"""Deterministic context compilation with provenance and a secret refusal gate."""
from __future__ import annotations

import hashlib
import re
from typing import Any


_SECRET_PATTERN = re.compile(
    r"(?:api[_-]?key|access[_-]?token|secret|password)\s*[:=]|-----BEGIN [A-Z ]+-----|\bsk-[A-Za-z0-9_-]{8,}",
    re.IGNORECASE,
)


class ContextError(ValueError):
    """Context input cannot safely enter an auditable compilation."""


def _normalise(inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(inputs, list):
        raise ContextError("inputs must be a list")
    normalised: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(inputs):
        if not isinstance(item, dict):
            raise ContextError(f"input {index} must be an object")
        source = item.get("source")
        priority = item.get("priority")
        content = item.get("content")
        if not isinstance(source, str) or not source:
            raise ContextError(f"input {index} needs a source")
        if source in seen:
            raise ContextError(f"duplicate context source: {source}")
        seen.add(source)
        if not isinstance(priority, int):
            raise ContextError(f"input {source} needs an integer priority")
        if not isinstance(content, str):
            raise ContextError(f"input {source} needs string content")
        if _SECRET_PATTERN.search(content):
            raise ContextError(f"secret-like material refused from source: {source}")
        normalised.append({"source": source, "priority": priority, "content": content})
    return sorted(normalised, key=lambda item: (-item["priority"], item["source"]))


def _record(item: dict[str, Any]) -> dict[str, Any]:
    content = item["content"]
    return {"source": item["source"], "priority": item["priority"], "chars": len(content),
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()}


def compile_context(inputs: list[dict[str, Any]], budget: int) -> dict[str, Any]:
    """Compile complete inputs under a character budget; partial input is never sliced."""
    if not isinstance(budget, int) or budget < 0:
        raise ContextError("budget must be a non-negative integer")
    ordered = _normalise(inputs)
    included: list[dict[str, Any]] = []
    omitted: list[dict[str, Any]] = []
    selected: list[str] = []
    used = 0
    for item in ordered:
        record = _record(item)
        if used + record["chars"] <= budget:
            included.append(record)
            selected.append(item["content"])
            used += record["chars"]
        else:
            omitted.append(record)
    return {
        "schema": "hpp.context/v1",
        "budget": budget,
        "used": used,
        "remaining": budget - used,
        "included": included,
        "omitted": omitted,
        "text": "\n\n".join(selected),
    }
