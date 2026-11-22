#!/usr/bin/env python3
"""
lane_orca -- the board's mirror on Orca's workspace card, and the one resolver of the Orca CLI.

Opt-in (`mailbox.orca_status: true` in lanes.yaml; off by default, and lanes.yaml needs PyYAML): after
a board transition, outside the board lock, `orca worktree set` gives this worktree's card in Orca the
workspace status of the item's new state and one comment line `HPP: <item> <state>`. A verdict that
sends the work back (NEEDS-FIX) also marks the workspace unread, so it shows in Orca's sidebar.

    CLAIMED, BUILDING, NEEDS-FIX         -> in-progress   (NEEDS-FIX also --unread)
    CHECKPOINT-READY, UNDER-REVIEW       -> in-review
    VERIFIED, MERGED                     -> completed
    any other state                      -> no call

Orca is a view of the board, never its record: the read and the write share one budget (the caller's
timeout; the runner adds at most 3 s to end a process that outlives it). There is no retry, nothing
raises, and every outcome is one line the board prints on stderr. It is fired by a board event,
never by a clock. The user's own comment lines on the card are kept: the comment is read first
(`orca worktree list --json`) and only the line starting `HPP:` is rewritten. A folder Orca does not
manage is skipped without a call to `worktree set`.

stdlib only. The board passes its bounded runner (`lane_board._run_bounded`) in, so this module never
imports the board, and the dashboard resolves the CLI through `orca_cli` here.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from collections.abc import Callable
from pathlib import Path

STATUS_BY_STATE = {
    "CLAIMED": "in-progress", "BUILDING": "in-progress", "NEEDS-FIX": "in-progress",
    "CHECKPOINT-READY": "in-review", "UNDER-REVIEW": "in-review",
    "VERIFIED": "completed", "MERGED": "completed",
}
UNREAD_STATES = ("NEEDS-FIX",)
COMMENT_PREFIX = "HPP:"

# (exit code or None after a timeout, stdout, stderr) -- the shape of lane_board._run_bounded
Runner = Callable[[list, float], "tuple[int | None, str, str]"]


def orca_cli(which: Callable[[str], str | None] = shutil.which, env=None, system: str | None = None) -> str | None:
    """Resolve one executable, without falling through to a different Orca build.

    On Linux the bare `orca` belongs to the GNOME screen reader. An explicit override
    is an executable name or path, not a shell command with arguments.
    """
    env = os.environ if env is None else env
    system = sys.platform if system is None else system
    return which(env.get("ORCA_CLI_COMMAND") or ("orca-ide" if system.startswith("linux") else "orca"))


def _same_dir(left: str, right: Path) -> bool:
    try:
        return os.path.normcase(os.path.realpath(left)) == os.path.normcase(os.path.realpath(str(right)))
    except (OSError, ValueError):
        return False


def merged_comment(current: str, line: str) -> str:
    """The card's comment with its `HPP:` line replaced (or added last); every other line kept."""
    kept = [text for text in (current or "").splitlines() if not text.startswith(COMMENT_PREFIX)]
    return "\n".join([*kept, line])


def mirror(project_dir: Path, item_id: str, state: str, *, run: Runner, timeout: float,
           which: Callable[[str], str | None] = shutil.which, env=None, system: str | None = None) -> str:
    """Mirror one board transition on the Orca card of `project_dir`. Returns the outcome line.

    `timeout` is ONE budget for the read and the write together (review of 22/11, RC-03): the write gets
    only what the read left, and none when nothing is left.
    """
    status = STATUS_BY_STATE.get(state)
    if not status:
        return f"none ({state or 'no state'} is not mirrored)"
    executable = orca_cli(which, env, system)
    if not executable:
        return "skipped (orca not on PATH)"
    deadline = time.monotonic() + timeout
    try:
        code, stdout, _stderr = run([executable, "worktree", "list", "--json"], timeout)
    except OSError as exc:
        return f"failed ({exc.strerror or exc})"
    if code is None:
        return f"failed (timeout after {timeout:g}s)"
    if code != 0:
        return f"failed (worktree list exit {code})"
    try:
        result = json.loads(stdout).get("result") or {}
        trees = [tree for tree in result.get("worktrees", []) if isinstance(tree, dict)]
    except (ValueError, AttributeError):
        return "failed (worktree list did not answer JSON)"
    tree = next((tree for tree in trees if tree.get("path") and _same_dir(str(tree["path"]), project_dir)), None)
    if tree is None:
        return "skipped (not an Orca worktree)"
    comment = merged_comment(str(tree.get("comment") or ""), f"{COMMENT_PREFIX} {item_id} {state}")
    comment_args, note = ["--comment", comment], ""
    # Why: cmd.exe cuts a batch file's arguments at a line break, so through `orca.cmd` a two-line comment
    # would drop every flag after it. Orca's own `orca.exe` carries it; a batch launcher keeps the status.
    if ((system or sys.platform) == "win32" and executable.lower().endswith((".bat", ".cmd"))
            and "\n" in comment):
        comment_args, note = [], "; comment left as it was: a batch launcher cannot carry a multi-line comment"
    argv = [executable, "worktree", "set", "--worktree", f"path:{project_dir}", "--workspace-status", status,
            *comment_args, *(["--unread"] if state in UNREAD_STATES else []), "--json"]
    left = deadline - time.monotonic()
    if left <= 0:
        return f"failed (timeout after {timeout:g}s)"
    try:
        code, stdout, stderr = run(argv, left)
    except OSError as exc:
        return f"failed ({exc.strerror or exc})"
    if code is None:
        return f"failed (timeout after {timeout:g}s)"
    if code != 0:
        detail = (stderr or stdout or "").strip().splitlines()
        return f"failed (exit {code}{': ' + detail[0][:120] if detail else ''})"
    return f"sent ({status}{', unread' if state in UNREAD_STATES else ''}{note})"


def _self_test() -> int:
    calls: list = []
    listing = {"ok": True, "result": {"worktrees": [{"path": str(Path.cwd()), "comment": "my note\nHPP: X1 BUILDING"}]}}

    def run(argv, timeout):
        calls.append(argv)
        return (0, json.dumps(listing), "") if argv[2] == "list" else (0, "{}", "")

    def which(name):
        return "orca"

    checks = []
    checks.append(mirror(Path.cwd(), "X1", "APPROVED", run=run, timeout=1, which=which).startswith("none"))
    checks.append(not calls)
    checks.append(mirror(Path.cwd(), "X1", "NEEDS-FIX", run=run, timeout=1, which=which) == "sent (in-progress, unread)")
    sent = calls[-1]
    checks.append(sent[sent.index("--comment") + 1] == "my note\nHPP: X1 NEEDS-FIX" and "--unread" in sent)
    checks.append(mirror(Path.cwd(), "X1", "VERIFIED", run=run, timeout=1, which=lambda name: None)
                  == "skipped (orca not on PATH)")
    checks.append(mirror(Path("/no/such/orca/worktree"), "X1", "VERIFIED", run=run, timeout=1, which=which)
                  == "skipped (not an Orca worktree)")
    if not all(checks):
        print(f"self-test FAIL: {checks}", file=sys.stderr)
        return 1
    print(f"self-test OK — {len(checks)} of {len(checks)} checks: unmapped state makes no call; NEEDS-FIX sends "
          "in-progress + unread and keeps the user's comment line; no orca -> skipped; a folder Orca does not "
          "manage -> skipped")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        raise SystemExit(_self_test())
    print(__doc__)
    raise SystemExit(0 if sys.argv[1:] in ([], ["--help"], ["-h"]) else 2)
