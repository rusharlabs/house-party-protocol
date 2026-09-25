#!/usr/bin/env python3
"""House Session runner: seats a panel on this host, read-only by proof.

The HPP core validates, counts, stops and seals a deliberation, and never calls a model. This
runner is the part that does call something: for one seat and one round, it runs the command the
seat declares, turns its answer into an `hpp.turn/v1`, and keeps the verbatim text beside it.

  families [--maker P] [--require]
      Which model families this host can seat: the maker's own, plus every other CLI found on the
      PATH (the detection of checker_router.py). Fewer than two is `DEFERRED` — a panel of one
      family is ceremony, never run and never called a panel.
      Exit: 0 ready · 1 DEFERRED · 2 DEFERRED with --require.

  seat --panel P --seat S --round R --out DIR [--seen HASH...] [--root DIR] [--timeout S] -- ARGV...
      Runs ARGV in the seat's worktree (--root, default the current directory) with the session
      context as JSON on stdin: {"panel", "seat", "round", "seen_turns"}. The command prints one
      JSON answer: {"position", "confidence"?, "claims", "text"}. When `text` is an
      hpp.findings/v1 document (a review lens), it must pass `hpp findings check`.
      Before and after the command the runner fingerprints the repository: `git status`, the diff
      against HEAD, untracked contents, HEAD and every ref (the stash included), the worktree list,
      the config, the hooks and `info/exclude`. If anything moved, the seat wrote: no turn is
      written and the exit is 2. A reviewer with a pen is not a reviewer. The seat and the round are
      checked BEFORE the command runs, and the command runs with the core's bounded runner, so a
      timeout stops its whole process tree. With --subject, a lens's findings must name that file.
      Exit: 0 turn written · 1 the seat failed or timed out (not judged: no turn) · 2 refused.

Limits, stated: the fingerprint is git's view of the worktree, so a write into a path the
repository ignores is not seen; and the runner proves what the seat did to its worktree, not what
it did elsewhere with your permissions. Run every seat in its own lane (its own worktree): two
seats sharing one worktree would be blamed for each other's writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from checker_router import PROVIDERS, detect  # noqa: E402  (sibling script, not a package)

# Why: a family is the vendor that trained the model a CLI runs. A CLI that serves several
# vendors' models (cursor) says nothing about the family of the model behind it.
FAMILY = {"claude": "anthropic", "codex": "openai", "gemini": "google", "cursor": None}
ANSWER_KEYS = {"position", "confidence", "claims", "text"}


def families(maker: str, which: Callable[[str], str | None] | None = None) -> dict:
    available = detect(which) if which is not None else detect()
    providers: dict[str, list[str]] = {}
    unknown = []
    if FAMILY.get(maker):
        providers.setdefault(FAMILY[maker], []).append(maker)
    for name, found in available.items():
        if name == maker or not found["available"]:
            continue
        family = FAMILY.get(name)
        if family is None:
            unknown.append(name)
        elif name not in providers.setdefault(family, []):
            providers[family].append(name)
    names = sorted(providers)
    return {"status": "ready" if len(names) >= 2 else "DEFERRED", "maker": maker, "families": names,
            "providers": {family: providers[family] for family in names}, "unknown_family": sorted(unknown)}


def _git(root: Path, *args: str, check: bool = True) -> bytes:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=60)
    if result.returncode != 0 and check:
        raise RuntimeError(result.stderr.decode("utf-8", "replace").strip() or f"git {args[0]} failed")
    return result.stdout


def _files(directory: Path) -> list[Path]:
    return sorted(path for path in directory.rglob("*") if path.is_file()) if directory.is_dir() else []


def fingerprint(root: Path) -> tuple[str, list[str]]:
    """A hash of git's view of the repository a seat sits in, and the paths that differ from HEAD.

    Covers the worktree (status of every untracked file, the diff against HEAD, the content of
    untracked files) AND what a seat could move without touching the worktree: HEAD and the
    branch it names, every ref (the stash included), the worktree list, the repository's config,
    its hooks and `info/exclude`. Paths are resolved from the top of the repository, whatever
    directory `--root` names.
    """
    top = Path(_git(root, "rev-parse", "--show-toplevel").decode("utf-8").strip())
    common = Path(_git(top, "rev-parse", "--git-common-dir").decode("utf-8").strip())
    common = common if common.is_absolute() else (top / common)
    status = _git(top, "status", "--porcelain=v1", "-uall", "-z")
    digest = hashlib.sha256()
    for part in (status, _git(top, "diff", "HEAD", "--binary", "--no-ext-diff", "--no-color"),
                 _git(top, "rev-parse", "HEAD"), _git(top, "symbolic-ref", "-q", "HEAD", check=False),
                 _git(top, "for-each-ref", "--format=%(refname) %(objectname)"),
                 _git(top, "worktree", "list", "--porcelain"), _git(top, "config", "--list", "--show-origin")):
        digest.update(hashlib.sha256(part).digest())
    for control in [*_files(common / "hooks"), common / "info" / "exclude", common / "config"]:
        if control.is_file():
            digest.update(control.as_posix().encode("utf-8") + b"\0" + hashlib.sha256(control.read_bytes()).digest())
    paths = []
    for entry in (item for item in status.split(b"\0") if item):
        code, path = entry[:2], entry[3:].decode("utf-8", "replace")
        paths.append(path)
        if code == b"??":
            target = top / path
            if target.is_file():
                digest.update(path.encode("utf-8") + b"\0" + hashlib.sha256(target.read_bytes()).digest())
    return digest.hexdigest(), sorted(paths)


def _refuse(message: str) -> int:
    print(f"house_session: {message}", file=sys.stderr)
    return 2


def seat(args: argparse.Namespace) -> int:
    try:
        from hpp._process import run_bounded
        from hpp.deliberation import TURN_SCHEMA, DeliberationError, normalise_panel, normalise_turn
        from hpp.findings import FindingsError, check as check_findings
    except ImportError:
        return _refuse("needs the HPP core importable (pip install house-party-protocol, or PYTHONPATH=<checkout>)")
    root = Path(args.root).resolve()
    try:
        panel = normalise_panel(json.loads(Path(args.panel).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, DeliberationError) as exc:
        return _refuse(f"panel: {exc}")
    if not args.command:
        return _refuse("the seat's command comes after `--`")
    # Why: a turn the core would refuse must not cost a model run first.
    participants = [item["id"] for item in panel["seats"] if item["role"] != "judge"]
    if args.seat not in participants:
        return _refuse(f"seat {args.seat!r} is not a participant of this panel (the judge takes no turns)")
    if not 1 <= args.round <= panel["budget"]["max_rounds"]:
        return _refuse(f"round must be from 1 to {panel['budget']['max_rounds']}")
    if args.round == 1 and args.seen:
        return _refuse("the first round is blind: a round-1 seat cannot have seen other turns")
    subject = None
    if args.subject:
        try:
            subject = Path(args.subject).read_bytes()
        except OSError as exc:
            return _refuse(f"subject: {exc}")
    try:
        before, _ = fingerprint(root)
    except (RuntimeError, OSError) as exc:
        return _refuse(f"cannot prove read-only outside a git worktree with a commit ({exc})")
    context = {"panel": panel, "seat": args.seat, "round": args.round, "seen_turns": list(args.seen)}
    # Why: subprocess.run's timeout kills only the direct child; the core's
    # run_bounded stops the whole process tree, so a CLI's worker cannot outlive the seat.
    state, code, stdout, _ = run_bounded(list(args.command), timeout=args.timeout, cwd=str(root),
                                         stdin=json.dumps(context).encode("utf-8"))
    try:
        after, paths = fingerprint(root)
    except (RuntimeError, OSError) as exc:
        return _refuse(f"seat {args.seat} left the repository unreadable to git; the turn is invalid ({exc})")
    if after != before:
        # Why: checked before anything else, and before this runner writes a byte, so the
        # verdict is about the seat alone.
        return _refuse(f"seat {args.seat} wrote to its worktree; the turn is invalid. Paths now differing "
                       f"from HEAD: {', '.join(paths) or '(the diff changed)'}")
    if state != "exited" or code != 0:
        why = "timed out" if state == "timeout" else "could not start" if state == "could-not-start" else f"exited {code}"
        print(f"house_session: seat {args.seat} {why}: not judged, no turn written", file=sys.stderr)
        return 1
    try:
        answer = json.loads(stdout.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _refuse(f"seat {args.seat} did not print one JSON answer")
    if not isinstance(answer, dict):
        return _refuse("the answer must be a JSON object")
    extra = sorted(set(answer) - ANSWER_KEYS)
    if extra:
        return _refuse(f"the answer carries keys the contract does not define: {extra}")
    text = answer.get("text")
    if not isinstance(text, str) or not text.strip():
        return _refuse("the answer needs its verbatim text")
    try:
        lens = json.loads(text)
    except json.JSONDecodeError:
        lens = None
    if isinstance(lens, dict) and str(lens.get("schema", "")).startswith("hpp.findings/"):
        try:
            check_findings(lens, subject)
        except FindingsError as exc:
            return _refuse(f"the lens answered with findings that do not check: {exc}")
    turn = {"schema": TURN_SCHEMA, "panel_sha256": panel["sha256"], "seat": args.seat, "round": args.round,
            "position": answer.get("position"), "confidence": answer.get("confidence"),
            "claims": answer.get("claims", []), "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "chars": len(text), "seen_turns": list(args.seen)}
    try:
        turn = normalise_turn(turn, panel)
    except DeliberationError as exc:
        return _refuse(f"turn refused: {exc}")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{args.seat}-r{args.round}"
    (out / f"{stem}.txt").write_bytes(text.encode("utf-8"))
    (out / f"{stem}.turn.json").write_text(json.dumps(turn, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "turn", "turn": (out / f"{stem}.turn.json").as_posix(), "sha256": turn["sha256"]}))
    return 0


def _self_test() -> int:
    import tempfile

    only_maker = families("claude", which=lambda name: None)
    assert only_maker["status"] == "DEFERRED" and only_maker["families"] == ["anthropic"], only_maker
    two = families("claude", which=lambda name: "/bin/codex" if name == "codex" else None)
    assert two["status"] == "ready" and two["families"] == ["anthropic", "openai"], two
    unknown = families("claude", which=lambda name: "/bin/agent" if name == "agent" else None)
    assert unknown["status"] == "DEFERRED" and unknown["unknown_family"] == ["cursor"], unknown
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        try:
            for command in (["init", "-q"], ["config", "user.email", "t@example.invalid"],
                            ["config", "user.name", "t"]):
                _git(root, *command)
            (root / "a.txt").write_text("a\n", encoding="utf-8")
            _git(root, "add", "a.txt")
            _git(root, "commit", "-q", "-m", "base")
        except (RuntimeError, OSError) as exc:
            print(f"self-test PARTIAL — families OK; git unavailable, fingerprint not exercised ({exc})")
            return 0
        clean, _ = fingerprint(root)
        assert fingerprint(root)[0] == clean, "the fingerprint must be stable when nothing moved"
        (root / "a.txt").write_text("a\nb\n", encoding="utf-8")
        edited, paths = fingerprint(root)
        assert edited != clean and paths == ["a.txt"], paths
        (root / "a.txt").write_text("a\nb\nc\n", encoding="utf-8")
        assert fingerprint(root)[0] != edited, "a second edit to a modified file must still move it"
        (root / "new.txt").write_text("x", encoding="utf-8")
        assert fingerprint(root)[1] == ["a.txt", "new.txt"]
    print("self-test OK — one family defers, two are ready, and every write moves the fingerprint")
    return 0


def main(argv: list[str]) -> int:
    if argv == ["--self-test"]:
        return _self_test()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="action", required=True)
    fam = sub.add_parser("families", help="which model families this host can seat")
    fam.add_argument("--maker", default="claude", choices=tuple(PROVIDERS))
    fam.add_argument("--require", action="store_true")
    run = sub.add_parser("seat", help="run one seat for one round and write its turn")
    run.add_argument("--panel", required=True)
    run.add_argument("--seat", required=True)
    run.add_argument("--round", type=int, required=True)
    run.add_argument("--out", required=True)
    run.add_argument("--seen", nargs="*", default=[])
    run.add_argument("--root", default=".")
    run.add_argument("--timeout", type=float, default=600.0)
    run.add_argument("--subject", help="the change under review; a lens's findings must name it by its sha256")
    run.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.action == "families":
        report = families(args.maker)
        print(json.dumps(report))
        if report["status"] == "ready":
            return 0
        return 2 if args.require else 1
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    return seat(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
