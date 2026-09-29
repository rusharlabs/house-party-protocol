"""How `run_bounded` stops a timed-out command's process tree on Windows.

`taskkill /PID <pid> /T` walks the process table by parent id alone. A process keeps its parent's id
after that parent exits, and Windows gives an exited process's id to a later process, so a process
whose parent id names an EARLIER process that had the same id as the command (or as one of its
descendants) -- an orphan older than the tree -- is ended too, and nothing verified it was the
command's. These tests build a fake Windows process table (ids, parent ids, creation times, handles
and id reuse) and inject it into `hpp._process`: no real process is signalled except the `python -c`
processes the last test starts itself.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

from hpp import _process


class _WinProcess:
    def __init__(self, name: str, pid: int, parent: int, created: int, alive: bool = True,
                 pinned: bool = False) -> None:
        self.name, self.pid, self.parent, self.created = name, pid, parent, created
        self.alive, self.pinned, self.handles = alive, pinned, 0


class _FakeWindows:
    """A process table with the rules the fix relies on: an id names one process at a time; a process
    that exited keeps its id while a handle to it is open (the Popen of the command pins the command);
    once no handle holds a dead process its id is free, and `reuse` hands it at once to another process.
    `taskkill /PID p [/T] /F` ends the live process that holds p now (and, with /T, every live process
    whose parent id is p, transitively), whatever process that is: the /T walk goes by the parent id
    alone, with no creation-time check, which is the worst case the runner has to be safe against.
    `first_contact`, when set, runs once, at the first snapshot (right after it is taken) or at the
    first taskkill (before it acts): "a process started while the tree was being stopped"."""

    def __init__(self, clock: int = 2000) -> None:
        self.table: dict[int, _WinProcess] = {}
        self.reuse: dict[int, _WinProcess] = {}
        self.killed: list[str] = []
        self.handles: dict[int, _WinProcess] = {}
        self.taskkills: list[list[str]] = []
        self.clock = clock
        self.first_contact = None
        self._next = 1

    def spawn(self, name: str, pid: int, parent: int, created: int, **flags) -> _WinProcess:
        self.table[pid] = process = _WinProcess(name, pid, parent, created, **flags)
        return process

    def _contact(self) -> None:
        hook, self.first_contact = self.first_contact, None
        if hook:
            hook()

    def _free(self) -> None:
        for pid, process in list(self.table.items()):
            if not process.alive and not process.handles and not process.pinned:
                del self.table[pid]
                if pid in self.reuse:
                    self.table[pid] = self.reuse.pop(pid)

    def _kill(self, process: _WinProcess) -> None:
        if process.alive:
            process.alive = False
            self.killed.append(process.name)

    def die(self, pid: int) -> None:
        """An exit of its own, not a kill."""
        self.table[pid].alive = False
        self._free()

    # the OS functions the runner calls
    def parents(self) -> dict[int, int]:
        snapshot = {pid: process.parent for pid, process in self.table.items() if process.alive}
        self._contact()
        return snapshot

    def open(self, pid: int):
        process = self.table.get(pid)
        if process is None:
            return None
        handle, self._next = self._next, self._next + 1
        self.handles[handle] = process
        process.handles += 1
        return handle

    def creation_time(self, handle) -> int:
        return self.handles[handle].created

    def close(self, handle) -> None:
        process = self.handles.pop(handle)
        process.handles -= 1
        self._free()

    def now(self) -> int:
        return self.clock

    def taskkill(self, argv, **_options) -> subprocess.CompletedProcess:
        argv = list(argv)
        assert argv[0] == "taskkill", f"the runner started something other than taskkill: {argv}"
        self.taskkills.append(argv)
        self._contact()
        pid = int(argv[argv.index("/PID") + 1])
        target = self.table.get(pid)
        if target is None or not target.alive:
            return subprocess.CompletedProcess(argv, 128, b"", f"ERROR: The process \"{pid}\" not found.".encode())
        victims, queue = [target], [target]
        while "/T" in argv and queue:
            parent = queue.pop()
            for child in self.table.values():
                if child.alive and child.parent == parent.pid and child not in victims:
                    victims.append(child)
                    queue.append(child)
        for victim in victims:
            self._kill(victim)
        self._free()
        return subprocess.CompletedProcess(argv, 0, b"", b"")


class _FakePopen:
    """The runner's Popen of the command: it holds the command's handle, so the command's id is pinned,
    and its kill() is TerminateProcess on that handle -- it can only reach the command itself."""

    def __init__(self, world: _FakeWindows, root: _WinProcess) -> None:
        self.world, self.root, self.pid = world, root, root.pid

    def kill(self) -> None:
        self.world._kill(self.root)

    def wait(self, timeout=None) -> int:
        return 1


class _OsAs:
    def __init__(self, name: str, **overrides) -> None:
        self.name = name
        self.__dict__.update(overrides)

    def __getattr__(self, attribute: str):
        return getattr(os, attribute)


class _SubprocessWith:
    def __init__(self, run) -> None:
        self.run = run

    def __getattr__(self, attribute: str):
        return getattr(subprocess, attribute)


def _on_fake_windows(monkeypatch, world: _FakeWindows) -> None:
    monkeypatch.setattr(_process, "os", _OsAs("nt"))
    monkeypatch.setattr(_process, "subprocess", _SubprocessWith(world.taskkill))
    for name, function in (("_windows_process_parents", world.parents), ("_windows_open", world.open),
                           ("_windows_creation_time", world.creation_time), ("_windows_close", world.close),
                           ("_windows_now", world.now)):
        monkeypatch.setattr(_process, name, function, raising=False)


def _older_orphan_names_the_command(world: _FakeWindows) -> _WinProcess:
    root = world.spawn("command", 100, 1, 1000, pinned=True)
    world.spawn("child", 5001, 100, 1001)
    # an orphan of an EARLIER process that had id 100: created before the command, it is not the command's
    world.spawn("bystander", 6000, 100, 500)
    return root


def _older_orphan_names_a_descendant(world: _FakeWindows) -> _WinProcess:
    root = world.spawn("command", 100, 1, 1000, pinned=True)
    world.spawn("child", 5001, 100, 1001)
    # an orphan of an EARLIER process that had id 5001: its parent id names the child's id, but it was
    # created before that child, so it is not the child's
    world.spawn("bystander", 7000, 5001, 800)
    return root


def _id_freed_by_a_kill_then_reused(world: _FakeWindows) -> _WinProcess:
    root = world.spawn("command", 100, 1, 1000, pinned=True)
    world.spawn("child", 5001, 100, 1001)
    world.spawn("grandchild", 5002, 5001, 1002)
    world.reuse[5001] = _WinProcess("bystander", 5001, 4, 9000)  # takes 5001 the moment it is free
    return root


def _id_reused_between_snapshot_and_check(world: _FakeWindows) -> _WinProcess:
    root = world.spawn("command", 100, 1, 1000, pinned=True)
    world.spawn("child", 5001, 100, 1001)
    world.reuse[5001] = _WinProcess("bystander", 5001, 4, 9000)
    world.first_contact = lambda: world.die(5001)
    return root


@pytest.mark.parametrize("scenario, must_die", [
    (_older_orphan_names_the_command, {"command", "child"}),
    (_older_orphan_names_a_descendant, {"command", "child"}),
    (_id_freed_by_a_kill_then_reused, {"command", "child", "grandchild"}),
    (_id_reused_between_snapshot_and_check, {"command"}),
], ids=["older-orphan-of-a-previous-id-100", "older-orphan-of-a-previous-id-5001",
        "id-freed-by-a-kill-then-reused", "id-reused-between-snapshot-and-check"])
def test_the_timeout_kill_never_ends_a_process_it_did_not_verify(monkeypatch, scenario, must_die: set) -> None:
    world = _FakeWindows()
    root = scenario(world)
    _on_fake_windows(monkeypatch, world)
    _process._kill_tree(_FakePopen(world, root))
    assert "bystander" not in world.killed, \
        f"a process that is not the command's descendant was killed by an id it inherited: {world.killed}"
    assert must_die <= set(world.killed), f"the command's own tree must still die: {world.killed}"
    assert not world.handles, f"handles left open: {[p.name for p in world.handles.values()]}"


def test_no_kill_walks_the_process_table_by_parent_id(monkeypatch) -> None:
    """The structural half of the same defect: `/T` is the walk that trusts parent ids."""
    world = _FakeWindows()
    root = _older_orphan_names_the_command(world)
    _on_fake_windows(monkeypatch, world)
    _process._kill_tree(_FakePopen(world, root))
    assert world.taskkills, "no taskkill ran: the child was not stopped"
    assert all("/T" not in argv for argv in world.taskkills), world.taskkills


def _started_while_the_tree_is_stopped(parent_id: int):
    def scenario(world: _FakeWindows) -> _WinProcess:
        root = world.spawn("command", 100, 1, 1000, pinned=True)
        world.spawn("child", 5001, 100, 1001)

        def a_late_process_starts() -> None:
            world.clock = 3000
            world.spawn("late", 5003, parent_id, 2500)
        world.first_contact = a_late_process_starts
        return root
    return scenario


@pytest.mark.parametrize("scenario", [_started_while_the_tree_is_stopped(100),
                                      _started_while_the_tree_is_stopped(5001)],
                         ids=["late-child-of-the-command", "late-child-of-a-descendant"])
def test_CONTROLE_a_process_the_tree_starts_while_it_is_stopped_still_dies(monkeypatch, scenario) -> None:
    """What `taskkill /T` reached -- a child started just before its parent was killed -- is still
    reached once each kill ends one verified process: the tree is walked again after the kills, from the
    command and from every descendant already verified."""
    world = _FakeWindows()
    root = scenario(world)
    _on_fake_windows(monkeypatch, world)
    _process._kill_tree(_FakePopen(world, root))
    assert {"command", "child", "late"} <= set(world.killed), world.killed
    assert not world.handles, f"handles left open: {[p.name for p in world.handles.values()]}"


def test_CONTROLE_an_empty_first_snapshot_is_still_followed_by_a_walk(monkeypatch) -> None:
    """"Nothing new" is judged on a walk taken after the kills, never on the snapshot taken before them:
    a command with no child at the first snapshot that starts one just before it dies leaves no child."""
    world = _FakeWindows()
    root = world.spawn("command", 100, 1, 1000, pinned=True)

    def a_late_child_starts() -> None:
        world.clock = 3000
        world.spawn("late", 5003, 100, 2500)
    world.first_contact = a_late_child_starts
    _on_fake_windows(monkeypatch, world)
    _process._kill_tree(_FakePopen(world, root))
    assert {"command", "late"} <= set(world.killed), world.killed
    assert not world.handles, f"handles left open: {[p.name for p in world.handles.values()]}"


def test_CONTROLE_on_posix_the_kill_is_the_process_group_then_the_command(monkeypatch) -> None:
    """POSIX is untouched: SIGKILL to the command's process group, then kill() on the command itself."""
    calls: list[tuple] = []

    class _Popen:
        pid = 4242

        def kill(self) -> None:
            calls.append(("kill",))

    def refuse(*args, **kwargs):
        raise AssertionError(f"nothing is started to stop a POSIX tree: {args}")

    monkeypatch.setattr(_process, "os", _OsAs("posix", killpg=lambda pid, sig: calls.append(("killpg", pid, sig))))
    monkeypatch.setattr(_process, "signal", types.SimpleNamespace(SIGKILL=9))
    monkeypatch.setattr(_process, "subprocess", _SubprocessWith(refuse))
    _process._kill_tree(_Popen())
    assert calls == [("killpg", 4242, 9), ("kill",)], calls


_HELPER = ("import sys, time\n"
           "end = time.monotonic() + 30\n"
           "while time.monotonic() < end:\n"
           "    with open(sys.argv[1], 'a') as beat:\n"
           "        beat.write('.')\n"
           "    time.sleep(0.1)\n")


def _size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


@pytest.mark.skipif(os.name != "nt", reason="the real Windows tree walk (kernel32 through ctypes, taskkill)")
def test_CONTROLE_on_real_windows_a_timed_out_commands_child_is_stopped(tmp_path: Path) -> None:
    """The real path, with processes this test starts and nothing else: the command starts a helper that
    writes a beat every 0.1 s, then outlives the timeout; once `run_bounded` returns, the beat stops."""
    beat = tmp_path / "beat"
    command = ("import subprocess, sys, time\n"
               "subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]])\n"
               "time.sleep(30)\n")
    state, _code, _out, _err = _process.run_bounded([sys.executable, "-c", command, _HELPER, str(beat)],
                                                    timeout=5)
    assert state == "timeout"
    assert _size(beat) > 0, "the helper never started: the test measured nothing"
    time.sleep(0.5)
    before = _size(beat)
    time.sleep(1.5)
    assert _size(beat) == before, "the command's helper survived the timeout"
