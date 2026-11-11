"""Read a committed Git tree without executing repository-defined commands."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import unicodedata


class RepositoryError(ValueError):
    """The repository input cannot be measured safely."""


@dataclass(frozen=True)
class Snapshot:
    root: Path
    commit: str
    files: tuple[str, ...]
    modes: dict[str, str]
    blob_ids: dict[str, str]
    dirty_paths: tuple[str, ...]


_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_REGULAR = {"100644", "100755"}
_MAX_BYTES = 2 * 1024 * 1024


def _path(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise RepositoryError("repository contains an unsupported path")
    p = PurePosixPath(value)
    if p.is_absolute() or any(x in ("", ".", "..") for x in value.split("/")) or any(ord(c) < 32 for c in value):
        raise RepositoryError("repository contains an unsupported path")
    return unicodedata.normalize("NFC", value)


def _secret_path(path: str) -> bool:
    parts = PurePosixPath(path).parts
    name = parts[-1].lower()
    return (name == ".env" or name.startswith(".env.") or name in {
        ".envrc", ".npmrc", ".pypirc", ".netrc", "credentials", "credentials.json",
        "id_rsa", "id_ed25519", "secrets.json", "secrets.yaml", "secrets.yml",
    } or name.endswith((".pem", ".key", ".p12", ".pfx"))
        or any(p.lower() in {".ssh", "secrets", ".secrets"} for p in parts[:-1]))


def _git(root: Path, *args: str, ok: tuple[int, ...] = (0,), extra: tuple[str, ...] = ()) -> bytes:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    # Keep normal Git line-ending/encoding rules. Disabling global configuration
    # makes an autocrlf checkout look dirty despite an unchanged committed tree.
    # Execution-capable settings are disabled explicitly at each relevant call.
    env.update(GIT_TERMINAL_PROMPT="0", GIT_NO_REPLACE_OBJECTS="1")
    command = ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=",
               *extra, "-C", str(root), *args]
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=env, timeout=30, shell=False)
    except (OSError, subprocess.TimeoutExpired):
        raise RepositoryError("Git repository measurement failed") from None
    if result.returncode not in ok:
        raise RepositoryError("Git repository measurement failed")
    return result.stdout


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise RepositoryError("repository data is not UTF-8") from None


def _no_filters(root: Path) -> tuple[str, ...]:
    # diff may invoke a clean filter even with textconv/external diff disabled.
    # Read configuration KEY NAMES only, then neutralize every configured filter.
    keys = _decode(_git(root, "config", "--name-only", "--get-regexp", r"^filter\..*\.(clean|smudge|process|required)$", ok=(0, 1)))
    filters = sorted({k.rsplit(".", 1)[0] for k in keys.splitlines() if k.startswith("filter.")})
    return tuple(arg for key in filters for suffix in ("clean=", "smudge=", "process=", "required=false")
                 for arg in ("-c", key + "." + suffix))


def _paths(data: bytes) -> tuple[str, ...]:
    return tuple(sorted({_path(p) for p in _decode(data).split("\0") if p}))


def snapshot(target: str | Path) -> Snapshot:
    """Regular HEAD blobs in POSIX/NFC order; symlinks/gitlinks remain metadata only."""
    try:
        target_path = Path(target).absolute()
    except (TypeError, ValueError, OSError):
        raise RepositoryError("target must be a Git working tree") from None
    root = Path(_decode(_git(target_path, "rev-parse", "--show-toplevel")).strip())
    commit = _decode(_git(root, "rev-parse", "--verify", "HEAD^{commit}")).strip()
    if not _OID.fullmatch(commit):
        raise RepositoryError("repository has no readable HEAD commit")
    modes: dict[str, str] = {}
    blobs: dict[str, str] = {}
    for entry in _git(root, "ls-tree", "-r", "-z", "--full-tree", commit).split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, _kind, oid = _decode(metadata).split()
        path = _path(_decode(raw_path))
        if path in modes:
            raise RepositoryError("repository paths collide after NFC normalization")
        modes[path], blobs[path] = mode, oid
    diff_args = ("--name-only", "--no-ext-diff", "--no-textconv", "-z", "--ignore-submodules=all")
    filters = _no_filters(root)
    staged = _paths(_git(root, "diff", "--cached", *diff_args, commit, "--", extra=filters))
    work = _paths(_git(root, "diff", *diff_args, "--", extra=filters))
    if _decode(_git(root, "rev-parse", "--verify", "HEAD^{commit}")).strip() != commit:
        raise RepositoryError("HEAD changed during repository measurement")
    return Snapshot(root, commit, tuple(sorted(p for p in modes if modes[p] in _REGULAR)),
                    modes, blobs, tuple(sorted(set(staged) | set(work))))


def read_blob(snap: Snapshot, path: str, max_bytes: int = _MAX_BYTES) -> bytes:
    """Read an object ID, never a working-tree path or Git attribute conversion."""
    path = _path(path)
    if _secret_path(path):
        raise RepositoryError("secret-file content is excluded")
    if snap.modes.get(path) not in _REGULAR or path not in snap.files:
        raise RepositoryError("only regular snapshot files can be read")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 0:
        raise RepositoryError("max_bytes must be a non-negative integer")
    oid = snap.blob_ids[path]
    if not _OID.fullmatch(oid):
        raise RepositoryError("invalid blob identity")
    size = int(_git(snap.root, "cat-file", "-s", oid))
    if size > max_bytes:
        raise RepositoryError("snapshot file exceeds the read limit")
    data = _git(snap.root, "cat-file", "blob", oid)
    if len(data) != size:
        raise RepositoryError("snapshot blob changed during measurement")
    return data


def read_text(snap: Snapshot, path: str, max_bytes: int = _MAX_BYTES) -> str:
    return _decode(read_blob(snap, path, max_bytes))


def changed_paths_since(snap: Snapshot, base_commit: str) -> tuple[str, ...]:
    """Committed delta plus dirty tracked paths; no diff drivers or worktree code."""
    if not isinstance(base_commit, str) or not _OID.fullmatch(base_commit):
        raise RepositoryError("base commit must be an object identity")
    _git(snap.root, "cat-file", "-e", base_commit + "^{commit}")
    delta = _paths(_git(snap.root, "diff", "--name-only", "--no-ext-diff", "--no-textconv", "-z",
                        base_commit, snap.commit, "--"))
    return tuple(sorted(set(delta) | set(snap.dirty_paths)))


def _safe_parents(path: Path) -> None:
    for parent in (path, *path.parents):
        try:
            mode = parent.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            raise RepositoryError("artifact path cannot be inspected") from None
        if stat.S_ISLNK(mode.st_mode) or getattr(mode, "st_file_attributes", 0) & 0x400:
            raise RepositoryError("artifact paths must not traverse symlinks or reparse points")


def artifact_status(target: str | Path, document: dict | str | Path | None) -> dict:
    snap = snapshot(target)
    result = {"status": "absent", "commit": None, "head": snap.commit,
              "dirty_tracked": len(snap.dirty_paths), "changed_files": len(snap.dirty_paths),
              "changed_paths": list(snap.dirty_paths), "commits_behind": None}
    if document is None:
        return result
    if isinstance(document, (str, Path)):
        path = Path(document)
        if not path.is_absolute():
            path = snap.root / path
        _safe_parents(path)
        try:
            with path.open("rb") as stream:
                content = stream.read(4 * 1024 * 1024 + 1)
            if len(content) > 4 * 1024 * 1024:
                return {**result, "status": "invalid"}
            document = json.loads(content.decode("utf-8"))
        except FileNotFoundError:
            return result
        except (OSError, UnicodeError, ValueError):
            return {**result, "status": "invalid"}
    if (not isinstance(document, dict) or not isinstance(document.get("schema"), str)
            or not re.fullmatch(r"hpp\.[a-z][a-z0-9.-]*/v1", document["schema"])
            or not isinstance(document.get("commit"), str) or not _OID.fullmatch(document["commit"])):
        return {**result, "status": "invalid"}
    if document.get("status") in {"instrument-failure", "invalid", "not-measured"}:
        return {**result, "status": "invalid", "commit": document["commit"]}
    commit = document["commit"]
    universe_commit = document.get("universe_commit", commit)
    if not isinstance(universe_commit, str) or not _OID.fullmatch(universe_commit):
        return {**result, "status": "invalid", "commit": commit}
    try:
        _git(snap.root, "cat-file", "-e", commit + "^{commit}")
        delta = _paths(_git(snap.root, "diff", "--name-only", "--no-ext-diff", "--no-textconv", "-z", commit, snap.commit, "--"))
        behind = int(_git(snap.root, "rev-list", "--count", commit + ".." + snap.commit))
    except (RepositoryError, ValueError):
        return {**result, "status": "invalid", "commit": commit}
    changed = sorted(set(delta) | set(snap.dirty_paths))
    mismatch = universe_commit != commit
    return {**result, "status": "fresh" if commit == snap.commit and not snap.dirty_paths and not mismatch else "stale",
            "commit": commit, "changed_files": len(changed), "changed_paths": changed, "commits_behind": behind,
            **({"reason": "graph universe differs from artifact commit"} if mismatch else {})}


def write_artifact(target: str | Path, kind: str, document: dict, out: str | Path | None = None) -> Path:
    """Explicit, non-overwriting cache write; never updates the Git index."""
    snap = snapshot(target)
    if snap.dirty_paths:
        raise RepositoryError("artifact writes require a clean tracked snapshot; use stdout for dirty evidence")
    if not isinstance(kind, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", kind):
        raise RepositoryError("invalid artifact kind")
    if not isinstance(document, dict) or document.get("commit") != snap.commit or document.get("schema") != f"hpp.{kind}/v1":
        raise RepositoryError("artifact schema and commit must match the current snapshot")
    if document.get("universe_commit", snap.commit) != snap.commit:
        raise RepositoryError("artifact universe must match the current snapshot")
    path = Path(out) if out is not None else Path(".hpp") / kind / (snap.commit + ".json")
    if _secret_path(path.name):
        raise RepositoryError("artifact output must not be a secret-file path")
    if not path.is_absolute():
        path = snap.root / path
    path = Path(os.path.abspath(path))
    _safe_parents(path)
    try:
        content = (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
        if len(content) > 4 * 1024 * 1024:
            raise RepositoryError("artifact exceeds the 4 MiB read/write limit")
        if path.exists():
            if path.read_bytes() != content:
                raise RepositoryError("artifact already exists with different content")
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        _safe_parents(path)
        with path.open("xb") as stream:
            stream.write(content)
    except RepositoryError:
        raise
    except (OSError, TypeError, ValueError):
        raise RepositoryError("artifact could not be written safely") from None
    return path
