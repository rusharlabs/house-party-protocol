#!/usr/bin/env python3
"""
turn_checkpoint — a per-turn snapshot as a git object, in its own ref, touching nothing you own.

The problem it solves is not "backup". It is EVIDENCE. `git diff --numstat` is unreliable the
moment an index is shared between concurrent sessions: git consults the index stat cache to
decide whether to re-read a file, so the same command can report nothing over a real edit and
report a deletion over a file nobody touched. Anything that cites that number inherits the lie.

A checkpoint written here never consults the shared index. It builds a tree through a PRIVATE
`GIT_INDEX_FILE`, writes a commit object over it, and names it
`refs/hpp/checkpoints/<session>/turn/<n>`. From then on the turn is a content-addressed object:
`git diff <turn n-1> <turn n>` is that turn's change, `git show <ref>` is the state at its end,
and none of it depends on what any index believes.

What it deliberately does NOT do — the whole point:
  * the user's `.git/index` is never opened for writing (the private index is a temp file);
  * the working tree is never modified, never stashed, never checked out;
  * HEAD and every branch stay where they are (`refs/hpp/...` is outside `refs/heads/`);
  * any failure at all degrades to `(False, reason)` — a turn must never fail because the
    evidence of it could not be taken.

Usage:
    python turn_checkpoint.py write  --session <id> [--label <text>] [--tracked-only] [--keep N]
    python turn_checkpoint.py latest --session <id>
    python turn_checkpoint.py list   --session <id>
    python turn_checkpoint.py --self-test

Exit: 0 ok (including a no-op turn) · 1 the checkpoint could not be taken (never fatal for the
caller: the hooks that call it ignore this) · 2 invalid usage.

stdlib only. Adapted from cline/kanban (Apache-2.0) — concept only, reimplemented in Python.
v1.0.0 — 2026-09-22 (continuity-kit)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REF_NAMESPACE = "refs/hpp/checkpoints"
DEFAULT_KEEP = 50
DEFAULT_BUDGET_SECONDS = 20.0

# A checkpoint is a machine artifact. If the repository has no identity configured, `commit-tree`
# refuses outright — which would turn "no git identity" into "no evidence, ever". These are used
# ONLY when the repository configures none.
_FALLBACK_NAME = "hpp-checkpoint"
_FALLBACK_EMAIL = "checkpoint@localhost.invalid"

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


class _Budget:
    """A single wall-clock budget shared by every git call of one checkpoint."""

    def __init__(self, seconds: float):
        self.deadline = time.monotonic() + seconds

    def left(self) -> float:
        return max(0.1, self.deadline - time.monotonic())

    def spent(self) -> bool:
        return time.monotonic() >= self.deadline


def sanitize_session(session: str) -> str:
    """Turn any session identifier into one safe path component of a git ref."""
    name = _UNSAFE.sub("-", session or "")
    while ".." in name:
        name = name.replace("..", ".")
    if name.endswith(".lock"):
        name = name[: -len(".lock")] + "-lock"
    name = re.sub(r"-{2,}", "-", name)
    name = name.strip(".-")
    return name or "unknown"


def _run(repo: Path, args: list, env: dict, budget: _Budget, stdin_text: str = "") -> tuple:
    """(ok, stdout) — never raises; a non-zero exit or a timeout is just `not ok`."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            input=stdin_text if stdin_text else None,
            capture_output=True, text=True, env=env, timeout=budget.left(),
        )
    except Exception as exc:  # noqa: BLE001 — a checkpoint never raises into the caller
        return False, str(exc)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip()
    return True, result.stdout.strip()


# Why: a `git` subprocess costs around 200 ms on a Windows machine with real-time scanning on. A
# checkpoint that spends twelve of them burns 2.5 s of a hook whose whole budget is 30 s, on every
# turn. Each call removed here comes off every turn, so the identity lookup — which cannot change
# inside one process — is asked once per repository.
_IDENTITY_CACHE: dict = {}


def _identity_env(repo: Path, budget: _Budget) -> dict:
    env = dict(os.environ)
    key = str(repo)
    if key not in _IDENTITY_CACHE:
        ok_email, email = _run(repo, ["config", "--get", "user.email"], env, budget)
        ok_name, name = _run(repo, ["config", "--get", "user.name"], env, budget)
        _IDENTITY_CACHE[key] = bool(ok_email and email.strip()) and bool(ok_name and name.strip())
    if not _IDENTITY_CACHE[key]:
        env.setdefault("GIT_AUTHOR_NAME", _FALLBACK_NAME)
        env.setdefault("GIT_AUTHOR_EMAIL", _FALLBACK_EMAIL)
        env.setdefault("GIT_COMMITTER_NAME", _FALLBACK_NAME)
        env.setdefault("GIT_COMMITTER_EMAIL", _FALLBACK_EMAIL)
    return env


def session_key(session: str) -> str:
    """The ref/namespace component for a session: readable prefix + 8 hex of the RAW id.

    Why (adversarial review of 2.5.0): `sanitize_session` is lossy — "sess A", "sess-A" and "sess/A"
    all became `sess-A`, so two sessions interleaved turns and one session's retention pruned the
    other's evidence. And on NTFS loose refs are files, so `S1` overwrote `s1/turn/1` while the
    case-sensitive listing for `S1` came back empty. The hash of the RAW id makes distinct sessions
    distinct namespaces whatever the filesystem does with case.
    """
    raw = (session or "").encode("utf-8", "surrogatepass")
    return f"{sanitize_session(session)}-{hashlib.sha1(raw).hexdigest()[:8]}"


def _ref_prefix(session: str) -> str:
    return f"{REF_NAMESPACE}/{session_key(session)}/turn"


def list_checkpoints(session: str, repo=None, budget: "_Budget | None" = None) -> list:
    """[{turn, ref, commit, tree}] for this session, oldest first. Empty when there are none.

    `%(tree)` comes back from the same `for-each-ref`, which is what lets `write_checkpoint` decide
    whether the turn changed anything without a second `rev-parse`.
    """
    root = Path(repo) if repo else Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
    budget = budget or _Budget(DEFAULT_BUDGET_SECONDS)
    prefix = _ref_prefix(session)
    ok, out = _run(root, ["for-each-ref", "--format=%(refname) %(objectname) %(tree)", prefix + "/"],
                   dict(os.environ), budget)
    if not ok or not out:
        return []
    found = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        ref, commit = parts[0], parts[1]
        tree = parts[2] if len(parts) > 2 else ""
        tail = ref.rsplit("/", 1)[-1]
        if not tail.isdigit():
            continue
        found.append({"turn": int(tail), "ref": ref, "commit": commit, "tree": tree})
    return sorted(found, key=lambda item: item["turn"])


def latest(session: str, repo=None):
    """The newest checkpoint of this session, or None."""
    found = list_checkpoints(session, repo=repo)
    return found[-1] if found else None


def write_checkpoint(session: str, label: str = "", repo=None, include_untracked: bool = True,
                     keep: int = DEFAULT_KEEP, budget_seconds: float = DEFAULT_BUDGET_SECONDS) -> tuple:
    """Take one checkpoint. Returns (ok, info_dict) or (False, reason_string).

    `info_dict` = {session, turn, ref, commit, tree, unchanged, parent}. A turn whose tree equals
    the previous checkpoint's tree is a no-op: `unchanged=True`, no new ref, no ref spam.
    """
    root = Path(repo) if repo else Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
    budget = _Budget(budget_seconds)
    base_env = dict(os.environ)

    # One call for both facts: `rev-parse --show-toplevel HEAD` prints the root then the sha. It
    # fails as a whole in a repository with no commit yet, so that case falls back to two.
    ok, out = _run(root, ["rev-parse", "--show-toplevel", "HEAD"], base_env, budget)
    head = ""
    if ok:
        lines = out.splitlines()
        top = lines[0] if lines else ""
        head = lines[1] if len(lines) > 1 else ""
    else:
        ok, top = _run(root, ["rev-parse", "--show-toplevel"], base_env, budget)
        if not ok:
            return False, f"not a git repository ({root}): {top}"
    root = Path(top) if top else root
    has_head = bool(head)

    env = _identity_env(root, budget)
    index_path = _private_index_path(root, session)
    env["GIT_INDEX_FILE"] = str(index_path)
    _clear_stale_lock(index_path)

    try:
        # Why (adversarial review of 2.5.0): a private index seeded ONLY from HEAD has no stat cache,
        # so `git add -A` re-hashes every file — 12 s on a 17k-file repository, over the Stop budget,
        # so the checkpoint never landed and each attempt leaked an index.lock. Seeding by COPYING the
        # user's own index (a read; the user's index is never written) brings its stat cache along:
        # measured 12,05 s cold → 1,74 s warm. The copy is refreshed only while the private index is
        # missing; afterwards it keeps its own cache between turns.
        if not index_path.exists():
            if not _seed_from_user_index(root, index_path, base_env, budget) and has_head:
                _run(root, ["read-tree", head], env, budget)

        add_args = ["add", "-A" if include_untracked else "-u", "--", "."]
        ok_add, add_out = _run(root, add_args, env, budget)
        if not ok_add:
            return False, f"staging into the private index failed: {add_out}"
        if budget.spent():
            return False, f"checkpoint budget of {budget_seconds:g}s exhausted before write-tree"

        ok_tree, tree = _run(root, ["write-tree"], env, budget)
        if not ok_tree:
            return False, f"write-tree failed: {tree}"

        known = list_checkpoints(session, repo=root, budget=budget)
        previous = known[-1] if known else None
        parent = previous["commit"] if previous else (head if has_head else "")

        if parent:
            # The previous checkpoint's tree came back with the ref listing; only the HEAD case
            # still needs a lookup.
            if previous:
                parent_tree = previous.get("tree", "")
            else:
                _ok_tree, parent_tree = _run(root, ["rev-parse", f"{parent}^{{tree}}"], base_env, budget)
            if parent_tree and parent_tree == tree:
                if previous:
                    return True, {"session": session, "turn": previous["turn"], "ref": previous["ref"],
                                  "commit": previous["commit"], "tree": tree, "unchanged": True, "parent": parent}
                return True, {"session": session, "turn": 0, "ref": None, "commit": None,
                              "tree": tree, "unchanged": True, "parent": parent}

        turn = (previous["turn"] + 1) if previous else 1
        message = f"hpp checkpoint turn {turn} session {sanitize_session(session)}"
        if label:
            message += f" :: {label}"
        commit_args = ["commit-tree", tree]
        if parent:
            commit_args += ["-p", parent]
        ok_commit, commit = _run(root, commit_args, env, budget, stdin_text=message + "\n")
        if not ok_commit:
            return False, f"commit-tree failed: {commit}"

        ref = f"{_ref_prefix(session)}/{turn}"
        ok_ref, ref_out = _run(root, ["update-ref", ref, commit], base_env, budget)
        if not ok_ref:
            return False, f"update-ref failed: {ref_out}"

        # `known` is the listing from before this ref existed, so the new one is +1. No extra call.
        if keep > 0 and len(known) + 1 > keep:
            for item in known[: len(known) + 1 - keep]:
                _run(root, ["update-ref", "-d", item["ref"]], base_env, budget)
        return True, {"session": session, "turn": turn, "ref": ref, "commit": commit,
                      "tree": tree, "unchanged": False, "parent": parent}
    finally:
        # The private index is KEPT between turns (that is what makes the second turn cheap). What
        # must not survive is the lock a timed-out git leaves behind: with it in place every later
        # turn fails with "index.lock exists" and the checkpoint is dead until someone notices.
        _clear_stale_lock(index_path, max_age_seconds=0)


def _private_index_path(root: Path, session: str) -> Path:
    """One private index per (repository, session), under the system temp dir, reused across turns."""
    base = Path(os.environ.get("HPP_CHECKPOINT_STATE_DIR") or Path(tempfile.gettempdir()) / "hpp-checkpoint")
    repo_key = hashlib.sha1(str(root.resolve()).encode("utf-8", "surrogatepass")).hexdigest()[:12]
    folder = base / repo_key / session_key(session)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "index"


def _seed_from_user_index(root: Path, index_path: Path, base_env: dict, budget: "_Budget") -> bool:
    """Copy the USER's index (with its stat cache) into the private one. Read-only on the user's side."""
    ok, path = _run(root, ["rev-parse", "--git-path", "index"], base_env, budget)
    if not ok or not path:
        return False
    src = Path(path)
    if not src.is_absolute():
        src = root / src
    if not src.is_file():
        return False
    try:
        shutil.copyfile(src, index_path)
        return True
    except OSError:
        return False


def _clear_stale_lock(index_path: Path, max_age_seconds: float = 60.0) -> None:
    """Remove `<index>.lock` when it is older than `max_age_seconds` (0 = always): a git killed by the
    budget leaves it, and git refuses to touch the index while it exists."""
    lock = Path(str(index_path) + ".lock")
    try:
        if lock.exists() and (time.time() - lock.stat().st_mtime) >= max_age_seconds:
            lock.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------

def _self_test() -> int:
    import shutil

    tmp = Path(tempfile.mkdtemp(prefix="turn_checkpoint_selftest_"))
    repo = tmp / "repo"
    repo.mkdir()

    def g(*args: str) -> str:
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
        return r.stdout.strip()

    try:
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], capture_output=True, text=True)
        g("config", "user.email", "selftest@localhost.invalid")
        g("config", "user.name", "Self Test")
        (repo / "a.txt").write_text("one\n", encoding="utf-8")
        g("add", "a.txt")
        g("commit", "-qm", "first")

        (repo / "a.txt").write_text("one\ntwo\n", encoding="utf-8")
        (repo / "new.txt").write_text("new\n", encoding="utf-8")

        index_before = (repo / ".git" / "index").read_bytes()
        head_before = g("rev-parse", "HEAD")
        status_before = g("status", "--porcelain")

        ok1, first = write_checkpoint("s", repo=repo)
        assert ok1 and first["turn"] == 1, f"first checkpoint should be turn 1: {first}"
        assert g("cat-file", "-t", first["commit"]) == "commit", "the ref does not resolve to a commit"
        assert "new.txt" in g("ls-tree", "-r", "--name-only", first["commit"]), "untracked file missing"

        assert (repo / ".git" / "index").read_bytes() == index_before, "the user's index was touched"
        assert g("rev-parse", "HEAD") == head_before, "HEAD moved"
        assert g("status", "--porcelain") == status_before, "the working tree changed"
        assert g("stash", "list") == "", "a stash entry appeared"

        ok2, second = write_checkpoint("s", repo=repo)
        assert ok2 and second["unchanged"] is True and second["turn"] == 1, f"a no-op turn must not advance: {second}"

        (repo / "a.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
        ok3, third = write_checkpoint("s", repo=repo)
        assert ok3 and third["turn"] == 2, f"a changed turn must advance: {third}"
        numstat = g("diff", "--numstat", first["commit"], third["commit"])
        assert numstat == "1\t0\ta.txt", f"the turn diff is not the turn's change: {numstat!r}"

        assert latest("s", repo=repo)["turn"] == 2, "latest() disagrees with the refs"
        assert write_checkpoint("s", repo=tmp / "nope")[0] is False, "a missing repo must degrade, not raise"

        # A hostile session id must produce a ref git itself accepts — pinning a cosmetic string
        # would only prove the regex, not the legality.
        hostile = _ref_prefix("a b/../c~1:?*[x].lock") + "/1"
        legal = subprocess.run(["git", "check-ref-format", hostile], capture_output=True, text=True)
        assert legal.returncode == 0, f"sanitised ref rejected by git: {hostile} :: {legal.stderr}"
        rejected = subprocess.run(["git", "check-ref-format", f"{REF_NAMESPACE}/a b/../c~1/1"],
                                  capture_output=True, text=True)
        assert rejected.returncode != 0, "CONTROL: check-ref-format accepted a raw hostile id, so it proves nothing"

        print("self-test OK — private index (user index/HEAD/worktree/stash untouched), turn 1 with "
              "untracked file, no-op turn does not advance, turn diff is the turn's change, "
              "latest() agrees, missing repo degrades, hostile session id yields a ref git accepts "
              "(control: the raw id is rejected)")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="turn_checkpoint.py")
    sub = p.add_subparsers(dest="cmd")

    w = sub.add_parser("write")
    w.add_argument("--session", required=True)
    w.add_argument("--label", default="")
    w.add_argument("--tracked-only", action="store_true")
    w.add_argument("--keep", type=int, default=DEFAULT_KEEP)
    w.add_argument("--budget-seconds", type=float, default=DEFAULT_BUDGET_SECONDS)

    lt = sub.add_parser("latest")
    lt.add_argument("--session", required=True)

    ls = sub.add_parser("list")
    ls.add_argument("--session", required=True)

    p.add_argument("--self-test", action="store_true")
    return p


def main(argv) -> int:
    args = build_parser().parse_args(argv)
    if args.self_test:
        return _self_test()

    if args.cmd == "write":
        ok, info = write_checkpoint(args.session, label=args.label, include_untracked=not args.tracked_only,
                                    keep=args.keep, budget_seconds=args.budget_seconds)
        if not ok:
            print(f"turn_checkpoint: no checkpoint taken — {info}", file=sys.stderr)
            return 1
        print(json.dumps(info, ensure_ascii=False))
        return 0
    if args.cmd == "latest":
        print(json.dumps(latest(args.session), ensure_ascii=False))
        return 0
    if args.cmd == "list":
        print(json.dumps(list_checkpoints(args.session), ensure_ascii=False))
        return 0

    print("usage: write|latest|list --session <id>, or --self-test", file=sys.stderr)
    return 2


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
