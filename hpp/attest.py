"""Provider-neutral evidence attestations bound to repository bytes."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

from hpp.signing import SigningError, canonical as signable, sign as sign_bytes, signature_report


# Ordered from the least to the most strict: a gate may only move a verdict to the right.
VERDICTS = ("approved", "revise", "blocked")
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


def _repository_paths(root: Path, *args: str, timeout: Optional[float] = None,
                      env: Optional[dict[str, str]] = None) -> list[str]:
    raw = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", *args],
        cwd=root, capture_output=True, timeout=timeout, env=env,
    )
    if raw.returncode != 0:
        raise AttestationError(raw.stderr.decode("utf-8", errors="replace").strip())
    return sorted({item for item in raw.stdout.decode("utf-8", errors="surrogateescape").split("\0") if item})


def runtime_paths_in_snapshot(snapshot: dict[str, Any]) -> list[str]:
    """List HPP runtime paths already measured in an attestation snapshot."""
    return [entry["path"] for entry in snapshot["entries"] if ".hpp" in entry["path"].split("/")[:-1]]


def repository_runtime_paths(target: Path) -> list[str]:
    """Best-effort advisory check using the same Git selection as an attestation."""
    # Keep the fixed diagnostic pathspec independent of user-selected syntax and case modes.
    pathspec_modes = {"GIT_LITERAL_PATHSPECS", "GIT_GLOB_PATHSPECS", "GIT_NOGLOB_PATHSPECS", "GIT_ICASE_PATHSPECS"}
    env = {key: value for key, value in os.environ.items() if key.upper() not in pathspec_modes}
    try:
        return _repository_paths(target, "--full-name", "--", ":(top,glob)**/.hpp/**", timeout=10, env=env)
    except (AttestationError, OSError, subprocess.TimeoutExpired):
        # Doctor and init can run outside Git or without Git installed.
        return []


def _snapshot_digest(entries: list[dict[str, str]]) -> str:
    canonical = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(canonical)


def _snapshot(root: Path, excluded: set[str]) -> dict[str, Any]:
    entries: list[dict[str, str]] = []
    for relative in _repository_paths(root):
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
    return {"file_count": len(entries), "digest": _snapshot_digest(entries), "entries": entries}


def _changed_snapshot_paths(stored: Any, current: list[dict[str, str]]) -> dict[str, str]:
    if not isinstance(stored, dict) or not isinstance(stored.get("entries"), list):
        return {}
    entries = stored["entries"]
    previous = {}
    for entry in entries:
        if not isinstance(entry, dict) or not all(isinstance(entry.get(key), str) for key in ("path", "kind", "sha256")):
            return {}
        previous[entry["path"]] = entry
    try:
        if len(previous) != len(entries) or _snapshot_digest(entries) != stored.get("digest"):
            return {}
    except UnicodeEncodeError:
        return {}

    latest = {entry["path"]: entry for entry in current}
    changes = {}
    for path in sorted(previous.keys() | latest.keys()):
        before = previous.get(path)
        after = latest.get(path)
        if before == after:
            continue
        if before is None:
            changes[path] = "added"
        elif after is None or after["kind"] == "missing":
            changes[path] = "deleted"
        elif before["kind"] == "missing":
            changes[path] = "added"
        else:
            changes[path] = "modified"
    return changes


def create_attestation(
    repo: Path,
    spec: Path,
    output: Path,
    maker: str,
    checker: str,
    session: str,
    verdict: str,
    panel: Optional[dict[str, Any]] = None,
    sign_key: Optional[Path] = None,
    signer: Optional[str] = None,
    codegraph: Optional[dict[str, Any]] = None,
    base_commit: Optional[str] = None,
) -> dict[str, Any]:
    """Record a verdict bound to the repository, the spec and a full snapshot.

    With `panel` (the verdict of a sealed release-gate session, from `panel_verdict`), the recorded
    verdict is the STRICTER of the declared one and the panel's: a panel can block or send back a
    declared approval, never approve a declared block, and a panel that did not decide sends it back
    for revision. The panel's record hash is kept, so the attestation names the session behind it.

    With `sign_key`, the record is signed with that SSH private key through `ssh-keygen -Y sign`
    (namespace `hpp`) as `signer` -- by default the checker, who signs its own verdict. Without the
    binary nothing is written: a record is signed or it is not, never "signed" by assertion.
    """
    if base_commit is not None and codegraph is None:
        raise AttestationError("base_commit requires a code graph")
    root = _repo_root(repo)
    maker_id = maker.strip()
    checker_id = checker.strip()
    if not maker_id or not checker_id or maker_id.casefold() == checker_id.casefold():
        raise AttestationError("maker and checker must be different non-empty actors")
    if not _SESSION_RE.fullmatch(session):
        raise AttestationError("session must be 1-128 portable identifier characters")
    normalized_verdict = verdict.strip().lower()
    if normalized_verdict not in VERDICTS:
        raise AttestationError("verdict must be approved, revise, or blocked")
    deliberation = None
    if panel is not None:
        panel_value = panel["value"] if panel["status"] == "recommendation" and panel["value"] in VERDICTS else "revise"
        normalized_verdict = max(normalized_verdict, panel_value, key=VERDICTS.index)
        deliberation = {"record_sha256": panel["record_sha256"], "status": panel["status"],
                        "value": panel["value"], "judge_family": panel["judge_family"]}
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
    if deliberation is not None:
        record["deliberation"] = deliberation
    if codegraph is not None:
        from hpp.territories import measure_blast_radius
        record["blast_radius"] = measure_blast_radius(root, base_commit or record["base_commit"], codegraph)
    if sign_key is not None:
        try:
            record["signature"] = sign_bytes(signable(record), Path(sign_key), signer or checker_id)
        except SigningError as exc:
            raise AttestationError(str(exc)) from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    return record


def verify_attestation(path: Path, repo: Path, allowed_signers: Optional[Path] = None) -> dict[str, Any]:
    """Re-derive every binding of an attestation; with `allowed_signers`, also demand a signature
    that `ssh-keygen -Y verify` accepts for the signer it names. Without the file the signature is
    reported (`not-signed` or `not-verified`) and never claimed."""
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
    changed_paths = {}
    if not isinstance(stored_snapshot, dict) or stored_snapshot.get("digest") != current_snapshot["digest"]:
        mismatches.append("snapshot_digest")
        changed_paths = _changed_snapshot_paths(stored_snapshot, current_snapshot["entries"])
    signature = signature_report(signable(record), record.get("signature"),
                                 Path(allowed_signers) if allowed_signers is not None else None)
    if allowed_signers is not None and signature["status"] != "verified":
        mismatches.append("signature")
    report = {
        "schema": "hpp.attestation-verification/v1",
        "status": "valid" if not mismatches else "blocked",
        "mismatches": sorted(set(mismatches)),
        "base_commit": _git(root, "rev-parse", "HEAD"),
        "snapshot_digest": current_snapshot["digest"],
        "signature": signature,
    }
    if changed_paths:
        report["changed_paths"] = changed_paths
    return report
