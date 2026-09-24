"""The READMEs' images must exist, match across languages, and be real captured output.

Three surfaces can drift apart without anybody noticing, because a broken image renders as
a small grey box on GitHub and nothing in the suite looks at it:

1. a README shows `assets/…` that is not in the tree (renamed asset, typo in the path);
2. one language gains a capture and the other keeps the old set, so the pt-BR reader is
   shown a smaller product than the English reader;
3. a "screenshot" is drawn by hand instead of rendered from a command's real stdout, which
   is the whole reason this project keeps its captures as text (see
   `scripts/render_terminal_svg.py`): a hand-drawn one cannot go stale, because it was never
   true.

The first two checks are also this file's CONTROL: they pass over the captures that already
shipped, so a failure of the lane-board checks below means the lane board is missing, not
that the scan is broken. Both READMEs live beside this `tests/` directory in the source tree
and in the emitted copy alike, so nothing here skips.
"""
from __future__ import annotations

import re
from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parents[1]
READMES = ("README.md", "README.pt-BR.md")

# `src="…"` of an <img>, which is how every capture is placed (centred, inside <p align>).
_IMG_SRC = re.compile(r'<img\b[^>]*?\bsrc="([^"]+)"', re.IGNORECASE | re.DOTALL)

LANE_BOARD = "assets/terminal/lane-board.svg"

# The sentence `render()` writes into every SVG it paints. A capture without it was not
# produced by the generator — which is exactly what "drawn by hand" looks like from here.
GENERATOR_MARK = "scripts/render_terminal_svg.py; no image was edited by hand"

# The states `lane_board.py` imposes in code (its `_TRANSITIONS`). A board worth showing has
# items sitting in several of them at once; one item alone proves nothing about the machine.
BOARD_STATES = (
    "CLAIMED", "BUILDING", "CHECKPOINT-READY", "UNDER-REVIEW",
    "VERIFIED", "NEEDS-FIX", "DEFERRED", "MERGED",
)


def _image_sources(name: str) -> list[str]:
    text = (PRODUCT_ROOT / name).read_text(encoding="utf-8")
    return _IMG_SRC.findall(text)


def test_CONTROLE_every_image_the_readmes_show_exists_on_disk() -> None:
    """CONTROL — true for the captures already shipped; catches a renamed or mistyped asset."""
    missing = [
        f"{name}: {src}"
        for name in READMES
        for src in _image_sources(name)
        if not src.startswith(("http://", "https://")) and not (PRODUCT_ROOT / src).is_file()
    ]
    assert not missing, "README images with no file behind them:\n  " + "\n  ".join(missing)


def test_CONTROLE_both_languages_show_the_same_terminal_captures() -> None:
    """CONTROL — the pt-BR reader must be shown the same proof as the English reader."""
    per_language = {
        name: sorted(src for src in _image_sources(name) if src.startswith("assets/terminal/"))
        for name in READMES
    }
    english, portuguese = per_language["README.md"], per_language["README.pt-BR.md"]
    assert english == portuguese, (
        "the two READMEs show different terminal captures\n"
        f"  only in README.md:       {sorted(set(english) - set(portuguese))}\n"
        f"  only in README.pt-BR.md: {sorted(set(portuguese) - set(english))}"
    )


def test_readmes_show_the_lane_board_capture() -> None:
    """The lane board is the product's one enforced state machine and had no visual proof."""
    absent = [name for name in READMES if LANE_BOARD not in _image_sources(name)]
    assert not absent, f"{LANE_BOARD} is not shown by: {', '.join(absent)}"


def test_the_lane_board_capture_is_rendered_from_a_real_render_command() -> None:
    """It must be generator output of `lane_board.py render`, with items in several states."""
    capture = PRODUCT_ROOT / LANE_BOARD
    assert capture.is_file(), f"{LANE_BOARD} does not exist"
    svg = capture.read_text(encoding="utf-8")

    assert GENERATOR_MARK in svg, (
        f"{LANE_BOARD} carries no trace of scripts/render_terminal_svg.py — a capture that was "
        "not rendered from a command's stdout is a drawing, and a drawing cannot go stale"
    )
    assert "lane_board.py render" in svg, (
        f"{LANE_BOARD} does not show `lane_board.py render` as the command that produced it"
    )

    shown = {state for state in BOARD_STATES if state in svg}
    assert len(shown) >= 4, (
        f"{LANE_BOARD} shows only {sorted(shown)} — a board with items in fewer than four of "
        f"the states in {list(BOARD_STATES)} does not demonstrate the state machine"
    )
    items = set(re.findall(r"EXAMPLE-[A-Z0-9-]+", svg))
    assert len(items) >= 3, (
        f"{LANE_BOARD} shows {len(items)} example item(s) ({sorted(items)}); the point of the "
        "capture is several lanes on one board, and the ids must be plainly examples"
    )
