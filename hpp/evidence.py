"""Evidence bundles: a declared criterion command, its exit code and the hashes of what it produced.

The harness drives no browser and calls no model: it runs the command you name (an end-to-end
spec, a pytest suite, any script), measures its exit code outside the model, and hashes the
artifact files you declared (traces, screenshots, logs). The bundle passes only when the command
exited 0 AND every declared pattern matched a file this run wrote; a screenshot that was never
written, or one left over from an earlier run, is not evidence.

`verify` re-derives a bundle from the files on disk. It exits 0 only for an intact record of a run
that passed. The record's self-hash makes an edited record visible, but it is not a signature:
anyone who can write the file can rewrite the hash. A checker that must not trust the maker
re-runs `command` instead of relying on `verify` alone.

The record holds hashes and byte counts, never the command's output text or an absolute path, and
a command line that looks like it carries a secret is refused before it runs.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Optional

from hpp._process import MAX_TIMEOUT, run_bounded, valid_timeout
from hpp.context import _SECRET_PATTERN
from hpp.state import StateError, append_event, event_path

SCHEMA = "hpp.evidence/v1"
VERDICTS = ("passed", "failed", "missing-artifacts", "timeout", "could-not-start")
DEFAULT_OUT = Path(".hpp") / "evidence"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_DRIVE = re.compile(r"^[A-Za-z]:")
_SECRET_FLAG = re.compile(
    r"^--?(?:password|passwd|token|api[-_]?key|apikey|secret|access[-_]?token|client[-_]?secret|private[-_]?key)"
    r"(?:=(?P<inline>.*))?$",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT = re.compile(
    r"^[A-Z0-9_]*(?:TOKEN|SECRET|SECRET_KEY|PASSWORD|PASSWD|API_?KEY|ACCESS_KEY|PRIVATE_KEY)="
    r"(?!(?:\d*|true|false|yes|no|on|off)$)\S+",
)
_SECRET_VALUE = re.compile(
    r"\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"
    r"|\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}"
    r"|\bxox[abprs]-[A-Za-z0-9-]{10,}|\bAKIA[0-9A-Z]{16}\b",
    re.IGNORECASE,
)
_UNHASHED = ("record_sha256", "event", "event_error")


class EvidenceError(ValueError):
    """The evidence request is unsafe or malformed; nothing was run or recorded."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical(record: dict[str, Any]) -> bytes:
    # Why: the event outcome is added after the record is written, so it is outside the hash;
    # the printed record and the written one then verify the same way.
    body = {key: value for key, value in record.items() if key not in _UNHASHED}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _inside(value: str) -> bool:
    normalised = value.replace("\\", "/")
    return bool(normalised) and not (normalised.startswith("/") or _DRIVE.match(normalised)
                                     or ".." in PurePosixPath(normalised).parts)


def _check_pattern(pattern: str) -> str:
    if not isinstance(pattern, str) or not pattern.strip():
        raise EvidenceError("an artifact pattern must be a non-empty path glob")
    if not _inside(pattern):
        raise EvidenceError(f"artifact pattern {pattern!r} must stay inside the workspace (relative, no '..')")
    normalised = pattern.replace("\\", "/")
    if normalised.endswith("**"):
        # Why: a trailing `**` matches only directories before Python 3.13, which would turn
        # every such pattern into a missing artifact on older interpreters.
        normalised += "/*"
    return normalised


def _check_out_dir(out_dir: Optional[Path]) -> Path:
    if out_dir is None:
        return DEFAULT_OUT
    if not _inside(str(out_dir)):
        raise EvidenceError(f"record directory {str(out_dir)!r} must stay inside the workspace (relative, no '..')")
    return Path(out_dir)


def _check_timeout(timeout: Any) -> float:
    if not valid_timeout(timeout):
        raise EvidenceError(f"timeout must be a positive, finite number of seconds, at most {MAX_TIMEOUT:g}")
    return float(timeout)


def _carries_secret(command: list[str]) -> bool:
    if _SECRET_PATTERN.search(" ".join(command)) or _SECRET_VALUE.search(" ".join(command)):
        return True
    for index, item in enumerate(command):
        if _SECRET_ASSIGNMENT.match(item):
            return True
        flag = _SECRET_FLAG.match(item)
        if flag and (flag.group("inline") or index + 1 < len(command)):
            return True
    return False


def _head(root: Path) -> Optional[str]:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(root), capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None if result.returncode == 0 else None


def _run(command: list[str], root: Path, timeout: float) -> tuple[str, Optional[int], bytes, bytes]:
    # Why: an end-to-end criterion starts a browser, which starts its own children. The bounded
    # runner stops the whole tree on timeout instead of waiting on pipes those children hold.
    state, exit_code, stdout, stderr = run_bounded(command, timeout=timeout, cwd=str(root))
    if state != "exited":
        return state, None, stdout, stderr
    return ("passed" if exit_code == 0 else "failed"), exit_code, stdout, stderr


def _matches(root: Path, pattern: str) -> dict[str, Path]:
    resolved_root = root.resolve()
    found: dict[str, Path] = {}
    for match in sorted(root.glob(pattern)):
        if not match.is_file():
            continue
        real = match.resolve()
        if resolved_root not in real.parents:
            continue  # Why: a symlink that points outside the workspace is not the workspace's artifact.
        found[real.relative_to(resolved_root).as_posix()] = real
    return found


def _stamp(path: Path) -> tuple[int, int]:
    info = path.stat()
    return info.st_size, info.st_mtime_ns


def _collect(root: Path, pattern: str, before: dict[str, tuple[int, int]]) -> dict[str, Any]:
    # Why: a screenshot left by yesterday's run matches today's glob. A file that is exactly as it
    # was before the command started was not produced by it, so it is listed as unchanged and does
    # not satisfy the pattern.
    files, unchanged = [], []
    for relative, real in _matches(root, pattern).items():
        if before.get(relative) == _stamp(real):
            unchanged.append(relative)
            continue
        files.append({"path": relative, "size": real.stat().st_size, "sha256": _file_digest(real)})
    return {"pattern": pattern, "files": files, "unchanged": unchanged}


def run_evidence(record_id: str, command: list[str], artifacts: list[str], *, root: Path,
                 timeout: float = 600.0, out_dir: Optional[Path] = None,
                 manifest: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Run `command` in `root`, hash the declared artifacts, write the record and return it.

    With `manifest`, a passed bundle also appends `evidence_recorded` to the event log.
    Everything that can be refused is refused before the command runs.
    """
    if not isinstance(record_id, str) or not _ID.match(record_id):
        raise EvidenceError("id must be a plain name: letters, digits, '.', '_' or '-', up to 80 characters")
    if not command or not all(isinstance(item, str) and item for item in command):
        raise EvidenceError("the criterion command must be a non-empty argv list")
    if _carries_secret(list(command)):
        raise EvidenceError("the command line looks like it carries a secret; pass it through the environment instead")
    patterns = list(dict.fromkeys(_check_pattern(item) for item in artifacts))
    timeout = _check_timeout(timeout)
    out = _check_out_dir(out_dir)
    if manifest is not None and not patterns:
        raise EvidenceError("recording an event needs at least one artifact: an exit code alone leaves "
                            "nothing for a later verify to re-derive")
    root = Path(root)
    target_dir = root / out
    if root.resolve() != target_dir.resolve() and root.resolve() not in target_dir.resolve().parents:
        raise EvidenceError(f"record directory {out.as_posix()!r} resolves outside the workspace")
    before = {relative: _stamp(real) for pattern in patterns for relative, real in _matches(root, pattern).items()}
    started = datetime.now(timezone.utc)
    clock = time.monotonic()
    verdict, exit_code, stdout, stderr = _run(list(command), root, timeout)
    duration = round(time.monotonic() - clock, 3)
    groups = [_collect(root, pattern, before) for pattern in patterns]
    missing = [group["pattern"] for group in groups if not group["files"]]
    if verdict == "passed" and missing:
        verdict = "missing-artifacts"
    target_dir.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "id": record_id,
        "command": list(command),
        "base_commit": _head(root),
        "started_at": started.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "duration_s": duration,
        "timeout_s": timeout,
        "exit_code": exit_code,
        "verdict": verdict,
        "stdout": {"bytes": len(stdout), "sha256": _sha256(stdout)},
        "stderr": {"bytes": len(stderr), "sha256": _sha256(stderr)},
        "artifacts": groups,
        "missing": missing,
    }
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    counter = 1
    while True:
        suffix = "" if counter == 1 else f"-{counter}"
        target = target_dir / f"{record_id}-{stamp}{suffix}.json"
        record["record_path"] = target.relative_to(root).as_posix()
        record["record_sha256"] = _sha256(_canonical(record))
        try:
            with target.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
            break
        except FileExistsError:
            counter += 1
    record["event"] = None
    if manifest is not None and verdict == "passed":
        # Why: the loop advances only through recorded evidence; a failed or partial bundle is a
        # measurement, not evidence of completion, so it never moves the loop.
        data = {"evidence": record["record_path"], "evidence_sha256": record["record_sha256"], "id": record_id}
        try:
            append_event(event_path(root), "evidence_recorded", manifest, data)
            record["event"] = {"type": "evidence_recorded", "data": data}
        except (StateError, OSError) as exc:
            record["event_error"] = str(exc)
    return record


def _contradictions(record: dict[str, Any]) -> list[str]:
    verdict, exit_code = record.get("verdict"), record.get("exit_code")
    if verdict not in VERDICTS:
        return [f"unknown verdict {verdict!r}"]
    groups = record.get("artifacts")
    missing = record.get("missing")
    if not isinstance(groups, list) or not isinstance(missing, list):
        return ["the record's artifact lists are malformed"]
    for group in groups:
        files = group.get("files") if isinstance(group, dict) else None
        if not isinstance(group.get("pattern") if isinstance(group, dict) else None, str) \
                or not isinstance(files, list) or not all(
                isinstance(item, dict) and isinstance(item.get("path"), str) and isinstance(item.get("sha256"), str)
                for item in files):
            return ["the record's artifact lists are malformed"]
        if not all(_inside(item["path"]) for item in files):
            return ["the record names an artifact outside the workspace"]
    empty = sorted(group.get("pattern") for group in groups if not group["files"])
    if sorted(missing) != empty:
        return ["the record's missing list does not match its artifact groups"]
    is_int = isinstance(exit_code, int) and not isinstance(exit_code, bool)
    expected = {
        "passed": is_int and exit_code == 0 and not missing,
        "missing-artifacts": is_int and exit_code == 0 and bool(missing),
        "failed": is_int and exit_code != 0,
        "timeout": exit_code is None,
        "could-not-start": exit_code is None,
    }
    if not expected[verdict]:
        return [f"verdict {verdict!r} contradicts exit code {exit_code!r}"]
    return []


def _report(record: dict[str, Any], status: str, problems: list[str], changed: list[str],
            missing: list[str]) -> dict[str, Any]:
    return {"status": status, "id": record.get("id"), "verdict": record.get("verdict"),
            "base_commit": record.get("base_commit"), "problems": problems, "changed": changed, "missing": missing}


def verify_evidence(record_path: Path, *, root: Path) -> dict[str, Any]:
    """Re-derive a bundle: the record's own hash, its internal consistency, then every artifact.

    Status is `valid` for an intact record of a passed run, `not-evidence` for an intact record
    of a run that did not pass, and `blocked` when the record or its artifacts changed. A record
    whose own hash does not match is blocked before any path it names is read.
    """
    path = Path(record_path)
    if not path.is_file():
        raise EvidenceError(f"evidence record not found: {record_path}")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"evidence record is not JSON: {exc.msg}") from exc
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        raise EvidenceError(f"evidence record schema must be {SCHEMA}")
    if record.get("record_sha256") != _sha256(_canonical(record)):
        return _report(record, "blocked", ["the record was edited after it was written"], [], [])
    contradictions = _contradictions(record)
    if contradictions:
        return _report(record, "blocked", contradictions, [], [])
    root = Path(root)
    resolved_root = root.resolve()
    changed: list[str] = []
    missing: list[str] = []
    for group in record["artifacts"]:
        for item in group["files"]:
            file_path = (root / item["path"]).resolve()
            if resolved_root not in file_path.parents or not file_path.is_file():
                missing.append(item["path"])
            elif _file_digest(file_path) != item["sha256"]:
                changed.append(item["path"])
    problems: list[str] = []
    if changed:
        problems.append(f"{len(changed)} artifact(s) changed since the run")
    if missing:
        problems.append(f"{len(missing)} artifact(s) missing since the run")
    if problems:
        return _report(record, "blocked", problems, changed, missing)
    if record["verdict"] != "passed":
        return _report(record, "not-evidence", [f"the run did not pass (verdict: {record['verdict']})"], [], [])
    return _report(record, "valid", [], [], [])


def exit_for_run(record: dict[str, Any]) -> int:
    if record.get("event_error"):
        return 2
    return 0 if record["verdict"] == "passed" else 1


def exit_for_verify(report: dict[str, Any]) -> int:
    return {"valid": 0, "not-evidence": 1}.get(report["status"], 2)
