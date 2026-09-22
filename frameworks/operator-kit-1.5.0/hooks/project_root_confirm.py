#!/usr/bin/env python3
"""
project_root_confirm (Operator Kit) - PreToolUse WARN-only: detects an action
(git / Write / Edit) whose target falls OUTSIDE the pinned project root, flagging
a possible cross-project operation (e.g. editing another repo by mistake).

Why it exists: whoever works with several neighboring repos open at the same time
(e.g. a monorepo + 2-3 satellite repos on the same Desktop) risks editing
the wrong repo by mistake - an expensive, silent error. This hook compares the
TARGET/cwd git root against the EXPECTED root.

Matcher (not wired): Bash(git) | Write | Edit.
Reads JSON from stdin: tool_input.{file_path, command, cwd}.

Expected root (precedence):
  1. env EXPECTED_ROOT
  2. paths.expected_root from the profile
  3. git toplevel of the cwd

Bypass: env ALLOW_CROSS_ROOT=1  (or guardrails.allow_cross_root: true in the profile).

WARN to stderr - exit 0 ALWAYS - any error -> exit 0 (defensive).

v1.0.0 - 2026-06-19 (Operator Kit - guard-distinct cluster)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from _lib.profile_loader import load_profile, get
except Exception:  # noqa: BLE001
    load_profile = None  # type: ignore[assignment]

    def get(_p, _d, default=None):  # type: ignore[misc]
        return default


def _git_toplevel(start: Path) -> Path | None:
    """git rev-parse --show-toplevel starting from `start` (existing dir)."""
    try:
        d = start if start.is_dir() else start.parent
        r = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(d), capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip()).resolve()
    except Exception:  # noqa: BLE001
        pass
    return None


def _norm(p: Path | None) -> str:
    return str(p).replace("\\", "/").rstrip("/").lower() if p else ""


def expected_root(prof: dict, cwd: Path) -> Path | None:
    """Expected root by env > profile > git toplevel of the cwd."""
    env = os.environ.get("EXPECTED_ROOT")
    if env:
        return Path(env).resolve()
    cfg = get(prof, "paths.expected_root", None)
    if cfg:
        return Path(str(cfg)).resolve()
    return _git_toplevel(cwd)


def target_dir(tool_input: dict, cwd: Path) -> Path:
    """Target directory: file_path's dir, else the command's cwd, else cwd."""
    fp = tool_input.get("file_path") or tool_input.get("path")
    if fp:
        p = Path(str(fp))
        if not p.is_absolute():
            p = (cwd / p)
        return p.resolve().parent
    c = tool_input.get("cwd")
    if c:
        return Path(str(c)).resolve()
    return cwd


def evaluate(tool_input: dict, cwd: Path, prof: dict) -> tuple[str, str] | None:
    """
    Compares target root vs expected root. Returns (expected_root, target_root)
    if they diverge; None if ok or indeterminate. Deterministic (receives roots
    already resolved via deps), testable without git through absolute paths.
    """
    exp = expected_root(prof, cwd)
    if exp is None:
        return None  # no reliable anchor -> does not warn (defensive)
    tgt = target_dir(tool_input, cwd)
    tgt_root = _git_toplevel(tgt) or tgt
    exp_n, tgt_n = _norm(exp), _norm(tgt_root)
    if not exp_n or not tgt_n:
        return None
    # ok if the target is inside the expected root
    if tgt_n == exp_n or tgt_n.startswith(exp_n + "/"):
        return None
    return (str(exp), str(tgt_root))


def _allowed(prof: dict) -> bool:
    if os.environ.get("ALLOW_CROSS_ROOT") == "1":
        return True
    return bool(get(prof, "guardrails.allow_cross_root", False))


def _warn(exp: str, tgt: str) -> None:
    sys.stderr.write(
        "[project_root_confirm] WARNING: target outside the pinned root — possible cross-project write.\n"
        f"  expected root: {exp}\n"
        f"  target root  : {tgt}\n"
        "  -> Confirm this is the right repo. If intentional, set ALLOW_CROSS_ROOT=1. "
        "WARN-only — not blocking.\n"
    )


def main() -> None:
    try:
        raw = sys.stdin.read()
    except Exception:  # noqa: BLE001
        sys.exit(0)
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001
        sys.exit(0)
    try:
        prof = load_profile() if load_profile is not None else {}
        if _allowed(prof):
            sys.exit(0)
        tool_input = data.get("tool_input") or {}
        if not isinstance(tool_input, dict):
            tool_input = {}
        cwd_raw = data.get("cwd") or os.getcwd()
        cwd = Path(str(cwd_raw)).resolve()
        verdict = evaluate(tool_input, cwd, prof)
        if verdict:
            _warn(*verdict)
    except Exception:  # noqa: BLE001
        pass
    sys.exit(0)


def _self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        base = Path(td).resolve()
        repo_a = base / "repoA"
        repo_b = base / "repoB"
        (repo_a / "sub").mkdir(parents=True)
        repo_b.mkdir()
        prof = {"paths": {"expected_root": str(repo_a)}}
        # 1. target INSIDE the expected root -> no warning
        v1 = evaluate({"file_path": str(repo_a / "sub" / "x.md")}, repo_a, prof)
        assert v1 is None, f"internal target should not warn: {v1}"
        # 2. target in ANOTHER repo -> warns
        v2 = evaluate({"file_path": str(repo_b / "y.md")}, repo_a, prof)
        assert v2 is not None, "cross-root target should warn"
        assert _norm(Path(v2[0])) == _norm(repo_a)
        # 3. no anchor (no env/profile/git) -> None (does not break)
        #    forces an empty profile and a cwd outside any git repo in tmp
        v3 = evaluate({"file_path": str(repo_b / "z.md")}, base, {})
        # base is not git; expected_root falls back to git toplevel of the cwd (None in tmp)
        assert v3 is None, f"without an anchor it should be None: {v3}"
        # 4. env EXPECTED_ROOT overrides
        os.environ["EXPECTED_ROOT"] = str(repo_a)
        try:
            v4 = evaluate({"file_path": str(repo_b / "y.md")}, base, {})
            assert v4 is not None, "env EXPECTED_ROOT should anchor and warn"
        finally:
            del os.environ["EXPECTED_ROOT"]
        # 5. bypass ALLOW_CROSS_ROOT
        os.environ["ALLOW_CROSS_ROOT"] = "1"
        try:
            assert _allowed({}) is True
        finally:
            del os.environ["ALLOW_CROSS_ROOT"]
        assert _allowed({"guardrails": {"allow_cross_root": True}}) is True
        # 6. target_dir resolves a relative file_path against cwd
        tdv = target_dir({"file_path": "sub/x.md"}, repo_a)
        assert _norm(tdv) == _norm(repo_a / "sub"), f"wrong relative target_dir: {tdv}"
    print("self-test OK")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    if len(sys.argv) > 1 and sys.argv[1] in ("--self-test", "-t"):
        _self_test()
    else:
        main()
