"""Terminal capability detection and ANSI output with graceful degradation."""
from __future__ import annotations

import os
import shutil
import sys
import time
from typing import IO, Any, Mapping, Optional

TIERS = ("truecolor", "256", "16", "none")

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[31m"
_CLEAR_LINE = "\033[2K"

# Why: the xterm defaults are the most widely rendered 16-colour table, so nearest-colour
# matching against them degrades predictably on terminals without 256/truecolor support.
_BASIC16 = (
    (30, (0, 0, 0)), (31, (205, 0, 0)), (32, (0, 205, 0)), (33, (205, 205, 0)),
    (34, (0, 0, 238)), (35, (205, 0, 205)), (36, (0, 205, 205)), (37, (229, 229, 229)),
    (90, (127, 127, 127)), (91, (255, 0, 0)), (92, (0, 255, 0)), (93, (255, 255, 0)),
    (94, (92, 92, 255)), (95, (255, 0, 255)), (96, (0, 255, 255)), (97, (255, 255, 255)),
)

GLYPHS_UNICODE = {
    "ok": "✓", "fail": "✗", "warn": "!", "skip": "·", "bullet": "▸", "cursor": "█",
    "full": "█", "half": "▓", "light": "░", "bar": "│", "tee": "├", "corner": "└", "rule": "─",
}
GLYPHS_ASCII = {
    "ok": "OK", "fail": "X", "warn": "!", "skip": "-", "bullet": ">", "cursor": "#",
    "full": "#", "half": "=", "light": ".", "bar": "|", "tee": "+", "corner": "`", "rule": "-",
}


def enable_windows_vt(stream: Optional[IO[str]] = None) -> bool:
    """Turn on virtual-terminal processing for a Windows console; True when escapes will render."""
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle_id = -12 if stream is sys.stderr else -11
        handle = kernel32.GetStdHandle(handle_id)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        if mode.value & 0x0004:
            return True
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except (AttributeError, OSError, ValueError):
        return False


def _is_tty(stream: Any) -> bool:
    probe = getattr(stream, "isatty", None)
    if probe is None:
        return False
    try:
        return bool(probe())
    except (OSError, ValueError):
        return False


def detect_tier(stream: Optional[IO[str]] = None, env: Optional[Mapping[str, str]] = None,
                isatty: Optional[bool] = None, platform: Optional[str] = None) -> str:
    """Pick the colour tier: NO_COLOR > FORCE_COLOR > tty > TERM > COLORTERM > platform."""
    env = os.environ if env is None else env
    stream = sys.stdout if stream is None else stream
    platform = os.name if platform is None else platform
    if env.get("NO_COLOR", "") != "":
        return "none"
    force = env.get("FORCE_COLOR")
    if force is not None and force != "":
        lowered = force.strip().lower()
        if lowered in {"0", "false", "no"}:
            return "none"
        return {"1": "16", "2": "256"}.get(lowered, "truecolor")
    tty = _is_tty(stream) if isatty is None else isatty
    if not tty:
        return "none"
    term = env.get("TERM", "")
    if term == "dumb":
        return "none"
    if env.get("COLORTERM", "").lower() in {"truecolor", "24bit"}:
        return "truecolor"
    if platform == "nt":
        if not enable_windows_vt(stream):
            return "none"
        return "truecolor" if env.get("WT_SESSION") else "256"
    if "256color" in term:
        return "256"
    return "16"


def rgb_to_256(rgb: tuple[int, int, int]) -> int:
    red, green, blue = rgb
    if abs(red - green) < 10 and abs(green - blue) < 10:
        if red < 8:
            return 16
        if red > 248:
            return 231
        return 232 + round((red - 8) / 247 * 23)
    return 16 + 36 * round(red / 255 * 5) + 6 * round(green / 255 * 5) + round(blue / 255 * 5)


def rgb_to_16(rgb: tuple[int, int, int]) -> int:
    red, green, blue = rgb

    def distance(candidate: tuple[int, int, int]) -> int:
        return (candidate[0] - red) ** 2 + (candidate[1] - green) ** 2 + (candidate[2] - blue) ** 2

    return min(_BASIC16, key=lambda item: distance(item[1]))[0]


def color_prefix(rgb: tuple[int, int, int], tier: str) -> str:
    if tier == "truecolor":
        return "\033[38;2;%d;%d;%dm" % rgb
    if tier == "256":
        return "\033[38;5;%dm" % rgb_to_256(rgb)
    if tier == "16":
        return "\033[%dm" % rgb_to_16(rgb)
    return ""


class Console:
    """Writes styled text to one stream; every effect collapses to plain text when unsupported."""

    def __init__(self, stream: Optional[IO[str]] = None, tier: Optional[str] = None,
                 animate: Optional[bool] = None, env: Optional[Mapping[str, str]] = None,
                 width: Optional[int] = None, sleep: Any = time.sleep) -> None:
        self.stream = sys.stdout if stream is None else stream
        self.env = os.environ if env is None else env
        self.tier = detect_tier(self.stream, self.env) if tier is None else tier
        if self.tier not in TIERS:
            raise ValueError(f"unknown colour tier: {self.tier}")
        tty = _is_tty(self.stream)
        wants_animation = tty and self.tier != "none" and not self.env.get("CI")
        self.animate = wants_animation if animate is None else (animate and wants_animation)
        self.width = width or shutil.get_terminal_size((80, 24)).columns
        self._sleep = sleep
        self.glyphs = GLYPHS_UNICODE if self._encodes("█✓✗▓░│├└▸─") else GLYPHS_ASCII

    def _encodes(self, sample: str) -> bool:
        encoding = getattr(self.stream, "encoding", None) or "utf-8"
        try:
            sample.encode(encoding)
        except (UnicodeEncodeError, LookupError):
            return False
        return True

    def glyph(self, name: str) -> str:
        return self.glyphs[name]

    def paint(self, text: str, rgb: Optional[tuple[int, int, int]] = None, *, bold: bool = False,
              dim: bool = False, red: bool = False) -> str:
        if self.tier == "none" or not text:
            return text
        prefix = ""
        if bold:
            prefix += _BOLD
        if dim:
            prefix += _DIM
        if red:
            prefix += _RED
        elif rgb is not None:
            prefix += color_prefix(rgb, self.tier)
        return f"{prefix}{text}{_RESET}" if prefix else text

    def _emit(self, text: str) -> None:
        if self.glyphs is GLYPHS_ASCII:
            text = text.replace("·", "-").replace("—", "-")
        try:
            self.stream.write(text)
        except UnicodeEncodeError:
            encoding = getattr(self.stream, "encoding", None) or "utf-8"
            self.stream.write(text.encode(encoding, errors="replace").decode(encoding))

    def write(self, text: str = "", end: str = "\n") -> None:
        self._emit(text + end)

    def transient(self, text: str) -> None:
        """Show a line that a later `rewrite` will replace; a no-op unless animating."""
        if self.animate:
            self._emit(text)
            self.stream.flush()

    def rewrite(self, text: str) -> None:
        if self.animate:
            self._emit("\r" + _CLEAR_LINE + text + "\n")
            self.stream.flush()
        else:
            self.write(text)

    def pause(self, seconds: float) -> None:
        if self.animate and seconds > 0:
            self._sleep(seconds)

    def blink_cursor(self, text: str, cycles: int = 3) -> None:
        """Blink the brand cursor after `text`; without animation the cursor is simply printed."""
        cursor = self.glyph("cursor")
        if self.animate:
            for _ in range(cycles):
                self._emit("\r" + _CLEAR_LINE + text + cursor)
                self.stream.flush()
                self._sleep(0.22)
                self._emit("\r" + _CLEAR_LINE + text + " ")
                self.stream.flush()
                self._sleep(0.16)
            self._emit("\r" + _CLEAR_LINE)
        self.write(text + cursor)
        self.stream.flush()
