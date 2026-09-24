"""Run a declared command with a timeout that actually bounds the wait.

`subprocess.run(..., timeout=...)` kills only the direct child and then keeps reading its pipes.
A command that started its own children (a test runner starting a browser, a retriever starting a
helper) leaves them holding those pipes, and the read lasts until they exit: the timeout stops
bounding anything. Every command hpp runs for you goes through `run_bounded` instead.
"""
from __future__ import annotations

import math
import os
import shutil
import signal
import subprocess
import threading
import time
from typing import Any, Optional

from hpp.context import _SECRET_PATTERN

MAX_TIMEOUT = 86400.0
_DRAIN_GRACE = 2.0


def valid_timeout(timeout: Any) -> bool:
    """A usable timeout: a real number, finite, above zero and at most a day."""
    return (not isinstance(timeout, bool) and isinstance(timeout, (int, float)) and math.isfinite(timeout)
            and 0 < timeout <= MAX_TIMEOUT)


def stderr_tail(stderr: bytes) -> str:
    """The last stderr line, short enough for a report, or a note that it was withheld."""
    lines = stderr.decode("utf-8", errors="replace").strip().splitlines()
    if not lines:
        return "no stderr"
    # Why: a report is kept and shared; a connection string on stderr would travel with it.
    if _SECRET_PATTERN.search(lines[-1]):
        return "stderr withheld: it looks like it carries a secret"
    return lines[-1][:200]


def _launcher(command: list[str]) -> list[str]:
    # Why: on Windows, `npx`, `npm` and many runners are `.cmd` files. CreateProcess does not apply
    # PATHEXT, so the bare name fails to start although the same line works in a terminal.
    if os.name != "nt" or os.sep in command[0] or (os.altsep and os.altsep in command[0]):
        return command
    found = shutil.which(command[0])
    return [found, *command[1:]] if found else command


def _kill_tree(process: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=30)
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        process.kill()
    except OSError:
        pass


def _pump(stream: Any, sink: list[bytes]) -> None:
    # Why: `read(n)` on a buffered pipe waits for n bytes or EOF, and a descendant holding the pipe
    # means no EOF: output the command already wrote would never be handed back. `read1` returns
    # what is available.
    try:
        for block in iter(lambda: stream.read1(65536), b""):
            sink.append(block)
    except (OSError, ValueError):
        pass


def _feed(stream: Any, data: bytes) -> None:
    try:
        stream.write(data)
        stream.close()
    except (OSError, ValueError):
        pass


def run_bounded(command: list[str], *, timeout: float, cwd: Optional[str] = None,
                stdin: Optional[bytes] = None) -> tuple[str, Optional[int], bytes, bytes]:
    """Return (state, exit_code, stdout, stderr); state is exited, timeout or could-not-start.

    The command runs in its own process group. On timeout the whole tree is stopped. Once the
    command itself has exited, its output is complete: a descendant still holding the pipes is
    given a short grace to let the readers drain, then it is no longer waited for.
    """
    group = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
             else {"start_new_session": True})
    try:
        process = subprocess.Popen(_launcher(list(command)), cwd=cwd, shell=False,
                                   stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, **group)
    except OSError:
        return "could-not-start", None, b"", b""
    out: list[bytes] = []
    err: list[bytes] = []
    workers = [threading.Thread(target=_pump, args=(process.stdout, out), daemon=True),
               threading.Thread(target=_pump, args=(process.stderr, err), daemon=True)]
    if stdin is not None:
        workers.append(threading.Thread(target=_feed, args=(process.stdin, stdin), daemon=True))
    for worker in workers:
        worker.start()
    try:
        process.wait(timeout=timeout)
        state, exit_code = "exited", process.returncode
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        state, exit_code = "timeout", None
    deadline = time.monotonic() + _DRAIN_GRACE
    for worker in workers:
        worker.join(timeout=max(0.0, deadline - time.monotonic()))
    return state, exit_code, b"".join(out), b"".join(err)
