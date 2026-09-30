#!/usr/bin/env python3
"""Record the Lane Dashboard from a live run: the animated GIF the README and the manual show, and an MP4.

Nothing on the page is staged. `seed_lane_dashboard_demo.py` builds a throwaway project through
lane-kit's own writers; `lane_dashboard.py serve --no-orca --port 0` serves it on loopback; a
headless Chromium opens the page at 1280x800 and the story below plays against the live server:

    0 s    the page as it opens: the metrics, the backlog and its two dependency waves
    3 s    the board
    4 s    the recorder runs ONE terminal command in its own process,
               python lane_board.py set EXAMPLE-1 CHECKPOINT-READY ...
           and the page moves EXAMPLE-1 from "Building" to "Ready for review" by itself (the server
           re-reads the board every 0.75 s and tells the page over server-sent events)
    10 s   "Approve merge" on the red item EXAMPLE-2 opens its dialog, which names the terminal command
           that does the same thing (lane_board.py approve EXAMPLE-2); "Cancel" closes it
    14 s   the language switch: English, then Português, and the board in Portuguese (AT holds the clock)

Two things on screen are the recorder's, and the sidecar says so: the terminal strip at the bottom
during the command is an overlay drawn over the page, holding the command the recorder ran and the
stdout it printed; and every POST the page sends is counted, the ones to the server's actions
(`api/...`) aborted before they leave, so no action can be submitted by accident. A run that counts
any POST, or whose card does not move within five seconds, stops without writing anything.

Frames come from Chromium's screencast (a frame each time the page repaints, with its timestamp)
and are resampled to a fixed rate, the last frame held until the next. The encode is the one of
`render_demo_media.py`: one palette over every frame, no dithering, an endless loop; H.264 yuv420p
for the MP4. Beside the GIF the recorder writes `<name>.gif.txt`, the sidecar: the command that
produced it, the seed's commands, the story as it was measured, and the sizes. A GIF has no place
for its own command; the svg captures keep theirs in `<desc>`. Every `--copy-to` directory gets the
sidecar with the GIF, so the manual served from `docs/` can point at it.

This is a maintainer tool, run when the dashboard changes. It is not part of the package and it
needs what the harness does not: the `playwright` package with its Chromium, `ffmpeg` with
`ffprobe` beside it, and `git`. Every process it starts (the writers, the server, the browser) is
stopped before it exits, on success and on failure.

    python scripts/record_lane_dashboard.py --out-dir assets/ui --copy-to docs/assets/ui
    python scripts/record_lane_dashboard.py --out-dir assets/ui --lane-kit DIR --mp4 media/lane-dashboard.mp4

Exit: 0 recorded within budget · 1 the story or a budget failed · 2 invalid usage.
"""
from __future__ import annotations

import argparse
import base64
import json
import queue
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
# Why: importing the two scripts beside this one would leave a __pycache__ inside the product tree.
sys.dont_write_bytecode = True
import render_demo_media as media  # noqa: E402 -- the maintainer scripts beside this one
import seed_lane_dashboard_demo as seed  # noqa: E402

NAME = "lane-dashboard"
VIEWPORT = {"width": 1280, "height": 800}
# The story's clock, in seconds from the first frame; the last frame is held until DURATION.
AT = {"board": 3.0, "terminal": 3.8, "strip_off": 10.0, "dialog": 10.4, "cancel": 13.4, "top": 13.8,
      "portuguese": 14.6, "board_pt": 17.0}
DURATION = 19.5
TYPING = 90  # characters per second of the command typed into the strip
BRAND = {"black": "#0F1113", "paper": "#F4F1EB", "signal": "#FF6A00"}
# The server as the sidecar prints it: the seeded project lives in a temporary directory.
SERVE_SHOWN = ("python", "lane_dashboard.py", "serve", "--project-dir", "<the seeded project>", "--no-orca", "--port", "0")

# The strip the recorder draws over the page while its command runs. It is the recorder's, not the
# dashboard's, and it says only what the command was and what it printed.
_OVERLAY = """([title, command, charsPerSecond]) => {
  const box = document.createElement("div");
  box.id = "hpp-recorder-terminal";
  box.setAttribute("style", "position:fixed;left:20px;right:20px;bottom:16px;z-index:2147483647;"
    + "background:%(black)s;color:%(paper)s;border:1px solid rgba(244,241,235,.28);border-radius:12px;"
    + "padding:12px 16px 14px;font:13px/1.55 'JetBrains Mono',Consolas,monospace;"
    + "box-shadow:0 12px 40px rgba(0,0,0,.55);white-space:pre-wrap;word-break:break-all");
  const head = document.createElement("div");
  head.setAttribute("style", "font-size:11px;letter-spacing:.14em;text-transform:uppercase;"
    + "color:rgba(244,241,235,.6);margin-bottom:6px");
  head.textContent = title;
  const line = document.createElement("div");
  const prompt = document.createElement("span");
  prompt.setAttribute("style", "color:%(signal)s");
  prompt.textContent = "$ ";
  const typed = document.createElement("span");
  const out = document.createElement("div");
  out.setAttribute("style", "color:rgba(244,241,235,.82);margin-top:4px");
  line.append(prompt, typed);
  box.append(head, line, out);
  document.body.append(box);
  window.__hppTyped = false;
  let shown = 0;
  const timer = setInterval(() => {
    shown += 1;
    typed.textContent = command.slice(0, shown);
    if (shown >= command.length) { clearInterval(timer); window.__hppTyped = true; }
  }, 1000 / charsPerSecond);
  window.__hppPrint = text => { out.textContent = text; };
}""" % BRAND
_BOARD_TOP = ("() => { const s = document.querySelector('section[aria-labelledby=board-title]');"
              " return Math.max(0, s.getBoundingClientRect().top + window.scrollY - 16); }")
_SCROLL = "y => window.scrollTo({top: y, behavior: 'instant'})"
_IN_COLUMN = ("([group, item]) => [...document.querySelectorAll(`section.column[data-group=${group}] .card .id`)]"
              ".some(e => e.textContent.trim() === item)")


def shown_path(path: Path) -> str:
    """A path as the sidecar may print it: relative to the product root, never a machine path."""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return f"<outside this repository>/{path.name}"


def kit_version(kit: Path) -> str:
    manifest = kit / ".claude-plugin" / "plugin.json"
    try:
        return str(json.loads(manifest.read_text(encoding="utf-8")).get("version") or "unknown")
    except (OSError, ValueError):
        return "unknown"


class Server:
    """`lane_dashboard.py serve` on a free loopback port, its output drained so the pipe never fills."""

    def __init__(self, kit: Path, project: Path) -> None:
        self.process = subprocess.Popen(
            [sys.executable, "-X", "utf8", str(kit / seed.DASHBOARD), "serve", "--project-dir", str(project),
             "--no-orca", "--port", "0"], cwd=project, env=seed.environment(project), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        self.lines: queue.Queue[str] = queue.Queue()
        self.tail: list[str] = []
        threading.Thread(target=self._drain, daemon=True).start()
        self.url = self._url()

    def _drain(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self.tail = [*self.tail[-20:], line.rstrip()]
            self.lines.put(line)

    def _url(self) -> str:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                line = self.lines.get(timeout=0.5)
            except queue.Empty:
                if self.process.poll() is not None:
                    break
                continue
            found = re.search(r"Lane Dashboard: (http://127\.0\.0\.1:\d+/)", line)
            if found:
                return found.group(1)
        self.stop()
        raise SystemExit("record: the dashboard did not print its URL:\n" + "\n".join(self.tail))

    def stop(self) -> int | None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(10)
        return self.process.returncode


def play(url: str, kit: Path, project: Path, raw: Path) -> dict:
    """Open the page, play the story, and write every screencast frame to `raw`; return what was measured."""
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise SystemExit("record: the recording needs the playwright package and its Chromium: "
                         "pip install playwright, then python -m playwright install chromium") from exc
    frames: list[tuple[float, Path]] = []
    posts: list[str] = []
    beats: list[tuple[float, str]] = []
    facts: dict = {}
    with sync_playwright() as driver:
        browser = driver.chromium.launch()
        try:
            facts["browser"] = f"Chromium {browser.version}"
            context = browser.new_context(viewport=VIEWPORT, color_scheme="dark", locale="en-US",
                                          reduced_motion="no-preference")
            page = context.new_page()
            page.on("request", lambda request: posts.append(request.url) if request.method == "POST" else None)
            page.route("**/api/**", lambda route: route.abort() if route.request.method == "POST" else route.continue_())
            page.goto(url)
            page.wait_for_function("() => document.querySelectorAll('section.column').length === 6")
            page.wait_for_timeout(1500)  # the first snapshot and the live indicator settle
            cdp = context.new_cdp_session(page)

            def on_frame(event: dict) -> None:
                path = raw / f"{len(frames):06d}.png"
                path.write_bytes(base64.b64decode(event["data"]))
                frames.append((float(event["metadata"]["timestamp"]), path))
                cdp.send("Page.screencastFrameAck", {"sessionId": event["sessionId"]})

            cdp.on("Page.screencastFrame", on_frame)
            cdp.send("Page.startScreencast", {"format": "png", "maxWidth": VIEWPORT["width"],
                                              "maxHeight": VIEWPORT["height"], "everyNthFrame": 1})
            while not frames:
                page.wait_for_timeout(20)
            start = time.monotonic()

            def at(second: float, what: str) -> None:
                left = second - (time.monotonic() - start)
                if left > 0:
                    page.wait_for_timeout(int(left * 1000))
                beats.append((round(time.monotonic() - start, 1), what))

            at(0.0, "the page as it opens: the metrics, the backlog and its two dependency waves")
            at(AT["board"], "the board")
            page.evaluate(_SCROLL, page.evaluate(_BOARD_TOP))
            at(AT["terminal"], f"the recorder types and runs `{seed.display(seed.LIVE_STEP)}`")
            page.evaluate(_OVERLAY, ["terminal · " + project.name, seed.display(seed.LIVE_STEP), TYPING])
            page.wait_for_function("() => window.__hppTyped === true")
            writer, argv, declared = seed.LIVE_STEP
            ran = subprocess.Popen([sys.executable, "-X", "utf8", str(kit / writer), *argv], cwd=project,
                                   env=seed.environment(project), stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
            while ran.poll() is None:
                page.wait_for_timeout(40)
            stdout, stderr = ran.communicate()
            finished = time.monotonic()
            if ran.returncode != declared or stderr.strip():
                raise SystemExit(f"record: {seed.display(seed.LIVE_STEP)} exited {ran.returncode}:\n{stdout}{stderr}")
            page.evaluate("text => window.__hppPrint(text)", stdout.strip())
            facts["live_stdout"] = stdout.strip()
            page.wait_for_function(_IN_COLUMN, arg=["ready", "EXAMPLE-1"], timeout=5000)
            facts["card_moved_after"] = round(time.monotonic() - finished, 2)
            beats.append((round(time.monotonic() - start, 1),
                          f"EXAMPLE-1 is in Ready for review, {facts['card_moved_after']} s after the command exited"))
            at(AT["strip_off"], "the strip is removed")
            page.evaluate("() => document.getElementById('hpp-recorder-terminal').remove()")
            at(AT["dialog"], f"Approve merge on {seed.APPROVE_ITEM} opens its dialog")
            page.click(f'button[data-action="approve"][data-id="{seed.APPROVE_ITEM}"]')
            page.wait_for_selector("#approve-dialog[open]")
            facts["dialog_command"] = page.inner_text("#approve-dialog [data-cli]").strip()
            if f"lane_board.py approve {seed.APPROVE_ITEM}" not in facts["dialog_command"]:
                raise SystemExit(f"record: the dialog does not name the terminal command: {facts['dialog_command']!r}")
            at(AT["cancel"], "Cancel closes the dialog; nothing is submitted")
            page.click("#approve-dialog button[data-close]")
            at(AT["top"], "the top of the page, where the language switch is")
            page.evaluate(_SCROLL, 0)
            at(AT["portuguese"], "Português")
            page.click('[data-lang="pt-BR"]')
            at(AT["board_pt"], "the board in Portuguese")
            page.evaluate(_SCROLL, page.evaluate(_BOARD_TOP))
            at(DURATION, "the end of the loop")
            cdp.send("Page.stopScreencast")
            context.close()
        finally:
            browser.close()
    if posts:
        raise SystemExit(f"record: the page attempted {len(posts)} POST(s); a demo submits nothing: {posts}")
    facts.update(beats=beats, posts=len(posts), frames=frames)
    return facts


def resample(frames: list[tuple[float, Path]], fps: int, duration: float, out: Path) -> int:
    """Frame k of the output is the last screencast frame painted at or before k/fps seconds."""
    first = frames[0][0]
    count = round(duration * fps)
    index = 0
    for k in range(count):
        moment = k / fps
        while index + 1 < len(frames) and frames[index + 1][0] - first <= moment:
            index += 1
        shutil.copyfile(frames[index][1], out / f"{k:06d}.png")
    return count


def sidecar(args: argparse.Namespace, kit: Path, commands: list[str], facts: dict, measured: dict) -> str:
    invocation = ["python", "scripts/record_lane_dashboard.py", "--out-dir", shown_path(args.out_dir)]
    for target in args.copy_to:
        invocation += ["--copy-to", shown_path(target)]
    if args.lane_kit:
        invocation += ["--lane-kit", f"<lane-kit {kit_version(kit)}>"]
    if args.mp4:
        invocation += ["--mp4", shown_path(args.mp4)]
    gif = measured["gif"]
    lines = [
        f"{NAME}.gif -- the Lane Dashboard of lane-kit {kit_version(kit)}, recorded from a live run.",
        "",
        "Produced by (from the root of this repository):",
        f"    {shlex.join(invocation)}",
        f"Recorded {time.strftime('%Y-%m-%d')} with {facts['browser']} headless, a {VIEWPORT['width']}x"
        f"{VIEWPORT['height']} viewport, the dark colour scheme and the en-US locale.",
        f"Encoded {gif['width']}x{gif['height']}, {args.fps} fps, {gif['frames']} frames = {gif['duration']:g} s, "
        f"one 128-colour palette, no dithering, looping forever: {gif['bytes']:,} bytes.",
        "",
        "The project: a new temporary directory, made a git repository of its own, built by",
        "scripts/seed_lane_dashboard_demo.py through lane-kit's own writers, each command with the exit",
        "status the story declares:",
        *(f"    {command}" for command in commands),
        "",
        "The server, on a free loopback port:",
        f"    {shlex.join(SERVE_SHOWN)}",
        "",
        "The story, as measured (seconds from the first frame):",
        *(f"    {second:5.1f}  {what}" for second, what in facts["beats"]),
        "",
        "The terminal command's stdout, as printed:",
        f"    {facts['live_stdout']}",
        f"The dialog's line: {facts['dialog_command']}",
        "",
        "What on screen is not the dashboard: the terminal strip at the bottom is an overlay the recorder",
        "draws over the page while its command runs; it holds the command the recorder ran and the stdout",
        "that command printed, unedited. The recorder counts every POST the page sends and aborts the",
        f"ones to the server's actions (api/...) before they leave; the page sent {facts['posts']}: nothing",
        "was submitted.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, required=True, help=f"where {NAME}.gif and its sidecar are written")
    parser.add_argument("--copy-to", type=Path, action="append", default=[],
                        help="another directory that receives the same GIF and sidecar, byte for byte (repeatable)")
    parser.add_argument("--mp4", type=Path, help=f"where the MP4 is written (default: <out-dir>/{NAME}.mp4)")
    parser.add_argument("--lane-kit", type=Path, help="a lane-kit directory (default: multi-session/lane-kit-*)")
    parser.add_argument("--fps", type=int, default=10, help="frames per second of the output (default 10)")
    parser.add_argument("--width", type=int, default=960, help="width of both outputs in pixels (default 960)")
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg"), help="the ffmpeg binary (default: on PATH)")
    parser.add_argument("--gif-budget", type=int, default=3_000_000, help="largest GIF in bytes (default 3 MB)")
    parser.add_argument("--mp4-budget", type=int, default=3_000_000, help="largest MP4 in bytes (default 3 MB)")
    args = parser.parse_args(argv)
    ffmpeg = (shutil.which(args.ffmpeg) or (args.ffmpeg if Path(args.ffmpeg).is_file() else None)) if args.ffmpeg else None
    if ffmpeg is None:
        parser.error("no ffmpeg: pass --ffmpeg or put it on PATH")
    ffprobe = shutil.which("ffprobe", path=str(Path(ffmpeg).parent)) or shutil.which("ffprobe")
    if ffprobe is None:
        parser.error("no ffprobe beside ffmpeg or on PATH: the outputs could not be measured")
    kit = seed.find_lane_kit(args.lane_kit)
    gif = args.out_dir / f"{NAME}.gif"
    mp4 = args.mp4 or args.out_dir / f"{NAME}.mp4"
    with tempfile.TemporaryDirectory(prefix="hpp-dashboard-") as tmp:
        stage = Path(tmp)
        project, raw, frames = stage / "example-project", stage / "raw", stage / "frames"
        raw.mkdir()
        frames.mkdir()
        commands = seed.seed(kit, project)
        server = Server(kit, project)
        try:
            facts = play(server.url, kit, project, raw)
        finally:
            code = server.stop()
            print(f"lane_dashboard.py serve stopped (exit {code})")
        count = resample(facts.pop("frames"), args.fps, DURATION, frames)
        staged_gif, staged_mp4 = stage / f"{NAME}.gif", stage / f"{NAME}.mp4"
        media.encode(ffmpeg, frames, args.fps, args.width, staged_gif, staged_mp4)
        measured, missed = {}, []
        for key, path, budget in (("gif", staged_gif, args.gif_budget), ("mp4", staged_mp4, args.mp4_budget)):
            measured[key] = {**media.probe(ffprobe, path), "bytes": path.stat().st_size}
            verdict = "ok" if measured[key]["bytes"] <= budget and measured[key]["frames"] == count else "MISS"
            if verdict == "MISS":
                missed.append(path.name)
            print(f"{path.name}: {measured[key]['width']}x{measured[key]['height']}, {measured[key]['frames']} frames, "
                  f"{measured[key]['duration']:g} s, {measured[key]['bytes']:,} bytes (budget {budget:,}) {verdict}")
        if missed:
            print(f"over budget or short of frames: {', '.join(missed)}; nothing written", file=sys.stderr)
            return 1
        place(staged_gif, sidecar(args, kit, commands, facts, measured), [args.out_dir, *args.copy_to])
        mp4.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(staged_mp4, mp4)
    print(f"wrote {gif}, {gif}.txt and {mp4}; copies in {', '.join(map(str, args.copy_to)) or 'nowhere else'}")
    return 0


def place(staged_gif: Path, sidecar_text: str, targets: list[Path]) -> None:
    """Write the GIF and its sidecar, the same bytes, into every target directory.

    Why (2026-09-29): the sidecar went to `--out-dir` only, so `docs/assets/ui/` held the GIF
    without the `.gif.txt` the manual's caption names, and the published site had no such file."""
    for target in targets:
        target.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(staged_gif, target / f"{NAME}.gif")
        (target / f"{NAME}.gif.txt").write_bytes(sidecar_text.encode("utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
