"""Brand data for the CLI: palette, block wordmark, signature and closing lines."""
from __future__ import annotations

from typing import Sequence

from hpp.term import Console

# Why: one table holds every brand colour the CLI may emit, so a palette change is a data edit.
PALETTE = {
    "black": (0, 0, 0),
    "charcoal": (15, 17, 19),
    "warm_white": (244, 241, 235),
    "signal_orange": (255, 106, 0),
}

PALETTE_HEX = {name: "#%02X%02X%02X" % rgb for name, rgb in PALETTE.items()}

WORDMARK = ("HOUSE PARTY", "PROTOCOL")
SIGNATURE = "BY RUSHAR LABS"
BRAND_LINES = (
    "Welcome to the party.",
    "Open. Modular. Auditable. Composable.",
    "Agents today. A more open tomorrow.",
)

# Why: a 4x5 cell font keeps both wordmark rows under 60 columns, which fits an 80-column
# terminal with the indentation used by the rest of the report.
_FONT = {
    "H": ("#  #", "#  #", "####", "#  #", "#  #"),
    "O": ("####", "#  #", "#  #", "#  #", "####"),
    "U": ("#  #", "#  #", "#  #", "#  #", "####"),
    "S": ("####", "#   ", "####", "   #", "####"),
    "E": ("####", "#   ", "### ", "#   ", "####"),
    "P": ("####", "#  #", "####", "#   ", "#   "),
    "A": ("####", "#  #", "####", "#  #", "#  #"),
    "R": ("####", "#  #", "### ", "# # ", "#  #"),
    "T": ("####", " #  ", " #  ", " #  ", " #  "),
    "Y": ("#  #", "#  #", "####", "  # ", "  # "),
    "C": ("####", "#   ", "#   ", "#   ", "####"),
    "L": ("#   ", "#   ", "#   ", "#   ", "####"),
    " ": ("  ", "  ", "  ", "  ", "  "),
}
_ROWS = 5


def render_wordmark(text: str, cell: str) -> list[str]:
    """Render `text` in the block font, using `cell` for filled cells."""
    rows: list[str] = []
    for row_index in range(_ROWS):
        parts = []
        for letter in text.upper():
            glyph = _FONT.get(letter)
            if glyph is None:
                raise ValueError(f"no glyph for {letter!r}")
            parts.append(glyph[row_index].replace("#", cell))
        rows.append(" ".join(parts).rstrip())
    return rows


def wordmark_width() -> int:
    return max(len(line) for text in WORDMARK for line in render_wordmark(text, "#"))


def logo_lines(console: Console, indent: str = "  ") -> list[str]:
    """The lockup as printable lines: wordmark rows, rule and signature."""
    orange = PALETTE["signal_orange"]
    white = PALETTE["warm_white"]
    lines: list[str] = []
    if console.width >= wordmark_width() + len(indent) + 2:
        for row in render_wordmark(WORDMARK[0], console.glyph("full")):
            lines.append(indent + console.paint(row, white, bold=True))
        for row in render_wordmark(WORDMARK[1], console.glyph("half")):
            lines.append(indent + console.paint(row, orange, bold=True))
    else:
        compact = f"{WORDMARK[0]} {console.glyph('bullet')} {WORDMARK[1]}"
        lines.append(indent + console.paint(compact, white, bold=True))
    rule = console.glyph("rule") * min(wordmark_width(), max(console.width - len(indent) - 2, 8))
    lines.append(indent + console.paint(rule, orange))
    lines.append(indent + console.paint(SIGNATURE, white, dim=True))
    return lines


def closing_line(console: Console, text: str) -> str:
    """The `> <brand line>` prompt that precedes the blinking cursor."""
    return console.paint("> ", PALETTE["signal_orange"]) + console.paint(text, PALETTE["warm_white"], bold=True)


def pick_closing(status: str, lines: Sequence[str] = BRAND_LINES) -> str:
    """A brand line for a successful run; a halted run never gets the party line."""
    return lines[0] if status in {"ok", "no-op", "warn"} else lines[1]
