"""Color and animation degrade honestly: NO_COLOR zeroes escapes, output with
no TTY has no ANSI, FORCE_COLOR chooses the tier, the palette maps to 256/16
colors in a predictable way, and an ASCII stdout falls to ASCII glyphs without raising.

The control proves that a truecolor Console on a TTY EMITS escapes -- without
this, "zero escapes" would be satisfied by a Console that never colors anything.
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

from hpp import brand, term
from hpp.term import Console

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
ESC = "\033"


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def _run(argv: list[str], env_overrides: dict[str, str], tmp_target: Path) -> subprocess.CompletedProcess:
    env = {key: value for key, value in os.environ.items() if key not in {"NO_COLOR", "FORCE_COLOR", "COLORTERM"}}
    env.update(env_overrides)
    return subprocess.run([sys.executable, "-m", "hpp", "init", "--target", str(tmp_target), "--no-benchmark", *argv],
                          cwd=PRODUCT_ROOT, capture_output=True, env=env, timeout=60)


@pytest.fixture()
def target(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    return workspace


def test_NO_COLOR_zeroes_every_escape_even_with_FORCE_COLOR(target):
    result = _run([], {"NO_COLOR": "1", "FORCE_COLOR": "3"}, target)
    assert result.returncode == 0
    assert ESC.encode() not in result.stdout
    assert b"protocol online." in result.stdout
    assert b"BY RUSHAR LABS" in result.stdout


def test_output_with_no_tty_has_no_ansi_nor_carriage_return(target):
    result = _run([], {}, target)
    assert result.returncode == 0
    assert ESC.encode() not in result.stdout
    assert b"\r\x1b" not in result.stdout
    assert result.stdout.count(b"> ") >= 7


def test_FORCE_COLOR_3_emits_truecolor_from_the_palette(target):
    result = _run([], {"FORCE_COLOR": "3"}, target)
    orange = "\033[38;2;%d;%d;%dm" % brand.PALETTE["signal_orange"]
    assert orange.encode() in result.stdout
    assert b"\033[38;5;" not in result.stdout


def test_FORCE_COLOR_2_and_1_degrade_to_256_and_16_colors(target):
    result_256 = _run([], {"FORCE_COLOR": "2"}, target)
    assert ("\033[38;5;%dm" % term.rgb_to_256(brand.PALETTE["signal_orange"])).encode() in result_256.stdout
    assert b"\033[38;2;" not in result_256.stdout
    result_16 = _run([], {"FORCE_COLOR": "1"}, target)
    assert ("\033[%dm" % term.rgb_to_16(brand.PALETTE["signal_orange"])).encode() in result_16.stdout
    assert b"\033[38;5;" not in result_16.stdout and b"\033[38;2;" not in result_16.stdout


def test_no_animation_removes_the_carriage_return_even_on_a_tty():
    stream = _Tty()
    console = Console(stream=stream, tier="truecolor", animate=False, env={}, width=100)
    console.transient("> loading...")
    console.rewrite("> loaded")
    console.blink_cursor("> done")
    output = stream.getvalue()
    assert "\r" not in output
    assert "> loading..." not in output
    assert output.endswith("> done" + console.glyph("cursor") + "\n")


def test_palette_maps_to_256_and_16_colors_in_a_stable_way():
    assert term.rgb_to_256(brand.PALETTE["signal_orange"]) == 208
    assert term.rgb_to_256(brand.PALETTE["black"]) == 16
    assert term.rgb_to_256(brand.PALETTE["charcoal"]) == 233
    assert term.rgb_to_256(brand.PALETTE["warm_white"]) == 254
    assert term.rgb_to_16(brand.PALETTE["signal_orange"]) == 91
    assert term.rgb_to_16(brand.PALETTE["warm_white"]) == 37
    assert term.rgb_to_16(brand.PALETTE["black"]) == 30


def test_published_palette_matches_the_official_hex_codes():
    assert brand.PALETTE_HEX == {"black": "#000000", "charcoal": "#0F1113", "warm_white": "#F4F1EB", "signal_orange": "#FF6A00"}


@pytest.mark.parametrize("env,isatty,platform,expected", [
    ({"NO_COLOR": "1", "COLORTERM": "truecolor"}, True, "posix", "none"),
    ({"NO_COLOR": ""}, True, "posix", "16"),
    ({}, False, "posix", "none"),
    ({"TERM": "dumb"}, True, "posix", "none"),
    ({"COLORTERM": "truecolor"}, True, "posix", "truecolor"),
    ({"COLORTERM": "24bit"}, True, "posix", "truecolor"),
    ({"TERM": "xterm-256color"}, True, "posix", "256"),
    ({"TERM": "xterm"}, True, "posix", "16"),
    ({"FORCE_COLOR": "0"}, True, "posix", "none"),
    ({"FORCE_COLOR": "1"}, False, "posix", "16"),
    ({"FORCE_COLOR": "2"}, False, "posix", "256"),
    ({"FORCE_COLOR": "true"}, False, "posix", "truecolor"),
])
def test_tier_detection_matrix(env, isatty, platform, expected):
    assert term.detect_tier(stream=io.StringIO(), env=env, isatty=isatty, platform=platform) == expected


def test_windows_without_enableable_VT_falls_to_zero_escape(monkeypatch):
    monkeypatch.setattr(term, "enable_windows_vt", lambda stream=None: False)
    assert term.detect_tier(stream=io.StringIO(), env={}, isatty=True, platform="nt") == "none"


def test_windows_with_VT_enabled_uses_256_and_windows_terminal_truecolor(monkeypatch):
    monkeypatch.setattr(term, "enable_windows_vt", lambda stream=None: True)
    assert term.detect_tier(stream=io.StringIO(), env={}, isatty=True, platform="nt") == "256"
    assert term.detect_tier(stream=io.StringIO(), env={"WT_SESSION": "abc"}, isatty=True, platform="nt") == "truecolor"


def test_enable_windows_vt_never_raises_outside_windows_or_with_no_console():
    stream = io.StringIO()
    result = term.enable_windows_vt(stream)
    assert result in {True, False}


def test_ascii_stdout_falls_to_ascii_glyphs_without_raising(target):
    env = {"PYTHONIOENCODING": "ascii"}
    result = _run(["--no-animation"], env, target)
    assert result.returncode == 0, result.stderr.decode("ascii", "replace")
    assert b"OK greenfield" in result.stdout
    assert b"\xe2" not in result.stdout


def test_ascii_console_swaps_the_glyphs_and_the_separator():
    class Ascii(io.StringIO):
        encoding = "ascii"

    console = Console(stream=Ascii(), tier="none", animate=False, env={}, width=80)
    assert console.glyph("ok") == "OK"
    console.write("a · b — c " + console.glyph("full"))
    assert console.stream.getvalue() == "a - b - c #\n"


def test_logo_fits_in_80_columns_and_compacts_below_that():
    wide = Console(stream=io.StringIO(), tier="none", animate=False, env={}, width=80)
    lines = brand.logo_lines(wide)
    assert max(len(line) for line in lines) <= 80
    assert any(line.strip().startswith("█") for line in lines)
    narrow = Console(stream=io.StringIO(), tier="none", animate=False, env={}, width=40)
    compact = brand.logo_lines(narrow)
    assert any("HOUSE PARTY" in line and "PROTOCOL" in line for line in compact)
    assert max(len(line) for line in compact) <= 40


def test_wordmark_renders_every_letter_of_the_brand():
    for text in brand.WORDMARK:
        rows = brand.render_wordmark(text, "#")
        assert len(rows) == 5 and all(rows)
    with pytest.raises(ValueError):
        brand.render_wordmark("Z", "#")


def test_CONTROLE_truecolor_console_on_a_tty_emits_escapes_and_animates():
    """Control: proves that the instrument knows how to produce the opposite result -- a
    truecolor Console on a TTY ACTUALLY writes ESC and uses \\r in the animation."""
    stream = _Tty()
    slept: list[float] = []
    console = Console(stream=stream, tier="truecolor", animate=True, env={}, width=100, sleep=slept.append)
    assert console.animate is True
    console.transient("> loading...")
    console.rewrite(console.paint("> loaded", brand.PALETTE["signal_orange"]))
    console.blink_cursor("> done")
    output = stream.getvalue()
    assert ESC in output and "\r" in output
    assert "\033[38;2;255;106;0m" in output
    assert slept and all(0 < pause < 0.5 for pause in slept)
