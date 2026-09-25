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
import io
import json
import re
import shutil
import subprocess
import tempfile
import time
import tokenize
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


# --------------------------------------------------------------------------- criterion sensitivity

MUTATION_SCHEMA = "hpp.mutation/v1"
MUTANTS_SCHEMA = "hpp.mutants/v1"
# Why: a fixed, small operator table. Each swap changes behaviour at a boundary or a branch, which
# is exactly what a criterion that "passes" may never exercise. Applied to tokens only, never to
# text inside strings or comments, where a swap changes nothing and would read as a blind spot.
OPERATORS = {"==": "!=", "!=": "==", "<": "<=", "<=": "<", ">": ">=", ">=": ">",
             "and": "or", "or": "and", "True": "False", "False": "True"}
_COPY_IGNORE = (".git", ".hpp", "__pycache__", "node_modules", ".venv", "venv", ".tox")


def _workspace_file(root: Path, relative: Any) -> str:
    if not isinstance(relative, str) or not _inside(relative):
        raise EvidenceError(f"mutant file {relative!r} must stay inside the workspace (relative, no '..')")
    normalised = PurePosixPath(relative.replace("\\", "/")).as_posix()
    parts = PurePosixPath(normalised).parts
    ignored = [part for part in parts if part in _COPY_IGNORE]
    if ignored:
        raise EvidenceError(f"mutant file {normalised!r} is under {ignored[0]!r}, which is left out of the copy "
                            f"the criterion runs in")
    # Why (review 2026-09-25): a symlinked directory or file is recreated as a symlink in the copy,
    # so a mutation written "in the copy" landed in the user's tree. No component may be a symlink.
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise EvidenceError(f"mutant file {normalised!r} is reached through a symlink "
                                f"({current.relative_to(root).as_posix()}); a mutation there would land outside the copy")
    path = root / normalised
    if not path.is_file():
        raise EvidenceError(f"mutant file {normalised!r} is not a file inside the workspace")
    try:
        path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvidenceError(f"mutant file {normalised!r} is not UTF-8 text; mutants are applied to UTF-8 only") from exc
    return normalised


def generate_mutants(root: Path, files: list[str]) -> list[dict[str, Any]]:
    """One mutant per operator token in each Python file, from the fixed OPERATORS table."""
    root = Path(root)
    mutants: list[dict[str, Any]] = []
    for relative in files:
        normalised = _workspace_file(root, relative)
        if not normalised.endswith(".py"):
            raise EvidenceError(f"generated mutants read Python tokens; declare mutants for {normalised!r} instead")
        text = (root / normalised).read_bytes().decode("utf-8")
        if text.startswith("﻿"):
            # Why (review 2026-09-25): Python runs a source saved with a BOM, but the tokenizer on
            # decoded text rejects it, which read as "not Python". Say what it is instead.
            raise EvidenceError(f"{normalised} starts with a UTF-8 byte-order mark; save it without the BOM "
                                f"to generate mutants, or declare them with --mutants")
        try:
            # Why (review 2026-09-25): the positions must use the same line breaks as `_offset`:
            # \r\n, \r and \n, which is how Python itself reads a source file.
            tokens = list(tokenize.generate_tokens(io.StringIO(text, newline=None).readline))
        except (tokenize.TokenError, SyntaxError) as exc:
            raise EvidenceError(f"{normalised} does not tokenize as Python: {exc}") from exc
        for token in tokens:
            if token.type in (tokenize.OP, tokenize.NAME) and token.string in OPERATORS:
                line, column = token.start
                replace = OPERATORS[token.string]
                mutants.append({"id": f"{normalised}:{line}:{column}:{token.string}->{replace}", "file": normalised,
                                "find": token.string, "replace": replace, "line": line, "column": column})
    return mutants


def _check_mutants(root: Path, mutants: Any) -> list[dict[str, Any]]:
    if not isinstance(mutants, list) or not mutants:
        raise EvidenceError("mutation needs at least one mutant (declared with --mutants or generated with --generate)")
    checked, ids = [], set()
    for raw in mutants:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not raw["id"]:
            raise EvidenceError("every mutant needs an id")
        if raw["id"] in ids:
            raise EvidenceError(f"mutant ids must be unique: {raw['id']!r} repeats")
        ids.add(raw["id"])
        find, replace = raw.get("find"), raw.get("replace")
        if not isinstance(find, str) or not find or not isinstance(replace, str):
            raise EvidenceError(f"mutant {raw['id']}: find must be non-empty text and replace must be text")
        if find == replace:
            raise EvidenceError(f"mutant {raw['id']}: replace equals find, so it changes nothing")
        item = {"id": raw["id"], "file": _workspace_file(root, raw.get("file")), "find": find, "replace": replace}
        if "line" in raw or "column" in raw:
            line, column = raw.get("line"), raw.get("column")
            if any(isinstance(value, bool) or not isinstance(value, int) for value in (line, column)) \
                    or line < 1 or column < 0:
                raise EvidenceError(f"mutant {raw['id']}: line (from 1) and column (from 0) must be whole numbers")
            item.update({"line": line, "column": column})
        else:
            occurrence = raw.get("occurrence", 1)
            if isinstance(occurrence, bool) or not isinstance(occurrence, int) or occurrence < 1:
                raise EvidenceError(f"mutant {raw['id']}: occurrence must be a whole number from 1")
            item["occurrence"] = occurrence
        checked.append(item)
    return checked


def _lines(text: str) -> list[str]:
    """Lines with their ends, broken on \r\n, \r and \n only - never on \u2028, \x85 or \f."""
    lines, start, index = [], 0, 0
    while index < len(text):
        if text[index] in "\r\n":
            end = index + 2 if text.startswith("\r\n", index) else index + 1
            lines.append(text[start:end])
            start = index = end
            continue
        index += 1
    if start < len(text):
        lines.append(text[start:])
    return lines


def _position(text: str, offset: int) -> tuple[int, int]:
    """(line from 1, column from 0) of `offset`, with the line breaks of `_lines`."""
    done = [line for line in _lines(text[:offset]) if line.endswith(("\n", "\r"))]
    return len(done) + 1, offset - sum(len(line) for line in done)


def _offset(text: str, mutant: dict[str, Any]) -> Optional[int]:
    """Where the mutant's `find` starts in `text`, or None when it is not there."""
    if "line" in mutant:
        # Why (review 2026-09-25): `splitlines` also breaks on \u2028, \x85 and friends, and
        # `readlines` on \n only; the tokenizer that produced `line` read universal newlines.
        lines = _lines(text)
        if mutant["line"] > len(lines):
            return None
        offset = sum(len(item) for item in lines[:mutant["line"] - 1]) + mutant["column"]
        return offset if text.startswith(mutant["find"], offset) else None
    offset = -1
    for _ in range(mutant["occurrence"]):
        offset = text.find(mutant["find"], offset + 1)
        if offset < 0:
            return None
    return offset


def _criterion(command: list[str], cwd: Path, timeout: float) -> dict[str, Any]:
    clock = time.monotonic()
    verdict, exit_code, _, _ = _run(command, cwd, timeout)
    return {"verdict": verdict, "exit_code": exit_code, "duration_s": round(time.monotonic() - clock, 3)}


def _fresh_copy(root: Path, scratch: Path, index: int) -> Path:
    # Why (review 2026-09-25): one copy shared by every run let a criterion that is not idempotent
    # (it creates a directory, a table, a lock) fail on its second run for its own reasons, and
    # every mutant read as killed. A fresh copy per run also means no bytecode cache from the clean
    # run exists when a mutant runs: an equal-size swap (`==` -> `!=`) can no longer reuse a `.pyc`.
    copy = scratch / f"run-{index}"
    try:
        shutil.copytree(root, copy, symlinks=True, ignore=shutil.ignore_patterns(*_COPY_IGNORE))
    except (shutil.Error, OSError) as exc:
        raise EvidenceError(f"the workspace could not be copied for the criterion to run in: {str(exc)[:300]}") from exc
    return copy


def _mutate(root: Path, scratch: Path, index: int, command: list[str], mutant: dict[str, Any],
            timeout: float) -> dict[str, Any]:
    text = (root / mutant["file"]).read_bytes().decode("utf-8")
    offset = _offset(text, mutant)
    entry = {key: mutant[key] for key in ("id", "file", "find", "replace")}
    if offset is None:
        # Why (review 2026-09-25): located in the source before any copy, so a mutant that does
        # not apply costs nothing.
        entry.update({"line": mutant.get("line"), "column": mutant.get("column"),
                      "outcome": "not-applied", "exit_code": None})
        return entry
    line, column = _position(text, offset)
    mutated = text[:offset] + mutant["replace"] + text[offset + len(mutant["find"]):]
    copy = _fresh_copy(root, scratch, index)
    try:
        target = copy / mutant["file"]
        if target.is_symlink() or copy.resolve() not in target.resolve().parents:
            raise EvidenceError(f"mutant file {mutant['file']!r} does not resolve inside the copy")
        target.write_bytes(mutated.encode("utf-8"))
        run = _criterion(command, copy, timeout)
    finally:
        shutil.rmtree(copy, ignore_errors=True)
    # Why: the criterion has to FAIL on a mutant. A run that times out did not pass, so it killed
    # the mutant; a run that could not start measured nothing and is counted apart.
    outcome = {"passed": "survived", "failed": "killed", "timeout": "killed"}.get(run["verdict"], "error")
    entry.update({"line": line, "column": column, "outcome": outcome, "exit_code": run["exit_code"]})
    if run["verdict"] == "timeout":
        entry["note"] = "the criterion timed out on this mutant"
    return entry


def run_mutation(record_id: str, command: list[str], mutants: Any, *, root: Path,
                 timeout: float = 600.0, out_dir: Optional[Path] = None) -> dict[str, Any]:
    """Run the criterion on a copy of the workspace: clean (must pass), then per mutant (must fail).

    The user's tree is never written to, except for the record under `out_dir`. A clean run that
    does not pass is `no-control`: no mutant runs and there is no score.
    """
    if not isinstance(record_id, str) or not _ID.match(record_id):
        raise EvidenceError("id must be a plain name: letters, digits, '.', '_' or '-', up to 80 characters")
    if not command or not all(isinstance(item, str) and item for item in command):
        raise EvidenceError("the criterion command must be a non-empty argv list")
    if _carries_secret(list(command)):
        raise EvidenceError("the command line looks like it carries a secret; pass it through the environment instead")
    root = Path(root)
    checked = _check_mutants(root, mutants)
    timeout = _check_timeout(timeout)
    out = _check_out_dir(out_dir)
    started = datetime.now(timezone.utc)
    results: list[dict[str, Any]] = []
    temporary = Path(tempfile.gettempdir()).resolve()
    if temporary == root.resolve() or root.resolve() in temporary.parents:
        # Why (review 2026-09-25): a temporary directory inside the workspace makes every copy
        # copy itself.
        raise EvidenceError(f"the temporary directory {temporary} is inside the workspace; point TMPDIR elsewhere")
    # Why (review 2026-09-25): a descendant of the criterion can still hold a handle on Windows
    # when the directory is removed; that must not turn a finished measurement into exit 3.
    with tempfile.TemporaryDirectory(prefix="hpp-mutate-", ignore_cleanup_errors=True) as scratch:
        # Why: the criterion runs against copies, so a crash in the middle of a mutant can never
        # leave the user's file mutated. Paths in the command must be relative for this to hold.
        base = Path(scratch)
        copy = _fresh_copy(root, base, 0)
        clean = _criterion(list(command), copy, timeout)
        shutil.rmtree(copy, ignore_errors=True)
        if clean["verdict"] == "passed":
            results = [_mutate(root, base, index, list(command), mutant, timeout)
                       for index, mutant in enumerate(checked, start=1)]
    counts = {name: sum(1 for item in results if item["outcome"] == name)
              for name in ("killed", "survived", "not-applied", "error")}
    measured = counts["killed"] + counts["survived"]
    metrics = {"total": len(results), "killed": counts["killed"], "survived": counts["survived"],
               "not_applied": counts["not-applied"], "errors": counts["error"],
               "score": (counts["killed"] / measured) if measured else None}
    if clean["verdict"] != "passed":
        verdict = "no-control"
    elif not measured:
        verdict = "no-mutants"
    elif counts["survived"]:
        verdict = "blind-spots"
    elif counts["error"]:
        verdict = "incomplete"
    else:
        verdict = "sensitive"
    record: dict[str, Any] = {
        "schema": MUTATION_SCHEMA, "id": record_id, "command": list(command), "base_commit": _head(root),
        "started_at": started.isoformat(timespec="seconds").replace("+00:00", "Z"), "timeout_s": timeout,
        "clean": clean, "mutants": results, "metrics": metrics, "verdict": verdict,
        "survivors": [f"{item['file']}:{item['line']} {item['find']} -> {item['replace']}"
                      for item in results if item["outcome"] == "survived"],
    }
    target_dir = root / out
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    counter = 1
    while True:
        suffix = "" if counter == 1 else f"-{counter}"
        target = target_dir / f"{record_id}-mutate-{stamp}{suffix}.json"
        record["record_path"] = target.relative_to(root).as_posix()
        body = {key: value for key, value in record.items() if key != "record_sha256"}
        record["record_sha256"] = _sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
                                                     ensure_ascii=False).encode("utf-8"))
        try:
            with target.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
            break
        except FileExistsError:
            counter += 1
    return record


def exit_for_mutation(record: dict[str, Any]) -> int:
    """0 sensitive · 1 blind spots, incomplete or nothing measured · 2 no control (the ruler cannot run)."""
    return {"sensitive": 0, "no-control": 2}.get(record["verdict"], 1)
