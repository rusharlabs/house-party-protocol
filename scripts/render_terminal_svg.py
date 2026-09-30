#!/usr/bin/env python3
"""Render the real output of `hpp doctor` and `hpp init` as SVG "screenshots" for the README.

A PNG screenshot goes stale the day the output changes and cannot be diffed. These SVGs are
text: the generator runs the two commands against an empty target, keeps the bytes it read, and
paints them in the brand palette with a system monospace font (no font is embedded, nothing is
fetched). Regenerate after any change to the wizard's output:

    python scripts/render_terminal_svg.py                 # writes assets/terminal/hpp-{doctor,init}.svg
    python scripts/render_terminal_svg.py --from-text out.txt --command "hpp status" --out x.svg
    python scripts/render_terminal_svg.py --animate       # writes assets/terminal/hpp-demo.svg
    python scripts/render_terminal_svg.py --animate --session attest   # writes assets/terminal/hpp-attest-demo.svg
    python scripts/render_terminal_svg.py --animate --session install  # writes assets/terminal/hpp-install.svg

The commands run with the repository root on PYTHONPATH from a temporary directory whose only
content is an empty `your-repo/`, so the captured text carries no machine path: every command
the wizard prints reads `--target your-repo`. Standard library only.

`--animate` writes the README's session instead: the commands in DEMO (doctor, init, eval run,
benchmark) run in turn from one temporary directory holding an empty `your-repo/` and a copy of
`examples/reliable-coding/`, and become ONE svg in which each command is typed at a prompt, its
output follows row by row, the finished screen holds with a blinking cursor, and the story loops
(about 25 s). Every row is a whole line of the real stdout; a line left out is counted on screen
(`⋯ N lines not shown`), and the desc records each command and which of its lines are shown. The
motion is CSS only, and with `prefers-reduced-motion` the file is a still of the finished screen.
With `--from-text`, `--animate` animates that one capture the same way.

`--animate --session attest` renders the second story instead (`--session demo` is the default
above): an author refused as its own checker, an approval by a different checker that verifies,
one byte of a committed file changed, and the same approval blocked. It runs in a throwaway git
repository (`git` must be on PATH) whose single commit has a fixed author and date, so the base
commit on screen reproduces. A refusal is the point of that story, so each of its beats declares
the exit status it must return and any other one stops the run; a status other than 0 is shown on
screen after the command's output, and every status is recorded in the desc.

`--animate --session install` renders the README's first image, the install journey: `pip install
house-party-protocol`, then `hpp init --target your-repo`, typed as a reader types them. A wheel is
built from --root (the version being released is not on PyPI while its README is rendered) and served
by a local index that PIP_INDEX_URL names in pip's environment, never on the command line; both
commands run in a throwaway virtual environment, from a temporary directory holding an empty
`your-repo/`, so this story needs no network for the package and the setting says so on the image.
pip shows only its `Successfully installed` line, which must name the version of --root alone; `hpp
init` shows two runs of its output, its start up to the READINESS bar and its end from the wordmark to
the welcome line, with the lines between them counted on screen (`Shot.between`). A beat that exits
non-zero, writes to stderr, or would show a path of the machine stops the run.

`assets/terminal/lane-board.svg` is the third capture and the only one this script cannot
re-capture on its own, because the board is not a command of `hpp`: it is
`multi-session/lane-kit-1.8.1/scripts/lane_board.py`, and a board worth showing has to be
DRIVEN first. To redo it, point `CLAUDE_PROJECT_DIR` at a throwaway directory (unset, the board
lands wherever the cwd happens to be), drive four items with `claim` and `set` until they sit in
different states -- MERGED, a red one held at VERIFIED, one DEFERRED with `--checker-unavailable`,
one back to BUILDING after NEEDS-FIX -- then:

    python .../lane_board.py render > board.txt
    python scripts/render_terminal_svg.py --from-text board.txt \
        --command "python lane_board.py render" --out assets/terminal/lane-board.svg --no-truncate

Item ids in the capture are `EXAMPLE-*` on purpose: a board showing plausible-looking real ids
would be read as somebody's actual work.
"""
from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import NamedTuple
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets" / "terminal"

BG, PANEL, FG, ACCENT, DIM = "#0F1113", "#16191C", "#F4F1EB", "#FF6A00", "#8E8A83"
FONT = "ui-monospace, Menlo, Consolas, 'Liberation Mono', monospace"
FONT_SIZE, LINE_H, CHAR_W, PAD, HEADER_H = 13, 20, 7.9, 24, 40

# Lines that open a section the README does not need: the init capture stops before the first.
DEFAULT_STOP = ("  PLAN", "  MODULES", "  WIRE", "  NEXT")
_SECTION = re.compile(r"^(\s{2})([A-Z][A-Z ]+?)(\s{2,}.*)?$")
# A Markdown ATX heading, which is how a captured board announces each item and its state
# (`lane_board.py render` prints Markdown to stdout). Measured before this branch existed: the two
# captures that already shipped contain ZERO lines matching it, so highlighting headings cannot
# change them — the board rendered flat, in one colour, with the state names lost in the wall.
_HEADING = re.compile(r"^(#{1,6})(\s+)(.+)$")


def run_capture(argv: list[str], root: Path) -> str:
    """Run the harness of `root` from a clean temporary directory with an empty `your-repo/` target."""
    with tempfile.TemporaryDirectory(prefix="hpp-svg-") as tmp:
        (Path(tmp) / "your-repo").mkdir()
        env = dict(os.environ, PYTHONPATH=str(root), PYTHONIOENCODING="utf-8", PYTHONUTF8="1",
                   PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run([sys.executable, "-X", "utf8", "-m", "hpp", *argv], cwd=tmp, env=env,
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise SystemExit(f"hpp {' '.join(argv)} exited {result.returncode}:\n{result.stdout}{result.stderr}")
    return result.stdout


# The README's two static captures: file -> (hpp arguments, the command it shows, where it stops).
# At module level so the test that re-runs them (tests/test_static_captures_match_a_live_run.py) runs
# exactly what this script runs.
STATIC_JOBS: dict[str, tuple[list[str], str, tuple[str, ...]]] = {
    "hpp-doctor.svg": (["doctor"], "python -m hpp doctor", ()),
    "hpp-init.svg": (["init", "--target", "your-repo", "--non-interactive", "--no-animation"],
                     "python -m hpp init --target your-repo --non-interactive --no-animation", DEFAULT_STOP),
}
# Why (2026-09-27): the readiness block prints the interpreter it ran, and the shipped capture said
# `python.exe --version`, a Windows name in a README read on every system. One neutral name.
_INTERPRETER = re.compile(r"(└ )\S*python[\w.]*(?= --version)")


def neutral(line: str) -> str:
    """The captured line with the interpreter it names written as `python`."""
    return _INTERPRETER.sub(r"\1python", line)


def truncate(lines: list[str], stop: tuple[str, ...]) -> tuple[list[str], list[str]]:
    """Keep everything before the first section named in `stop`; return (kept, labels of the cut)."""
    labels = {s.strip() for s in stop}
    for index, line in enumerate(lines):
        if line.startswith(stop):
            cut = []
            for later in lines[index:]:
                match = _SECTION.match(later)
                if match and match.group(2).strip() in labels:
                    cut.append(match.group(2).strip())
            kept = lines[:index]
            while kept and not kept[-1].strip():
                kept.pop()
            return kept, cut
    return lines, []


def _span(text: str, fill: str, weight: str | None = None) -> str:
    style = f' font-weight="{weight}"' if weight else ""
    return f'<tspan fill="{fill}"{style}>{escape(text)}</tspan>'


def paint(line: str) -> str:
    """Colour one output line: accents for verdict marks and section labels, dim for reproductions."""
    if not line.strip():
        return ""
    if line.lstrip()[0] in "└│·":
        return _span(line, DIM)
    heading = _HEADING.match(line)
    if heading:
        # The `#` marks are Markdown syntax, not content: dim them and accent what they announce.
        return _span(heading.group(1) + heading.group(2), DIM) + _span(heading.group(3), ACCENT, "bold")
    match = _SECTION.match(line)
    if match and match.group(2).strip().isupper():
        return _span(match.group(1) + match.group(2), ACCENT, "bold") + _span(match.group(3) or "", DIM)
    out: list[str] = []
    buffer = ""
    for index, char in enumerate(line):
        colour = ACCENT if char in "█▓✓" or (char == ">" and index == 0) else DIM if char == "░" else None
        if colour is None:
            buffer += char
            continue
        if buffer:
            out.append(_span(buffer, FG))
            buffer = ""
        out.append(_span(char, colour))
    if buffer:
        out.append(_span(buffer, FG))
    return "".join(out)


def render(command: str, lines: list[str], cut: list[str], stamp: str) -> str:
    body = [f"$ {command}", *lines]
    if cut:
        body += ["", f"⋯ {' · '.join(cut)} follow — run the command for the full output"]
    width = int(max(len(text) for text in body) * CHAR_W + 2 * PAD)
    height = HEADER_H + PAD + len(body) * LINE_H + PAD // 2
    rows = []
    for index, line in enumerate(body):
        y = HEADER_H + PAD + index * LINE_H
        if index == 0:
            content = _span("$ ", ACCENT, "bold") + _span(command, FG, "bold")
        elif cut and index == len(body) - 1:
            content = _span(line, DIM)
        else:
            content = paint(line)
        if content:
            rows.append(f'  <text x="{PAD}" y="{y}" xml:space="preserve">{content}</text>')
    title = f"{command} — measured output, {stamp}"
    return "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="{escape(title)}" font-family="{escape(FONT)}" font-size="{FONT_SIZE}">',
        f"  <title>{escape(title)}</title>",
        "  <desc>Rendered from the command's real stdout by scripts/render_terminal_svg.py; no image was edited by hand.</desc>",
        f'  <rect width="{width}" height="{height}" rx="10" fill="{BG}"/>',
        f'  <path d="M0 10a10 10 0 0 1 10-10h{width - 20}a10 10 0 0 1 10 10v{HEADER_H - 10}H0z" fill="{PANEL}"/>',
        f'  <circle cx="22" cy="20" r="5" fill="{ACCENT}"/><circle cx="40" cy="20" r="5" fill="{DIM}"/><circle cx="58" cy="20" r="5" fill="{DIM}"/>',
        f'  <text x="{width // 2}" y="25" text-anchor="middle" fill="{DIM}" font-size="12">{escape(command)}</text>',
        *rows,
        "</svg>",
        "",
    ])


# --------------------------------------------------------------------------- the animated session
#
# Why CSS, one keyframes block per row (2026-09-27): a README shows an svg through an <img>, where
# CSS animations run and scripts never do. `animation-delay` alone cannot make a stagger LOOP: it
# shifts only the first iteration, so from the second pass on every row would be out of step. So
# every row gets its own keyframes over ONE shared cycle, all starting together. At rest -- with
# `prefers-reduced-motion`, or in a renderer that runs no CSS -- each element shows its resting
# state, which is the finished screen: every row visible, the typing covers hidden by their
# `opacity="0"` attribute.

DEMO_FILE = "hpp-demo.svg"
DEMO_CAPTION = "python -m hpp · diagnose → plan → measure → pass"
DEMO_SETTING = ("Every command ran from one temporary directory holding an empty your-repo/ and a copy of "
                "examples/reliable-coding/; a line left out is counted on screen, and no line was edited.")
# The README's story, one command per beat. `keep` picks the WHOLE lines a command shows: a
# (first, last) pair of line prefixes, both lines included; None keeps its every line.
DEMO: tuple[tuple[tuple[str, ...], tuple[str, str] | None], ...] = (
    (("doctor",), None),
    (("init", "--target", "your-repo", "--non-interactive", "--no-animation"),
     ("house-party init", "> protocol online.")),
    (("eval", "run", "examples/reliable-coding/benchmark-suite.json", "-k", "3", "--gate", "both"),
     ('  "k": ', "  },")),
    (("benchmark", "-k", "3"), None),
)
PROVENANCE = "Rendered from the command's real stdout by scripts/render_terminal_svg.py; no image was edited by hand."

# Seconds. A long command is typed faster, not for longer; the reading pause grows with the output.
TYPE_S, TYPE_MAX_S, THINK_S, ENTER_S = 0.05, 2.8, 0.5, 0.4
LINE_S, READ_S, READ_ROW_S = 0.12, 0.9, 0.1
LEAD_S, HOLD_S, BLANK_S, BLINK_S = 0.4, 4.5, 0.6, 1.1


class Shot(NamedTuple):
    """One command of a session and the whole lines of its output that it shows."""

    command: str            # the command line exactly as it ran
    lines: tuple[str, ...]  # whole lines of its output (see `stream`), unedited, consecutive within each run
    before: int = 0         # lines of that output above them, left out
    after: int = 0          # lines of that output below them, left out
    stream: str = "stdout"  # where the lines were read; any other stream is named in the desc
    exit_code: int | None = None  # the status it returned, when the story depends on it; None = not recorded
    # Where `lines` is more than one run of the output: (how many of `lines` come before the cut,
    # how many lines of the output were left out there), in order. Empty for a shot of one run.
    between: tuple[tuple[int, int], ...] = ()


def select(lines: list[str], keep: tuple[str, str] | None) -> tuple[int, int]:
    """Index of the first and of the last whole line to show; an anchor that is not there is an error.

    Refusing is the point: a demo that fell back to "some other lines" when the output changed
    shape would show a story nobody ran.
    """
    if keep is None:
        return 0, len(lines) - 1
    opening, closing = keep
    first = next((index for index, line in enumerate(lines) if line.startswith(opening)), None)
    if first is None:
        raise ValueError(f"no line starts with {opening!r}")
    last = next((index for index in range(first, len(lines)) if lines[index].startswith(closing)), None)
    if last is None:
        raise ValueError(f"no line at or after {opening!r} starts with {closing!r}")
    return first, last


def select_segments(lines: list[str], keeps: tuple[tuple[str, str], ...]) -> list[tuple[int, int]]:
    """Index of the first and the last line of each run to show, each found as `select` finds one.

    A run is searched only below the run before it. Two runs are shown because lines lie between
    them, so a run that starts right below the previous one is refused as well: its anchors no
    longer describe the output they were written for.
    """
    ranges: list[tuple[int, int]] = []
    start = 0
    for keep in keeps:
        first, last = select(lines[start:], keep)
        first, last = first + start, last + start
        if ranges and first == ranges[-1][1] + 1:
            raise ValueError(f"nothing is left out between {lines[ranges[-1][1]]!r} and {lines[first]!r}")
        ranges.append((first, last))
        start = last + 1
    return ranges


def segmented_shot(command: str, lines: list[str], ranges: list[tuple[int, int]], stream: str = "stdout",
                   exit_code: int | None = None) -> Shot:
    """The shot of the runs `ranges` picks from `lines`, every line left out counted where it was."""
    shown: list[str] = []
    between = []
    for index, (first, last) in enumerate(ranges):
        if index:
            between.append((len(shown), first - ranges[index - 1][1] - 1))
        shown.extend(lines[first:last + 1])
    return Shot(command, tuple(shown), ranges[0][0], len(lines) - 1 - ranges[-1][1], stream, exit_code,
                tuple(between))


def session_shots(steps: tuple[tuple[tuple[str, ...], tuple[str, str] | None], ...],
                  outputs: list[str]) -> list[Shot]:
    """Each step's command line and the whole lines its `keep` selects from the stdout it printed."""
    shots = []
    for (argv, keep), stdout in zip(steps, outputs, strict=True):
        command = shlex.join(["python", "-m", "hpp", *argv])
        lines = stdout.splitlines()
        try:
            first, last = select(lines, keep)
        except ValueError as exc:
            raise ValueError(f"{command}: {exc}") from exc
        shots.append(Shot(command, tuple(lines[first:last + 1]), first, len(lines) - 1 - last))
    return shots


def run_session(argvs: list[tuple[str, ...]], root: Path) -> list[str]:
    """Run each `hpp` command in turn from ONE temporary directory and return every stdout.

    The directory holds what the story needs and nothing else -- an empty `your-repo/` for init to
    plan against and a copy of the shipped `examples/reliable-coding/` -- so every path a command
    reads or prints is relative and no machine path reaches the image. A command that exits
    non-zero stops the run: a failure is not a demo.
    """
    examples = root / "examples" / "reliable-coding"
    if not examples.is_dir():
        raise SystemExit(f"{examples} is missing: the demo reads its example suite from there")
    env = dict(os.environ, PYTHONPATH=str(root), PYTHONIOENCODING="utf-8", PYTHONUTF8="1",
               PYTHONDONTWRITEBYTECODE="1")
    outputs = []
    with tempfile.TemporaryDirectory(prefix="hpp-svg-") as tmp:
        stage = Path(tmp)
        (stage / "your-repo").mkdir()
        shutil.copytree(examples, stage / "examples" / "reliable-coding")
        for argv in argvs:
            result = subprocess.run([sys.executable, "-X", "utf8", "-m", "hpp", *argv], cwd=stage, env=env,
                                    capture_output=True, text=True, encoding="utf-8", errors="replace")
            if result.returncode != 0:
                raise SystemExit(f"hpp {' '.join(argv)} exited {result.returncode}:\n{result.stdout}{result.stderr}")
            outputs.append(result.stdout)
    return outputs


def _not_shown(count: int) -> str:
    return f"⋯ {count} line{'' if count == 1 else 's'} not shown"


def _exited(code: int) -> str:
    """The row a status other than 0 adds after a command's output: a terminal prints no status."""
    return f"⋯ exit {code}"


def _ending(shot: Shot) -> str:
    """What the desc adds after a shot's lines: the stream when it is not stdout, the status when recorded."""
    stream = f" on {shot.stream}" if shot.stream != "stdout" else ""
    return stream + (f", exit {shot.exit_code}" if shot.exit_code is not None else "")


def _shown_range(shot: Shot) -> str:
    """Which lines of its output a shot shows, as the desc records it, e.g. `lines 5-7 of 8`."""
    if shot.between:
        return _shown_runs(shot)
    total = shot.before + len(shot.lines) + shot.after
    first, last = shot.before + 1, shot.before + len(shot.lines)
    if not shot.lines:
        return "no output" if not total else f"none of {total} lines"
    return f"line {first} of {total}" if first == last else f"lines {first}-{last} of {total}"


def _shown_runs(shot: Shot) -> str:
    """The desc's record of a shot of several runs, e.g. `lines 1-12 and 107-120 of 120`."""
    spans, start, taken = [], shot.before + 1, 0
    for position, count in (*shot.between, (len(shot.lines), 0)):
        last = start + position - taken - 1
        spans.append(f"{start}" if start == last else f"{start}-{last}")
        start, taken = last + 1 + count, position
    total = shot.before + len(shot.lines) + sum(count for _, count in shot.between) + shot.after
    return f"lines {', '.join(spans[:-1])} and {spans[-1]} of {total}"


def _timeline(shots: list[Shot]) -> tuple[list[tuple[str, str, float, tuple[float, float, float] | None]], float, float]:
    """Every row with the second it appears, then when the screen clears and when the loop restarts.

    A command row also carries (typing starts, typing ends, Enter); its output rows follow Enter.
    """
    rows: list[tuple[str, str, float, tuple[float, float, float] | None]] = []
    at = LEAD_S
    for shot in shots:
        start = at + THINK_S
        end = start + min(len(shot.command) * TYPE_S, TYPE_MAX_S)
        enter = end + ENTER_S
        rows.append(("cmd", shot.command, at, (start, end, enter)))
        body = [("gap", _not_shown(shot.before))] if shot.before else []
        cuts = dict(shot.between)
        for position, line in enumerate(shot.lines):
            body += [("gap", _not_shown(cuts[position]))] if position in cuts else []
            body.append(("out", line))
        body += [("gap", _not_shown(shot.after))] if shot.after else []
        body += [("exit", _exited(shot.exit_code))] if shot.exit_code else []
        for offset, (kind, text) in enumerate(body):
            rows.append((kind, text, enter + offset * LINE_S, None))
        at = enter + len(body) * LINE_S + READ_S + READ_ROW_S * len(body)
    rows.append(("idle", "", at, None))
    return rows, at + HOLD_S, at + HOLD_S + BLANK_S


def _cursor(x: float, y: int, css_class: str = "") -> str:
    attribute = f' class="{css_class}"' if css_class else ""
    return f'<rect{attribute} x="{x:g}" y="{y - 11}" width="{CHAR_W:g}" height="14" fill="{ACCENT}"/>'


def render_animated(shots: list[Shot], stamp: str, caption: str, setting: str = "") -> str:
    """Paint a session as one looping svg: each row a whole line of real stdout, shown in order."""
    rows, clear, cycle = _timeline(shots)
    cycle = round(cycle, 2)

    def pct(seconds: float) -> str:
        return f"{100 * seconds / cycle:.2f}"

    typed_x = PAD + 2 * CHAR_W  # where a command starts, right after "$ "
    shown = ["$ " + text if kind == "cmd" else "$ █" if kind == "idle" else text for kind, text, _, _ in rows]
    width = int(max(len(line) for line in shown) * CHAR_W + 2 * PAD)
    height = HEADER_H + PAD + len(rows) * LINE_H + PAD // 2
    prompt = _span("$ ", ACCENT, "bold")
    frames = [f"@keyframes s{{0%{{opacity:1}}{pct(clear)}%,100%{{opacity:0}}}}", "@keyframes b{50%{opacity:0}}"]
    groups = []
    for index, (kind, text, at, typing) in enumerate(rows):
        if kind == "out" and not text.strip():
            continue  # a blank line paints nothing, as in the static render; it still takes its row
        y = HEADER_H + PAD + index * LINE_H
        frames.append(f"@keyframes r{index}{{0%{{opacity:0}}{pct(at)}%,100%{{opacity:1}}}}")
        if kind == "cmd" and typing is not None:
            start, end, enter = typing
            shift = f"{len(text) * CHAR_W:g}"
            # The cover slides right one character per step, uncovering the command; the cursor
            # rides its left edge, and both vanish on Enter.
            frames.append(
                f"@keyframes t{index}{{0%,{pct(start)}%{{transform:translateX(0px);opacity:1;"
                f"animation-timing-function:steps({len(text)},end)}}"
                f"{pct(end)}%{{transform:translateX({shift}px);opacity:1;animation-timing-function:step-end}}"
                f"{pct(enter)}%,100%{{transform:translateX({shift}px);opacity:0}}}}"
            )
            inner = (
                f'<text x="{PAD}" y="{y}" xml:space="preserve">{prompt}</text>'
                f'<text x="{typed_x:g}" y="{y}" xml:space="preserve" textLength="{shift}">'
                f"{_span(text, FG, 'bold')}</text>"
                f'<g class="t" opacity="0" style="animation-name:t{index}">'
                f'<rect x="{typed_x:g}" y="{y - 14}" width="{(len(text) + 1) * CHAR_W:g}" height="18" fill="{BG}"/>'
                f"{_cursor(typed_x, y)}</g>"
            )
        elif kind == "idle":
            inner = f'<text x="{PAD}" y="{y}" xml:space="preserve">{prompt}</text>{_cursor(typed_x, y, "b")}'
        elif kind == "exit":
            label, code = text.rsplit(" ", 1)
            content = _span(f"{label} ", DIM) + _span(code, ACCENT, "bold")
            inner = f'<text x="{PAD}" y="{y}" xml:space="preserve">{content}</text>'
        else:
            content = _span(text, DIM) if kind == "gap" else paint(text)
            inner = f'<text x="{PAD}" y="{y}" xml:space="preserve">{content}</text>'
        groups.append(f'    <g class="r" style="animation-name:r{index}">{inner}</g>')
    title = f"{caption} — measured output, {stamp}"
    record = "; ".join(f"{number}) {shot.command} — {_shown_range(shot)}{_ending(shot)}"
                       for number, shot in enumerate(shots, 1))
    streams = "stdout" if all(shot.stream == "stdout" for shot in shots) else "stdout (or stderr, where noted)"
    desc = f"{PROVENANCE} Commands, in the order they ran, and the whole lines of each {streams} shown: {record}."
    if setting:
        desc += f" {setting}"
    quoted = {'"': "&quot;"}
    return "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="{escape(title, quoted)}" font-family="{escape(FONT, quoted)}" font-size="{FONT_SIZE}">',
        f"  <title>{escape(title)}</title>",
        f"  <desc>{escape(desc)}</desc>",
        "  <style>",
        f"    .s{{animation:s {cycle:g}s step-end infinite}}",
        f"    .r,.t{{animation-duration:{cycle:g}s;animation-timing-function:step-end;"
        "animation-iteration-count:infinite}",
        f"    .b{{animation:b {BLINK_S:g}s step-end infinite}}",
        *(f"    {frame}" for frame in frames),
        "    @media (prefers-reduced-motion:reduce){.s,.r,.t,.b{animation:none!important}}",
        "  </style>",
        f'  <rect width="{width}" height="{height}" rx="10" fill="{BG}"/>',
        f'  <path d="M0 10a10 10 0 0 1 10-10h{width - 20}a10 10 0 0 1 10 10v{HEADER_H - 10}H0z" fill="{PANEL}"/>',
        f'  <circle cx="22" cy="20" r="5" fill="{ACCENT}"/><circle cx="40" cy="20" r="5" fill="{DIM}"/><circle cx="58" cy="20" r="5" fill="{DIM}"/>',
        f'  <text x="{width // 2}" y="25" text-anchor="middle" fill="{DIM}" font-size="12">{escape(caption)}</text>',
        '  <g class="s">',
        *groups,
        "  </g>",
        "</svg>",
        "",
    ])


# --------------------------------------------------------------------------- the second story
#
# Why (2026-09-27): the behaviour that sets the harness apart is an approval that goes stale, and
# the README states it only as a table row. This story plays it with real commands: an author is
# refused as its own checker, an approval by a different checker verifies, one byte of a committed
# file changes, and the same approval is then blocked. A refusal is the point here, so each beat
# DECLARES the exit status it must return and the run stops on any other: the status on screen is
# always the one the command returned.

ATTEST_FILE = "hpp-attest-demo.svg"
ATTEST_CAPTION = "python -m hpp attest · a stale approval is refused"
ATTEST_SETTING = ("Every command ran in one temporary git repository, your-repo/, whose single commit holds spec.md "
                  "and app.py under a fixed author and date, so the base commit shown is the same wherever the story "
                  "is regenerated; the python -c line is the only edit, a line left out is counted on screen, a "
                  "status other than 0 is shown as it was returned, and no line was edited.")
# The committed repository the story starts from, byte for byte, and the date of its one commit.
ATTEST_REPO = (("spec.md", b"add(a, b) returns a + b.\n"), ("app.py", b"def add(a, b):\n    return a + b\n"))
ATTEST_DATE = "2000-01-01T00:00:00+00:00"
# Each beat: the argv after `python`, the whole lines it shows (as in DEMO), the status it returns.
ATTEST: tuple[tuple[tuple[str, ...], tuple[str, str] | None, int], ...] = (
    (("-m", "hpp", "attest", "create", "--spec", "spec.md", "--output", "att.json", "--maker", "a",
      "--checker", "a", "--session", "s1", "--verdict", "approved"), None, 2),
    (("-m", "hpp", "attest", "create", "--spec", "spec.md", "--output", "att.json", "--maker", "a",
      "--checker", "b", "--session", "s1", "--verdict", "approved"), ('  "status": ', "}"), 0),
    (("-m", "hpp", "attest", "verify", "att.json"), None, 0),
    (("-c", 'with open("app.py", "a") as f: f.write("#")'), None, 0),
    (("-m", "hpp", "attest", "verify", "att.json"), None, 2),
)


def run_beat(argv: tuple[str, ...], keep: tuple[str, str] | None, declared: int, cwd: Path,
             env: dict[str, str]) -> Shot:
    """Run one beat (`python` + argv) and return what it shows, with its stream and its status.

    A beat that returns a status other than the one it declares stops the run, and so does one
    that writes to both stdout and stderr, whose order on a terminal nobody measured.
    """
    command = shlex.join(["python", *argv])
    result = subprocess.run([sys.executable, "-X", "utf8", *argv], cwd=cwd, env=env, capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    if result.returncode != declared:
        raise SystemExit(f"{command} exited {result.returncode}; the story declares {declared}:\n"
                         f"{result.stdout}{result.stderr}")
    if result.stdout and result.stderr:
        raise SystemExit(f"{command} wrote to stdout and stderr, and their order on a terminal is unknown")
    stream, text = ("stderr", result.stderr) if result.stderr else ("stdout", result.stdout)
    lines = text.splitlines()
    try:
        first, last = select(lines, keep)
    except ValueError as exc:
        raise ValueError(f"{command}: {exc}") from exc
    return Shot(command, tuple(lines[first:last + 1]), first, len(lines) - 1 - last, stream, result.returncode)


def run_attest_session(steps: tuple[tuple[tuple[str, ...], tuple[str, str] | None, int], ...],
                       root: Path) -> list[Shot]:
    """Run each beat in turn inside ONE throwaway git repository and return what each shows.

    The repository is `your-repo/` holding ATTEST_REPO in a single commit with a fixed author and
    date. git runs without the system or global configuration and without the caller's GIT_*
    variables: a GIT_DIR or GIT_INDEX_FILE left in the environment would point the story at
    another repository, and a global hook or signing key would change its commit.
    """
    git = shutil.which("git")
    if git is None:
        raise SystemExit("git is not on PATH, and an attestation is bound to a git repository")
    with tempfile.TemporaryDirectory(prefix="hpp-svg-") as tmp:
        stage = Path(tmp)
        (stage / "gitconfig").write_bytes(b"")
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        env.update(PYTHONPATH=str(root), PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1",
                   GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=str(stage / "gitconfig"),
                   GIT_AUTHOR_DATE=ATTEST_DATE, GIT_COMMITTER_DATE=ATTEST_DATE)
        repo = stage / "your-repo"
        repo.mkdir()
        for name, data in ATTEST_REPO:
            (repo / name).write_bytes(data)
        setup = (["init", "-q"], ["config", "user.name", "you"], ["config", "user.email", "you@example.invalid"],
                 ["add", "--", *(name for name, _ in ATTEST_REPO)], ["commit", "-q", "-m", "spec and code"])
        for args in setup:
            done = subprocess.run([git, *args], cwd=repo, env=env, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")
            if done.returncode != 0:
                raise SystemExit(f"git {' '.join(args)} exited {done.returncode}:\n{done.stdout}{done.stderr}")
        shots = [run_beat(argv, keep, declared, repo, env) for argv, keep, declared in steps]
    return shots


# --------------------------------------------------------------------------- the install journey
#
# Why: the README's first image is what a reader does first, install and then init, and no image
# showed how `hpp init` ends (the wordmark, the signature and the welcome line): the static capture
# stops at the plan. This story runs both commands as a reader types them. The version being
# released is not on PyPI while its README is rendered, so pip reads a wheel built from --root from
# a local index named by PIP_INDEX_URL in its environment: the command on screen is the one that ran.

INSTALL_FILE = "hpp-install.svg"
INSTALL_CAPTION = "pip install house-party-protocol · hpp init · from install to the party"
INSTALL_SETTING = ("Both commands ran in a throwaway virtual environment, from a temporary directory whose only "
                   "content is an empty your-repo/. pip read this version's wheel, built from the checkout being "
                   "released, from a local index named by PIP_INDEX_URL in its environment, because the recording "
                   "is made before the upload; the same command installs the same package from PyPI. hpp init ran "
                   "with its output captured rather than on a terminal, so it asked nothing and took the defaults it "
                   "names; a line left out is counted on screen, and no line was edited.")
# Each beat: the command exactly as typed, and the runs of whole lines it shows, each a (first, last)
# pair of line prefixes as in DEMO, found in order. `hpp init` shows its start up to the READINESS bar
# (the first line after it to start with a filled cell) and its end from the wordmark on.
INSTALL: tuple[tuple[tuple[str, ...], tuple[tuple[str, str], ...]], ...] = (
    (("pip", "install", "house-party-protocol"),
     (("Successfully installed house-party-protocol-", "Successfully installed house-party-protocol-"),)),
    (("hpp", "init", "--target", "your-repo"),
     (("house-party init", "  █"), ("  █  █ ████", "> Welcome to the party."))),
)
# Why: the files a wheel is built from, as tests/test_installed_package.py builds it: pyproject.toml
# names README.md as `readme` and LICENSE as a license file, and the backend refuses to build without them.
_WHEEL_INPUTS = ("pyproject.toml", "hpp.manifest.json", "README.md", "LICENSE")
# Why: pyproject.toml's `[build-system] requires` floor; below it the in-process backend cannot read the
# SPDX `license` string, so the build goes through pip's isolated one instead.
_SETUPTOOLS_FLOOR = 77


def project_version(root: Path) -> str:
    """The version `root` builds, as its pyproject.toml declares it (tomllib is 3.11+ only)."""
    found = re.search(r'^version = "([^"]+)"', (root / "pyproject.toml").read_text(encoding="utf-8"), re.MULTILINE)
    if found is None:
        raise SystemExit(f"{root / 'pyproject.toml'} declares no version")
    return found.group(1)


def build_wheel(root: Path, work: Path) -> Path:
    """A real wheel of `root`, built from a copy so that no build/ or *.egg-info lands in the checkout."""
    source, out = work / "source", work / "wheel"
    shutil.copytree(root / "hpp", source / "hpp", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in _WHEEL_INPUTS:
        shutil.copyfile(root / name, source / name)
    command = [sys.executable, "-m", "pip", "wheel", str(source), "--no-deps", "-w", str(out), "-q",
               "--disable-pip-version-check"]
    from importlib.metadata import PackageNotFoundError, version
    try:
        local = int(version("setuptools").split(".")[0])
    except (PackageNotFoundError, ValueError):
        local = 0
    if local >= _SETUPTOOLS_FLOOR:
        command.append("--no-build-isolation")  # Why: builds offline, from the backend already installed
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    wheels = sorted(out.glob("*.whl"))
    if result.returncode != 0 or len(wheels) != 1:
        raise SystemExit(f"pip wheel exited {result.returncode}:\n{result.stdout}{result.stderr}")
    return wheels[0]


def run_install_session(steps: tuple[tuple[tuple[str, ...], tuple[tuple[str, str], ...]], ...],
                        root: Path) -> list[Shot]:
    """Serve a wheel of `root` from a local index, then run each beat in a throwaway virtual environment.

    The index is a directory in the simple-repository layout, read through a file: URL, so pip needs no
    network for the package; PIP_INDEX_URL names it in the environment, every other PIP_ variable is
    left out, and PIP_CONFIG_FILE points at the null device, which skips the user's pip configuration
    file (a global or site pip configuration file would still be read). Each beat runs its program
    from the environment's scripts directory, from a directory whose only content is an empty
    `your-repo/`, with stdin closed and without PYTHONPATH, so `hpp` is the installed package. A beat that
    exits non-zero or writes to stderr stops the run, and so does a shown line naming the machine.
    """
    with tempfile.TemporaryDirectory(prefix="hpp-svg-") as tmp:
        base = Path(tmp)
        wheel = build_wheel(root, base)
        project = base / "index" / "house-party-protocol"
        project.mkdir(parents=True)
        shutil.copyfile(wheel, project / wheel.name)
        (project / "index.html").write_text(
            f'<!DOCTYPE html>\n<html><body><a href="{wheel.name}">{wheel.name}</a></body></html>\n', encoding="utf-8")
        venv = base / "venv"
        made = subprocess.run([sys.executable, "-m", "venv", str(venv)], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=600)
        if made.returncode != 0:
            raise SystemExit(f"python -m venv exited {made.returncode}:\n{made.stdout}{made.stderr}")
        scripts = venv / ("Scripts" if os.name == "nt" else "bin")
        stage = base / "work"
        (stage / "your-repo").mkdir(parents=True)
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("PIP_") and key not in ("PYTHONPATH", "PYTHONHOME")}
        env.update(PATH=str(scripts) + os.pathsep + os.environ.get("PATH", ""), VIRTUAL_ENV=str(venv),
                   PIP_INDEX_URL=(base / "index").as_uri() + "/", PIP_CONFIG_FILE=os.devnull,
                   PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_NO_INPUT="1", PYTHONIOENCODING="utf-8", PYTHONUTF8="1",
                   PYTHONDONTWRITEBYTECODE="1")
        home = Path.home()
        # Why: a home that is the filesystem root (some containers) would mark every line holding a slash.
        machine = [base.name.lower(), *((str(home).lower(), home.as_posix().lower()) if len(home.parts) > 1 else ())]
        shots = []
        for argv, keeps in steps:
            command = shlex.join(argv)
            program = shutil.which(argv[0], path=str(scripts))
            if program is None:
                raise SystemExit(f"{argv[0]} is not in the virtual environment's {scripts.name}/")
            result = subprocess.run([program, *argv[1:]], cwd=stage, env=env, stdin=subprocess.DEVNULL,
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
            if result.returncode != 0:
                raise SystemExit(f"{command} exited {result.returncode}:\n{result.stdout}{result.stderr}")
            if result.stderr:
                raise SystemExit(f"{command} wrote to stderr, where a line would sit among the ones shown and be "
                                 f"counted nowhere:\n{result.stderr}")
            lines = result.stdout.splitlines()
            try:
                shot = segmented_shot(command, lines, select_segments(lines, keeps))
            except ValueError as exc:
                raise ValueError(f"{command}: {exc}") from exc
            leaked = [line for line in shot.lines if any(mark in line.lower() for mark in machine)]
            if leaked:
                raise SystemExit(f"{command} would show a path of this machine: {leaked[0]!r}")
            shots.append(shot)
    return shots


def _install_shots(root: Path) -> list[Shot]:
    shots = run_install_session(INSTALL, root)
    expected = f"Successfully installed house-party-protocol-{project_version(root)}"
    if shots[0].lines != (expected,):
        raise SystemExit(f"pip showed {shots[0].lines!r}, not the version of {root} alone ({expected!r})")
    return shots


class Story(NamedTuple):
    """A session `--animate --session NAME` renders: its file, caption and setting, and its run."""

    file: str
    caption: str
    setting: str
    shoot: Callable[[Path], list[Shot]]  # runs the story with the hpp of the given checkout


def _demo_shots(root: Path) -> list[Shot]:
    return session_shots(DEMO, run_session([step for step, _ in DEMO], root))


def _attest_shots(root: Path) -> list[Shot]:
    return run_attest_session(ATTEST, root)


SESSIONS = {
    "demo": Story(DEMO_FILE, DEMO_CAPTION, DEMO_SETTING, _demo_shots),
    "attest": Story(ATTEST_FILE, ATTEST_CAPTION, ATTEST_SETTING, _attest_shots),
    "install": Story(INSTALL_FILE, INSTALL_CAPTION, INSTALL_SETTING, _install_shots),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from-text", type=Path, help="render this captured stdout instead of running hpp")
    parser.add_argument("--command", help="command label for --from-text (e.g. 'python -m hpp doctor')")
    parser.add_argument("--out", type=Path, help="output .svg for --from-text")
    parser.add_argument("--no-truncate", action="store_true", help="keep the whole init output")
    parser.add_argument("--root", type=Path, default=ROOT,
                        help="checkout whose `hpp` runs (default: the repository this script lives in). "
                             "The README assets come from a clone of the emitted repository, where "
                             "marketplace.json sits beside the manifest and init reads 9/11.")
    parser.add_argument("--out-dir", type=Path, default=ASSETS, help="where the two SVGs are written")
    parser.add_argument("--animate", action="store_true",
                        help=f"write the README's animated session instead ({DEMO_FILE}: the DEMO commands run "
                             "in turn from --root); with --from-text, animate that one capture")
    parser.add_argument("--session", choices=sorted(SESSIONS),
                        help=f"with --animate, the story to render: demo (the default, {DEMO_FILE}), attest "
                             f"(a stale approval is refused, {ATTEST_FILE}; needs git) or install (pip install, "
                             f"then hpp init, from a wheel of --root, {INSTALL_FILE}; the README's first image)")
    args = parser.parse_args(argv)
    if args.session and not args.animate:
        parser.error("--session needs --animate")
    if args.session and args.from_text:
        parser.error("--session runs a story of its own; it does not animate --from-text")
    stamp = date.today().isoformat()

    if args.from_text:
        if not (args.command and args.out):
            parser.error("--from-text needs --command and --out")
        lines = args.from_text.read_text(encoding="utf-8").splitlines()
        kept, cut = (lines, []) if args.no_truncate else truncate(lines, DEFAULT_STOP)
        if args.animate:
            shot = Shot(args.command, tuple(kept), 0, len(lines) - len(kept))
            args.out.write_text(render_animated([shot], stamp, args.command), encoding="utf-8", newline="\n")
            print(f"wrote {args.out} (animated, {len(kept)} line(s))")
            return 0
        args.out.write_text(render(args.command, kept, cut, stamp), encoding="utf-8", newline="\n")
        print(f"wrote {args.out} ({len(kept)} line(s))")
        return 0

    jobs = {name: (hpp_args, label, () if args.no_truncate else stop)
            for name, (hpp_args, label, stop) in STATIC_JOBS.items()}
    root = args.root.resolve()
    if not (root / "hpp" / "__init__.py").is_file():
        parser.error(f"{root} has no hpp/ package")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if args.animate:
        name = args.session or "demo"
        story = SESSIONS[name]
        try:
            shots = story.shoot(root)
        except ValueError as exc:
            raise SystemExit(f"the {name} session cannot pick its lines: {exc}") from exc
        out = args.out_dir / story.file
        out.write_text(render_animated(shots, stamp, story.caption, story.setting), encoding="utf-8", newline="\n")
        print(f"wrote {out} ({len(shots)} commands, {sum(len(shot.lines) for shot in shots)} line(s) shown)")
        return 0
    for name, (hpp_args, label, stop) in jobs.items():
        lines = [neutral(line) for line in run_capture(hpp_args, root).splitlines()]
        kept, cut = truncate(lines, stop) if stop else (lines, [])
        out = args.out_dir / name
        out.write_text(render(label, kept, cut, stamp), encoding="utf-8", newline="\n")
        print(f"wrote {out} ({len(kept)} of {len(lines)} line(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
