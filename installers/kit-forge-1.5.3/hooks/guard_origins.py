#!/usr/bin/env python3
"""
guard_origins -- protects live sources from accidental writes, in 2 modes.

LIBRARY MODE (main mechanism -- used by kit_assembler.py itself):
  sweep(root, files)          -> {relpath: mtime} BEFORE copying
  verify(before, root, files) -> [relpath drifted/vanished] AFTER copying
  Detects whether something in the SOURCE changed during assembly (another session
  editing the same staging while the assembler was reading) -- a supply-chain
  integrity failure, not a permission one. kit_assembler calls sweep() before the
  copy loop and verify() after (and again before the final swap) -- if there is drift, it ABORTS the emission.

--hook MODE (optional -- for agentic extraction/porting sessions):
  PreToolUse hook (stdin JSON -> exit code) that BLOCKS Edit/Write/MultiEdit/
  NotebookEdit and destructive Bash commands that target a path listed in
  `origins` (config/env -- NEVER hardcoded).

Origin config (--hook mode, first one that exists):
  1. --config <file.json or .yaml> with {"origins": ["path/substring", ...]}
  2. env GUARD_ORIGINS="path1,path2" (comma- or newline-separated)
  3. none -> empty list -> hook never blocks (fail-open, documented)

Usage:
    from guard_origins import sweep, verify                          # library mode
    echo '{"tool_name":"Write","tool_input":{...}}' | python guard_origins.py --hook
    python guard_origins.py --self-test

Exit (--hook mode): 0 allowed - 2 blocked (PreToolUse). Library mode does not use an
exit code (returns dict/list for the caller to decide).
stdlib only (+ optional PyYAML only for --config .yaml). v1.0.0 -- 2026-07-10 (kit-forge)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml  # PyYAML -- only for --config *.yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

_DESTRUCTIVE_BASH = re.compile(
    r"(\brm\b|\bmv\b|\bsed\s+-i\b|\btee\b|>>?(?!\d)|\bgit\b[^|]*\b(commit|checkout|reset|clean|rebase|merge|restore)\b)"
)
_WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


# ---------------------------------------------------------------------------
# LIBRARY MODE -- used by kit_assembler.py
# ---------------------------------------------------------------------------

def sweep(root: Path, files: list) -> dict:
    """Snapshot of the mtime (ns) of each file in `files` (paths relative to `root`).
    A file missing at sweep time = None (compared later in verify)."""
    out = {}
    for rel in files:
        p = root / rel
        try:
            out[rel] = p.stat().st_mtime_ns
        except OSError:
            out[rel] = None
    return out


def verify(before: dict, root: Path, files: list) -> list:
    """Returns the list of relpaths whose mtime changed (or that vanished/appeared)
    between the earlier `sweep()` and now. Empty list = source stable during the window."""
    drifted = []
    for rel in files:
        p = root / rel
        try:
            now = p.stat().st_mtime_ns
        except OSError:
            now = None
        if now != before.get(rel):
            drifted.append(rel)
    return drifted


# ---------------------------------------------------------------------------
# --hook MODE -- standalone PreToolUse
# ---------------------------------------------------------------------------

def _norm(s) -> str:
    return str(s or "").replace("\\", "/")


def _hits_origin(path_or_cmd: str, origins: list) -> bool:
    n = _norm(path_or_cmd)
    return any(o in n for o in origins)


def load_origins(config_path: str | None) -> list:
    if config_path:
        p = Path(config_path)
        if p.exists():
            text = p.read_text(encoding="utf-8")
            if p.suffix in (".yaml", ".yml") and yaml is not None:
                data = yaml.safe_load(text) or {}
            else:
                data = json.loads(text) if text.strip() else {}
            origins = data.get("origins") if isinstance(data, dict) else None
            if isinstance(origins, list):
                return [str(o) for o in origins]
    env = os.environ.get("GUARD_ORIGINS", "")
    if env:
        parts = re.split(r"[,\n]", env)
        return [p.strip() for p in parts if p.strip()]
    return []


def decide(payload: dict, origins: list) -> tuple:
    """Returns (exit_code, message). Logic isolated from stdin/exit so it can be tested without a real process."""
    if not origins:
        return 0, ""

    tool = payload.get("tool_name") or ""
    ti = payload.get("tool_input") or {}

    if tool in _WRITE_TOOLS:
        file_path = ti.get("file_path")
        if file_path and _hits_origin(file_path, origins):
            return 2, f"[guard_origins] BLOCKED — write to a live source: {file_path}. Use Read/Grep/Glob, or write to the destination repo."
        return 0, ""

    if tool == "Bash":
        command = ti.get("command") or ""
        if _DESTRUCTIVE_BASH.search(_norm(command)) and _hits_origin(command, origins):
            return 2, "[guard_origins] BLOCKED — potentially destructive command against a live source."
        return 0, ""

    return 0, ""


def main(argv) -> int:
    p = argparse.ArgumentParser(prog="guard_origins.py")
    p.add_argument("--hook", action="store_true")
    p.add_argument("--config", default=None)
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args(argv)

    if args.self_test:
        return _self_test()

    if not args.hook:
        print("usage: guard_origins.py --hook [--config origins.json]  (or import sweep/verify)", file=sys.stderr)
        return 3

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return 0  # a malformed payload never blocks -- fail-safe

    origins = load_origins(args.config)
    code, message = decide(payload, origins)
    if message:
        print(message, file=sys.stderr if code == 2 else sys.stdout)
    return code


def _self_test() -> int:
    import shutil
    import tempfile
    import time

    # --- library mode ---
    tmp = Path(tempfile.mkdtemp(prefix="guard_origins_selftest_"))
    try:
        (tmp / "a.txt").write_text("A", encoding="utf-8")
        (tmp / "b.txt").write_text("B", encoding="utf-8")
        files = ["a.txt", "b.txt"]

        before = sweep(tmp, files)
        assert verify(before, tmp, files) == [], "no change -> no drift"

        time.sleep(0.05)
        (tmp / "a.txt").write_text("A-CHANGED", encoding="utf-8")
        drift = verify(before, tmp, files)
        assert drift == ["a.txt"], f"should detect drift in a.txt: {drift}"

        (tmp / "a.txt").write_text("A", encoding="utf-8")
        before2 = sweep(tmp, files)
        (tmp / "b.txt").unlink()
        drift2 = verify(before2, tmp, files)
        assert drift2 == ["b.txt"], f"a vanished file should count as drift: {drift2}"

        before3 = sweep(tmp, ["a.txt", "c-does-not-exist.txt"])
        assert before3["c-does-not-exist.txt"] is None
        assert verify(before3, tmp, ["a.txt", "c-does-not-exist.txt"]) == []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # --- --hook mode ---
    origins = ["Desktop/LIVE-SOURCE"]
    code1, msg1 = decide({"tool_name": "Write", "tool_input": {"file_path": "Desktop/LIVE-SOURCE/x.py"}}, origins)
    assert code1 == 2 and "BLOCKED" in msg1, (code1, msg1)

    code2, msg2 = decide({"tool_name": "Write", "tool_input": {"file_path": "Desktop/OTHER-REPO/x.py"}}, origins)
    assert code2 == 0 and msg2 == "", (code2, msg2)

    code3, msg3 = decide({"tool_name": "Bash", "tool_input": {"command": "rm -rf Desktop/LIVE-SOURCE/tmp"}}, origins)
    assert code3 == 2, (code3, msg3)

    code4, msg4 = decide({"tool_name": "Bash", "tool_input": {"command": "ls Desktop/LIVE-SOURCE"}}, origins)
    assert code4 == 0, (code4, msg4)  # ls is not destructive -> passes even when aimed at the origin

    code5, _ = decide({"tool_name": "Write", "tool_input": {"file_path": "Desktop/LIVE-SOURCE/x.py"}}, [])
    assert code5 == 0, "no origins configured -> fail-open (never blocks)"

    print("self-test OK — library (sweep/verify: stable/drift/vanished/absent) + hook (blocks write/destructive, allows the rest, fail-open without config)")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
