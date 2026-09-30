"""lane-kit's board verifies `--evidence-record` through the HPP core -- and that branch has to RUN.

Why this file exists (2.6.1): `lane_board.py --self-test` covers `set <item> CHECKPOINT-READY
--evidence-record` in two branches. The fail-closed one (core absent) always runs. The one that
matters -- a `valid` record accepted, a `not-evidence` / `blocked` / missing record refused, the
event storing `{path, record_sha256, id}` -- runs only when `hpp.evidence` is importable. The
installer runs the module's self-test WITHOUT the core on the path, so in CI that branch never ran,
and the self-test said so in its own summary while still exiting 0.

This test runs the self-test of the lane-kit that ships in the emitted tree with the product root
on PYTHONPATH and asserts, from the summary line, that the branch ran. It lives in the product
suite because only the emitted tree has `multi-session/`; in the source tree it skips and says why.

Issue #16: run from a checkout with no PYTHONPATH, the self-test ran 20 of its 41 checks, and a
contributor running the documented command got the partial result without noticing. Inside a
checkout (`multi-session/<kit>/scripts/` with `hpp/__init__.py` at the root) the self-test now puts
that root on sys.path for itself only and says so. A kit copied anywhere else, and every command
other than the self-test, still needs the core installed or on PYTHONPATH.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
MULTI_SESSION = PRODUCT_ROOT / "multi-session"
# The summary line lane_board.py prints for each branch of its evidence-record self-test.
RAN = "HPP core importable: the valid / not-evidence / blocked branch ran"
NOT_RAN = "HPP core NOT importable"
FROM_CHECKOUT = "HPP core from the source checkout"


def _board() -> Path:
    if not MULTI_SESSION.is_dir():
        pytest.skip("multi-session/ exists only in the emitted tree (the release step assembles the "
                    "modules there); this is the source tree, where lane-kit is not laid out")
    boards = sorted(MULTI_SESSION.glob("lane-kit-*/scripts/lane_board.py"))
    assert len(boards) == 1, f"expected exactly one emitted lane-kit, found {[b.as_posix() for b in boards]}"
    return boards[0]


def _self_test(board: Path, cwd: Path, with_core: bool) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    cmd = [sys.executable, "-X", "utf8"]
    if with_core:
        env["PYTHONPATH"] = str(PRODUCT_ROOT)
    else:
        # Why: `-I` ignores PYTHON* variables and the user site; `-S` keeps site-packages off the path,
        # so a pip-installed copy of the product cannot make the core importable behind this test's back.
        cmd += ["-I", "-S"]
    return subprocess.run([*cmd, str(board), "--self-test"], cwd=cwd, env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=300)


def _copied_outside(board: Path, tmp_path: Path) -> Path:
    """The same lane-kit, copied where no checkout surrounds it (as an installed kit would sit)."""
    target = tmp_path / "kits" / board.parent.parent.name
    shutil.copytree(board.parent.parent, target, ignore=shutil.ignore_patterns("__pycache__"))
    return target / "scripts" / "lane_board.py"


def test_the_evidence_record_branch_runs_with_the_core_on_the_path(tmp_path: Path) -> None:
    result = _self_test(_board(), tmp_path, with_core=True)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    assert RAN in result.stdout, (
        "the self-test passed WITHOUT verifying a real record -- the core was not importable:\n"
        + result.stdout[-1500:])
    assert NOT_RAN not in result.stdout


def test_CONTROLE_without_the_core_the_summary_says_the_branch_did_not_run(tmp_path: Path) -> None:
    """The assertion above reads a summary line; this proves the line discriminates. The kit is copied
    out of the checkout: inside it the self-test now finds the core on purpose (issue #16)."""
    result = _self_test(_copied_outside(_board(), tmp_path), tmp_path, with_core=False)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    assert NOT_RAN in result.stdout and RAN not in result.stdout, result.stdout[-1500:]
    assert FROM_CHECKOUT not in result.stdout, "a kit outside a checkout claimed to have found one"


def test_from_a_checkout_the_self_test_runs_every_check_without_pythonpath(tmp_path: Path) -> None:
    """Issue #16: from the repository root and from any other directory, with no PYTHONPATH and no
    site-packages, the self-test runs the evidence branch and says where the core came from."""
    board = _board()
    for cwd in (PRODUCT_ROOT, tmp_path):
        result = _self_test(board, cwd, with_core=False)
        assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
        assert RAN in result.stdout and NOT_RAN not in result.stdout, (
            f"from {cwd} the self-test still skipped the evidence branch: {result.stdout[-1500:]}")
        assert FROM_CHECKOUT in result.stdout, "the self-test did not say it took the core from the checkout"


def test_CONTROLE_a_normal_command_still_needs_the_core(tmp_path: Path) -> None:
    """The discovery is for the self-test only: `set --evidence-record` without the core is refused
    (exit 2) and writes nothing, even from inside the checkout."""
    record = tmp_path / "record.json"
    record.write_text(json.dumps({"schema": "hpp.evidence/v1"}), encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["CLAUDE_PROJECT_DIR"] = str(project)
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-S", str(_board()), "set", "ITEM-1", "CHECKPOINT-READY",
         "--lane", "lane-1", "--role", "executor", "--model", "claude-opus-5-5", "--evidence-record", str(record)],
        cwd=project, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    assert result.returncode == 2, f"exit {result.returncode}: {result.stderr[-1500:]}"
    assert "needs the HPP core" in result.stderr, result.stderr[-1500:]
    assert not (project / ".claude" / "lanes" / "board.jsonl").exists(), "a refused command wrote the board"
