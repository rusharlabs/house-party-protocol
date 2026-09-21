"""Provider-neutral evidence attestations bound to repository bytes."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


SCHEMA = "hpp.evidence-attestation/v1"
_SESSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class AttestationError(ValueError):
    """An attestation cannot be created or evaluated truthfully."""


def _git(repo: Path, *args: str, required: bool = True) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, encoding="utf-8",
        errors="replace", capture_output=True,
    )
    if required and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise AttestationError(detail)
    return result.stdout.strip() if result.returncode == 0 else ""


def _repo_root(repo: Path) -> Path:
    candidate = repo.resolve()
    if not candidate.is_dir():
        raise AttestationError(f"repository not found: {candidate}")
    return Path(_git(candidate, "rev-parse", "--show-toplevel")).resolve()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _repo_identity(root: Path) -> dict[str, str]:
    remote = _git(root, "config", "--get", "remote.origin.url", required=False)
    seed = remote or root.name
    return {"name": root.name, "id": _sha256_bytes(seed.encode("utf-8"))}


def _relative(root: Path, path: Path, label: str) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise AttestationError(f"{label} must be inside the repository") from exc


def _snapshot(root: Path, excluded: set[str]) -> dict[str, Any]:
    raw = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root, capture_output=True,
    )
    if raw.returncode != 0:
        raise AttestationError(raw.stderr.decode("utf-8", errors="replace").strip())
    paths = sorted({item for item in raw.stdout.decode("utf-8", errors="surrogateescape").split("\0") if item})
    entries: list[dict[str, str]] = []
    for relative in paths:
        normalized = Path(relative).as_posix()
        if normalized in excluded:
            continue
        target = root / relative
        if target.is_symlink():
            kind = "symlink"
            digest = _sha256_bytes(os.readlink(target).encode("utf-8"))
        elif target.is_file():
            kind = "file"
            digest = _sha256_file(target)
        else:
            kind = "missing"
            digest = _sha256_bytes(b"hpp:missing")
        entries.append({"path": normalized, "kind": kind, "sha256": digest})
    canonical = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"file_count": len(entries), "digest": _sha256_bytes(canonical), "entries": entries}


def create_attestation(
    repo: Path,
    spec: Path,
    output: Path,
    maker: str,
    checker: str,
    session: str,
    verdict: str,
) -> dict[str, Any]:
    root = _repo_root(repo)
    maker_id = maker.strip()
    checker_id = checker.strip()
    if not maker_id or not checker_id or maker_id.casefold() == checker_id.casefold():
        raise AttestationError("maker and checker must be different non-empty actors")
    if not _SESSION_RE.fullmatch(session):
        raise AttestationError("session must be 1-128 portable identifier characters")
    normalized_verdict = verdict.strip().lower()
    if normalized_verdict not in {"approved", "revise", "blocked"}:
        raise AttestationError("verdict must be approved, revise, or blocked")
    spec_path = spec.resolve()
    if not spec_path.is_file():
        raise AttestationError(f"spec not found: {spec_path}")
    spec_relative = _relative(root, spec_path, "spec")
    excluded: set[str] = set()
    try:
        excluded.add(output.resolve().relative_to(root).as_posix())
    except ValueError:
        pass
    record = {
        "schema": SCHEMA,
        "repo": _repo_identity(root),
        "base_commit": _git(root, "rev-parse", "HEAD"),
        "spec": {"path": spec_relative, "sha256": _sha256_file(spec_path)},
        "actors": {"maker": maker_id, "checker": checker_id},
        "session": session,
        "verdict": normalized_verdict,
        "snapshot": _snapshot(root, excluded),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    return record


def verify_attestation(path: Path, repo: Path) -> dict[str, Any]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AttestationError(f"attestation not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AttestationError(f"invalid attestation JSON: {exc.msg}") from exc
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        raise AttestationError(f"attestation schema must be {SCHEMA}")
    root = _repo_root(repo)
    mismatches: list[str] = []
    if record.get("verdict") != "approved":
        mismatches.append("verdict")
    actors = record.get("actors", {})
    if not isinstance(actors, dict) or not actors.get("maker") or not actors.get("checker") or \
            str(actors.get("maker", "")).casefold() == str(actors.get("checker", "")).casefold():
        mismatches.append("actors")
    if not _SESSION_RE.fullmatch(str(record.get("session", ""))):
        mismatches.append("session")
    if record.get("repo") != _repo_identity(root):
        mismatches.append("repo")
    if record.get("base_commit") != _git(root, "rev-parse", "HEAD"):
        mismatches.append("base_commit")
    spec = record.get("spec", {})
    spec_relative = str(spec.get("path", "")) if isinstance(spec, dict) else ""
    spec_path = root / spec_relative
    if not spec_relative or not spec_path.is_file() or spec.get("sha256") != _sha256_file(spec_path):
        mismatches.append("spec_sha256")
    excluded: set[str] = set()
    try:
        excluded.add(path.resolve().relative_to(root).as_posix())
    except ValueError:
        pass
    current_snapshot = _snapshot(root, excluded)
    stored_snapshot = record.get("snapshot", {})
    if not isinstance(stored_snapshot, dict) or stored_snapshot.get("digest") != current_snapshot["digest"]:
        mismatches.append("snapshot_digest")
    return {
        "schema": "hpp.attestation-verification/v1",
        "status": "valid" if not mismatches else "blocked",
        "mismatches": sorted(set(mismatches)),
        "base_commit": _git(root, "rev-parse", "HEAD"),
        "snapshot_digest": current_snapshot["digest"],
    }
