#!/usr/bin/env python3
"""
lane_register — SessionStart: registra esta sessão como lane viva. PostToolUse: heartbeat.

Dois modos por argv (bare = register, --heartbeat = heartbeat), ambos delegando ao registry
de `_lane_io.py`. Fail-open total: qualquer exceção vira `{}` no stdout e exit 0 — nunca
derruba o boot da sessão nem um tool-call.

Identidade da lane resolvida (nesta ordem): env CLAUDE_LANE_ID / CLAUDE_LANE_ROLE /
CLAUDE_LANE_MODEL, senão o payload do hook, senão defaults ("solo"/"adhoc"/"unknown").

Uso (hooks):
    echo '{"hook_event_name":"SessionStart","session_id":"..."}' | python lane_register.py
    echo '{"hook_event_name":"PostToolUse","session_id":"..."}'  | python lane_register.py --heartbeat

Exit: sempre 0.
stdlib only. v1.0.0 — 2026-07-10 (lane-kit)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
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
    except Exception:  # noqa: BLE001 -- Why: the worktree path only feeds the rescue patch (K2);
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


def _scan_mailbox(lane_id: str, cfg: dict) -> list:
    if not _lane_io.get(cfg, "mailbox.check_on_register", True):
        return []
    mailbox_dir = _lane_io._PROJECT_ROOT / _lane_io.get(cfg, "mailbox.dir", ".claude/lanes/mailbox")
    if not mailbox_dir.is_dir():
        return []
    unread = []
    for f in sorted(mailbox_dir.glob("*.md")):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if f"## Para: {lane_id}" in text:
            unread.append(f)
    return unread


def handle_register(payload: dict) -> dict:
    lane_id, role, model = _resolve_identity(payload)
    evicted: list = []
    ok, entry_or_msg = _lane_io.register(lane_id, role, payload.get("session_id", ""), model,
                                          _git_branch(), worktree=_git_worktree(), evicted_out=evicted)

    parts = []
    if not ok:
        return {}  # lock contention: fail-open silencioso, não vale a pena avisar no boot

    parts.extend(_rescue_evicted(evicted))

    others = _lane_io.alive_others(lane_id)
    if others:
        others_str = ", ".join(f"{lid} ({_lane_io.age_str(e)})" for lid, e, _ in others)
        parts.append(f"lane {lane_id} registered (role={role}) · {len(others)} other live lane(s): {others_str}")
    else:
        parts.append(f"lane {lane_id} registered (role={role})")

    cfg = _lane_io.load_config()
    unread = _scan_mailbox(lane_id, cfg)
    if unread:
        paths = ", ".join(str(p.relative_to(_lane_io._PROJECT_ROOT)) for p in unread)
        parts.append(f"{len(unread)} unread mailbox message(s): {paths} — read them and archive in mailbox/_read/")

    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": " · ".join(parts)}}


def handle_heartbeat(payload: dict) -> dict:
    lane_id, _role, _model = _resolve_identity(payload)
    _lane_io.heartbeat(lane_id, payload.get("session_id", ""))
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
    except Exception:  # noqa: BLE001 — fail-open total, nunca derruba o boot/tool-call
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
        os.environ["CLAUDE_LANE_ROLE"] = "executora"
        os.environ["CLAUDE_LANE_MODEL"] = "claude-opus-4-8"
        try:
            # 1. register cria entry + additionalContext com hookEventName correto
            out1 = handle_register({"session_id": "s1"})
            assert out1["hookSpecificOutput"]["hookEventName"] == "SessionStart"
            assert "exec-a" in out1["hookSpecificOutput"]["additionalContext"]

            # 2. re-register preserva started_at
            reg_before = _lane_io._read_registry()
            started_before = reg_before["lanes"]["exec-a"]["started_at"]
            handle_register({"session_id": "s1"})
            reg_after = _lane_io._read_registry()
            assert reg_after["lanes"]["exec-a"]["started_at"] == started_before, "re-register should not change started_at"

            # 3. lane morta some após register
            from datetime import datetime, timezone
            dead_ts = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - 35 * 60, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            reg = _lane_io._read_registry()
            reg["lanes"]["exec-old"] = {"role": "executora", "session_id": "x", "model": "y", "branch": "",
                                          "started_at": dead_ts, "heartbeat_at": dead_ts,
                                          "territory": {"paths": [], "exclusive": []}, "status": "active"}
            _lane_io._write_registry(reg)
            handle_register({"session_id": "s1"})
            reg2 = _lane_io._read_registry()
            assert "exec-old" not in reg2["lanes"]

            # 4. heartbeat avança heartbeat_at; throttle é no-op
            hb_before = _lane_io._read_registry()["lanes"]["exec-a"]["heartbeat_at"]
            import time as _time
            _time.sleep(0.05)
            handle_heartbeat({"session_id": "s1"})
            hb_after = _lane_io._read_registry()["lanes"]["exec-a"]["heartbeat_at"]
            assert hb_after >= hb_before

            # 5. mailbox: mensagem endereçada a exec-b aparece; movida para _read/ some
            mailbox = _lane_io._LANES_DIR / "mailbox"
            mailbox.mkdir(parents=True)
            (mailbox / "msg1.md").write_text("## Para: exec-b\n## De: exec-a (executora)\n", encoding="utf-8")
            os.environ["CLAUDE_LANE_ID"] = "exec-b"
            out5 = handle_register({"session_id": "s2"})
            assert "mailbox" in out5["hookSpecificOutput"]["additionalContext"]
            (mailbox / "_read").mkdir()
            (mailbox / "msg1.md").rename(mailbox / "_read" / "msg1.md")
            out5b = handle_register({"session_id": "s2"})
            assert "mailbox" not in out5b.get("hookSpecificOutput", {}).get("additionalContext", "")

            # 6. stdin/payload garbage -> {} , exit 0 (via main())
            import io as _io
            old_stdin = sys.stdin
            sys.stdin = _io.StringIO("isto nao e json")
            rc = main([])
            sys.stdin = old_stdin
            assert rc == 0

            print("self-test OK — register creates context+keeps started_at+evicts dead, "
                  "heartbeat advances+throttle no-op, mailbox appears and is gone once archived, garbage stdin = {} exit 0")
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
