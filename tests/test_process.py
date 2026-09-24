"""The bounded runner every declared command goes through.

A timeout that waits for a grandchild's pipe is not a timeout. These tests start commands that
leave a descendant holding stdout, and measure the wall clock.
"""
from __future__ import annotations

import os
import sys
import time

import pytest

from hpp._process import MAX_TIMEOUT, run_bounded, valid_timeout

# A helper that inherits stdout and outlives its parent; it stops by itself after `seconds`.
# The bounds below leave wide room between fixed (~2-4 s) and broken (~20 s) so a loaded machine
# does not turn a timing margin into a flaky failure.
def _leaves_helper(seconds: float, then: str) -> list[str]:
    helper = f"import time; time.sleep({seconds})"
    code = ("import subprocess, sys\n"
            f"subprocess.Popen([sys.executable, '-c', {helper!r}])\n" + then)
    return [sys.executable, "-c", code]


def test_CONTROLE_a_plain_command_returns_its_exit_code_and_output():
    state, code, out, err = run_bounded([sys.executable, "-c", "import sys; print('ok'); sys.exit(3)"], timeout=10)
    assert (state, code, out.strip()) == ("exited", 3, b"ok")


def test_stdin_reaches_the_command():
    state, code, out, _ = run_bounded([sys.executable, "-c", "import sys; print(sys.stdin.read().upper())"],
                                      timeout=10, stdin=b"abc")
    assert (state, code, out.strip()) == ("exited", 0, b"ABC")


def test_a_command_that_exits_is_not_held_by_a_helper_on_its_pipe():
    started = time.monotonic()
    state, code, out, _ = run_bounded(_leaves_helper(20, "print('[1]')"), timeout=30)
    assert (state, code, out.strip()) == ("exited", 0, b"[1]")
    assert time.monotonic() - started < 12


def test_a_timeout_bounds_the_wait_even_when_a_helper_holds_the_pipe():
    started = time.monotonic()
    state, code, _, _ = run_bounded(_leaves_helper(20, "import time; time.sleep(20)"), timeout=1.5)
    assert (state, code) == ("timeout", None)
    assert time.monotonic() - started < 12


def test_a_command_that_cannot_start_is_reported():
    assert run_bounded([os.path.join(os.sep, "no", "such", "binary")], timeout=5)[0] == "could-not-start"


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan"), MAX_TIMEOUT + 1, True, "5"])
def test_invalid_timeouts_are_rejected(value):
    assert not valid_timeout(value)


def test_CONTROLE_ordinary_timeouts_are_accepted():
    assert valid_timeout(0.5) and valid_timeout(600) and valid_timeout(MAX_TIMEOUT)
