#!/usr/bin/env python3
"""Build the throwaway project the Lane Dashboard demo is recorded from, through lane-kit's own writers.

The README's animated demo of `lane_dashboard.py` shows a board. That board is not drawn and not
written by hand: this script builds it in an empty directory by calling the same three writers a
real project uses, each as a command, each with the exit status it must return, and it stops on
any other status. So every rule the kit enforces in code also holds in the demo: a checkpoint only
from the lane that claimed the item and only with evidence, a verdict only from another lane and
another model family, MERGED only after VERIFIED.

    hooks/_lane_io.py register     three lanes: exec-a and exec-b (executors), rev-a (reviewer)
    scripts/lane_board.py          six items, EXAMPLE-1 to EXAMPLE-6, one in every column of the page:
                                   building, ready for review, in review, two decisions (a red item
                                   VERIFIED and waiting for the operator's approval, a NEEDS-FIX), merged
    scripts/lane_dashboard.py      three specs in the backlog, EXAMPLE-7 to EXAMPLE-9; EXAMPLE-8 depends
                                   spec add                    on EXAMPLE-7, so the backlog plans two waves

The ids are EXAMPLE-* on purpose: a board of plausible real ids would be read as somebody's work.
The directory is also made a git repository of its own (`git init`, no commit): served from inside
another repository, the dashboard would add that repository's other worktrees to the page. The
states, lanes and specs are the same on every run; the timestamps are the run's own. A registered
lane stays alive for ten minutes (lane-kit's default), which is the window for recording it.

This is a maintainer tool, like `render_terminal_svg.py`: it is not part of the package and needs
only the standard library, `git`, and a lane-kit directory (`multi-session/lane-kit-<version>` in
this repository, or `--lane-kit`). `scripts/record_lane_dashboard.py` runs it before recording.

    python scripts/seed_lane_dashboard_demo.py --out demo-project
    python scripts/seed_lane_dashboard_demo.py --out demo-project --lane-kit multi-session/lane-kit-1.8.1

Exit: 0 built · 1 a writer returned a status the story does not declare · 2 invalid usage, or --out
is a directory that is not empty (nothing in it is touched).
"""
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXECUTOR_MODEL = "claude-opus-5-5"
REVIEWER_MODEL = "gpt-5.6"
LANES = (("exec-a", "executor", EXECUTOR_MODEL), ("exec-b", "executor", EXECUTOR_MODEL),
         ("rev-a", "reviewer", REVIEWER_MODEL))

_EXEC_A = ("--lane", "exec-a", "--role", "executor", "--model", EXECUTOR_MODEL)
_EXEC_B = ("--lane", "exec-b", "--role", "executor", "--model", EXECUTOR_MODEL)
_REVIEW = ("--lane", "rev-a", "--role", "reviewer", "--model", REVIEWER_MODEL)
_VERDICT = (*_REVIEW, "--verdict-by-lane", "rev-a", "--verdict-by-model", REVIEWER_MODEL)

# The writers, by the path each has inside a lane-kit directory.
REGISTRY, BOARD, DASHBOARD = "hooks/_lane_io.py", "scripts/lane_board.py", "scripts/lane_dashboard.py"

Step = tuple[str, tuple[str, ...], int]  # (writer, argv after the script, the exit status it must return)


def _build(item: str, lane: tuple[str, ...], evidence: str = "", tag: str = "green") -> list[Step]:
    steps: list[Step] = [(BOARD, ("claim", item, *lane, "--tag", tag), 0),
                         (BOARD, ("set", item, "BUILDING", *lane), 0)]
    if evidence:
        steps.append((BOARD, ("set", item, "CHECKPOINT-READY", *lane, "--evidence", evidence), 0))
    return steps


def _review(item: str) -> list[Step]:
    return [(BOARD, ("set", item, "UNDER-REVIEW", *_REVIEW), 0)]


def _spec(spec_id: str, title: str, acceptance: str, priority: int, *depends: str) -> Step:
    extra = [value for dependency in depends for value in ("--depends-on", dependency)]
    return (DASHBOARD, ("spec", "add", "--id", spec_id, "--title", title, "--acceptance", acceptance,
                        *extra, "--priority", str(priority), "--create-plan"), 0)


# The story, in the order the events are written (the page sorts each column newest first).
STEPS: tuple[Step, ...] = (
    *((REGISTRY, ("register", "--lane", lane, "--role", role, "--model", model, "--session", f"demo-{lane}"), 0)
      for lane, role, model in LANES),
    # merged: built by exec-a, verified by rev-a, merged
    *_build("EXAMPLE-5", _EXEC_A, "exit=0 sha=1f4c2ab"), *_review("EXAMPLE-5"),
    (BOARD, ("set", "EXAMPLE-5", "VERIFIED", *_VERDICT), 0),
    (BOARD, ("set", "EXAMPLE-5", "MERGED", *_REVIEW), 0),
    # a red item, verified: merging it waits for the operator's approval
    *_build("EXAMPLE-2", _EXEC_A, "exit=0 sha=9b7e014", tag="red"), *_review("EXAMPLE-2"),
    (BOARD, ("set", "EXAMPLE-2", "VERIFIED", *_VERDICT), 0),
    # sent back: the reviewer found the checkpoint failing
    *_build("EXAMPLE-4", _EXEC_B, "exit=1 sha=7a30ce5"), *_review("EXAMPLE-4"),
    (BOARD, ("set", "EXAMPLE-4", "NEEDS-FIX", *_VERDICT, "--evidence", "2 of 14 tests fail"), 0),
    # in review, ready for review, building
    *_build("EXAMPLE-6", _EXEC_B, "exit=0 sha=5d02e41"), *_review("EXAMPLE-6"),
    *_build("EXAMPLE-3", _EXEC_B, "exit=0 sha=4c1d88f"),
    *_build("EXAMPLE-1", _EXEC_A),
    # the backlog: EXAMPLE-8 waits for EXAMPLE-7, so the plan has two waves
    _spec("EXAMPLE-7", "Export the board as CSV", "the export lists every item with its last state", 3),
    _spec("EXAMPLE-8", "Filter the export by lane", "a filtered export holds only the items of that lane", 2, "EXAMPLE-7"),
    _spec("EXAMPLE-9", "Show the heartbeat age of each lane", "the age matches the heartbeat in the registry", 1),
)

# What the recording does to the seeded board while it records: one terminal command that moves
# EXAMPLE-1 from "Building" to "Ready for review" (the page follows by itself), and the dialog of
# the one action the page offers on the red item, whose terminal equivalent it shows.
LIVE_STEP: Step = (BOARD, ("set", "EXAMPLE-1", "CHECKPOINT-READY", *_EXEC_A, "--evidence", "exit=0 sha=3e5a1c9"), 0)
APPROVE_ITEM = "EXAMPLE-2"


def display(step: Step) -> str:
    """The command as a person would type it from the kit's directory: `python lane_board.py ...`."""
    writer, argv, _status = step
    return shlex.join(["python", Path(writer).name, *argv])


def refuse(message: str, status: int) -> SystemExit:
    print(f"seed: {message}", file=sys.stderr)
    return SystemExit(status)


def find_lane_kit(explicit: Path | None) -> Path:
    """The lane-kit directory: --lane-kit, or the one `multi-session/lane-kit-*` of this repository."""
    if explicit is not None:
        kit = explicit.resolve()
    else:
        found = sorted(p for p in (ROOT / "multi-session").glob("lane-kit-*") if p.is_dir())
        if len(found) != 1:
            raise refuse(f"found {len(found)} multi-session/lane-kit-* directories; pass --lane-kit DIR", 2)
        kit = found[0].resolve()
    missing = [writer for writer in (REGISTRY, BOARD, DASHBOARD) if not (kit / writer).is_file()]
    if missing:
        raise refuse(f"{kit.name} is not a lane-kit directory (missing {', '.join(missing)})", 2)
    return kit


def environment(project: Path) -> dict[str, str]:
    """The writers' environment: the project named explicitly, and nothing inherited that would move
    the story elsewhere -- a lane identity, a lanes.yaml of another project, or a GIT_* variable."""
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_") and key not in ("CLAUDE_LANE_ID", "CLAUDE_LANE_ROLE", "CLAUDE_LANE_MODEL",
                                                          "LANE_KIT_CONFIG")}
    env.update(CLAUDE_PROJECT_DIR=str(project), PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    return env


def run_step(kit: Path, project: Path, step: Step) -> subprocess.CompletedProcess:
    """Run one writer and return what it printed; a status other than the declared one stops the run."""
    writer, argv, declared = step
    extra = ("--project-dir", str(project)) if writer == DASHBOARD else ()
    result = subprocess.run([sys.executable, "-X", "utf8", str(kit / writer), *argv, *extra], cwd=project,
                            env=environment(project), capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=120)
    if result.returncode != declared:
        raise refuse(f"{display(step)} exited {result.returncode}; the story declares {declared}\n"
                     f"{result.stdout}{result.stderr}", 1)
    return result


def init_repository(project: Path) -> None:
    """`git init` with branch `main`, under an empty configuration: no global hook or template runs."""
    git = shutil.which("git")
    if git is None:
        raise refuse("git is not on PATH; the demo project must be a repository of its own", 2)
    config = project / ".git-seed-config"
    config.write_bytes(b"")
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=str(config))
    try:
        for args in (["init", "-q"], ["symbolic-ref", "HEAD", "refs/heads/main"]):
            done = subprocess.run([git, *args], cwd=project, env=env, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=60)
            if done.returncode != 0:
                raise refuse(f"git {' '.join(args)} exited {done.returncode}:\n{done.stderr}", 1)
    finally:
        config.unlink(missing_ok=True)


def seed(kit: Path, project: Path) -> list[str]:
    """Build the demo in `project` (created; it must not hold anything) and return the commands run."""
    if project.exists() and (not project.is_dir() or any(project.iterdir())):
        raise refuse(f"{project.name} is not empty; the demo is built only in a new or empty directory", 2)
    project.mkdir(parents=True, exist_ok=True)
    init_repository(project)
    commands = []
    for step in STEPS:
        run_step(kit, project, step)
        commands.append(display(step))
    return commands


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="the demo project (new or empty directory)")
    parser.add_argument("--lane-kit", type=Path, help="a lane-kit directory (default: multi-session/lane-kit-*)")
    args = parser.parse_args(argv)
    kit = find_lane_kit(args.lane_kit)
    project = args.out.resolve()
    commands = seed(kit, project)
    print(f"seeded {project.name}: {len(commands)} commands through {kit.name}'s writers")
    for command in commands:
        print(f"  {command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
