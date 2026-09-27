"""lane-kit's board: the operator's two hand-offs (`release-fix`, `start-review`) and the red gate.

Why this file exists (Lane Dashboard): the dashboard lets the operator route a NEEDS-FIX to a named
executor and open a review for a named reviewer. Both are writes to the board, so they live in the
writer (`lane_board.py`), never in the dashboard, and they are proved here against the emitted
lane-kit through its CLI, the same way a lane calls it.

It also pins a gate that did not hold. Measured before the fix: a red item reached MERGED without
`--human-approved` when the caller simply omitted `--tag` -- the flag defaults to green, the check
read the flag instead of the item, and the MERGED event recorded the item as green.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
MULTI_SESSION = PRODUCT_ROOT / "multi-session"

BUILDER = ("exec-a", "claude-opus-4-8")
REVIEWER = ("rev-x", "gpt-5.6")


def _kit() -> Path:
    if not MULTI_SESSION.is_dir():
        pytest.skip("multi-session/ exists only in the emitted tree; this is the source tree")
    kits = sorted(board.parents[1] for board in MULTI_SESSION.glob("lane-kit-*/scripts/lane_board.py"))
    assert len(kits) == 1, f"expected exactly one emitted lane-kit, found {[k.as_posix() for k in kits]}"
    return kits[0]


class Board:
    def __init__(self, project: Path) -> None:
        self.project = project
        self.kit = _kit()
        self.env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}

    def _run(self, script: str, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-X", "utf8", str(self.kit / script), *args],
                              cwd=self.project, env=self.env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=60)

    def lb(self, *args: str) -> subprocess.CompletedProcess:
        return self._run("scripts/lane_board.py", *args)

    def ok(self, *args: str) -> dict:
        result = self.lb(*args)
        assert result.returncode == 0, f"{args}: {result.stderr}"
        return json.loads(result.stdout)

    def register(self, lane: str, role: str, model: str) -> None:
        result = self._run("hooks/_lane_io.py", "register", "--lane", lane, "--role", role, "--model", model)
        assert result.returncode == 0, result.stderr

    def stop_heartbeat(self, lane: str) -> None:
        """Push a lane's heartbeat into the past, as a lane that stopped beating would leave it."""
        path = self.project / ".claude" / "lanes" / "registry.json"
        registry = json.loads(path.read_text(encoding="utf-8"))
        registry["lanes"][lane]["heartbeat_at"] = "2000-01-01T00:00:00+00:00"
        path.write_text(json.dumps(registry), encoding="utf-8")

    def events(self, item: str) -> list:
        path = self.project / ".claude" / "lanes" / "board.jsonl"
        return [e for e in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line)
                if e.get("item_id") == item]

    def to_checkpoint(self, item: str, tag: str = "green") -> None:
        lane, model = BUILDER
        self.ok("claim", item, "--lane", lane, "--role", "executor", "--model", model, "--tag", tag)
        self.ok("set", item, "BUILDING", "--lane", lane, "--role", "executor", "--model", model, "--tag", tag)
        self.ok("set", item, "CHECKPOINT-READY", "--lane", lane, "--role", "executor", "--model", model,
                "--evidence", "pytest -q: 3 passed, exit=0", "--tag", tag)

    def to_needs_fix(self, item: str) -> None:
        self.to_checkpoint(item)
        lane, model = REVIEWER
        self.ok("set", item, "UNDER-REVIEW", "--lane", lane, "--role", "reviewer", "--model", model)
        self.ok("set", item, "NEEDS-FIX", "--lane", lane, "--role", "reviewer", "--model", model,
                "--verdict-by-lane", lane, "--verdict-by-model", model,
                "--evidence", "test_login fails: the token is never refreshed")


@pytest.fixture
def board(tmp_path: Path) -> Board:
    return Board(tmp_path)


# --- the red gate -------------------------------------------------------------------------------

def _verified_red(board: Board, item: str) -> None:
    board.to_checkpoint(item, tag="red")
    lane, model = REVIEWER
    board.ok("set", item, "UNDER-REVIEW", "--lane", lane, "--role", "reviewer", "--model", model)
    board.ok("set", item, "VERIFIED", "--lane", lane, "--role", "reviewer", "--model", model,
             "--verdict-by-lane", lane, "--verdict-by-model", model)


def test_a_red_item_is_not_merged_when_the_caller_omits_the_tag(board: Board) -> None:
    _verified_red(board, "R1")
    result = board.lb("set", "R1", "MERGED", "--lane", "exec-a", "--role", "executor", "--model", "claude-opus-4-8")
    assert result.returncode == 1, f"a red item merged without --human-approved: {result.stdout}"
    assert "human-approved" in result.stderr


def test_a_red_item_stays_red_on_every_event_it_receives(board: Board) -> None:
    _verified_red(board, "R2")
    merged = board.ok("set", "R2", "MERGED", "--lane", "operator", "--role", "operator", "--model", "human",
                      "--human-approved")
    assert merged["tag"] == "red", f"the MERGED event downgraded the item to {merged['tag']}"


def test_CONTROLE_a_green_item_merges_without_human_approval(board: Board) -> None:
    """The refusal above is about red: a green item with the same history must merge."""
    board.to_checkpoint("G1")
    lane, model = REVIEWER
    board.ok("set", "G1", "UNDER-REVIEW", "--lane", lane, "--role", "reviewer", "--model", model)
    board.ok("set", "G1", "VERIFIED", "--lane", lane, "--role", "reviewer", "--model", model,
             "--verdict-by-lane", lane, "--verdict-by-model", model)
    merged = board.ok("set", "G1", "MERGED", "--lane", "exec-a", "--role", "executor", "--model", "claude-opus-4-8")
    assert merged["tag"] == "green"


# --- release-fix --------------------------------------------------------------------------------

def test_set_cannot_write_FIX_QUEUED(board: Board) -> None:
    board.to_needs_fix("F0")
    result = board.lb("set", "F0", "FIX-QUEUED", "--lane", "exec-b", "--role", "executor", "--model", "gpt-5.6")
    assert result.returncode == 1 and "release-fix" in result.stderr, result.stderr


def test_release_fix_queues_the_fix_for_a_live_executor_and_delivers_a_kickoff(board: Board) -> None:
    board.to_needs_fix("F1")
    board.register("exec-b", "executor", "gpt-5.6")
    event = board.ok("release-fix", "F1", "--target-lane", "exec-b")
    assert event["state"] == "FIX-QUEUED" and event["target_lane"] == "exec-b"
    assert event["role"] == "operator"
    kickoff = board.project / event["kickoff"]
    text = kickoff.read_text(encoding="utf-8")
    assert "exec-b" in text and "the token is never refreshed" in text, text


def test_release_fix_requires_NEEDS_FIX(board: Board) -> None:
    board.to_checkpoint("F2")
    board.register("exec-b", "executor", "gpt-5.6")
    result = board.lb("release-fix", "F2", "--target-lane", "exec-b")
    assert result.returncode == 1 and "NEEDS-FIX" in result.stderr, result.stderr


def test_release_fix_refuses_a_lane_that_is_not_a_live_executor(board: Board) -> None:
    board.to_needs_fix("F3")
    board.register("rev-y", "reviewer", "gemini-2.5")
    not_executor = board.lb("release-fix", "F3", "--target-lane", "rev-y")
    assert not_executor.returncode == 1 and "executor" in not_executor.stderr, not_executor.stderr
    unknown = board.lb("release-fix", "F3", "--target-lane", "nobody")
    assert unknown.returncode == 1, unknown.stdout


def test_only_the_named_lane_takes_a_queued_fix(board: Board) -> None:
    board.to_needs_fix("F4")
    board.register("exec-b", "executor", "gpt-5.6")
    board.ok("release-fix", "F4", "--target-lane", "exec-b")
    stolen = board.lb("set", "F4", "BUILDING", "--lane", "exec-c", "--role", "executor", "--model", "gemini-2.5")
    assert stolen.returncode == 1 and "exec-b" in stolen.stderr, stolen.stderr
    board.ok("set", "F4", "BUILDING", "--lane", "exec-b", "--role", "executor", "--model", "gpt-5.6")


def test_a_fix_queued_for_a_dead_lane_can_be_rerouted_and_says_so(board: Board) -> None:
    board.to_needs_fix("F5")
    board.register("exec-b", "executor", "gpt-5.6")
    board.ok("release-fix", "F5", "--target-lane", "exec-b")
    board.register("exec-c", "executor", "gemini-2.5")
    alive = board.lb("release-fix", "F5", "--target-lane", "exec-c")
    assert alive.returncode == 1 and "alive" in alive.stderr, "a fix in progress was taken from a live lane"
    board.stop_heartbeat("exec-b")
    event = board.ok("release-fix", "F5", "--target-lane", "exec-c")
    assert event["target_lane"] == "exec-c" and event["reroute"]["from"] == "exec-b", event
    text = (board.project / event["kickoff"]).read_text(encoding="utf-8")
    assert "the token is never refreshed" in text, "the rerouted kickoff lost the NEEDS-FIX direction"


def test_the_fix_builder_family_cannot_review_the_fix(board: Board) -> None:
    """exec-b (gpt) built the fix of an item exec-a (claude) claimed: a gpt reviewer is checking gpt work."""
    board.to_needs_fix("F8")
    board.register("exec-b", "executor", "gpt-5.6")
    board.ok("release-fix", "F8", "--target-lane", "exec-b")
    board.ok("set", "F8", "BUILDING", "--lane", "exec-b", "--role", "executor", "--model", "gpt-5.6")
    board.ok("set", "F8", "CHECKPOINT-READY", "--lane", "exec-b", "--role", "executor", "--model", "gpt-5.6",
             "--evidence", "pytest -q: 4 passed, exit=0")
    board.ok("set", "F8", "UNDER-REVIEW", "--lane", "rev-z", "--role", "reviewer", "--model", "gpt-5.5")
    same_family = board.lb("set", "F8", "VERIFIED", "--lane", "rev-z", "--role", "reviewer", "--model", "gpt-5.5",
                           "--verdict-by-lane", "rev-z", "--verdict-by-model", "gpt-5.5")
    assert same_family.returncode == 1 and "family" in same_family.stderr, same_family.stdout
    board.ok("set", "F8", "VERIFIED", "--lane", "rev-g", "--role", "reviewer", "--model", "gemini-2.5",
             "--verdict-by-lane", "rev-g", "--verdict-by-model", "gemini-2.5")


def test_the_executor_may_still_resume_a_NEEDS_FIX_directly(board: Board) -> None:
    """Routing through the operator is an option, not a new obligation for existing flows."""
    board.to_needs_fix("F6")
    board.ok("set", "F6", "BUILDING", "--lane", "exec-a", "--role", "executor", "--model", "claude-opus-4-8")


# --- start-review -------------------------------------------------------------------------------

def test_start_review_opens_the_review_for_a_live_reviewer(board: Board) -> None:
    board.to_checkpoint("V1")
    board.register("rev-x", "reviewer", "gpt-5.6")
    event = board.ok("start-review", "V1", "--target-lane", "rev-x")
    assert event["state"] == "UNDER-REVIEW" and event["target_lane"] == "rev-x"
    text = (board.project / event["kickoff"]).read_text(encoding="utf-8")
    assert "pytest -q: 3 passed" in text and "rev-x" in text, text


def test_start_review_refuses_the_builder_lane(board: Board) -> None:
    board.to_checkpoint("V2")
    board.register("exec-a", "reviewer", "gpt-5.6")
    result = board.lb("start-review", "V2", "--target-lane", "exec-a")
    assert result.returncode == 1 and "maker" in result.stderr, result.stderr


def test_start_review_requires_a_checkpoint(board: Board) -> None:
    board.ok("claim", "V3", "--lane", "exec-a", "--role", "executor", "--model", "claude-opus-4-8")
    board.register("rev-x", "reviewer", "gpt-5.6")
    result = board.lb("start-review", "V3", "--target-lane", "rev-x")
    assert result.returncode == 1 and "CHECKPOINT-READY" in result.stderr, result.stderr


def test_the_render_names_the_lane_a_fix_is_queued_for(board: Board) -> None:
    board.to_needs_fix("F7")
    board.register("exec-b", "executor", "gpt-5.6")
    board.ok("release-fix", "F7", "--target-lane", "exec-b")
    rendered = board.lb("render")
    assert rendered.returncode == 0, rendered.stderr
    assert "FIX-QUEUED" in rendered.stdout and "exec-b" in rendered.stdout, rendered.stdout
