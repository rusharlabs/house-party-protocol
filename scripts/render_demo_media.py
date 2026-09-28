#!/usr/bin/env python3
"""Turn an animated terminal svg into a looping GIF and an MP4 for places that do not play svg.

The README's sessions are svg files animated by CSS (`scripts/render_terminal_svg.py --animate`).
A social timeline shows neither an svg nor its animation, so the posts carry a GIF and an MP4 of
the same file. Nothing is re-typed or re-timed: a headless browser loads the svg, pauses every
CSS animation in it, and steps them all to one instant of the file's own cycle per frame, at a
fixed rate from 0 to the cycle the svg declares. One loop of the video is one loop of the file.

The capture forces `prefers-reduced-motion: no-preference`. Under `reduce` the svg is, by design,
a still of its finished screen, and on a machine whose system turns animations off the browser
would otherwise record that still a few hundred times. The run refuses when the page reports no
animation to step, and it checks the opposite once: under `reduce` the same page must report
none. The page behind the svg is painted the terminal's own background, so the window's rounded
corners do not show white in a video frame.

Two encodes follow, both at the same width:

- GIF: one palette computed from all the frames (palettegen, then paletteuse without dithering),
  looping forever. A GIF counts each frame's delay in hundredths of a second, so at 10 frames per
  second every delay is exactly 10 and the loop lasts the svg's cycle; at a rate that does not
  divide 100 (12 fps is 8.33) each delay is rounded and the loop runs fast.
- MP4: H.264, yuv420p, with the index moved to the front (+faststart) for players that stream.

Each output is then measured with ffprobe, frames and duration, and compared with the cycle and
with a size budget (4 MB for the GIF, 2 MB for the MP4 by default); a miss exits 1.

This is a maintainer tool, run when a capture changes. It is not part of the package (the wheel
ships only `hpp/`), and it needs what the harness does not: the `playwright` Python package with
its Chromium, and an `ffmpeg` binary with `ffprobe` beside it (`--ffmpeg`, or on PATH).

    python scripts/render_demo_media.py assets/terminal/hpp-demo.svg --out-dir media/
    python scripts/render_demo_media.py assets/terminal/*.svg --out-dir media/ --ffmpeg /path/to/ffmpeg
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# What scripts/render_terminal_svg.py writes into every animated capture: the shared cycle of the
# screen, and the size of the file.
_CYCLE = re.compile(r"\.s\s*\{[^}]*animation:\s*s\s+([\d.]+)s")
_SIZE = re.compile(r'<svg\b[^>]*?\bwidth="(\d+)"[^>]*?\bheight="(\d+)"')
BACKGROUND = "#0F1113"  # the terminal's own background (BG in render_terminal_svg.py)

# Pause every animation of the document and move it to `t` milliseconds; answer how many there are.
_STEP = "t => { const all = document.getAnimations(); for (const a of all) { a.pause(); a.currentTime = t; } return all.length; }"


def read_capture(svg: Path) -> tuple[float, int, int]:
    """(cycle in seconds, width, height) of an animated capture; anything else is refused."""
    text = svg.read_text(encoding="utf-8")
    cycle, size = _CYCLE.search(text), _SIZE.search(text)
    if cycle is None or size is None:
        raise SystemExit(f"{svg}: not an animated capture of scripts/render_terminal_svg.py (no cycle or no size)")
    return float(cycle.group(1)), int(size.group(1)), int(size.group(2))


def capture(svg: Path, frames: Path, fps: int, scale: int) -> tuple[int, int]:
    """Screenshot one loop of `svg` into frames/000000.png onwards; return (frames, animations)."""
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise SystemExit("the capture needs the playwright package and its Chromium: "
                         "pip install playwright, then python -m playwright install chromium") from exc
    cycle, width, height = read_capture(svg)
    count = round(cycle * fps)
    url = svg.resolve().as_uri()
    with sync_playwright() as driver:
        browser = driver.chromium.launch()
        try:
            still = browser.new_context(reduced_motion="reduce")
            page = still.new_page()
            page.goto(url)
            if page.evaluate(_STEP, 0):
                raise SystemExit(f"{svg}: under prefers-reduced-motion: reduce it still animates; it must be a still")
            still.close()
            moving = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=scale,
                                         reduced_motion="no-preference")
            page = moving.new_page()
            page.goto(url)
            animations = page.evaluate(_STEP, 0)
            if not animations:
                raise SystemExit(f"{svg}: the page reports no CSS animation to step")
            page.evaluate(f"() => {{ document.documentElement.style.background = '{BACKGROUND}'; }}")
            for index in range(count):
                page.evaluate(_STEP, index * 1000 / fps)
                page.screenshot(path=str(frames / f"{index:06d}.png"))
        finally:
            browser.close()
    return count, animations


def encode(ffmpeg: str, frames: Path, fps: int, width: int, gif: Path, mp4: Path) -> None:
    """The GIF (one palette over every frame, no dithering, endless loop) and the MP4 (H.264 yuv420p)."""
    source = ["-framerate", str(fps), "-i", str(frames / "%06d.png")]
    scale = f"scale={width}:-2:flags=lanczos"
    commands = (
        [*source, "-vf", f"{scale},split[a][b];[a]palettegen=max_colors=128:stats_mode=full[p];"
                         "[b][p]paletteuse=dither=none:diff_mode=rectangle", "-loop", "0", str(gif)],
        [*source, "-vf", f"{scale},format=yuv420p", "-c:v", "libx264", "-preset", "veryslow", "-crf", "20",
         "-movflags", "+faststart", str(mp4)],
    )
    for arguments in commands:
        result = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *arguments],
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise SystemExit(f"ffmpeg exited {result.returncode}:\n{result.stderr}")


def probe(ffprobe: str, path: Path) -> dict[str, float]:
    """Width, height, decoded frame count and duration of a video file, as ffprobe reads them."""
    result = subprocess.run([ffprobe, "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                             "stream=width,height,nb_read_frames:format=duration", "-of", "json", str(path)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise SystemExit(f"ffprobe could not read {path}:\n{result.stderr}")
    data = json.loads(result.stdout)
    stream = data["streams"][0]
    return {"width": int(stream["width"]), "height": int(stream["height"]),
            "frames": int(stream["nb_read_frames"]), "duration": float(data["format"]["duration"])}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("svgs", nargs="+", type=Path, help="animated captures written by render_terminal_svg.py")
    parser.add_argument("--out-dir", type=Path, required=True, help="where <name>.gif and <name>.mp4 are written")
    parser.add_argument("--fps", type=int, default=10, help="frames per second of the capture (default 10)")
    parser.add_argument("--width", type=int, default=960, help="width of both outputs in pixels (default 960)")
    parser.add_argument("--scale", type=int, default=2,
                        help="device pixels per svg pixel while capturing; the encode scales down (default 2)")
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg"), help="the ffmpeg binary (default: on PATH)")
    parser.add_argument("--gif-budget", type=int, default=4_000_000, help="largest GIF in bytes (default 4 MB)")
    parser.add_argument("--mp4-budget", type=int, default=2_000_000, help="largest MP4 in bytes (default 2 MB)")
    args = parser.parse_args(argv)
    ffmpeg = (shutil.which(args.ffmpeg) or (args.ffmpeg if Path(args.ffmpeg).is_file() else None)) if args.ffmpeg else None
    if ffmpeg is None:
        parser.error("no ffmpeg: pass --ffmpeg or put it on PATH")
    ffprobe = shutil.which("ffprobe", path=str(Path(ffmpeg).parent)) or shutil.which("ffprobe")
    if ffprobe is None:
        parser.error("no ffprobe beside ffmpeg or on PATH: the outputs could not be measured")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    missed = []
    for svg in args.svgs:
        cycle, _, _ = read_capture(svg)
        gif, mp4 = args.out_dir / f"{svg.stem}.gif", args.out_dir / f"{svg.stem}.mp4"
        with tempfile.TemporaryDirectory(prefix="hpp-media-") as tmp:
            count, animations = capture(svg, Path(tmp), args.fps, args.scale)
            encode(ffmpeg, Path(tmp), args.fps, args.width, gif, mp4)
        print(f"{svg.name}: cycle {cycle:g} s, {animations} animations stepped, {count} frames at {args.fps} fps "
              f"= {count / args.fps:g} s")
        for path, budget in ((gif, args.gif_budget), (mp4, args.mp4_budget)):
            measured = probe(ffprobe, path)
            size = path.stat().st_size
            verdict = "ok" if size <= budget and measured["frames"] == count else "MISS"
            if verdict == "MISS":
                missed.append(path.name)
            print(f"  {path}: {measured['width']}x{measured['height']}, {measured['frames']} frames, "
                  f"{measured['duration']:g} s, {size:,} bytes (budget {budget:,}) {verdict}")
    if missed:
        print(f"over budget or short of frames: {', '.join(missed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
