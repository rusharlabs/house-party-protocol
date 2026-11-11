"""Read-only journey state: profile and commit-keyed project measurements."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hpp._repository import RepositoryError, artifact_status, snapshot


def read_document(path: Path) -> dict[str, Any]:
    """Bound JSON input, refusing links and reparse points before opening it."""
    for part in (path, *path.parents):
        if part.is_symlink() or (part.exists() and getattr(part.lstat(), "st_file_attributes", 0) & 0x400):
            raise ValueError("measurement input must not traverse a link or reparse point")
    try:
        with path.open("rb") as stream:
            raw = stream.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError("measurement JSON exceeds 4 MiB")
        result = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("cannot read measurement JSON") from exc
    if not isinstance(result, dict):
        raise ValueError("measurement JSON must contain an object")
    return result


def cached_document(target: Path, kind: str) -> dict[str, Any] | None:
    """Prefer HEAD; otherwise select a historical artifact deterministically."""
    if kind not in {"inventory", "codegraph"}:
        raise ValueError("unknown measurement kind")
    snap = snapshot(target)
    directory = snap.root / ".hpp" / kind
    if not directory.exists():
        return None
    # Do not enumerate through a linked cache directory.
    for part in (directory, directory.parent):
        if part.is_symlink() or getattr(part.lstat(), "st_file_attributes", 0) & 0x400:
            raise ValueError("measurement cache must not traverse a link or reparse point")
    current = directory / f"{snap.commit}.json"
    if current.exists():
        return read_document(current)
    candidates = sorted(directory.glob("*.json"))
    if not candidates:
        return None
    # A lexical historical selection is labelled stale; it is never presented as latest by time.
    return read_document(candidates[-1])


def project_journey(target: Path, *, inventory: dict[str, Any] | None = None,
                    codegraph: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return measured next actions without changing a profile or running a project."""
    profile_path = target / ".hpp" / "profile.json"
    profile = "absent"
    if profile_path.exists():
        try:
            value = read_document(profile_path)
            profile = "present" if value.get("schema") == "hpp.init/v1" else "invalid"
        except ValueError:
            profile = "invalid"
    try:
        inventory = inventory if inventory is not None else cached_document(target, "inventory")
        codegraph = codegraph if codegraph is not None else cached_document(target, "codegraph")
        measurements = {"inventory": artifact_status(target, inventory),
                        "codegraph": artifact_status(target, codegraph)}
        for kind, value in (("inventory", inventory), ("codegraph", codegraph)):
            if value is not None and value.get("schema") != f"hpp.{kind}/v1":
                measurements[kind] = {**measurements[kind], "status": "invalid",
                                      "reason": "unexpected measurement schema"}
    except (RepositoryError, ValueError):
        return {"schema": "hpp.journey/v1", "profile": profile, "status": "not-measured",
                "reason": "repository or measurement input could not be inspected",
                "next_command": "hpp inventory --target ."}
    if profile != "present":
        next_command = "hpp init --target ."  # Plan first; never silently apply.
    elif measurements["inventory"]["status"] != "fresh":
        next_command = "hpp inventory --target . --out"
    elif measurements["codegraph"]["status"] != "fresh":
        next_command = "hpp codegraph build --target . --out"
    else:
        next_command = "hpp lanes propose --target ."
    return {"schema": "hpp.journey/v1", "profile": profile, "status": "measured",
            **measurements, "next_command": next_command}
