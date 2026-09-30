"""The Lane Dashboard demo: an animated GIF recorded from a live run, shown by both READMEs and both manuals.

The terminal captures carry the command that produced them inside the svg (`<desc>`). A GIF has no
such place, so the recording keeps its command, and what it did, in a text file beside it: the
sidecar. Without the sidecar the GIF is a picture nobody can reproduce, which is how a screenshot
goes stale without anybody noticing.

What this file holds in place:

1. both READMEs and both manuals show the same GIF, with alt text; in the READMEs it sits in the
   section right below the page's opening, "Agent teams, under evidence", once;
2. the manuals are served from `docs/` (Pages publishes `docs/` as the root), so the manual's copy
   lives in `docs/assets/ui/` and must be the same bytes as the README's, and so must the sidecar
   the manual's caption names;
3. the GIF is an animated loop, about 960 pixels wide, under 3 MB;
4. the sidecar names the recorder, the seed, and the steps of the story, and says what on screen
   is not the dashboard (the terminal strip the recorder draws over the page).

The CONTROL below passes on anything a README already shows under `assets/terminal/`, so a
failure of the other tests means the demo is missing, not that the scan is broken.
"""
from __future__ import annotations

import importlib.util
import re
import struct
from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parents[1]
DOCS = PRODUCT_ROOT / "docs"
READMES = ("README.md", "README.pt-BR.md")
MANUALS = ("MANUAL.html", "MANUAL.pt-BR.html")

GIF = "assets/ui/lane-dashboard.gif"
SIDECAR = GIF + ".txt"
BUDGET = 3_000_000
RECORDER = "scripts/record_lane_dashboard.py"
SEED = "scripts/seed_lane_dashboard_demo.py"

_IMG = re.compile(r"<img\b[^>]*>", re.IGNORECASE | re.DOTALL)
_SRC = re.compile(r'\bsrc="([^"]+)"', re.IGNORECASE)
_ALT = re.compile(r'\balt="([^"]*)"', re.IGNORECASE)


def _images(path: Path) -> dict[str, str]:
    """src -> alt of every <img> in a page."""
    found = {}
    for tag in _IMG.findall(path.read_text(encoding="utf-8")):
        src, alt = _SRC.search(tag), _ALT.search(tag)
        if src:
            found[src.group(1)] = alt.group(1) if alt else ""
    return found


def test_CONTROLE_the_scan_sees_the_captures_already_shipped() -> None:
    """CONTROL: the same scan finds the terminal captures every README already shows."""
    for name in READMES:
        shown = [src for src in _images(PRODUCT_ROOT / name) if src.startswith("assets/terminal/")]
        assert len(shown) >= 3, f"{name}: the scan found {shown}; it would find nothing below either"


def test_both_readmes_show_the_dashboard_demo_with_alt_text() -> None:
    for name in READMES:
        images = _images(PRODUCT_ROOT / name)
        assert GIF in images, f"{name} does not show {GIF}"
        assert len(images[GIF]) >= 60, f"{name}: the alt text of {GIF} is {images[GIF]!r}"
        assert "lane_dashboard.py" in images[GIF], f"{name}: the alt text does not name the command"


AGENT_TEAMS = {"README.md": "## Agent teams, under evidence", "README.pt-BR.md": "## Times de agentes, sob evidência"}


def test_the_readmes_show_the_demo_in_the_section_below_the_opening() -> None:
    """The demo is the picture of an agent team at work, so it sits in the first section after the
    logo, the badges and the install journey: the one that says what an agent team is here."""
    for name, heading in AGENT_TEAMS.items():
        text = (PRODUCT_ROOT / name).read_text(encoding="utf-8")
        sections = re.findall(r"^## .+$", text, re.MULTILINE)
        assert sections and sections[0] == heading, f"{name}: the first section is {sections[:1]}"
        start = text.index(f"\n{heading}\n")
        end = text.index("\n## ", start + 1)
        assert text.count(f'src="{GIF}"') == 1, f"{name} shows {GIF} {text.count(GIF)} times"
        assert f'src="{GIF}"' in text[start:end], f"{name}: {GIF} is not in the section {heading!r}"


def test_both_languages_show_the_same_ui_captures() -> None:
    per_language = {name: sorted(src for src in _images(PRODUCT_ROOT / name) if src.startswith("assets/ui/"))
                    for name in READMES}
    assert per_language["README.md"] == per_language["README.pt-BR.md"], per_language


def test_both_manuals_show_the_demo_and_the_site_can_serve_it() -> None:
    for name in MANUALS:
        images = _images(DOCS / name)
        assert GIF in images, f"docs/{name} does not show {GIF}"
        assert len(images[GIF]) >= 60, f"docs/{name}: the alt text of {GIF} is {images[GIF]!r}"
    copy, original = DOCS / GIF, PRODUCT_ROOT / GIF
    assert copy.is_file(), f"docs/{GIF} is missing: the published manual resolves images inside docs/"
    assert copy.read_bytes() == original.read_bytes(), f"docs/{GIF} and {GIF} differ"
    # Why (2026-09-29): the manual's caption names the sidecar by the same relative path, and the
    # site serves docs/ as its root; the GIF travelled there and the sidecar did not.
    for name in MANUALS:
        assert SIDECAR in (DOCS / name).read_text(encoding="utf-8"), f"docs/{name} no longer names {SIDECAR}"
    side_copy, side_original = DOCS / SIDECAR, PRODUCT_ROOT / SIDECAR
    assert side_copy.is_file(), f"docs/{SIDECAR} is missing: the manual names it and the site cannot serve it"
    assert side_copy.read_bytes() == side_original.read_bytes(), f"docs/{SIDECAR} and {SIDECAR} differ"


def test_the_recorder_places_the_sidecar_beside_every_copy_of_the_gif(tmp_path: Path) -> None:
    recorder = _recorder()
    staged = tmp_path / "staged.gif"
    staged.write_bytes(b"GIF89a-bytes")
    targets = [tmp_path / "assets" / "ui", tmp_path / "docs" / "assets" / "ui"]
    recorder.place(staged, "the sidecar\n", targets)
    for target in targets:
        assert (target / "lane-dashboard.gif").read_bytes() == b"GIF89a-bytes", target
        assert (target / "lane-dashboard.gif.txt").read_bytes() == b"the sidecar\n", target


def test_the_gif_is_an_animated_loop_under_the_budget() -> None:
    path = PRODUCT_ROOT / GIF
    assert path.is_file(), f"{GIF} does not exist"
    data = path.read_bytes()
    assert data[:6] == b"GIF89a", f"{GIF} is not a GIF89a file"
    assert len(data) <= BUDGET, f"{GIF} is {len(data):,} bytes, over the {BUDGET:,} budget"
    width, height = struct.unpack("<HH", data[6:10])
    assert 900 <= width <= 1000 and height >= 500, f"{GIF} is {width}x{height}"
    assert b"NETSCAPE2.0" in data, f"{GIF} does not loop"
    frames = data.count(b"\x21\xF9\x04")  # one graphic control extension per frame
    assert frames >= 100, f"{GIF} has {frames} frames; a 15 s story at 10 fps has 150"


def test_the_sidecar_names_the_command_and_the_story() -> None:
    path = PRODUCT_ROOT / SIDECAR
    assert path.is_file(), f"{SIDECAR} does not exist: a GIF cannot carry its command inside it"
    text = path.read_text(encoding="utf-8")
    for needle in (RECORDER, SEED, "lane_dashboard.py serve", "lane_board.py set EXAMPLE-1 CHECKPOINT-READY",
                   "lane_board.py approve EXAMPLE-2", "overlay"):
        assert needle in text, f"{SIDECAR} does not say {needle!r}"
    assert "\r" not in text, f"{SIDECAR} must use LF line endings"
    items = set(re.findall(r"\b[A-Z]+-\d+\b", text))
    assert items and all(item.startswith("EXAMPLE-") for item in items), f"{SIDECAR} names non-example items: {items}"


def _seed():
    import sys
    spec = importlib.util.spec_from_file_location("seed_lane_dashboard_demo", PRODUCT_ROOT / SEED)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_seed_finds_the_lane_kit_beside_its_zip(tmp_path: Path, monkeypatch) -> None:
    """Every distribution ships `lane-kit-<v>.zip` beside `lane-kit-<v>/`; the documented default
    (no --lane-kit) must pick the directory, not refuse because the zip matched the same name."""
    seed = _seed()
    kit = tmp_path / "multi-session" / "lane-kit-9.9.9"
    for writer in (seed.REGISTRY, seed.BOARD, seed.DASHBOARD):
        (kit / writer).parent.mkdir(parents=True, exist_ok=True)
        (kit / writer).write_text("", encoding="utf-8")
    (tmp_path / "multi-session" / "lane-kit-9.9.9.zip").write_bytes(b"PK\x05\x06" + bytes(18))
    monkeypatch.setattr(seed, "ROOT", tmp_path)
    assert seed.find_lane_kit(None) == kit.resolve()


def _recorder():
    spec = importlib.util.spec_from_file_location("record_lane_dashboard", PRODUCT_ROOT / RECORDER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_recorder_holds_each_painted_frame_until_the_next(tmp_path: Path) -> None:
    """Chromium's screencast sends a frame only when the page repaints; the output rate is fixed, so
    output frame k is the last frame painted at or before k/fps -- never a later one, never a gap."""
    recorder = _recorder()
    painted = []
    for index, second in enumerate((100.0, 100.25, 100.31, 101.0)):
        path = tmp_path / f"raw{index}.png"
        path.write_bytes(bytes([index]))
        painted.append((second, path))
    out = tmp_path / "out"
    out.mkdir()
    assert recorder.resample(painted, 10, 1.5, out) == 15
    shown = [(out / f"{k:06d}.png").read_bytes()[0] for k in range(15)]
    assert shown == [0, 0, 0, 1, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3], shown


def test_the_sidecar_prints_no_machine_path() -> None:
    recorder = _recorder()
    assert recorder.shown_path(PRODUCT_ROOT / "assets" / "ui") == "assets/ui"
    outside = recorder.shown_path(PRODUCT_ROOT.parents[2] / "somewhere" / "lane-dashboard.mp4")
    assert outside == "<outside this repository>/lane-dashboard.mp4", outside


def test_the_recorder_and_the_seed_are_in_the_maintainer_scripts() -> None:
    for script in (RECORDER, SEED):
        path = PRODUCT_ROOT / script
        assert path.is_file(), f"{script} does not exist"
        source = path.read_text(encoding="utf-8")
        assert re.search(r"^from playwright|^import playwright", source, re.MULTILINE) is None, (
            f"{script} imports playwright at module level; loading it must need only the standard library")
