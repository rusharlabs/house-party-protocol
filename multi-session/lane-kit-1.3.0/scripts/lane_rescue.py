#!/usr/bin/env python3
"""
lane_rescue — a lane's uncommitted work becomes a patch BEFORE anything can destroy its worktree.

A lane is a worktree. When a lane goes `dead` the registry drops it, and from that moment its
worktree is unowned: the next `git worktree remove --force`, the next idle-cleanup cron, the next
`rm -rf` takes whatever was never committed, and nothing anywhere says what was lost. Eviction is
cheap to reverse; deletion is not. This module makes the difference reversible.

Two halves, and the second is the one that is easy to get wrong:

  capture   `git diff --binary` of the working tree against its base, taken through a PRIVATE
            `GIT_INDEX_FILE` so a shared index cannot make it report changes that are not there
            (or miss ones that are). Untracked files are included — they are the ones a removal
            destroys without trace. Beside the patch goes a `.meta.json` with the BASE COMMIT.

  reapply   refuses, whole, when the base moved or when the patch does not apply cleanly. A
            half-applied rescue is worse than a lost one: it looks like the work came back.
            `git apply --check` runs first, and the override for a moved base is explicit.

Usage:
    python lane_rescue.py capture --lane <id> [--worktree <path>] [--out <dir>]
    python lane_rescue.py reapply <patch> [--worktree <path>] [--force-base]
    python lane_rescue.py list [--out <dir>]
    python lane_rescue.py --self-test

Exit: 0 ok (including "nothing to rescue") · 1 refused (moved base, conflicting patch, no repo) ·
2 invalid usage.

stdlib only. Adapted from cline/kanban (Apache-2.0) — concept only, reimplemented in Python.
v1.0.0 — 2026-09-22 (lane-kit)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_BUDGET_SECONDS = 30.0
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def project_root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())


def default_out_dir() -> Path:
    return project_root() / ".claude" / "lanes" / "rescue"


def _safe(name: str) -> str:
    return _UNSAFE.sub("-", name or "").strip("-.") or "unknown"


def _run(repo, args: list, env: dict, timeout: float, binary: bool = False) -> tuple:
    """(ok, output) — never raises. `output` is bytes when `binary`, else stripped text."""
    try:
        result = subprocess.run(["git", "-C", str(repo), *args],
                                capture_output=True, text=not binary, env=env, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 — a rescue never raises into the caller
        return False, (b"" if binary else str(exc))
    if result.returncode != 0:
        err = result.stderr if not binary else result.stderr.decode("utf-8", "replace")
        return False, (err or "").strip() if not binary else err.strip().encode()
    return True, (result.stdout if binary else result.stdout.strip())



def _autocrlf(worktree) -> str:
    """`core.autocrlf` as git sees it for this worktree ("" when unset) — recorded, never acted on."""
    try:
        r = subprocess.run(["git", "-C", str(worktree), "config", "--get", "core.autocrlf"],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""

def capture(lane_id: str, worktree, out_dir=None, budget_seconds: float = DEFAULT_BUDGET_SECONDS) -> tuple:
    """Write `lane-<id>-<ts>.patch` + `.meta.json` for everything uncommitted in `worktree`.

    Returns (True, {"empty": bool, "patch": str|None, "meta": str|None, ...}) or (False, reason).
    A clean worktree is a success with `empty=True` and no file written — an empty patch beside
    the real ones is how a rescue directory stops being readable.
    """
    wt = Path(worktree)
    env = dict(os.environ)
    ok, top = _run(wt, ["rev-parse", "--show-toplevel"], env, budget_seconds)
    if not ok:
        return False, f"not a git worktree ({wt}): {top}"
    wt = Path(top) if top else wt

    # One call for both: `rev-parse HEAD --abbrev-ref HEAD` prints the sha then the branch.
    has_head, head_out = _run(wt, ["rev-parse", "HEAD", "--abbrev-ref", "HEAD"], env, budget_seconds)
    lines = head_out.splitlines() if has_head else []
    base_commit = lines[0] if lines else ""
    branch = lines[1] if len(lines) > 1 else ""

    tmp_dir = tempfile.mkdtemp(prefix="lane-rescue-")
    index_path = Path(tmp_dir) / "index"
    index_env = dict(env, GIT_INDEX_FILE=str(index_path))
    try:
        if base_commit:
            _run(wt, ["read-tree", base_commit], index_env, budget_seconds)
            against = base_commit
        else:
            ok_empty, empty_tree = _run(wt, ["hash-object", "-t", "tree", "--stdin"], env, budget_seconds)
            if not ok_empty:
                return False, f"could not resolve the empty tree: {empty_tree}"
            against = empty_tree

        ok_add, add_out = _run(wt, ["add", "-A", "--", "."], index_env, budget_seconds)
        if not ok_add:
            return False, f"staging into the private index failed: {add_out}"

        ok_diff, patch = _run(wt, ["diff", "--binary", "--cached", against], index_env, budget_seconds, binary=True)
        if not ok_diff:
            return False, f"diff --binary failed: {patch.decode('utf-8', 'replace')}"
    finally:
        try:
            if index_path.exists():
                index_path.unlink()
            os.rmdir(tmp_dir)
        except OSError:
            pass

    if not patch.strip():
        return True, {"empty": True, "patch": None, "meta": None, "lane_id": lane_id,
                      "base_commit": base_commit, "worktree": str(wt), "files": 0}

    target_dir = Path(out_dir) if out_dir else default_out_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = f"lane-{_safe(lane_id)}-{stamp}"
    patch_path = target_dir / f"{stem}.patch"
    meta_path = target_dir / f"{stem}.meta.json"

    # Binary mode, always: a rescue patch that went through newline translation is not a rescue.
    # Known limit (adversarial review of 2.5.0): this protects the FILE write. With `core.autocrlf=true`
    # (the Git for Windows installer default) git itself normalises TEXT blobs on `diff` and on `apply`,
    # so text files come back LF-normalised while binary files round-trip byte-exact. The byte-exact
    # promise holds for binaries and for repositories with autocrlf off; it is not a promise about
    # line endings under autocrlf, and the meta records `autocrlf` so the reader knows which case it is.
    with open(patch_path, "wb") as handle:
        handle.write(patch)

    meta = {
        "lane_id": lane_id,
        "base_commit": base_commit,
        "branch": branch,
        "worktree": str(wt),
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": patch.count(b"\ndiff --git ") + (1 if patch.startswith(b"diff --git ") else 0),
        "bytes": len(patch),
        "sha256": hashlib.sha256(patch).hexdigest(),
        "reapply_cmd": f"python lane_rescue.py reapply {patch_path.name} --worktree {wt}",
        # Which newline regime this patch was captured under (see the comment above the write):
        # "true" means text files are LF-normalised by git on both sides; binaries are exact either way.
        "autocrlf": _autocrlf(wt),
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    info = dict(meta)
    info.update({"empty": False, "patch": str(patch_path), "meta": str(meta_path)})
    return True, info


def reapply(patch, worktree=None, allow_base_moved: bool = False,
            budget_seconds: float = DEFAULT_BUDGET_SECONDS) -> tuple:
    """Put a captured patch back. Refuses WHOLE — a half-applied rescue is worse than none."""
    patch_path = Path(patch)
    if not patch_path.is_absolute():
        candidate = default_out_dir() / patch_path.name
        if candidate.exists():
            patch_path = candidate
    if not patch_path.exists():
        return False, f"patch not found: {patch_path}"

    meta_path = patch_path.with_name(patch_path.stem + ".meta.json")
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except ValueError:
            meta = {}

    wt = Path(worktree) if worktree else Path(meta.get("worktree") or project_root())
    env = dict(os.environ)
    ok, top = _run(wt, ["rev-parse", "--show-toplevel"], env, budget_seconds)
    if not ok:
        return False, f"not a git worktree ({wt}): {top}"
    wt = Path(top) if top else wt

    recorded = meta.get("base_commit") or ""
    if recorded:
        ok_head, head = _run(wt, ["rev-parse", "HEAD"], env, budget_seconds)
        if ok_head and head != recorded and not allow_base_moved:
            return False, (f"refused: the base moved (patch was taken on {recorded[:12]}, "
                           f"{wt} is on {head[:12]}). Re-run with --force-base to apply anyway; "
                           f"nothing was changed.")

    ok_check, check_out = _run(wt, ["apply", "--binary", "--check", str(patch_path)], env, budget_seconds)
    if not ok_check:
        return False, f"refused: the patch does not apply cleanly, nothing was changed — {check_out}"

    ok_apply, apply_out = _run(wt, ["apply", "--binary", str(patch_path)], env, budget_seconds)
    if not ok_apply:
        return False, f"apply failed after a passing --check (nothing partial is expected): {apply_out}"
    return True, {"patch": str(patch_path), "worktree": str(wt), "base_commit": recorded,
                  "forced": bool(recorded and allow_base_moved)}


def list_rescues(out_dir=None) -> list:
    target = Path(out_dir) if out_dir else default_out_dir()
    if not target.is_dir():
        return []
    found = []
    for patch_path in sorted(target.glob("*.patch")):
        meta_path = patch_path.with_name(patch_path.stem + ".meta.json")
        meta = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except ValueError:
                meta = {}
        found.append({"patch": str(patch_path), "bytes": patch_path.stat().st_size, **meta})
    return found


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------

def _self_test() -> int:
    import shutil

    tmp = Path(tempfile.mkdtemp(prefix="lane_rescue_selftest_"))
    repo = tmp / "wt"
    repo.mkdir()
    payload = bytes(range(256)) * 4

    def g(*args: str) -> str:
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
        return r.stdout.strip()

    try:
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], capture_output=True, text=True)
        g("config", "user.email", "selftest@localhost.invalid")
        g("config", "user.name", "Self Test")
        (repo / "kept.txt").write_text("base\n", encoding="utf-8")
        g("add", "kept.txt")
        g("commit", "-qm", "base")

        out = tmp / "rescue"
        ok_clean, clean = capture("exec-a", repo, out_dir=out)
        assert ok_clean and clean["empty"] is True and clean["patch"] is None, f"a clean tree must write nothing: {clean}"

        (repo / "kept.txt").write_text("base\nedited\n", encoding="utf-8")
        (repo / "added.txt").write_text("only in the lane\n", encoding="utf-8")
        (repo / "blob.bin").write_bytes(payload)

        ok, info = capture("exec-a", repo, out_dir=out)
        assert ok and not info["empty"], f"capture failed: {info}"
        body = Path(info["patch"]).read_bytes()
        assert b"GIT binary patch" in body, "the binary file was not encoded as a binary patch"
        assert info["base_commit"] == g("rev-parse", "HEAD"), "the base commit was not recorded"

        # destroy the work exactly as `worktree remove --force` would
        (repo / "kept.txt").write_text("base\n", encoding="utf-8")
        (repo / "added.txt").unlink()
        (repo / "blob.bin").unlink()
        assert g("status", "--porcelain") == "", "the sandbox was not actually cleaned"

        ok2, back = reapply(info["patch"], repo)
        assert ok2, f"a valid reapply was refused: {back}"
        assert (repo / "blob.bin").read_bytes() == payload, "the binary did not survive the round trip"
        assert (repo / "added.txt").exists(), "the untracked file did not come back"

        # a moved base is refused, and the refusal changes nothing
        (repo / "kept.txt").write_text("base\n", encoding="utf-8")
        (repo / "added.txt").unlink()
        (repo / "blob.bin").unlink()
        (repo / "other.txt").write_text("someone else\n", encoding="utf-8")
        g("add", "other.txt")
        g("commit", "-qm", "moved")
        before = g("status", "--porcelain")
        ok3, why = reapply(info["patch"], repo)
        assert ok3 is False and "base" in str(why).lower(), f"a moved base must be refused: {why}"
        assert g("status", "--porcelain") == before, "the refused reapply touched the tree"
        ok4, _ = reapply(info["patch"], repo, allow_base_moved=True)
        assert ok4, "the explicit override must still work"

        # CONTROL: a conflicting patch on the SAME base is refused whole, not half applied
        (repo / "conflict.txt").write_text("mine\n", encoding="utf-8")
        ok5, conflicting = capture("exec-b", repo, out_dir=out)
        assert ok5 and not conflicting["empty"]
        (repo / "conflict.txt").write_text("someone else wrote this\n", encoding="utf-8")
        kept_before = (repo / "kept.txt").read_bytes()
        ok6, why6 = reapply(conflicting["patch"], repo)
        assert ok6 is False and "apply cleanly" in str(why6), f"a conflicting patch must be refused: {why6}"
        assert (repo / "kept.txt").read_bytes() == kept_before, "the refused patch changed another file"

        assert capture("exec-a", tmp / "nope", out_dir=out)[0] is False, "a missing worktree must degrade, not raise"
        assert len(list_rescues(out)) == 2, list_rescues(out)

        print("self-test OK — clean tree writes nothing, capture records the base commit, binary "
              "round trip byte-exact, untracked file restored, moved base refused without touching "
              "the tree (override works), conflicting patch refused whole, missing worktree degrades")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lane_rescue.py")
    sub = p.add_subparsers(dest="cmd")

    c = sub.add_parser("capture")
    c.add_argument("--lane", required=True)
    c.add_argument("--worktree", default="")
    c.add_argument("--out", default="")

    r = sub.add_parser("reapply")
    r.add_argument("patch")
    r.add_argument("--worktree", default="")
    r.add_argument("--force-base", action="store_true")

    ls = sub.add_parser("list")
    ls.add_argument("--out", default="")

    p.add_argument("--self-test", action="store_true")
    return p


def main(argv) -> int:
    args = build_parser().parse_args(argv)
    if args.self_test:
        return _self_test()

    if args.cmd == "capture":
        ok, info = capture(args.lane, args.worktree or project_root(), out_dir=args.out or None)
        if not ok:
            print(f"lane_rescue: nothing captured — {info}", file=sys.stderr)
            return 1
        print(json.dumps(info, ensure_ascii=False))
        return 0
    if args.cmd == "reapply":
        ok, info = reapply(args.patch, args.worktree or None, allow_base_moved=args.force_base)
        if not ok:
            print(f"lane_rescue: {info}", file=sys.stderr)
            return 1
        print(json.dumps(info, ensure_ascii=False))
        return 0
    if args.cmd == "list":
        print(json.dumps(list_rescues(args.out or None), ensure_ascii=False, indent=2))
        return 0

    print("usage: capture --lane <id> | reapply <patch> | list, or --self-test", file=sys.stderr)
    return 2


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
