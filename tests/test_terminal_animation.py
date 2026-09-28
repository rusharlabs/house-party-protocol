"""The README's animated demo is a terminal session rendered from real stdout, not a video.

`scripts/render_terminal_svg.py --animate` runs a short story of `hpp` commands in turn and
paints it as ONE svg whose rows appear in order: each command is typed, its output follows, the
finished screen holds with the cursor blinking, then the screen clears and the story plays
again. A README shows an svg through an <img>, where CSS animations run and scripts never do,
so the whole effect is CSS keyframes, and the same file has to stay a truthful still for a
reader who asked for reduced motion.

What can break without anybody noticing, and what the tests below pin:

1. the static captures change because the animated mode was bolted onto the same code
   (the two CONTROL tests: every shipped static svg is still exactly what `render()` produces,
   and `--from-text` without `--animate` still writes it);
2. rows appear out of order or together, so the "session" is a slide show;
3. the file stops being valid XML, grows a script or an external reference, or loses the
   generator's provenance, at which point it is a drawing and not a capture;
4. the animation ignores `prefers-reduced-motion`, or its final frame hides a line;
5. the lines shown stop being WHOLE lines of the output: the selection must refuse an anchor it
   cannot find instead of quietly showing something else, and every line it leaves out is
   counted on screen;
6. the second story (`--animate --session attest`: a stale approval is refused) draws a refusal
   the command did not return. Its beats declare the exit status they must return and the run
   stops on any other; a status other than 0 is shown on screen, every status is recorded in
   the desc, and a line read from stderr is named as such. Adding it must not move the README
   demo by one byte (the CONTROL tests on `hpp-demo.svg` and on `--animate` without a session).

The reveal time of a row is read from the CSS itself. A looping stagger cannot be written with
`animation-delay` alone (it shifts only the first iteration, so from the second loop on every
row would drift), so each row has its own keyframes over one shared cycle; the tests parse those
keyframes rather than trust any number the generator could write beside them.
"""
from __future__ import annotations

import datetime
import importlib.util
import os
import re
import shlex
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import unescape

import pytest

PRODUCT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PRODUCT_ROOT / "scripts" / "render_terminal_svg.py"
MEDIA_SCRIPT = PRODUCT_ROOT / "scripts" / "render_demo_media.py"
TERMINAL = PRODUCT_ROOT / "assets" / "terminal"
DEMO_SVG = TERMINAL / "hpp-demo.svg"
ATTEST_SVG = TERMINAL / "hpp-attest-demo.svg"
STATIC_CAPTURES = ("hpp-doctor.svg", "hpp-init.svg", "lane-board.svg")
SVG = "{http://www.w3.org/2000/svg}"


@pytest.fixture(scope="module")
def rts():
    """The renderer, imported from its file: `scripts/` is not a package."""
    spec = importlib.util.spec_from_file_location("render_terminal_svg", SCRIPT)
    assert spec is not None and spec.loader is not None, SCRIPT
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- reading an svg back

_TITLE = re.compile(r"<title>(.*) — measured output, (\d{4}-\d{2}-\d{2})</title>")
_HEIGHT = re.compile(r'<svg [^>]*\bheight="(\d+)"')
_TSPAN = re.compile(r"<tspan[^>]*>(.*?)</tspan>")
_CUT = re.compile(r"^⋯ (.*) follow — run the command for the full output$")


def _static_inputs(rts, text: str) -> tuple[str, list[str], list[str], str]:
    """(command, lines, cut, stamp) a static capture shows, read back from its own rows."""
    command, stamp = (unescape(part) for part in _TITLE.search(text).groups())
    top = rts.HEADER_H + rts.PAD
    row = re.compile(rf'^  <text x="{rts.PAD}" y="(\d+)" xml:space="preserve">(.*)</text>$')
    rows: dict[int, str] = {}
    for line in text.splitlines():
        match = row.match(line)
        if match:
            rows[(int(match.group(1)) - top) // rts.LINE_H] = unescape("".join(_TSPAN.findall(match.group(2))))
    # A blank line paints no row, but the height still counts it: recover every line from there.
    height = int(_HEIGHT.search(text).group(1))
    body = [rows.get(index, "") for index in range((height - top - rts.PAD // 2) // rts.LINE_H)]
    cut = _CUT.match(body[-1])
    if cut:
        return command, body[1:-2], cut.group(1).split(" · "), stamp
    return command, body[1:], [], stamp


_NOT_SHOWN = re.compile(r"⋯ (\d+) lines? not shown")


def _demo_inputs(rts, raw: bytes) -> tuple[list, str, str]:
    """(shots, caption, stamp) an animated capture shows, read back from its own rows.

    A command row opens a shot. A `⋯ N lines not shown` row before its first line counts the lines
    above them, one after its last line the lines below; a row index the file skips is a blank
    output line, which paints nothing and still takes its row. Only the README demo's kinds of row
    are understood here: it has no exit status and no stderr line.
    """
    root = ET.fromstring(raw)
    caption, stamp = (unescape(part) for part in _TITLE.search(raw.decode("utf-8")).groups())
    shots: list[dict] = []
    seen = -1
    for group in root.iter(f"{SVG}g"):
        if group.get("class") != "r":
            continue
        index = int(re.fullmatch(r"animation-name:r(\d+)", group.get("style", "")).group(1))
        if shots:
            shots[-1]["lines"] += [""] * (index - seen - 1)
        seen = index
        texts = group.findall(f"{SVG}text")
        if any(child.tag == f"{SVG}g" and child.get("class") == "t" for child in group):
            shots.append({"command": "".join(texts[1].itertext()), "lines": [], "before": 0, "after": 0})
            continue
        if group.find(f"{SVG}rect[@class='b']") is not None:
            break
        text = "".join("".join(node.itertext()) for node in texts)
        gap = _NOT_SHOWN.fullmatch(text)
        if gap:
            shots[-1]["after" if shots[-1]["lines"] else "before"] = int(gap.group(1))
        else:
            shots[-1]["lines"].append(text)
    return [rts.Shot(s["command"], tuple(s["lines"]), s["before"], s["after"]) for s in shots], caption, stamp


def _keyframes(style: str) -> dict[str, list[tuple[list[float], dict[str, str]]]]:
    """name -> [(stops in percent, {property: value})] for every @keyframes of a stylesheet."""
    found: dict[str, list[tuple[list[float], dict[str, str]]]] = {}
    for name, body in re.findall(r"@keyframes ([\w-]+)\s*\{((?:[^{}]*\{[^{}]*\})*)\s*\}", style):
        blocks = []
        for selector, declarations in re.findall(r"([^{}]+)\{([^{}]*)\}", body):
            stops = [float(part.strip().rstrip("%")) for part in selector.split(",")]
            properties = dict(
                (key.strip(), value.strip())
                for key, value in (item.split(":", 1) for item in declarations.split(";") if item.strip())
            )
            blocks.append((stops, properties))
        found[name] = blocks
    return found


def _first_stop(blocks: list[tuple[list[float], dict[str, str]]], prop: str, value: str) -> float:
    """The earliest stop at which `prop` takes `value` in a keyframes block."""
    return min(stop for stops, properties in blocks for stop in stops if properties.get(prop) == value)


def _session(svg: str) -> dict:
    """Everything a test needs from an animated render, read from the file as a browser would."""
    root = ET.fromstring(svg.encode("utf-8"))
    style = "".join(node.text or "" for node in root.iter(f"{SVG}style"))
    frames = _keyframes(style)
    cycle = float(re.search(r"\.s\s*\{[^}]*animation:\s*s\s+([\d.]+)s", style).group(1))
    rows = []
    for group in root.iter(f"{SVG}g"):
        if group.get("class") != "r":
            continue
        name = re.fullmatch(r"animation-name:(r\d+)", group.get("style", "")).group(1)
        texts = group.findall(f"{SVG}text")
        typing = [child for child in group if child.tag == f"{SVG}g" and child.get("class") == "t"]
        kind = "cmd" if typing else "idle" if group.find(f"{SVG}rect[@class='b']") is not None else "line"
        rows.append({
            "at": _first_stop(frames[name], "opacity", "1") * cycle / 100,
            "ys": {float(text.get("y")) for text in texts},
            "text": "".join("".join(text.itertext()) for text in texts),
            "kind": kind,
            "typing": typing[0] if typing else None,
        })
    return {"root": root, "style": style, "frames": frames, "cycle": cycle,
            "clear": _first_stop(frames["s"], "opacity", "0") * cycle / 100, "rows": rows}


def _assert_self_contained(svg: str) -> None:
    """No script, no event handler, no reference to anything outside the file."""
    lowered = svg.lower()
    needles = ("<script", "javascript:", "<foreignobject", "<image", "@import", "@font-face", "url(", "href",
               "<!doctype", "<!entity")
    for needle in needles:
        assert needle not in lowered, f"the svg contains {needle!r}"
    assert not re.search(r"\son[a-z]+\s*=", lowered), "the svg declares an event handler"
    assert re.findall(r"https?://[^\s\"'<>]+", svg) == ["http://www.w3.org/2000/svg"], (
        "the only URL an svg may carry is its own namespace"
    )


SAMPLE_STAMP = "2026-09-27"


@pytest.fixture()
def sample(rts):
    """Three commands, one with lines left out on both sides and one with a blank line."""
    shots = [
        rts.Shot("python -m hpp doctor", ("HPP doctor: ok · modules=10",)),
        rts.Shot("python -m hpp eval run suite.json -k 3", ('  "k": 3,', '  "metrics": {', "  },"), before=4, after=1),
        rts.Shot("python -m hpp benchmark -k 3", ("", "HPP benchmark: pass@k=1.00 · pass^k=1.00 · gate=PASS")),
    ]
    return shots, rts.render_animated(shots, SAMPLE_STAMP, "sample session")


# --------------------------------------------------------------------------- CONTROL: the static path

def test_CONTROLE_every_static_capture_is_still_exactly_what_render_produces(rts) -> None:
    """CONTROL — the static path must not move: each shipped capture, re-rendered from the text it
    shows, comes back byte for byte. True before the animated mode existed and after it."""
    for name in STATIC_CAPTURES:
        raw = (TERMINAL / name).read_bytes()
        command, lines, cut, stamp = _static_inputs(rts, raw.decode("utf-8"))
        assert lines, f"{name}: no row was read back, the comparison would be vacuous"
        assert rts.render(command, lines, cut, stamp).encode("utf-8") == raw, (
            f"{name} is no longer what render() produces"
        )
        # the comparison discriminates: one changed character is a different file
        assert rts.render(command, [lines[0] + "x", *lines[1:]], cut, stamp).encode("utf-8") != raw


def test_CONTROLE_from_text_without_animate_still_writes_the_static_render(rts, tmp_path: Path) -> None:
    """CONTROL — `--from-text` without `--animate` writes what `render()` returns: no style, no motion."""
    capture = tmp_path / "out.txt"
    capture.write_text("HPP doctor: ok · modules=10\n", encoding="utf-8")
    out = tmp_path / "x.svg"
    assert rts.main(["--from-text", str(capture), "--command", "python -m hpp doctor", "--out", str(out)]) == 0
    written = out.read_text(encoding="utf-8")
    stamp = _TITLE.search(written).group(2)
    assert written == rts.render("python -m hpp doctor", ["HPP doctor: ok · modules=10"], [], stamp)
    assert "<style" not in written and "@keyframes" not in written


def test_CONTROLE_the_shipped_demo_is_still_exactly_what_render_animated_produces(rts) -> None:
    """CONTROL — the README demo must not move when a second story is added: the shipped
    `hpp-demo.svg`, re-rendered from the rows it shows with DEMO's caption and setting, comes back
    byte for byte. True before `--session` existed and after it."""
    raw = DEMO_SVG.read_bytes()
    shots, caption, stamp = _demo_inputs(rts, raw)
    assert caption == rts.DEMO_CAPTION
    assert len(shots) == len(rts.DEMO) and all(shot.lines for shot in shots), (
        f"read back {shots!r}: the comparison would be vacuous"
    )
    assert rts.render_animated(shots, stamp, rts.DEMO_CAPTION, rts.DEMO_SETTING).encode("utf-8") == raw, (
        "hpp-demo.svg is no longer what render_animated() produces from the rows it shows"
    )
    # the comparison discriminates: one changed character is a different file
    edited = shots[0]._replace(lines=(shots[0].lines[0] + "x", *shots[0].lines[1:]))
    assert rts.render_animated([edited, *shots[1:]], stamp, rts.DEMO_CAPTION, rts.DEMO_SETTING).encode("utf-8") != raw


# Stdout a live run of DEMO could print, cut to what its anchors need: the CONTROL below replaces
# the run with it so that it can compare whole files, fast, on any day.
CANNED_DEMO = [
    "HPP doctor: ok · modules=10\n",
    "banner\nhouse-party init · plan · target your-repo\n\n> protocol online.\nmore\n",
    '{\n  "k": 3,\n  "metrics": {\n    "pass_at_k": 1.0\n  },\n  "suite": "x"\n}\n',
    "HPP benchmark: pass@k=1.00 · pass^k=1.00 · gate=PASS\n",
]


class _Day:
    """A fixed `date` for the generator's stamp, so two renders on either side of midnight agree."""

    @staticmethod
    def today() -> datetime.date:
        return datetime.date(2026, 9, 27)


def test_CONTROLE_animate_without_a_session_still_writes_the_readme_demo(rts, tmp_path: Path, monkeypatch) -> None:
    """CONTROL — `--animate` alone runs the DEMO commands and writes `hpp-demo.svg` with DEMO's
    caption and setting, and nothing else, exactly as it did before a second story existed."""
    calls = []

    def canned(argvs, root):
        calls.append([tuple(argv) for argv in argvs])
        return list(CANNED_DEMO)

    monkeypatch.setattr(rts, "run_session", canned)
    monkeypatch.setattr(rts, "date", _Day)
    assert rts.main(["--animate", "--out-dir", str(tmp_path)]) == 0
    assert calls == [[argv for argv, _ in rts.DEMO]], calls
    assert [path.name for path in tmp_path.iterdir()] == [rts.DEMO_FILE]
    expected = rts.render_animated(rts.session_shots(rts.DEMO, CANNED_DEMO), "2026-09-27",
                                   rts.DEMO_CAPTION, rts.DEMO_SETTING)
    assert (tmp_path / rts.DEMO_FILE).read_bytes() == expected.encode("utf-8")


# --------------------------------------------------------------------------- the animated render

def test_animated_render_reveals_one_group_per_line_in_order(rts, sample) -> None:
    """Every row is its own group, and each appears strictly after the one above it."""
    _, svg = sample
    rows = _session(svg)["rows"]
    assert [row["text"] for row in rows] == [
        "$ python -m hpp doctor",
        "HPP doctor: ok · modules=10",
        "$ python -m hpp eval run suite.json -k 3",
        "⋯ 4 lines not shown",
        '  "k": 3,',
        '  "metrics": {',
        "  },",
        "⋯ 1 line not shown",
        "$ python -m hpp benchmark -k 3",
        "HPP benchmark: pass@k=1.00 · pass^k=1.00 · gate=PASS",  # the blank line paints nothing
        "$ ",
    ]
    times = [row["at"] for row in rows]
    assert all(later > earlier for earlier, later in zip(times, times[1:])), f"rows out of order: {times}"
    assert all(len(row["ys"]) == 1 for row in rows), "a row's texts must share one baseline"
    ys = [next(iter(row["ys"])) for row in rows]
    assert all(later > earlier for earlier, later in zip(ys, ys[1:])), ys
    # the blank line still takes its row, as it does on a terminal
    assert ys[-2] - ys[-3] == 2 * rts.LINE_H


def test_each_command_is_typed_one_character_per_step_before_its_output(rts, sample) -> None:
    """A command row uncovers its text in len(command) steps, and Enter comes after the last one."""
    _, svg = sample
    session = _session(svg)
    rows, cycle = session["rows"], session["cycle"]
    typed = 0
    for index, row in enumerate(rows):
        if row["kind"] != "cmd":
            continue
        typed += 1
        command = row["text"][2:]
        name = re.fullmatch(r"animation-name:(t\d+)", row["typing"].get("style")).group(1)
        blocks = session["frames"][name]
        timing = " ".join(properties.get("animation-timing-function", "") for _, properties in blocks)
        assert f"steps({len(command)},end)" in timing, (command, timing)
        final = blocks[-1][1]["transform"]
        shift = float(re.fullmatch(r"translateX\(([\d.]+)px\)", final).group(1))
        assert shift == pytest.approx(len(command) * rts.CHAR_W), (command, shift)
        starts_at = max(blocks[0][0]) * cycle / 100  # the last stop that still covers the whole command
        typed_at = _first_stop(blocks, "transform", final) * cycle / 100
        enter_at = _first_stop(blocks, "opacity", "0") * cycle / 100
        assert row["at"] < starts_at < typed_at < enter_at <= rows[index + 1]["at"] + 1e-6, (
            command, row["at"], starts_at, typed_at, enter_at, rows[index + 1]["at"],
        )
    assert typed == 3, f"{typed} typed commands found; the sample has three"


def test_animated_render_holds_the_finished_screen_then_loops(sample) -> None:
    """The last row stays up for a few seconds, the screen clears, and the story starts again."""
    _, svg = sample
    session = _session(svg)
    assert session["clear"] - session["rows"][-1]["at"] >= 3.0, "the finished screen must hold before it clears"
    assert session["cycle"] > session["clear"], "the loop needs a cleared screen before it restarts"
    moving = re.sub(r"@media[^{]*\{.*?\}\s*\}", "", session["style"], flags=re.S)  # reduced motion stops all
    repeats = re.findall(r"animation(?:-iteration-count)?:([^;}]*)", moving)
    assert len(repeats) >= 3, f"expected the screen, the rows and the cursor to repeat; found {repeats}"
    assert all("infinite" in value for value in repeats), repeats


def test_reduced_motion_shows_the_whole_session_as_a_still(sample) -> None:
    """With `prefers-reduced-motion` every animation is off, and the resting state is the full screen."""
    _, svg = sample
    session = _session(svg)
    media = re.search(r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{(.*?)\}\s*\}", session["style"], re.S)
    assert media, "the svg does not answer prefers-reduced-motion"
    selectors, declaration = media.group(1).split("{", 1)
    assert {part.strip() for part in selectors.split(",")} >= {".s", ".r", ".t", ".b"}
    assert declaration.replace(" ", "") == "animation:none!important"
    root = session["root"]
    for group in root.iter(f"{SVG}g"):
        if group.get("class") in ("s", "r"):
            assert group.get("opacity") is None, "a row hidden at rest would vanish from the still"
        if group.get("class") == "t":
            assert group.get("opacity") == "0", "a typing cover visible at rest would hide a command"


def test_animated_render_is_valid_xml_self_contained_and_carries_the_provenance(rts, sample) -> None:
    """Same provenance sentence as the static captures, the commands recorded, nothing external."""
    shots, svg = sample
    session = _session(svg)  # parses as XML or raises
    _assert_self_contained(svg)
    static = ET.fromstring(rts.render("python -m hpp doctor", ["ok"], [], SAMPLE_STAMP).encode("utf-8"))
    provenance = static.find(f"{SVG}desc").text
    desc = session["root"].find(f"{SVG}desc").text
    assert desc.startswith(provenance), desc
    positions = [desc.index(shot.command) for shot in shots]
    assert positions == sorted(positions), "the desc must record the commands in the order they ran"
    assert "lines 5-7 of 8" in desc, "the desc must say which whole lines of each stdout are shown"


def test_animated_render_keeps_the_palette_and_font_of_the_static_captures(rts, sample) -> None:
    _, svg = sample
    root = _session(svg)["root"]
    assert root.get("font-family") == rts.FONT
    assert set(re.findall(r"#[0-9A-Fa-f]{6}\b", svg)) <= {rts.BG, rts.PANEL, rts.FG, rts.ACCENT, rts.DIM}


def test_from_text_with_animate_writes_an_animated_capture(rts, tmp_path: Path) -> None:
    capture = tmp_path / "out.txt"
    capture.write_text("line one\nline two\n", encoding="utf-8")
    out = tmp_path / "x.svg"
    argv = ["--from-text", str(capture), "--command", "python -m hpp status", "--out", str(out), "--animate"]
    assert rts.main(argv) == 0
    rows = _session(out.read_text(encoding="utf-8"))["rows"]
    assert [row["text"] for row in rows] == ["$ python -m hpp status", "line one", "line two", "$ "]


# --------------------------------------------------------------------------- selecting whole lines

def test_select_keeps_the_whole_lines_between_two_anchors(rts) -> None:
    lines = ["head", "", "> one", "> two", "> done.", "tail", "> done."]
    assert rts.select(lines, None) == (0, 6)
    assert rts.select(lines, ("> one", "> done.")) == (2, 4)


def test_select_refuses_an_anchor_it_cannot_find(rts) -> None:
    """GATE 1e — a missing anchor is an error, never a silent fallback to other lines."""
    with pytest.raises(ValueError, match="no line starts with"):
        rts.select(["a", "b"], ("zzz", "b"))
    with pytest.raises(ValueError, match="after"):
        rts.select(["a", "b"], ("b", "a"))  # the closing anchor exists only ABOVE the opening one


def test_session_shots_count_every_line_they_leave_out(rts) -> None:
    steps = (
        (("doctor",), None),
        (("init", "--target", "your-repo"), ("house-party init", "> protocol online.")),
    )
    outputs = ["HPP doctor: ok\n", "banner\nhouse-party init · plan\n\n> protocol online.\nmore\nmore\n"]
    assert rts.session_shots(steps, outputs) == [
        rts.Shot("python -m hpp doctor", ("HPP doctor: ok",), 0, 0),
        rts.Shot("python -m hpp init --target your-repo", ("house-party init · plan", "", "> protocol online."), 1, 2),
    ]


# --------------------------------------------------------------------------- the README demo itself

def test_the_demo_commands_run_here_and_their_anchors_still_match(rts) -> None:
    """The demo is regenerated from live output: if a command changed shape, the anchors that pick
    its lines would no longer match and regeneration would refuse. Measured here, not at release."""
    outputs = rts.run_session([argv for argv, _ in rts.DEMO], PRODUCT_ROOT)
    shots = rts.session_shots(rts.DEMO, outputs)
    assert shots[0].command == "python -m hpp doctor"
    assert shots[-1].lines[-1].endswith("gate=PASS"), shots[-1]
    rows = sum(1 + len(shot.lines) + bool(shot.before) + bool(shot.after) for shot in shots) + 1
    assert rows <= 26, f"the demo would need {rows} rows; the README budget is about 24"


def test_the_readme_demo_is_a_rendered_session_of_real_commands(rts) -> None:
    """The shipped `hpp-demo.svg`: generator output, a short story that ends on PASS, 20-30 s a loop."""
    assert DEMO_SVG.is_file(), "assets/terminal/hpp-demo.svg does not exist"
    svg = DEMO_SVG.read_text(encoding="utf-8")
    _assert_self_contained(svg)
    session = _session(svg)
    rows = session["rows"]
    commands = [row["text"][2:] for row in rows if row["kind"] == "cmd"]
    assert 3 <= len(commands) <= 5, commands
    assert all(command.startswith("python -m hpp ") for command in commands), commands
    assert commands[0] == "python -m hpp doctor", "the story starts by diagnosing"
    desc = session["root"].find(f"{SVG}desc").text
    assert "scripts/render_terminal_svg.py; no image was edited by hand" in desc
    positions = [desc.index(command) for command in commands]
    assert positions == sorted(positions), "the desc must record the commands in the order they ran"
    lines = [row["text"] for row in rows if row["kind"] == "line"]
    assert "PASS" in lines[-1], f"the story must end on a PASS line, not {lines[-1]!r}"
    assert rows[-1]["kind"] == "idle", "the loop ends on an idle prompt"
    times = [row["at"] for row in rows]
    assert all(later > earlier for earlier, later in zip(times, times[1:])), times
    assert 20 <= session["cycle"] <= 30, f"one loop lasts {session['cycle']} s"
    assert len(rows) <= 26, f"{len(rows)} rows; the README budget is about 24"


# --------------------------------------------------------------------------- the second story: a stale approval

REFUSED_SELF_REVIEW = "hpp: maker and checker must be different non-empty actors"
# Why (2026-09-27): the story is posted as a video, so it must fit one screen of a post: 40 rows is
# 876 px at 20 px a row. Measured when it was written: 29 rows, and 35 with the 3-line `signature`
# block a verification gains when record signing lands. A budget of "what it measures today, plus
# one" would have refused that addition for no reason a reader could name.
STORY_ROWS = 40


def test_CONTROLE_a_shot_without_a_status_renders_as_it_always_did(sample) -> None:
    """CONTROL — a shot that records no exit status and reads stdout, as every shot of the README
    demo does, adds no row and no word: no `⋯ exit` row, and the desc names stdout alone."""
    _, svg = sample
    session = _session(svg)
    assert not any("exit" in row["text"] for row in session["rows"])
    desc = session["root"].find(f"{SVG}desc").text
    assert "the whole lines of each stdout shown: 1) " in desc
    assert ", exit" not in desc and "stderr" not in desc


@pytest.fixture()
def refusals(rts):
    """A self-review refused on stderr, an approval that verifies, and the same approval refused."""
    shots = [
        rts.Shot("python -m hpp attest create --maker a --checker a", (REFUSED_SELF_REVIEW,),
                 stream="stderr", exit_code=2),
        rts.Shot("python -m hpp attest verify att.json", ('  "status": "valid"',), before=4, after=1, exit_code=0),
        rts.Shot("python -m hpp attest verify att.json", ('  "status": "blocked"',), before=6, after=1, exit_code=2),
    ]
    return shots, rts.render_animated(shots, SAMPLE_STAMP, "refusal sample")


def test_a_status_other_than_zero_is_shown_after_the_output_it_ends(rts, refusals) -> None:
    """A refusal is an exit status, and a terminal does not print one: the generator does, in a
    row of its own after the command's last line. A status of 0 adds nothing, as on a terminal."""
    _, svg = refusals
    session = _session(svg)
    rows = session["rows"]
    assert [row["text"] for row in rows] == [
        "$ python -m hpp attest create --maker a --checker a",
        REFUSED_SELF_REVIEW,
        "⋯ exit 2",
        "$ python -m hpp attest verify att.json",
        "⋯ 4 lines not shown",
        '  "status": "valid"',
        "⋯ 1 line not shown",
        "$ python -m hpp attest verify att.json",
        "⋯ 6 lines not shown",
        '  "status": "blocked"',
        "⋯ 1 line not shown",
        "⋯ exit 2",
        "$ ",
    ]
    times = [row["at"] for row in rows]
    assert all(later > earlier for earlier, later in zip(times, times[1:])), times
    status_rows = [group for group in session["root"].iter(f"{SVG}g")
                   if group.get("class") == "r" and "".join(group.itertext()) == "⋯ exit 2"]
    assert len(status_rows) == 2
    for group in status_rows:  # the status is the accent of its row
        accents = [node.text for node in group.iter(f"{SVG}tspan") if node.get("fill") == rts.ACCENT]
        assert accents == ["2"], accents
    _assert_self_contained(svg)
    assert set(re.findall(r"#[0-9A-Fa-f]{6}\b", svg)) <= {rts.BG, rts.PANEL, rts.FG, rts.ACCENT, rts.DIM}


def test_the_desc_records_every_status_and_names_a_line_read_from_stderr(refusals) -> None:
    shots, svg = refusals
    desc = _session(svg)["root"].find(f"{SVG}desc").text
    assert "the whole lines of each stdout (or stderr, where noted) shown: " in desc
    assert f"1) {shots[0].command} — line 1 of 1 on stderr, exit 2; " in desc
    assert f"2) {shots[1].command} — line 5 of 6, exit 0; " in desc
    assert f"3) {shots[2].command} — line 7 of 8, exit 2." in desc


def test_animate_session_names_the_story_and_the_readme_demo_is_the_default(rts, tmp_path: Path, monkeypatch) -> None:
    assert sorted(rts.SESSIONS) == ["attest", "demo"]
    assert rts.SESSIONS["demo"].file == rts.DEMO_FILE
    assert rts.SESSIONS["attest"].file == ATTEST_SVG.name
    monkeypatch.setattr(rts, "run_session", lambda argvs, root: list(CANNED_DEMO))
    monkeypatch.setattr(rts, "date", _Day)
    default, named = tmp_path / "default", tmp_path / "named"
    assert rts.main(["--animate", "--out-dir", str(default)]) == 0
    assert rts.main(["--animate", "--session", "demo", "--out-dir", str(named)]) == 0
    assert (named / rts.DEMO_FILE).read_bytes() == (default / rts.DEMO_FILE).read_bytes()
    capture = tmp_path / "out.txt"
    capture.write_text("line\n", encoding="utf-8")
    refused = (
        ["--session", "attest"],  # a story is animated or it is nothing
        ["--animate", "--session", "nope"],
        ["--from-text", str(capture), "--command", "c", "--out", str(tmp_path / "x.svg"), "--animate",
         "--session", "attest"],  # a story runs its own commands; it animates no capture
    )
    for argv in refused:
        with pytest.raises(SystemExit) as stopped:
            rts.main([*argv, "--out-dir", str(tmp_path / "never")])
        assert stopped.value.code == 2, argv
    assert not (tmp_path / "never").exists() and not (tmp_path / "x.svg").exists()


def _json_value(shot, key: str) -> str:
    """The value of a top-level key in a shot of pretty-printed JSON, quotes and comma removed."""
    line = next(line for line in shot.lines if line.startswith(f'  "{key}": '))
    return line.split(": ", 1)[1].rstrip(",").strip('"')


def test_the_attest_story_runs_here_and_each_status_is_the_one_returned(rts) -> None:
    """The story is regenerated from a live run in a throwaway git repository: the self-review is
    refused on stderr with 2, the approval verifies with 0, the edit is one byte and prints
    nothing, and the same approval is then blocked with 2 because the snapshot moved while the
    commit did not. Measured here, not at release."""
    shots = rts.run_attest_session(rts.ATTEST, PRODUCT_ROOT)
    assert [shot.command for shot in shots] == [shlex.join(["python", *argv]) for argv, _, _ in rts.ATTEST]
    assert [shot.exit_code for shot in shots] == [code for _, _, code in rts.ATTEST] == [2, 0, 0, 0, 2]
    self_review, approval, valid, edit, stale = shots
    assert (self_review.stream, self_review.lines) == ("stderr", (REFUSED_SELF_REVIEW,))
    assert "--maker a --checker a" in self_review.command and "--maker a --checker b" in approval.command
    assert approval.lines[-3:] == ('  "status": "recorded",', '  "verdict": "approved"', "}"), approval
    assert approval.before > 0 and approval.after == 0
    assert '  "mismatches": [],' in valid.lines and _json_value(valid, "status") == "valid"
    assert edit.command == """python -c 'with open("app.py", "a") as f: f.write("#")'""" and edit.lines == ()
    assert '  "mismatches": [' in stale.lines and '    "snapshot_digest"' in stale.lines
    assert _json_value(stale, "status") == "blocked"
    assert _json_value(stale, "base_commit") == _json_value(valid, "base_commit"), "nothing was committed"
    assert _json_value(stale, "snapshot_digest") != _json_value(valid, "snapshot_digest"), "one byte moved it"
    rows = sum(1 + len(shot.lines) + bool(shot.before) + bool(shot.after) + bool(shot.exit_code) for shot in shots)
    assert rows + 1 <= STORY_ROWS, f"the story would need {rows + 1} rows"


def test_a_beat_that_returns_another_status_than_it_declares_stops_the_run(rts, tmp_path: Path) -> None:
    """GATE 1e — a status on screen must be the one the command returned. A beat declared 0 that
    exits 3, or declared 2 that exits 0, stops the run; so does a beat that writes to both streams,
    whose order on a terminal nobody measured. The CONTROL is the same beat runner accepting a
    beat that returns what it declares, with the line it printed and where it printed it."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    with pytest.raises(SystemExit, match="exited 3"):
        rts.run_beat(("-c", "raise SystemExit(3)"), None, 0, tmp_path, env)
    with pytest.raises(SystemExit, match="exited 0"):
        rts.run_beat(("-c", "pass"), None, 2, tmp_path, env)
    with pytest.raises(SystemExit, match="stdout and stderr"):
        rts.run_beat(("-c", "import sys; print(1); print(2, file=sys.stderr)"), None, 0, tmp_path, env)
    refused = rts.run_beat(("-c", 'import sys; sys.exit("refused")'), None, 1, tmp_path, env)
    assert refused == rts.Shot("""python -c 'import sys; sys.exit("refused")'""", ("refused",), 0, 0, "stderr", 1)


def test_the_attest_demo_is_a_rendered_session_of_a_stale_approval_refused(rts) -> None:
    """The shipped `hpp-attest-demo.svg`: generator output of the declared story, in its order,
    every status recorded as declared, ending on the blocked verification and its exit 2."""
    assert ATTEST_SVG.is_file(), "assets/terminal/hpp-attest-demo.svg does not exist"
    svg = ATTEST_SVG.read_text(encoding="utf-8")
    _assert_self_contained(svg)
    session = _session(svg)
    rows = session["rows"]
    declared = [(shlex.join(["python", *argv]), code) for argv, _, code in rts.ATTEST]
    assert [row["text"][2:] for row in rows if row["kind"] == "cmd"] == [command for command, _ in declared]
    desc = session["root"].find(f"{SVG}desc").text
    assert "scripts/render_terminal_svg.py; no image was edited by hand" in desc
    records = re.findall(r"\d\) (.+?) — [^;]*?, exit (\d+)(?:;|\.)", desc)
    assert [(command, int(code)) for command, code in records] == declared, records
    lines = [row["text"] for row in rows if row["kind"] == "line"]
    assert REFUSED_SELF_REVIEW in lines
    assert lines.index('  "status": "valid"') < lines.index('  "status": "blocked"')
    assert lines[-3:] == ['  "status": "blocked"', "}", "⋯ exit 2"], lines[-3:]
    assert rows[-1]["kind"] == "idle", "the loop ends on an idle prompt"
    times = [row["at"] for row in rows]
    assert all(later > earlier for earlier, later in zip(times, times[1:])), times
    assert "@media (prefers-reduced-motion:reduce)" in session["style"]
    assert 20 <= session["cycle"] <= 35, f"one loop lasts {session['cycle']} s"
    assert len(rows) <= STORY_ROWS, f"{len(rows)} rows"


def test_the_media_tool_reads_the_cycle_and_size_every_animated_capture_declares() -> None:
    """`scripts/render_demo_media.py` records a GIF and an MP4 by stepping a capture through the cycle
    its CSS declares. It reads that cycle and the size from the file, and refuses a capture with no
    cycle (a static one) instead of recording a still. Loading it needs nothing outside the standard
    library: the browser driver is imported only when a capture runs."""
    spec = importlib.util.spec_from_file_location("render_demo_media", MEDIA_SCRIPT)
    assert spec is not None and spec.loader is not None
    media = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(media)
    for path in (DEMO_SVG, ATTEST_SVG):
        session = _session(path.read_text(encoding="utf-8"))
        size = (int(session["root"].get("width")), int(session["root"].get("height")))
        assert media.read_capture(path) == (session["cycle"], *size), path.name
    with pytest.raises(SystemExit, match="not an animated capture"):
        media.read_capture(TERMINAL / "hpp-doctor.svg")
