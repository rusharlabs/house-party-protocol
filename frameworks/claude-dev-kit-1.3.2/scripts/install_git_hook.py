#!/usr/bin/env python3
"""
install_git_hook -- CHAIN-PRESERVING git hook installer (never replaces someone else's hook).

An existing `.git/hooks/pre-commit` can be an important wrapper; a naive installer
would replace that protection and create a silent regression. This installer never overwrites:
it chains.
if a hook different from ours already exists, it preserves it as `<hook>.pre-kitforge` and writes a new
`<hook>` that runs (1) the preserved original, (2) our payload -- in this order, with `set -e` (the
original failing aborts BEFORE our payload runs; we never skip someone else's guard).

Usage:
    python install_git_hook.py --repo <repo_dir> --hook-name pre-commit --payload <script.sh> [--self-test]

Exit: 0 installed or already-chained (idempotent) - 3 error (repo/.git/hooks missing, payload missing).
stdlib only. v1.0.0 -- 2026-07-10 (claude-dev-kit - Tier 1)
"""
from __future__ import annotations

import argparse
import shutil
import stat
import sys
from pathlib import Path

_MARKER = "installed-by: kit-forge/install_git_hook.py"


def _find_posix_shell() -> str | None:
    """Resolve Git for Windows' shell before Windows' WSL launcher."""
    git = shutil.which("git")
    if git:
        git_path = Path(git).resolve()
        roots = [git_path.parent.parent, git_path.parent]
        for root in roots:
            for relative in (Path("bin") / "sh.exe", Path("usr") / "bin" / "sh.exe"):
                candidate = root / relative
                if candidate.is_file():
                    return str(candidate)
    return shutil.which("sh")


def _make_executable(path: Path) -> None:
    try:
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except Exception:  # noqa: BLE001 -- Windows has no real chmod; the shebang is enough for git-bash
        pass


def install(repo: Path, hook_name: str, payload_path: Path) -> tuple:
    hooks_dir = repo / ".git" / "hooks"
    if not hooks_dir.is_dir():
        return 3, {"status": "error", "errors": [f".git/hooks does not exist in {repo}"]}
    if not payload_path.exists():
        return 3, {"status": "error", "errors": [f"payload does not exist: {payload_path}"]}

    target = hooks_dir / hook_name
    payload_dst = hooks_dir / f"{hook_name}.kitforge-payload"
    preserved = hooks_dir / f"{hook_name}.pre-kitforge"

    payload_text = payload_path.read_text(encoding="utf-8")

    if target.exists():
        existing_text = target.read_text(encoding="utf-8", errors="replace")
        if _MARKER in existing_text:
            # already chained by us -- update only the payload if it changed, idempotent otherwise
            if not payload_dst.exists() or payload_dst.read_text(encoding="utf-8") != payload_text:
                payload_dst.write_text(payload_text, encoding="utf-8")
                _make_executable(payload_dst)
                return 0, {"status": "payload-updated", "hook": str(target)}
            return 0, {"status": "no-op", "hook": str(target)}
        else:
            # someone else's hook (not ours) -- preserve chain-preserving, only once
            if not preserved.exists():
                shutil.copy2(target, preserved)
                _make_executable(preserved)
    else:
        preserved = None

    payload_dst.write_text(payload_text, encoding="utf-8")
    _make_executable(payload_dst)

    lines = ["#!/bin/sh", f"# {_MARKER}", "set -e"]
    if preserved is not None:
        lines.append(f'"$(dirname "$0")/{preserved.name}" "$@"')
    lines.append(f'"$(dirname "$0")/{payload_dst.name}" "$@"')
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _make_executable(target)

    return 0, {
        "status": "chained" if preserved is not None else "installed",
        "hook": str(target),
        "preserved_original": str(preserved) if preserved is not None else None,
        "payload": str(payload_dst),
    }


def _self_test() -> int:
    import subprocess
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="install_git_hook_selftest_"))
    try:
        repo = tmp / "repo"
        (repo / ".git" / "hooks").mkdir(parents=True)

        # scenario 1: no prior hook -- simple install
        payload1 = tmp / "payload1.sh"
        payload1.write_text("#!/bin/sh\necho payload1-ran >> \"$1\"\n", encoding="utf-8")
        code1, report1 = install(repo, "pre-commit", payload1)
        assert code1 == 0 and report1["status"] == "installed", f"simple install failed: {report1}"

        code1b, report1b = install(repo, "pre-commit", payload1)
        assert code1b == 0 and report1b["status"] == "no-op", f"2nd install should be a no-op: {report1b}"

        # scenario 2: an existing hook belonging to someone else -- should chain, not replace
        repo2 = tmp / "repo2"
        (repo2 / ".git" / "hooks").mkdir(parents=True)
        original_hook = repo2 / ".git" / "hooks" / "pre-commit"
        original_hook.write_text('#!/bin/sh\necho original-ran >> "$1"\n', encoding="utf-8")
        _make_executable(original_hook)

        payload2 = tmp / "payload2.sh"
        payload2.write_text('#!/bin/sh\necho payload2-ran >> "$1"\n', encoding="utf-8")
        code2, report2 = install(repo2, "pre-commit", payload2)
        assert code2 == 0 and report2["status"] == "chained", f"chaining should happen: {report2}"
        assert report2["preserved_original"] is not None

        marker_log = tmp / "marker.log"
        shell = _find_posix_shell()
        assert shell is not None, "no POSIX shell found to validate the hook"
        result = subprocess.run(
            [shell, str(repo2 / ".git" / "hooks" / "pre-commit"), str(marker_log)],
            capture_output=True, text=True,
        )
        log_content = marker_log.read_text(encoding="utf-8") if marker_log.exists() else ""
        assert "original-ran" in log_content, f"the original must NEVER stop running: {log_content!r} (stderr={result.stderr!r})"
        assert "payload2-ran" in log_content, f"the payload should run after the original: {log_content!r}"
        assert log_content.index("original-ran") < log_content.index("payload2-ran"), "wrong order: the original should run BEFORE the payload"

        code2b, report2b = install(repo2, "pre-commit", payload2)
        assert code2b == 0 and report2b["status"] == "no-op", f"2nd install (already chained, same payload) should be a no-op: {report2b}"

        payload2.write_text('#!/bin/sh\necho payload2-v2-ran >> "$1"\n', encoding="utf-8")
        code2c, report2c = install(repo2, "pre-commit", payload2)
        assert code2c == 0 and report2c["status"] == "payload-updated", f"the payload changed, it should be updated: {report2c}"

        print("self-test OK — simple install, chain-preserving (the original runs first), idempotency and payload update covered")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="install_git_hook.py")
    p.add_argument("--repo", default=None)
    p.add_argument("--hook-name", default="pre-commit")
    p.add_argument("--payload", default=None)
    p.add_argument("--self-test", action="store_true")
    return p


def main(argv) -> int:
    args = build_parser().parse_args(argv)

    if args.self_test:
        return _self_test()

    if not args.repo or not args.payload:
        print("usage: install_git_hook.py --repo <dir> --hook-name pre-commit --payload <script.sh>", file=sys.stderr)
        return 3

    code, report = install(Path(args.repo), args.hook_name, Path(args.payload))
    import json
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
