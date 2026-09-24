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
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
MULTI_SESSION = PRODUCT_ROOT / "multi-session"
# The summary line lane_board.py prints for each branch of its evidence-record self-test.
RAN = "HPP core importable: the valid / not-evidence / blocked branch ran"
NOT_RAN = "HPP core NOT importable"


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
        # Why: `-S` keeps site-packages off the path, so a pip-installed copy of the product cannot
        # make the core importable behind this control's back.
        cmd.append("-S")
    return subprocess.run([*cmd, str(board), "--self-test"], cwd=cwd, env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=300)


def test_the_evidence_record_branch_runs_with_the_core_on_the_path(tmp_path: Path) -> None:
    result = _self_test(_board(), tmp_path, with_core=True)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    assert RAN in result.stdout, (
        "the self-test passed WITHOUT verifying a real record -- the core was not importable:\n"
        + result.stdout[-1500:])
    assert NOT_RAN not in result.stdout


def test_CONTROLE_without_the_core_the_summary_says_the_branch_did_not_run(tmp_path: Path) -> None:
    """The assertion above reads a summary line; this proves the line discriminates."""
    result = _self_test(_board(), tmp_path, with_core=False)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    assert NOT_RAN in result.stdout and RAN not in result.stdout, result.stdout[-1500:]
