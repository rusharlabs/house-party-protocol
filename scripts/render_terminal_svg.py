#!/usr/bin/env python3
"""Render the real output of `hpp doctor` and `hpp init` as SVG "screenshots" for the README.

A PNG screenshot goes stale the day the output changes and cannot be diffed. These SVGs are
text: the generator runs the two commands against an empty target, keeps the bytes it read, and
paints them in the brand palette with a system monospace font (no font is embedded, nothing is
fetched). Regenerate after any change to the wizard's output:

    python scripts/render_terminal_svg.py                 # writes assets/terminal/hpp-{doctor,init}.svg
    python scripts/render_terminal_svg.py --from-text out.txt --command "hpp status" --out x.svg

The commands run with the repository root on PYTHONPATH from a temporary directory whose only
content is an empty `your-repo/`, so the captured text carries no machine path: every command
the wizard prints reads `--target your-repo`. Standard library only.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets" / "terminal"

BG, PANEL, FG, ACCENT, DIM = "#0F1113", "#16191C", "#F4F1EB", "#FF6A00", "#8E8A83"
FONT = "ui-monospace, Menlo, Consolas, 'Liberation Mono', monospace"
FONT_SIZE, LINE_H, CHAR_W, PAD, HEADER_H = 13, 20, 7.9, 24, 40

# Lines that open a section the README does not need: the init capture stops before the first.
DEFAULT_STOP = ("  PLAN", "  MODULES", "  WIRE", "  NEXT")
_SECTION = re.compile(r"^(\s{2})([A-Z][A-Z ]+?)(\s{2,}.*)?$")


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
    width = int(max(len(l) for l in body) * CHAR_W + 2 * PAD)
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
    args = parser.parse_args(argv)
    stamp = date.today().isoformat()

    if args.from_text:
        if not (args.command and args.out):
            parser.error("--from-text needs --command and --out")
        lines = args.from_text.read_text(encoding="utf-8").splitlines()
        kept, cut = (lines, []) if args.no_truncate else truncate(lines, DEFAULT_STOP)
        args.out.write_text(render(args.command, kept, cut, stamp), encoding="utf-8", newline="\n")
        print(f"wrote {args.out} ({len(kept)} line(s))")
        return 0

    jobs = {
        "hpp-doctor.svg": (["doctor"], "python -m hpp doctor", ()),
        "hpp-init.svg": (["init", "--target", "your-repo", "--non-interactive", "--no-animation"],
                         "python -m hpp init --target your-repo --non-interactive --no-animation",
                         () if args.no_truncate else DEFAULT_STOP),
    }
    root = args.root.resolve()
    if not (root / "hpp" / "__init__.py").is_file():
        parser.error(f"{root} has no hpp/ package")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name, (hpp_args, label, stop) in jobs.items():
        lines = run_capture(hpp_args, root).splitlines()
        kept, cut = truncate(lines, stop) if stop else (lines, [])
        out = args.out_dir / name
        out.write_text(render(label, kept, cut, stamp), encoding="utf-8", newline="\n")
        print(f"wrote {out} ({len(kept)} of {len(lines)} line(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
