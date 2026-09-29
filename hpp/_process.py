"""Run a declared command with a timeout that actually bounds the wait.

`subprocess.run(..., timeout=...)` kills only the direct child and then keeps reading its pipes.
A command that started its own children (a test runner starting a browser, a retriever starting a
helper) leaves them holding those pipes, and the read lasts until they exit: the timeout stops
bounding anything. Every command hpp runs for you goes through `run_bounded` instead.
"""
from __future__ import annotations

import functools
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
_KILL_WAIT = 10.0
# How many times a Windows tree is walked and killed: a killed process starts nothing more, so each walk
# after the first finds only what a process still alive started since the one before.
_WINDOWS_TREE_PASSES = 4


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


def _windows_process_parents() -> dict[int, int]:
    """{pid: parent pid} for every process, from one Toolhelp32 snapshot. {} when it cannot be taken."""
    import ctypes
    from ctypes import wintypes

    class ProcessEntry32(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_char * 260)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    for name in ("Process32First", "Process32Next"):
        getattr(kernel32, name).restype = wintypes.BOOL
        getattr(kernel32, name).argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry32)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
    if not snapshot or snapshot == ctypes.c_void_p(-1).value:
        return {}
    parents: dict[int, int] = {}
    try:
        entry = ProcessEntry32()
        entry.dwSize = ctypes.sizeof(ProcessEntry32)
        more = kernel32.Process32First(snapshot, ctypes.byref(entry))
        while more:
            parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            more = kernel32.Process32Next(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return parents


@functools.lru_cache(maxsize=1)
def _kernel32() -> Any:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
    kernel32.GetSystemTimeAsFileTime.restype = None
    kernel32.GetSystemTimeAsFileTime.argtypes = [ctypes.POINTER(wintypes.FILETIME)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    return kernel32


def _filetime(value: Any) -> int:
    return (int(value.dwHighDateTime) << 32) | int(value.dwLowDateTime)


def _windows_now() -> int:
    """The system time, in the unit and on the clock of a process's creation time (FILETIME)."""
    from ctypes import byref, wintypes
    now = wintypes.FILETIME()
    _kernel32().GetSystemTimeAsFileTime(byref(now))
    return _filetime(now)


def _windows_open(pid: int) -> Any:
    """A handle on the process that holds `pid` now, or None. While it is open, that process's pid is
    never given to another process, even after it exits."""
    handle = _kernel32().OpenProcess(0x1000 | 0x00100000, False, pid)  # QUERY_LIMITED_INFORMATION | SYNCHRONIZE
    return handle or None


def _windows_creation_time(handle: Any) -> Optional[int]:
    from ctypes import byref, wintypes
    created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
    if not _kernel32().GetProcessTimes(handle, byref(created), byref(exited), byref(kernel), byref(user)):
        return None
    return _filetime(created)


def _windows_close(handle: Any) -> None:
    _kernel32().CloseHandle(handle)


def _windows_verified_tree(root_pid: int, known: Optional[dict[int, int]] = None) -> list[tuple[int, Any, int]]:
    """Every process below `root_pid`, transitively, from one snapshot of (pid, parent pid), each as
    (pid, handle, creation time) with a handle opened on it and its identity verified: it was created
    before the snapshot began (so it is the process the snapshot saw) and not before its verified parent
    (so its parent id names that parent, not an earlier process that had the same pid). The open handle
    keeps the pid from being reused until the caller closes it. `known` is {pid: creation time} of
    descendants already verified whose handles the caller still holds: the walk also starts from them (a
    killed parent is no longer in the snapshot, its late children are) and does not return them again."""
    held: list[tuple[int, Any, int]] = []
    seeds = dict(known or {})
    try:
        started = _windows_now()
        parents = _windows_process_parents()
        root = _windows_open(root_pid)  # the Popen's own handle pins the command's pid
        if root is not None:
            try:
                root_created = _windows_creation_time(root)
            finally:
                _windows_close(root)
            if root_created is not None:
                seeds[root_pid] = root_created
        if not seeds:
            return held
        children: dict[int, list[int]] = {}
        for pid, parent in parents.items():
            children.setdefault(parent, []).append(pid)
        seen, queue = set(seeds), list(seeds.items())
        while queue:
            parent, parent_created = queue.pop()
            for pid in children.get(parent, []):
                if pid in seen:
                    continue
                seen.add(pid)
                handle = _windows_open(pid)
                if handle is None:
                    continue
                try:
                    created = _windows_creation_time(handle)
                except (OSError, AttributeError, ValueError):
                    created = None
                if created is None or not parent_created <= created <= started:
                    _windows_close(handle)
                    continue
                held.append((pid, handle, created))
                queue.append((pid, created))
    except (OSError, AttributeError, ValueError):
        pass  # what was verified before the failure is still verified: it is returned, and closed by the caller
    return held


def _kill_windows_tree(process: subprocess.Popen) -> None:
    # Why: `taskkill /T` walks the process table by parent id alone, so it also ended a process whose
    # parent id named an EARLIER process that had the same pid as the command or one of its descendants
    # (an orphan older than the tree), and nothing verified it. Now every kill ends one verified process:
    # the command through its own Popen handle, each descendant by a pid its held handle pins. A child
    # started just before its parent died, which `/T` used to reach, is found by walking the tree again
    # after the kills, from the command and from every descendant already held, until a walk finds
    # nothing new.
    held: list[tuple[int, Any, int]] = []
    try:
        found = _windows_verified_tree(process.pid)  # before anything dies: the tree is still whole
        held.extend(found)
        try:
            process.kill()
        except OSError:
            pass
        # Why: TerminateProcess only starts the end; waiting keeps the command from starting a child
        # after the walks below.
        try:
            process.wait(timeout=_KILL_WAIT)
        except subprocess.TimeoutExpired:
            pass
        for walk in range(1, _WINDOWS_TREE_PASSES + 1):
            for pid, _handle, _created in found:  # the held handle pins the pid: it is still this process
                try:
                    subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=30)
                except (OSError, subprocess.SubprocessError):
                    pass
            if walk == _WINDOWS_TREE_PASSES:
                break
            # Why: "nothing new" is judged on a walk taken after the kills, never on the snapshot taken
            # before them, or a child started just before the command died survives an empty first one.
            found = _windows_verified_tree(process.pid, {pid: created for pid, _handle, created in held})
            held.extend(found)
            if not found:
                break
    finally:
        for _pid, handle, _created in held:
            try:
                _windows_close(handle)
            except OSError:
                pass


def _kill_tree(process: subprocess.Popen) -> None:
    if os.name == "nt":
        _kill_windows_tree(process)
        return
    try:
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
    finally:
        # Why: the reader is the one thread that may close the pipe without racing another reader;
        # when a descendant kept it open past the return, it is closed here once EOF arrives.
        try:
            stream.close()
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
    # Why (2026-09-25, 77 ResourceWarnings under -W error): the pipes were never closed, so every
    # command leaked two descriptors. A stream is closed once the thread that uses it has finished;
    # one still blocked (a descendant holding the pipe) is left alone, because closing a file another
    # thread is reading can block on its buffer lock.
    for stream, worker in zip((process.stdout, process.stderr, process.stdin), workers + [None]):
        if stream is not None and (worker is None or not worker.is_alive()):
            try:
                stream.close()
            except OSError:
                pass
    return state, exit_code, b"".join(out), b"".join(err)
