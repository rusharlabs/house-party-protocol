"""The README's static captures show what their commands print today, or the build fails.

`hpp-doctor.svg` and `hpp-init.svg` are rendered from real output, but nothing ran the commands
again afterwards, so nothing noticed when the output moved on.

# Why (2026-09-27): measured that day, `hpp-init.svg` still showed `v2.5.8`, four releases late,
# and a Windows interpreter name (`python.exe --version`) in a README read on every system.

Each capture is compared, line by line, with a live run of the command it names, through the same
functions the renderer uses. Only the emitted copy runs them the way the README shows them: with
`marketplace.json` beside the manifest, `init` reads 9/11. In the source tree the comparison says so
and skips. The one normalization is the Python version, which is each machine's own; the package
version on the first line is compared as it is, so a release that bumps it must render again.
"""
from __future__ import annotations

import importlib.util
import os
import re
from html import unescape
from pathlib import Path

import pytest

PRODUCT_ROOT = Path(__file__).resolve().parents[1]
EMITTED = Path(os.environ.get("HPP_EMITTED_COPY") or PRODUCT_ROOT)
REGENERATE = "python scripts/render_terminal_svg.py --root <emitted copy> --out-dir assets/terminal"


def _load_renderer():
    """Load the renderer by path (the scripts are not a package; see test_terminal_animation)."""
    spec = importlib.util.spec_from_file_location("render_terminal_svg", PRODUCT_ROOT / "scripts" / "render_terminal_svg.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rts = _load_renderer()

# The same reading as test_terminal_animation._static_inputs: the rows a static capture shows.
_TITLE = re.compile(r"<title>(.*) — measured output, (\d{4}-\d{2}-\d{2})</title>")
_HEIGHT = re.compile(r'<svg [^>]*\bheight="(\d+)"')
_TSPAN = re.compile(r"<tspan[^>]*>(.*?)</tspan>")
_CUT = re.compile(r"^⋯ (.*) follow — run the command for the full output$")
_PYTHON_VERSION = re.compile(r"(python(?: version)?\s+)\d+\.\d+\.\d+")


def shown(text: str) -> tuple[str, list[str], list[str]]:
    """(command, lines, cut) a static capture shows."""
    command = unescape(_TITLE.search(text).group(1))
    top = rts.HEADER_H + rts.PAD
    row = re.compile(rf'^  <text x="{rts.PAD}" y="(\d+)" xml:space="preserve">(.*)</text>$')
    rows: dict[int, str] = {}
    for line in text.splitlines():
        match = row.match(line)
        if match:
            rows[(int(match.group(1)) - top) // rts.LINE_H] = unescape("".join(_TSPAN.findall(match.group(2))))
    height = int(_HEIGHT.search(text).group(1))
    body = [rows.get(index, "") for index in range((height - top - rts.PAD // 2) // rts.LINE_H)]
    cut = _CUT.match(body[-1])
    if cut:
        return command, body[1:-2], cut.group(1).split(" · ")
    return command, body[1:], []


def live(hpp_args: list[str], stop: tuple[str, ...]) -> tuple[list[str], list[str]]:
    """(lines, cut) the command prints now, cut where the capture is cut."""
    lines = [rts.neutral(line) for line in rts.run_capture(hpp_args, EMITTED).splitlines()]
    return rts.truncate(lines, stop) if stop else (lines, [])


def comparable(lines: list[str]) -> list[str]:
    return [_PYTHON_VERSION.sub(r"\1X.Y.Z", line) for line in lines]


def test_every_static_capture_shows_what_its_command_prints_now():
    if not (EMITTED / "marketplace.json").is_file():
        pytest.skip(f"no marketplace.json at {EMITTED} (source tree): init would read differently here")
    assert set(rts.STATIC_JOBS) == {"hpp-doctor.svg", "hpp-init.svg"}
    for name, (hpp_args, label, stop) in rts.STATIC_JOBS.items():
        command, lines, cut = shown((EMITTED / "assets" / "terminal" / name).read_text(encoding="utf-8"))
        assert command == label, f"{name} names `{command}`, the renderer runs `{label}`"
        assert lines, f"{name}: no row was read back, the comparison would be vacuous"
        now, now_cut = live(hpp_args, stop)
        assert (comparable(lines), cut) == (comparable(now), now_cut), (
            f"{name} no longer shows what `{label}` prints; render it again: {REGENERATE}")


def test_CONTROLE_a_stale_line_is_told_apart_from_the_real_one():
    """The comparison discriminates: the package version moved and nothing else did."""
    before = ["house-party init · v2.5.8 · plan · target your-repo", "    ✓ python version          3.14.3"]
    after = ["house-party init · v2.9.0 · plan · target your-repo", "    ✓ python version          3.10.12"]
    assert comparable(before) != comparable(after)
    assert comparable(before[1:]) == comparable(after[1:]), "the Python version alone must not fail a capture"


def test_the_prerequisites_line_names_each_machines_python_too():
    """-- Why: the first CI run of this comparison failed on every Linux and Windows job. The capture was
    taken on Python 3.14.3, the runner had 3.10.21, and the version is printed on TWO lines: the readiness
    row ("python version  3.14.3"), which was normalized, and the prerequisites line of the boot sequence
    ("python 3.14.3 · protocol 2.1"), which was not."""
    ours = "> checking prerequisites...   ✓ python 3.14.3 · protocol 2.1"
    runner = "> checking prerequisites...   ✓ python 3.10.21 · protocol 2.1"
    assert comparable([ours]) == comparable([runner])
    assert comparable([ours]) != comparable([ours.replace("protocol 2.1", "protocol 2.2")]), \
        "only the Python version is written away, never what follows it"


def test_the_interpreter_is_written_one_way():
    assert rts.neutral("        └ python.exe --version") == "        └ python --version"
    assert rts.neutral("        └ /usr/bin/python3 --version") == "        └ python --version"
    assert rts.neutral("        └ python -m hpp doctor") == "        └ python -m hpp doctor", "other rows are left alone"
