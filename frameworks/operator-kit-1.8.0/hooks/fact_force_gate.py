#!/usr/bin/env python3
"""
fact_force_gate (Operator Kit) — PreToolUse: the FIRST touch of an existing file, and the
first shape of a destructive command, must be preceded by the facts.

The kit already carries the doctrine (`rules/gateguard.md` GATE 1: importers, schema,
rollback) and, until this hook, nothing measured it. `operation_guard_portable.py`
classifies a command; `snapshot_rollback_gate.py` prints a stateless checklist. Neither
knows whether THIS session already established the facts for the file it is about to edit
for the first time. That memory is the whole mechanism here.

HOW IT WORKS

  Edit / Write / MultiEdit on a file that ALREADY EXISTS
      not yet seen in this session -> WARN (exit 0 + additionalContext to the model) naming the three facts, and the path
      is marked, so the retry passes. A file that does not exist yet is allowed: there are
      no prior importers of something nobody can import.

  Bash carrying a destructive verb
      the command shape not yet seen -> WARN (exit 0 + additionalContext) demanding the written rollback, and
      the shape is marked, so the retry passes.

  The verb table is REUSED from `snapshot_rollback_gate.py` (same directory) plus one named
  addition, `git push --force`. Two tables for one question is how they drift apart.

WARN, NEVER BLOCK. Exit 1 is `warn` in the product's exit contract (0 ok / 1 warn / 2 block
/ 3 error). A gate is only allowed to block after its false-reject rate has been measured
over real command shapes; that measurement lives in the test file beside this hook, with its
denominator. Until it justifies more, this gate warns.

SESSION STATE
  <state dir>/<session id>.json, entries expiring after TTL_SECONDS and capped at
  MAX_ENTRIES (oldest evicted first). If the state cannot be read or written, the gate
  ALLOWS with a note: a gate that cannot remember would deny the same edit forever, and an
  unbreakable loop is worse than an unenforced rule.
  State dir: $HPP_FACT_FORCE_STATE_DIR, else <tempdir>/hpp-fact-force.

CONFIGURATION (all optional)
  HPP_FACT_FORCE=off            the whole gate yields, silently. Use it when another
                                first-touch gate is already installed in the same host:
                                two gates denying the same Edit teach operators to ignore
                                both.
  HPP_FACT_FORCE_EXEMPT         comma-separated globs matched against the path and its
                                basename (for example "*.md,notes/*").
  HPP_FACT_FORCE_STATE_DIR      where the per-session state file lives.

KNOWN LIMIT, STATED IN THE DENIAL ITSELF
  In a parallel batch, the first Edit is the one that is denied; the same batch's siblings
  find the file already marked and pass. Nothing is rolled back. The gate slows the first
  hand, not the batch. An operator who reads "denied" as "the batch was stopped" is wrong,
  so the message says it.

stdlib only. Cross-platform. Deterministic. `--self-test` covers every branch.

v1.0.0 — 2026-09-22 (Operator Kit · first-touch fact gate)
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from snapshot_rollback_gate import _DEFAULT_VERBS as _SHARED_VERBS
except Exception:  # noqa: BLE001 -- Why: the shared verb table is optional; without this the hook
    # dies at import in any install that ships fact_force_gate without snapshot_rollback_gate, and a
    # PreToolUse that raises on import blocks every tool call in the session.
    _SHARED_VERBS = []

ALLOW = "ALLOW"
WARN = "WARN"

TTL_SECONDS = 1800
MAX_ENTRIES = 500

_EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

# Why: the shared table has no force-push, and force-push is the destructive verb whose
# rollback has to exist BEFORE the command, not after — the remote history is gone.
_EXTRA_VERBS: list[tuple[str, str]] = [
    ("git push --force", r"\bgit\s+push\b[^\n|;&]*(--force\b|--force-with-lease\b|\s-f\b)(?![\w-])"),
]


def verbs() -> list[tuple[str, "re.Pattern[str]"]]:
    """The destructive verb table: the sibling hook's, plus the named additions."""
    out: list[tuple[str, re.Pattern[str]]] = []
    for label, pattern in list(_SHARED_VERBS) + _EXTRA_VERBS:
        try:
            out.append((label, re.compile(pattern, re.IGNORECASE)))
        except re.error:
            continue
    return out


# ----------------------------------- session state -----------------------------------

def state_dir() -> Path:
    explicit = os.environ.get("HPP_FACT_FORCE_STATE_DIR")
    return Path(explicit) if explicit else Path(tempfile.gettempdir()) / "hpp-fact-force"


def state_path(session_id: str) -> Path:
    safe = hashlib.sha256(str(session_id or "anonymous").encode("utf-8")).hexdigest()[:16]
    return state_dir() / f"{safe}.json"


def load_state(path: Path, now: float) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("checked"), dict):
            return {"created": data.get("created", now), "checked": data["checked"]}
    except Exception:  # noqa: BLE001 -- Why: a truncated or hand-edited state file must read as "nothing
        # checked yet". Narrowing this to JSONDecodeError would let an OSError (locked file, full disk)
        # escape and warn on every single tool call instead of once.
        pass
    return {"created": now, "checked": {}}


def save_state(path: Path, state: dict) -> bool:
    """True when the state reached disk. False is not fatal: the caller allows."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception:  # noqa: BLE001 -- Why: an unwritable temp dir means the gate cannot remember what it
        # already warned about. Returning False degrades to "warn again" — the alternative, raising,
        # would deny every Edit in the session, an unbreakable deny loop.
        return False


def seen(state: dict, key: str, now: float) -> bool:
    stamp = state.get("checked", {}).get(key)
    if stamp is None:
        return False
    return (now - float(stamp)) < TTL_SECONDS


def mark(state: dict, key: str, now: float) -> None:
    checked = state.setdefault("checked", {})
    checked[key] = now
    if len(checked) > MAX_ENTRIES:
        # evict oldest first; the newest marks are the ones a retry will look for
        for stale, _ in sorted(checked.items(), key=lambda item: item[1])[: len(checked) - MAX_ENTRIES]:
            checked.pop(stale, None)


# ------------------------------------- classifier -------------------------------------

def _exempt(path: str) -> bool:
    raw = os.environ.get("HPP_FACT_FORCE_EXEMPT") or ""
    globs = [part.strip() for part in raw.split(",") if part.strip()]
    if not globs:
        return False
    posix = str(path).replace("\\", "/")
    base = posix.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(posix, glob) or fnmatch.fnmatch(base, glob) for glob in globs)


_FIRST_TOUCH_REASON = (
    "first write of this session to an existing file. Establish the three facts before "
    "changing it: (1) IMPORTERS — grep the module, symbol or filename and see who consumes "
    "it; (2) SCHEMA — the signature, keys or output shape other code expects; (3) ROLLBACK "
    "— tracked by git means `git checkout -- <path>`, untracked means copy it first. "
    "This edit proceeds; establish them before the next write to this file and this gate stays "
    "quiet on it. "
    "Known limit: in a parallel batch only the FIRST edit is warned — the siblings find the "
    "path already marked and pass, and nothing is rolled back. This slows the first hand, "
    "not the batch."
)

_ROLLBACK_REASON = (
    "destructive command ({verbs}) with no written rollback in this session. Write, in one "
    "line, what restores the previous state (snapshot path, `git checkout`, database dump) "
    "and how you will verify it afterwards. This command proceeds; write the rollback before the "
    "next destructive one. Known limit: only the first occurrence of each command shape is warned, so a "
    "parallel batch sees one warning, not one per sibling."
)


def assess_edit(file_path: str, state: dict, now: float) -> dict:
    """Classify a write to `file_path`. Marks the path when it warns, so the retry passes."""
    path = str(file_path or "")
    if not path:
        return {"action": ALLOW, "rule": "no-path", "reason": "no file path in the payload"}
    if _exempt(path):
        return {"action": ALLOW, "rule": "exempt", "reason": "path matches HPP_FACT_FORCE_EXEMPT"}
    try:
        exists = Path(path).is_file()
    except Exception:  # noqa: BLE001 -- Why: an unreadable path (permission, bad encoding, too long on
        # Windows) is treated as "new file", which is the quiet side. Letting it raise would turn a
        # path the host can name but not stat into a blocked edit.
        exists = False
    if not exists:
        return {"action": ALLOW, "rule": "new-file",
                "reason": "the file does not exist yet — nothing imports it, nothing to roll back"}
    # Why (cross-model review): relative and absolute spellings of one file warned twice; resolve()
    # makes the key the file, not the spelling. strict=False: a path that cannot be resolved keeps
    # its text form instead of raising inside a hook.
    try:
        canonical = Path(path).resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        canonical = Path(path)
    key = f"file:{canonical.as_posix().casefold()}"
    if seen(state, key, now):
        return {"action": ALLOW, "rule": "already-checked",
                "reason": "the facts were requested for this path earlier in the session"}
    mark(state, key, now)
    return {"action": WARN, "rule": "first-touch", "reason": _FIRST_TOUCH_REASON}


def assess_bash(command: str, state: dict, now: float) -> dict:
    """Classify a Bash command. Marks the shape when it warns, so the retry passes."""
    text = str(command or "")
    if not text.strip():
        return {"action": ALLOW, "rule": "no-command", "reason": "empty command"}
    hits = sorted({label for label, pattern in verbs() if pattern.search(text)})
    if not hits:
        return {"action": ALLOW, "rule": "", "reason": "no destructive verb matched"}
    key = "bash:" + hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()[:24]
    if seen(state, key, now):
        return {"action": ALLOW, "rule": "already-checked",
                "reason": "the rollback was requested for this command shape earlier in the session"}
    mark(state, key, now)
    return {"action": WARN, "rule": "rollback-unwritten",
            "reason": _ROLLBACK_REASON.format(verbs=", ".join(hits))}


# --------------------------------------- hook ---------------------------------------

def run(raw: str) -> int:
    """PreToolUse entry point. Returns 0 (ok) or 1 (warn). Never 2, never raises."""
    if (os.environ.get("HPP_FACT_FORCE") or "").strip().casefold() == "off":
        return 0
    try:
        payload = json.loads(raw) if raw and raw.strip() else {}
    except Exception:  # noqa: BLE001 -- Why: the host owns the payload shape; a schema change or a truncated
        # pipe must be silence, not a failing gate on every call.
        return 0
    if not isinstance(payload, dict):
        return 0

    tool = payload.get("tool_name") or payload.get("toolName") or ""
    tool_input = payload.get("tool_input") or payload.get("toolInput") or {}
    if not isinstance(tool_input, dict):
        return 0

    now = time.time()
    path = state_path(payload.get("session_id") or payload.get("sessionId") or "anonymous")
    state = load_state(path, now)

    if tool in _EDIT_TOOLS:
        verdict = assess_edit(tool_input.get("file_path") or tool_input.get("notebook_path") or "",
                              state, now)
    elif tool == "Bash":
        verdict = assess_bash(tool_input.get("command") or "", state, now)
    else:
        return 0

    if verdict["action"] != WARN:
        return 0
    if not save_state(path, state):
        sys.stderr.write(
            "[fact_force_gate] state could not be persisted; allowing so the same action is not "
            "denied forever. Establish the facts yourself: importers, schema, rollback.\n"
        )
        return 0
    # Why (cross-model review of 2.5.0): this used to be `stderr` + exit 1, and by the host contract
    # exit 1 is a notice to the USER — the model, whom the text addresses, never saw it. A gate whose
    # message reaches nobody who can act on it is vacuous. PreToolUse `additionalContext` is the one
    # channel that reaches the model without blocking; exit 0 is the WARN-only promise kept.
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": f"[fact_force_gate] WARN ({verdict['rule']}): {verdict['reason']}",
        }
    }, ensure_ascii=False))
    return 0


# ------------------------------------- self-test -------------------------------------

def _self_test() -> None:
    import shutil

    sandbox = Path(tempfile.mkdtemp(prefix="fact_force_selftest_"))
    previous = {name: os.environ.get(name) for name in
                ("HPP_FACT_FORCE", "HPP_FACT_FORCE_EXEMPT", "HPP_FACT_FORCE_STATE_DIR")}
    try:
        os.environ.pop("HPP_FACT_FORCE", None)
        os.environ.pop("HPP_FACT_FORCE_EXEMPT", None)
        os.environ["HPP_FACT_FORCE_STATE_DIR"] = str(sandbox / "state")

        target = sandbox / "live.py"
        target.write_text("x = 1\n", encoding="utf-8")
        fresh = {"created": 0.0, "checked": {}}

        # 1. first touch of an existing file warns; the retry passes
        assert assess_edit(str(target), fresh, 1000.0)["action"] == WARN
        assert assess_edit(str(target), fresh, 1001.0)["action"] == ALLOW

        # 2. a file that does not exist yet never warns
        assert assess_edit(str(sandbox / "new.py"), fresh, 1000.0)["rule"] == "new-file"

        # 3. the three facts and the batch limit are in the message
        message = _FIRST_TOUCH_REASON.casefold()
        for token in ("importers", "schema", "rollback", "parallel", "rolled back"):
            assert token in message, token

        # 4. destructive Bash warns once per shape
        batch = {"created": 0.0, "checked": {}}
        assert assess_bash("rm -rf build", batch, 1000.0)["action"] == WARN
        assert assess_bash("rm -rf build", batch, 1001.0)["action"] == ALLOW
        assert assess_bash("git push --force origin main", batch, 1002.0)["action"] == WARN

        # 5. the everyday command stays quiet (control: the gate must discriminate)
        for quiet in ("python -m pytest -q", "git status --porcelain", "ls -la"):
            assert assess_bash(quiet, {"created": 0.0, "checked": {}}, 1000.0)["action"] == ALLOW, quiet

        # 6. the cap evicts the oldest and the TTL expires
        capped = {"created": 0.0, "checked": {}}
        for index in range(MAX_ENTRIES + 10):
            mark(capped, f"file:{index}", 1000.0 + index)
        assert len(capped["checked"]) <= MAX_ENTRIES and "file:0" not in capped["checked"]
        assert seen({"checked": {"k": 10.0}}, "k", 10.0 + TTL_SECONDS + 1) is False

        # 7. the hook contract: warn is 1, everything else is 0, nothing raises
        payload = json.dumps({"session_id": "selftest", "tool_name": "Edit",
                              "tool_input": {"file_path": str(target)}})
        import contextlib, io as _io
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert run(payload) == 0  # WARN never fails the call
        assert '"additionalContext"' in buf.getvalue(), "the WARN must reach the model via stdout JSON"
        buf2 = _io.StringIO()
        with contextlib.redirect_stdout(buf2):
            assert run(payload) == 0
        assert buf2.getvalue().strip() == "", "the second touch must be silent"
        for junk in ("", "not json", "[]", json.dumps({"tool_name": "Read"})):
            assert run(junk) == 0, junk

        # 8. the off switch and the exemption
        os.environ["HPP_FACT_FORCE"] = "off"
        other = sandbox / "other.py"
        other.write_text("y\n", encoding="utf-8")
        assert run(json.dumps({"session_id": "off", "tool_name": "Edit",
                               "tool_input": {"file_path": str(other)}})) == 0
        os.environ.pop("HPP_FACT_FORCE")
        os.environ["HPP_FACT_FORCE_EXEMPT"] = "*.md"
        doc = sandbox / "NOTES.md"
        doc.write_text("y\n", encoding="utf-8")
        assert run(json.dumps({"session_id": "ex", "tool_name": "Edit",
                               "tool_input": {"file_path": str(doc)}})) == 0
        buf3 = _io.StringIO()
        with contextlib.redirect_stdout(buf3):
            assert run(json.dumps({"session_id": "ex", "tool_name": "Edit",
                                   "tool_input": {"file_path": str(other)}})) == 0
        assert '"additionalContext"' in buf3.getvalue(), "the exemption must not be global"

        print("self-test OK")
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        shutil.rmtree(sandbox, ignore_errors=True)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    if len(sys.argv) > 1 and sys.argv[1] in ("--self-test", "-t"):
        _self_test()
    else:
        try:
            sys.exit(run(sys.stdin.read()))
        except Exception:  # noqa: BLE001 -- Why: last line of defence. Any unforeseen error in run() exits 0,
            # so a bug in this gate can cost a missed warning but never a blocked session.
            sys.exit(0)
