#!/usr/bin/env python3
"""
lane_register -- SessionStart: registers this session as a live lane. PostToolUse: heartbeat.

Two modes by argv (bare = register, --heartbeat = heartbeat), both delegating to the registry
in `_lane_io.py`. Total fail-open: any exception becomes `{}` on stdout and exit 0 -- never
brings down the session boot or a tool-call.

Lane identity resolved (in this order): env CLAUDE_LANE_ID / CLAUDE_LANE_ROLE /
CLAUDE_LANE_MODEL, otherwise the hook payload, otherwise defaults ("solo"/"adhoc"/"unknown").

Mailbox (`.claude/lanes/mailbox/*.md`, config `mailbox.*` in lanes.yaml): a message is addressed
to a lane by a routing LINE, `## To: <lane_id>` (the legacy `## Para: <lane_id>` still routes),
matched whole, with the lane id bounded -- never a substring. The register announces every
unread message; the heartbeat announces a message that arrived while the lane was running, once
per message, on the first heartbeat that lands after it (a throttled beat does not scan). What
has been announced is kept per lane in `mailbox/.announced/<lane_id>.json`, so a register and
the heartbeats never repeat each other. Messages moved to `mailbox/_read/` are never announced.
The heartbeat speaks through `hookSpecificOutput.additionalContext` (`hookEventName:
PostToolUse`), the form the host reads as context after a tool call.

Usage (hooks):
    echo '{"hook_event_name":"SessionStart","session_id":"..."}' | python lane_register.py
    echo '{"hook_event_name":"PostToolUse","session_id":"..."}'  | python lane_register.py --heartbeat

Exit: always 0.
stdlib only. v1.0.0 -- 2026-07-10 (lane-kit) · mailbox routing + heartbeat announce -- lane-kit 1.6.x
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import _lane_io  # noqa: E402

try:
    import lane_rescue  # noqa: E402 — same kit, sibling directory
except ImportError:  # pragma: no cover — a copy install that took only hooks/ still boots
    lane_rescue = None  # type: ignore[assignment]


def _git_branch() -> str:
    try:
        r = subprocess.run(["git", "-C", str(_lane_io._PROJECT_ROOT), "branch", "--show-current"],
                            capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except Exception:  # noqa: BLE001 -- Why: branch name is decoration on the lane record; a repo
        # without git (or git absent from PATH) must still register the lane, so this is "".
        return ""


def _git_worktree() -> str:
    try:
        r = subprocess.run(["git", "-C", str(_lane_io._PROJECT_ROOT), "rev-parse", "--show-toplevel"],
                            capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except Exception:  # noqa: BLE001 -- Why: the worktree path only feeds the rescue patch;
        # without it the rescue is skipped for this lane, which is the documented fail-open, and the
        # SessionStart that registers the lane must never be the thing that fails.
        return ""


def _rescue_evicted(evicted: list) -> list:
    """Capture the uncommitted work of every lane this register just dropped.

    Eviction is the moment a lane's worktree becomes unowned; a `worktree remove --force` or an
    idle-cleanup cron after it destroys uncommitted work with no trace. This runs OUTSIDE the
    registry lock (it is git I/O) and never raises: a rescue that fails must not fail the boot.
    """
    if lane_rescue is None:
        return []
    notices = []
    for lane_id, entry in evicted:
        target = entry.get("worktree")
        if not target:
            # Why (adversarial review of 2.5.0): a registry entry written before `worktree` existed used
            # to fall back to THIS session's project root — so the "rescue of the dead lane" was a copy of
            # the LIVE session's dirty tree, mislabelled. In the common layout (lanes in one directory)
            # that happened at every eviction. No recorded worktree means nothing to rescue, and saying
            # so is more honest than rescuing the wrong thing.
            notices.append(f"lane {lane_id}: evicted without rescue (no worktree recorded — registered before 1.3.0)")
            continue
        try:
            ok, info = lane_rescue.capture(lane_id, target)
        except Exception:  # noqa: BLE001 -- Why: a rescue that cannot be captured (binary git missing,
            # worktree already gone, patch too large) must not stop the eviction loop nor the boot; the
            # loss is one lane's uncommitted work, and additionalContext says so.
            continue
        if ok and isinstance(info, dict) and not info.get("empty"):
            notices.append(f"lane {lane_id} was evicted (dead) with uncommitted work — rescue patch: "
                           f"{Path(info['patch']).name} · reapply with `lane_rescue.py reapply "
                           f"{Path(info['patch']).name}`")
    return notices


def _resolve_identity(payload: dict) -> tuple:
    lane_id = os.environ.get("CLAUDE_LANE_ID") or payload.get("lane_id") or "solo"
    role = os.environ.get("CLAUDE_LANE_ROLE") or payload.get("role") or "adhoc"
    model = os.environ.get("CLAUDE_LANE_MODEL") or payload.get("model") or "unknown"
    return lane_id, role, model


# Why: the routing line used to be matched as a SUBSTRING (`"## Para: <id>" in text`), so a message for
# `exec-bb` also reached `exec-b`, and it was Portuguese in an English-canonical product. The line is now
# matched whole (`^...$` per line), the lane id bounded by the end of the line; `Para` stays accepted
# because mailboxes already in the wild carry it.
_ROUTING_LINE = re.compile(r"^##\s*(?:To|Para):\s*(\S+)\s*$")
_ANNOUNCED_DIR = ".announced"
_ARCHIVE_DIR = "_read"


def _addressed_to(text: str, lane_id: str) -> bool:
    """True when a routing line of `text` names exactly `lane_id` (one lane id per line)."""
    for line in text.splitlines():
        match = _ROUTING_LINE.match(line)
        if match and match.group(1) == lane_id:
            return True
    return False


def _mailbox_dir(cfg: dict) -> Path:
    return _lane_io._PROJECT_ROOT / _lane_io.get(cfg, "mailbox.dir", ".claude/lanes/mailbox")


def _scan_mailbox(lane_id: str, cfg: dict) -> list:
    """Every message at the top level of the mailbox addressed to `lane_id`, in name order.

    Only `*.md` directly under the mailbox counts: `_read/` (archived) and `.announced/` (the
    per-lane record of what was already announced) are subdirectories and are never scanned.
    """
    mailbox_dir = _mailbox_dir(cfg)
    if not mailbox_dir.is_dir():
        return []
    unread = []
    for f in sorted(mailbox_dir.glob("*.md")):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _addressed_to(text, lane_id):
            unread.append(f)
    return unread


def _relative(path: Path) -> str:
    try:
        return path.relative_to(_lane_io._PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _mailbox_notice(lane_id: str, files: list, kind: str) -> str:
    paths = ", ".join(_relative(p) for p in files)
    return (f"{len(files)} {kind} mailbox message(s) for lane {lane_id}: {paths} — read them and archive in "
            f"mailbox/{_ARCHIVE_DIR}/")


# --- the announced-set: what this lane was already told, so a heartbeat never repeats it -------------
# Why: the heartbeat fires on every tool call; without a durable record of what was announced the
# lane would hear the same message on every beat, or never (if the record lived in the process).
# It sits beside the mailbox (runtime state, same .gitignore line), one small file per lane, keyed
# by file name + content digest so a re-used name with new content is announced again.
# Why (MAIL-ANNOUNCE-RACE): a host runs the PostToolUse hook once per tool call, and parallel tool calls
# of ONE session run it concurrently. Query ("not yet announced") and mark ("announced") were two steps
# with nothing between them, so two beats both found a message fresh and both announced it -- and both
# wrote the set through the SAME temp file name, so one write could lose the other's or fail on it.
# Now the read-modify-write holds a per-lane lock, and every write has a temp file of its own.

_ANNOUNCED_LOCK_TIMEOUT_SECONDS = 2.0
_ANNOUNCED_LOCK_STALE_SECONDS = 60.0


class _AnnouncedLock:
    """A per-lane mkdir lock beside the announced-set, held across query and mark. A holder that died
    leaves a directory; it is broken after _ANNOUNCED_LOCK_STALE_SECONDS, since a scan takes milliseconds.
    Raises _lane_io.LockError when it cannot be taken in time: the caller fails open (the next beat tells)."""

    def __init__(self, announced_path: Path) -> None:
        self.path = announced_path.with_name(announced_path.name + ".lock")
        self._held = False

    def __enter__(self) -> "_AnnouncedLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + _ANNOUNCED_LOCK_TIMEOUT_SECONDS
        while True:
            try:
                os.mkdir(self.path)
                self._held = True
                return self
            # Why: on Windows a lock directory another writer is removing stays "delete pending" for an
            # instant, and mkdir on it answers access denied, not "exists". That is a busy lock, as in
            # lane_board._Lock: letting it escape crashed the caller.
            except (FileExistsError, PermissionError) as exc:
                last = exc
                try:
                    if time.time() - self.path.stat().st_mtime > _ANNOUNCED_LOCK_STALE_SECONDS:
                        os.rmdir(self.path)
                        continue
                except OSError:
                    pass
                if time.monotonic() > deadline:
                    reason = f" (last answer: {last})" if isinstance(last, PermissionError) else ""
                    raise _lane_io.LockError(f"announced-set lock not acquired within "
                                             f"{_ANNOUNCED_LOCK_TIMEOUT_SECONDS}s: {self.path}{reason}") from None
                time.sleep(0.01)

    def __exit__(self, *exc) -> None:
        if self._held:
            try:
                os.rmdir(self.path)
            except OSError:
                pass


def _announced_path(lane_id: str, mailbox_dir: Path) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", lane_id) or "lane"
    return mailbox_dir / _ANNOUNCED_DIR / f"{safe}.json"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _load_announced(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}  # absent or corrupt: rebuilt from the next announcement, never fatal
    announced = data.get("announced") if isinstance(data, dict) else None
    return dict(announced) if isinstance(announced, dict) else {}


REPLACE_RETRY_SECONDS = 3.0


def _replace(source, target) -> None:
    """os.replace, retried on Windows while a reader holds the target.

    Why (WIN-REPLACE-READER): on Windows a file open for reading cannot be replaced; os.replace fails
    with PermissionError (WinError 5) until the reader closes it. The Lane Dashboard polls the records
    the supervisor and the hooks rewrite, and a supervisor that met it died with its agent running,
    unbounded. A reader holds a record for milliseconds; past REPLACE_RETRY_SECONDS the error is
    raised as before."""
    deadline = time.monotonic() + REPLACE_RETRY_SECONDS
    while True:
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if os.name != "nt" or time.monotonic() >= deadline:
                raise
            time.sleep(0.02)


def _save_announced(path: Path, announced: dict, mailbox_dir: Path) -> None:
    live = {f.name for f in mailbox_dir.glob("*.md")}
    kept = {name: digest for name, digest in announced.items() if name in live}  # archived = forgotten
    path.parent.mkdir(parents=True, exist_ok=True)
    # a temp file of this writer's own, in the same directory, then one rename: never a fixed name
    handle, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(json.dumps({"schema_version": "1.0", "announced": kept}, ensure_ascii=False,
                                    indent=2).encode("utf-8"))
        _replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _not_yet_announced(lane_id: str, mailbox_dir: Path, files: list) -> list:
    announced = _load_announced(_announced_path(lane_id, mailbox_dir))
    fresh = []
    for f in files:
        try:
            if announced.get(f.name) != _digest(f):
                fresh.append(f)
        except OSError:
            continue
    return fresh


def _mark_announced(lane_id: str, mailbox_dir: Path, files: list) -> None:
    if not files:
        return
    path = _announced_path(lane_id, mailbox_dir)
    announced = _load_announced(path)
    for f in files:
        try:
            announced[f.name] = _digest(f)
        except OSError:
            continue
    _save_announced(path, announced, mailbox_dir)


def handle_register(payload: dict) -> dict:
    lane_id, role, model = _resolve_identity(payload)
    evicted: list = []
    ok, entry_or_msg = _lane_io.register(lane_id, role, payload.get("session_id", ""), model,
                                          _git_branch(), worktree=_git_worktree(), evicted_out=evicted)

    parts = []
    if not ok:
        return {}  # lock contention: silent fail-open, not worth warning at boot

    parts.extend(_rescue_evicted(evicted))

    others = _lane_io.alive_others(lane_id)
    if others:
        others_str = ", ".join(f"{lid} ({_lane_io.age_str(e)})" for lid, e, _ in others)
        parts.append(f"lane {lane_id} registered (role={role}) · {len(others)} other live lane(s): {others_str}")
    else:
        parts.append(f"lane {lane_id} registered (role={role})")

    cfg = _lane_io.load_config()
    if _lane_io.get(cfg, "mailbox.check_on_register", True):
        unread = _scan_mailbox(lane_id, cfg)
        if unread:
            parts.append(_mailbox_notice(lane_id, unread, "unread"))
            try:
                mailbox_dir = _mailbox_dir(cfg)
                with _AnnouncedLock(_announced_path(lane_id, mailbox_dir)):
                    _mark_announced(lane_id, mailbox_dir, unread)
            except Exception:  # noqa: BLE001 -- Why: the announced-set only stops the heartbeat from
                # repeating what the register just said; failing to write it costs one repeated notice,
                # and the boot that registers the lane must never be the thing that fails.
                pass

    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": " · ".join(parts)}}


def _announce_new_mail(lane_id: str) -> dict:
    """The heartbeat's half of the mailbox: announce what arrived since the lane was last told, once."""
    cfg = _lane_io.load_config()
    if not _lane_io.get(cfg, "mailbox.check_on_heartbeat", True):
        return {}
    mailbox_dir = _mailbox_dir(cfg)
    files = _scan_mailbox(lane_id, cfg)
    if not files:
        return {}  # nothing addressed to this lane: no lock, and nothing written (no mailbox, no directory)
    # query and mark under ONE per-lane lock: two beats of the same lane never announce a message twice
    with _AnnouncedLock(_announced_path(lane_id, mailbox_dir)):
        fresh = _not_yet_announced(lane_id, mailbox_dir, files)
        if not fresh:
            return {}
        _mark_announced(lane_id, mailbox_dir, fresh)
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                   "additionalContext": _mailbox_notice(lane_id, fresh, "new")}}


def handle_heartbeat(payload: dict) -> dict:
    lane_id, _role, _model = _resolve_identity(payload)
    ok, outcome = _lane_io.heartbeat(lane_id, payload.get("session_id", ""))
    # Why: the heartbeat throttle is what keeps this hook cheap on every tool call. The mailbox is read
    # only on a beat that actually landed — a throttled beat (or one that lost the lock) scans nothing,
    # so a message is announced on the first beat that lands after it, never on every call.
    if not ok or outcome != "heartbeat":
        return {}
    try:
        return _announce_new_mail(lane_id)
    except Exception:  # noqa: BLE001 -- Why: the heartbeat already landed; an unreadable mailbox, a
        # corrupt announced-set or a full disk must not turn a PostToolUse hook into a failed tool
        # call. The lane is told at the next beat, or at the next register.
        return {}


def main(argv) -> int:
    if argv and argv[0] in ("--self-test", "-t"):
        return _self_test()

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:  # noqa: BLE001
        payload = {}

    try:
        if argv and argv[0] == "--heartbeat":
            result = handle_heartbeat(payload)
        else:
            result = handle_register(payload)
    except Exception:  # noqa: BLE001 -- total fail-open, never brings down the boot/tool-call
        result = {}

    print(json.dumps(result, ensure_ascii=False))
    return 0


def _self_test() -> int:
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="lane_register_selftest_"))
    orig = (_lane_io._PROJECT_ROOT, _lane_io._LANES_DIR, _lane_io.REGISTRY_PATH, _lane_io.CONFIG_PATH)
    try:
        _lane_io._PROJECT_ROOT = tmp
        _lane_io._LANES_DIR = tmp / ".claude" / "lanes"
        _lane_io.REGISTRY_PATH = _lane_io._LANES_DIR / "registry.json"
        _lane_io.CONFIG_PATH = _lane_io._LANES_DIR / "lanes.yaml"

        os.environ["CLAUDE_LANE_ID"] = "exec-a"
        os.environ["CLAUDE_LANE_ROLE"] = "executor"
        os.environ["CLAUDE_LANE_MODEL"] = "claude-opus-5-5"
        try:
            # 1. register creates the entry + additionalContext with the correct hookEventName
            out1 = handle_register({"session_id": "s1"})
            assert out1["hookSpecificOutput"]["hookEventName"] == "SessionStart"
            assert "exec-a" in out1["hookSpecificOutput"]["additionalContext"]

            # 2. re-register preserves started_at
            reg_before = _lane_io._read_registry()
            started_before = reg_before["lanes"]["exec-a"]["started_at"]
            handle_register({"session_id": "s1"})
            reg_after = _lane_io._read_registry()
            assert reg_after["lanes"]["exec-a"]["started_at"] == started_before, "re-register should not change started_at"

            # 3. a dead lane disappears after register
            from datetime import datetime, timezone
            dead_ts = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - 35 * 60, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            reg = _lane_io._read_registry()
            reg["lanes"]["exec-old"] = {"role": "executor", "session_id": "x", "model": "y", "branch": "",
                                          "started_at": dead_ts, "heartbeat_at": dead_ts,
                                          "territory": {"paths": [], "exclusive": []}, "status": "active"}
            _lane_io._write_registry(reg)
            handle_register({"session_id": "s1"})
            reg2 = _lane_io._read_registry()
            assert "exec-old" not in reg2["lanes"]

            # 4. heartbeat advances heartbeat_at -- measured with a controlled clock, strictly: `after >=
            #    before` after a 0.05 s sleep accepted an unchanged 1-second timestamp (TEST-HEARTBEAT-VACUOUS)
            from datetime import timedelta
            hb_before = _lane_io._read_registry()["lanes"]["exec-a"]["heartbeat_at"]
            orig_now = _lane_io._now
            later = _lane_io._parse_ts(hb_before) + timedelta(seconds=90)
            _lane_io._now = lambda: later
            try:
                handle_heartbeat({"session_id": "s1"})
            finally:
                _lane_io._now = orig_now
            hb_after = _lane_io._read_registry()["lanes"]["exec-a"]["heartbeat_at"]
            assert hb_after == later.strftime("%Y-%m-%dT%H:%M:%S") and hb_after > hb_before, (hb_before, hb_after)

            # 5. mailbox at register: `## To:` routes, the legacy `## Para:` still routes, and the lane id is
            #    bounded — exec-bb's message never reaches exec-b (nor the other way round)
            def ctx(out: dict) -> str:
                return out.get("hookSpecificOutput", {}).get("additionalContext", "")

            mailbox = _lane_io._LANES_DIR / "mailbox"
            mailbox.mkdir(parents=True)
            (mailbox / "to.md").write_text("## To: exec-b\n## From: exec-a (executor)\n", encoding="utf-8")
            (mailbox / "para.md").write_text("## Para: exec-b\n## De: exec-a (executor)\n", encoding="utf-8")
            (mailbox / "for-bb.md").write_text("## To: exec-bb\n## From: exec-a (executor)\n", encoding="utf-8")
            os.environ["CLAUDE_LANE_ID"] = "exec-b"
            out5 = ctx(handle_register({"session_id": "s2"}))
            assert "to.md" in out5, f"`## To:` must route: {out5}"
            assert "para.md" in out5, f"the legacy `## Para:` must still route: {out5}"
            assert "for-bb" not in out5, f"exec-bb's message routed to exec-b (substring match): {out5}"
            os.environ["CLAUDE_LANE_ID"] = "exec-bb"
            out5bb = ctx(handle_register({"session_id": "s3"}))
            assert "for-bb.md" in out5bb and "to.md" not in out5bb and "para.md" not in out5bb, out5bb
            os.environ["CLAUDE_LANE_ID"] = "exec-b"
            (mailbox / "_read").mkdir()
            for name in ("to.md", "para.md", "for-bb.md"):
                (mailbox / name).rename(mailbox / "_read" / name)
            out5b = ctx(handle_register({"session_id": "s2"}))
            assert "mailbox" not in out5b, f"archived messages must be silent at register: {out5b}"

            # 6. heartbeat: a message that arrives mid-session is announced ONCE, as PostToolUse context;
            #    the next beats are silent; an archived message is silent; a throttled beat does not scan
            orig_load_config = _lane_io.load_config
            _lane_io.load_config = lambda: {"liveness": {"heartbeat_throttle_seconds": 0}}
            try:
                (mailbox / "late.md").write_text("## To: exec-b\n## From: coord (planner)\n", encoding="utf-8")
                hb1 = handle_heartbeat({"session_id": "s2"})
                assert hb1.get("hookSpecificOutput", {}).get("hookEventName") == "PostToolUse", hb1
                assert "late.md" in ctx(hb1), f"the heartbeat must announce the new message: {hb1}"
                assert handle_heartbeat({"session_id": "s2"}) == {}, "the second heartbeat repeated the message"
                (mailbox / "late.md").rename(mailbox / "_read" / "late.md")
                (mailbox / "_read" / "older.md").write_text("## To: exec-b\n", encoding="utf-8")
                assert handle_heartbeat({"session_id": "s2"}) == {}, "an archived message was announced"
                (mailbox / "second.md").write_text("## To: exec-b\n", encoding="utf-8")
                assert "second.md" in ctx(handle_heartbeat({"session_id": "s2"})), "a later message must be announced too"
                assert handle_heartbeat({"session_id": "s2"}) == {}

                # 7. what the register announced is not repeated by the heartbeat
                (mailbox / "early.md").write_text("## To: exec-b\n", encoding="utf-8")
                assert "early.md" in ctx(handle_register({"session_id": "s2"}))
                assert handle_heartbeat({"session_id": "s2"}) == {}, "the heartbeat repeated what the register said"

                # 8. the throttle is honoured: a throttled beat announces nothing, the next landing beat does
                _lane_io.load_config = lambda: {"liveness": {"heartbeat_throttle_seconds": 3600}}
                (mailbox / "throttled.md").write_text("## To: exec-b\n", encoding="utf-8")
                assert handle_heartbeat({"session_id": "s2"}) == {}, "a throttled heartbeat scanned the mailbox"
                _lane_io.load_config = lambda: {"liveness": {"heartbeat_throttle_seconds": 0}}
                assert "throttled.md" in ctx(handle_heartbeat({"session_id": "s2"}))

                # 9. fail-open: a scan that raises leaves the heartbeat landed, `{}` on stdout, exit 0
                import contextlib as _contextlib
                import io as _io
                orig_scan = globals()["_scan_mailbox"]

                def _boom(*_a, **_k):
                    raise RuntimeError("the mailbox exploded")

                globals()["_scan_mailbox"] = _boom
                try:
                    (mailbox / "unseen.md").write_text("## To: exec-b\n", encoding="utf-8")
                    hb_before = _lane_io._read_registry()["lanes"]["exec-b"]["heartbeat_at"]
                    # the same controlled clock as step 4: the beat must land, strictly newer, scan or no scan
                    later9 = _lane_io._parse_ts(hb_before) + timedelta(seconds=90)
                    orig_now9, _lane_io._now = _lane_io._now, (lambda: later9)
                    try:
                        assert handle_heartbeat({"session_id": "s2"}) == {}, "a failing scan reached the caller"
                    finally:
                        _lane_io._now = orig_now9
                    assert _lane_io._read_registry()["lanes"]["exec-b"]["heartbeat_at"] == later9.strftime("%Y-%m-%dT%H:%M:%S"), \
                        "the heartbeat did not land when the scan failed"
                    out, err = _io.StringIO(), _io.StringIO()
                    old_stdin = sys.stdin
                    sys.stdin = _io.StringIO('{"session_id": "s2"}')
                    try:
                        with _contextlib.redirect_stdout(out), _contextlib.redirect_stderr(err):
                            rc = main(["--heartbeat"])
                    finally:
                        sys.stdin = old_stdin
                    assert rc == 0 and out.getvalue().strip() == "{}" and "Traceback" not in err.getvalue(), \
                        (rc, out.getvalue(), err.getvalue())
                finally:
                    globals()["_scan_mailbox"] = orig_scan
                assert "unseen.md" in ctx(handle_heartbeat({"session_id": "s2"})), "once the scan works again the lane is told"
            finally:
                _lane_io.load_config = orig_load_config

            # 10. garbage stdin/payload -> {} , exit 0 (via main())
            import io as _io
            old_stdin = sys.stdin
            sys.stdin = _io.StringIO("isto nao e json")
            rc = main([])
            sys.stdin = old_stdin
            assert rc == 0

            print("self-test OK — register creates context+keeps started_at+evicts dead, "
                  "heartbeat advances+throttle no-op, mailbox: `## To:` routes and the legacy `## Para:` still "
                  "routes, exec-bb's mail never reaches exec-b, archived is silent, the heartbeat announces a "
                  "mid-session message once (PostToolUse context) and repeats nothing the register said, a "
                  "throttled beat does not scan, a failing scan fails open; garbage stdin = {} exit 0")
            return 0
        finally:
            os.environ.pop("CLAUDE_LANE_ID", None)
            os.environ.pop("CLAUDE_LANE_ROLE", None)
            os.environ.pop("CLAUDE_LANE_MODEL", None)
    finally:
        _lane_io._PROJECT_ROOT, _lane_io._LANES_DIR, _lane_io.REGISTRY_PATH, _lane_io.CONFIG_PATH = orig
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
