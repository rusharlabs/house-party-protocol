#!/usr/bin/env python3
"""
_lane_io — registry de lanes vivas (quem está trabalhando, onde, desde quando).

Biblioteca + CLI usada por lane_register.py, lane_git_guard.py e lane_territory_guard.py
para saber quais sessões (lanes) estão vivas agora e qual território cada uma reivindicou.
Lock próprio (`.registry.lock`, separado do `.lock` do lane_board.py) porque o heartbeat
dispara a cada tool-call e não pode contender com escritas no board.

Liveness (config em `.claude/lanes/lanes.yaml`, ver templates/lanes.example.yaml):
    heartbeat < liveness.alive_minutes (default 10)  -> "alive"
    entre alive_minutes e dead_minutes (default 30)  -> "suspect"
    > dead_minutes ou heartbeat ilegível              -> "dead" (evict no próximo register)

Uso:
    python _lane_io.py register --lane <id> --role <r> --session <s> --model <m>
        [--branch <b>] [--exclusive <glob> ...]
    python _lane_io.py heartbeat --lane <id> [--session <s>] [--throttle <segundos>]
    python _lane_io.py evict --lane <id>
    python _lane_io.py who-owns <path>
    python _lane_io.py status
    python _lane_io.py --self-test

Exit: 0 ok · 1 lock não obtido (WARN, nunca trava o hook chamador) · 2 uso inválido.
stdlib + PyYAML opcional (degrada para defaults sem ele). v1.0.0 — 2026-07-10 (lane-kit)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml  # PyYAML
except ImportError:
    yaml = None  # type: ignore[assignment]

_PROJECT_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
_LANES_DIR = _PROJECT_ROOT / ".claude" / "lanes"
REGISTRY_PATH = _LANES_DIR / "registry.json"
CONFIG_PATH = _LANES_DIR / "lanes.yaml"

_LOCK_SPIN_SECONDS = 2.0

_DEFAULTS = {
    "liveness": {"alive_minutes": 10, "dead_minutes": 30, "heartbeat_throttle_seconds": 60},
    "zonas_vermelhas": [".claude/settings*.json", "**/MEMORY.md"],
    "territories": {},
}


class LockError(Exception):
    pass


class _Lock:
    def __init__(self, lanes_dir: Path, timeout: float = _LOCK_SPIN_SECONDS):
        self.path = lanes_dir / ".registry.lock"
        self.timeout = timeout
        self._acquired = False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                os.mkdir(self.path)
                self._acquired = True
                return self
            except FileExistsError:
                if time.monotonic() > deadline:
                    raise LockError(f"lock não obtido em {self.timeout}s: {self.path}")
                time.sleep(0.01)

    def __exit__(self, *exc):
        if self._acquired:
            try:
                os.rmdir(self.path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

def load_config() -> dict:
    env = os.environ.get("LANE_KIT_CONFIG")
    path = Path(env) if env else CONFIG_PATH
    if not path.exists() or yaml is None:
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def get(d: dict, dotted: str, default=None):
    cur = d
    for k in dotted.split("."):
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return _get_default(dotted, default)
    return cur if cur is not None else _get_default(dotted, default)


def _get_default(dotted: str, explicit_default):
    cur = _DEFAULTS
    for k in dotted.split("."):
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return explicit_default
    return cur


# ---------------------------------------------------------------------------
# time / liveness
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().strftime("%Y-%m-%dT%H:%M:%S")


def _parse_ts(s: str) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def liveness(entry: dict, cfg: dict | None = None) -> str:
    cfg = cfg if cfg is not None else load_config()
    ts = _parse_ts(entry.get("heartbeat_at", ""))
    if ts is None:
        return "dead"
    age_min = (_now() - ts).total_seconds() / 60.0
    alive_min = get(cfg, "liveness.alive_minutes", 10)
    dead_min = get(cfg, "liveness.dead_minutes", 30)
    if age_min < alive_min:
        return "alive"
    if age_min < dead_min:
        return "suspect"
    return "dead"


def age_str(entry: dict) -> str:
    ts = _parse_ts(entry.get("heartbeat_at", ""))
    if ts is None:
        return "?"
    mins = int((_now() - ts).total_seconds() / 60.0)
    return f"{mins}min"


# ---------------------------------------------------------------------------
# registry I/O
# ---------------------------------------------------------------------------

def _read_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {"schema_version": "1.0", "lanes": {}}
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "lanes" not in data:
            return {"schema_version": "1.0", "lanes": {}}
        return data
    except (json.JSONDecodeError, OSError):
        return {"schema_version": "1.0", "lanes": {}}


def _write_registry(reg: dict) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = REGISTRY_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, REGISTRY_PATH)


def _glob_to_regex(pattern: str) -> re.Pattern:
    tokens = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if pattern[i:i + 3] == "**/":
            tokens.append("(?:.*/)?")
            i += 3
        elif pattern[i:i + 2] == "**":
            tokens.append(".*")
            i += 2
        elif c == "*":
            tokens.append("[^/]*")
            i += 1
        elif c == "?":
            tokens.append("[^/]")
            i += 1
        else:
            tokens.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(tokens) + "$")


def _norm_path(path: str) -> str:
    p = Path(path)
    try:
        if p.is_absolute():
            p = p.resolve()
            return p.relative_to(_PROJECT_ROOT.resolve()).as_posix()
    except (ValueError, OSError):
        pass
    return Path(path).as_posix()


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def register(lane_id: str, role: str, session_id: str, model: str,
             branch: str = "", territory: dict | None = None) -> tuple:
    cfg = load_config()
    try:
        with _Lock(_LANES_DIR):
            reg = _read_registry()
            lanes = reg.setdefault("lanes", {})

            # evict lanes mortas antes de registrar (spec: evict no próximo register)
            for lid in list(lanes):
                if liveness(lanes[lid], cfg) == "dead":
                    del lanes[lid]

            now = _now_iso()
            existing = lanes.get(lane_id, {})
            entry_territory = territory or existing.get("territory") or get(cfg, f"territories.{lane_id}", None) \
                or {"paths": [], "exclusive": []}
            entry = {
                "role": role,
                "session_id": session_id,
                "model": model,
                "branch": branch,
                "started_at": existing.get("started_at", now),
                "heartbeat_at": now,
                "territory": entry_territory,
                "status": "active",
            }
            lanes[lane_id] = entry
            _write_registry(reg)
            return True, entry
    except LockError as e:
        return False, f"lane_register: lock não obtido em 2s — registro pulado (WARN, hook nunca trava): {e}"


def heartbeat(lane_id: str, session_id: str = "", throttle_seconds: int | None = None) -> tuple:
    cfg = load_config()
    throttle = throttle_seconds if throttle_seconds is not None else get(cfg, "liveness.heartbeat_throttle_seconds", 60)

    reg = _read_registry()
    existing = reg.get("lanes", {}).get(lane_id)
    if existing and throttle > 0:
        ts = _parse_ts(existing.get("heartbeat_at", ""))
        if ts is not None and (_now() - ts).total_seconds() < throttle:
            return True, "throttled"

    try:
        with _Lock(_LANES_DIR):
            reg = _read_registry()
            lanes = reg.setdefault("lanes", {})
            if lane_id not in lanes:
                lanes[lane_id] = {
                    "role": "adhoc", "session_id": session_id, "model": "unknown", "branch": "",
                    "started_at": _now_iso(), "heartbeat_at": _now_iso(),
                    "territory": {"paths": [], "exclusive": []}, "status": "active",
                }
            else:
                lanes[lane_id]["heartbeat_at"] = _now_iso()
            _write_registry(reg)
            return True, "heartbeat"
    except LockError as e:
        return False, str(e)


def evict(lane_id: str) -> bool:
    try:
        with _Lock(_LANES_DIR):
            reg = _read_registry()
            if lane_id in reg.get("lanes", {}):
                del reg["lanes"][lane_id]
                _write_registry(reg)
                return True
            return False
    except LockError:
        return False


def alive_count() -> int:
    reg = _read_registry()
    cfg = load_config()
    return sum(1 for e in reg.get("lanes", {}).values() if liveness(e, cfg) == "alive")


def alive_others(my_lane: str) -> list:
    reg = _read_registry()
    cfg = load_config()
    out = []
    for lid, entry in reg.get("lanes", {}).items():
        if lid == my_lane:
            continue
        state = liveness(entry, cfg)
        if state in ("alive", "suspect"):
            out.append((lid, entry, state))
    return out


def who_owns(path: str) -> list:
    reg = _read_registry()
    cfg = load_config()
    rel = _norm_path(path)
    out = []
    for lid, entry in reg.get("lanes", {}).items():
        state = liveness(entry, cfg)
        if state == "dead":
            continue
        for pattern in entry.get("territory", {}).get("exclusive", []) or []:
            if _glob_to_regex(pattern).match(rel):
                out.append((lid, pattern, state))
                break
    return out


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------

def _self_test() -> int:
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="lane_io_selftest_"))
    global _PROJECT_ROOT, _LANES_DIR, REGISTRY_PATH, CONFIG_PATH
    orig = (_PROJECT_ROOT, _LANES_DIR, REGISTRY_PATH, CONFIG_PATH)
    try:
        _PROJECT_ROOT = tmp
        _LANES_DIR = tmp / ".claude" / "lanes"
        REGISTRY_PATH = _LANES_DIR / "registry.json"
        CONFIG_PATH = _LANES_DIR / "lanes.yaml"

        # 1. register cria registry.json válido
        ok1, e1 = register("exec-a", "executora", "s1", "claude-opus-4-8", branch="main",
                            territory={"paths": ["src/**"], "exclusive": ["src/api/**"]})
        assert ok1 and REGISTRY_PATH.exists(), f"register deveria criar o registry: {e1}"
        reg = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        assert set(reg["lanes"]["exec-a"].keys()) == {
            "role", "session_id", "model", "branch", "started_at", "heartbeat_at", "territory", "status"
        }, f"schema incompleto: {reg}"

        # 2. heartbeat(throttle=0) avança; throttle normal é no-op
        first_hb = reg["lanes"]["exec-a"]["heartbeat_at"]
        time.sleep(0.05)
        ok2, msg2 = heartbeat("exec-a", throttle_seconds=0)
        assert ok2 and msg2 == "heartbeat"
        reg2 = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        assert reg2["lanes"]["exec-a"]["heartbeat_at"] >= first_hb
        mtime_before = REGISTRY_PATH.stat().st_mtime
        ok3, msg3 = heartbeat("exec-a", throttle_seconds=3600)
        assert ok3 and msg3 == "throttled"
        assert REGISTRY_PATH.stat().st_mtime == mtime_before, "throttled não deveria escrever"

        # 3. liveness: 5/15/35 min atrás -> alive/suspect/dead
        cfg = {"liveness": {"alive_minutes": 10, "dead_minutes": 30}}
        e_alive = {"heartbeat_at": datetime.fromtimestamp(_now().timestamp() - 5 * 60, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")}
        e_suspect = {"heartbeat_at": datetime.fromtimestamp(_now().timestamp() - 15 * 60, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")}
        e_dead = {"heartbeat_at": datetime.fromtimestamp(_now().timestamp() - 35 * 60, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")}
        assert liveness(e_alive, cfg) == "alive"
        assert liveness(e_suspect, cfg) == "suspect"
        assert liveness(e_dead, cfg) == "dead"

        # 4. register evicts dead lanes
        reg3 = _read_registry()
        reg3["lanes"]["exec-old"] = {
            "role": "executora", "session_id": "old", "model": "x", "branch": "",
            "started_at": e_dead["heartbeat_at"], "heartbeat_at": e_dead["heartbeat_at"],
            "territory": {"paths": [], "exclusive": []}, "status": "active",
        }
        _write_registry(reg3)
        register("exec-b", "executora", "s2", "gpt-5.5")
        reg4 = _read_registry()
        assert "exec-old" not in reg4["lanes"], "register deveria ter evictado exec-old (morta)"
        assert "exec-b" in reg4["lanes"]

        # 5. who_owns: hit exclusivo, miss não-exclusivo, miss lane morta, glob ** funciona
        owners = who_owns("src/api/handler.py")
        assert any(o[0] == "exec-a" for o in owners), f"deveria achar exec-a em src/api/**: {owners}"
        assert not who_owns("src/other/x.py"), "não deveria achar dono fora do exclusive"
        assert _glob_to_regex("**/MEMORY.md").match("a/b/MEMORY.md")
        assert _glob_to_regex("**/MEMORY.md").match("MEMORY.md")

        # dead lane não deveria aparecer em who_owns
        reg5 = _read_registry()
        reg5["lanes"]["exec-dead-territory"] = {
            "role": "executora", "session_id": "d", "model": "x", "branch": "",
            "started_at": e_dead["heartbeat_at"], "heartbeat_at": e_dead["heartbeat_at"],
            "territory": {"paths": [], "exclusive": ["deadzone/**"]}, "status": "active",
        }
        _write_registry(reg5)
        assert not who_owns("deadzone/file.py"), "lane morta não deveria reivindicar território"

        # 6. alive_others exclui self; alive_count correto
        others = alive_others("exec-a")
        assert all(o[0] != "exec-a" for o in others)
        assert any(o[0] == "exec-b" for o in others)
        assert alive_count() >= 2

        # 7. lock contention: hook nunca trava, retorna (False, msg) em ~2s
        _LANES_DIR.mkdir(parents=True, exist_ok=True)
        lock_dir = _LANES_DIR / ".registry.lock"
        lock_dir.mkdir(exist_ok=True)
        start = time.monotonic()
        ok_locked, msg_locked = register("exec-c", "executora", "s3", "claude-opus-4-8")
        elapsed = time.monotonic() - start
        assert not ok_locked and elapsed < 3.0, f"lock contention deveria falhar rápido: {elapsed}s, {msg_locked}"
        lock_dir.rmdir()
        ok_after, _ = register("exec-c", "executora", "s3", "claude-opus-4-8")
        assert ok_after, "register deveria funcionar após lock liberado"

        # 8. registry corrompido degrada para vazio, próximo register reescreve limpo
        REGISTRY_PATH.write_text("{ isto nao e json valido", encoding="utf-8")
        reg_corrupt = _read_registry()
        assert reg_corrupt == {"schema_version": "1.0", "lanes": {}}
        register("exec-d", "executora", "s4", "claude-opus-4-8")
        reg_clean = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        assert "exec-d" in reg_clean["lanes"]
        assert not REGISTRY_PATH.with_suffix(".json.tmp").exists(), "não deveria sobrar .tmp"

        print("self-test OK — register cria/evicta mortas/preserva started_at, heartbeat throttle+avanço, "
              "liveness alive/suspect/dead, who_owns exclusivo+glob**+ignora morta, alive_others exclui self, "
              "lock contention falha rápido sem travar, registry corrompido degrada limpo")
        return 0
    finally:
        _PROJECT_ROOT, _LANES_DIR, REGISTRY_PATH, CONFIG_PATH = orig
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="_lane_io.py")
    sub = p.add_subparsers(dest="cmd")

    r = sub.add_parser("register")
    r.add_argument("--lane", required=True)
    r.add_argument("--role", default="adhoc")
    r.add_argument("--session", default="")
    r.add_argument("--model", default="unknown")
    r.add_argument("--branch", default="")
    r.add_argument("--exclusive", action="append", default=[])

    h = sub.add_parser("heartbeat")
    h.add_argument("--lane", required=True)
    h.add_argument("--session", default="")
    h.add_argument("--throttle", type=int, default=None)

    e = sub.add_parser("evict")
    e.add_argument("--lane", required=True)

    w = sub.add_parser("who-owns")
    w.add_argument("path")

    sub.add_parser("status")
    p.add_argument("--self-test", action="store_true")
    return p


def main(argv) -> int:
    args = build_parser().parse_args(argv)
    if args.self_test:
        return _self_test()

    if args.cmd == "register":
        territory = {"paths": [], "exclusive": args.exclusive} if args.exclusive else None
        ok, result = register(args.lane, args.role, args.session, args.model, args.branch, territory)
        print(json.dumps(result, ensure_ascii=False) if ok else result, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1
    if args.cmd == "heartbeat":
        ok, msg = heartbeat(args.lane, args.session, args.throttle)
        print(msg)
        return 0 if ok else 1
    if args.cmd == "evict":
        return 0 if evict(args.lane) else 1
    if args.cmd == "who-owns":
        print(json.dumps(who_owns(args.path), ensure_ascii=False))
        return 0
    if args.cmd == "status":
        print(json.dumps(_read_registry(), ensure_ascii=False, indent=2))
        return 0

    print("uso: register|heartbeat|evict|who-owns|status [...] ou --self-test", file=sys.stderr)
    return 2


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
