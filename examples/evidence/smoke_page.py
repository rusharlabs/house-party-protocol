"""A stand-in e2e criterion that needs no browser: render a page, check it, leave artifacts.

`hpp evidence run` does not care what the criterion is. This script plays the part a Playwright
spec plays in a real project: it produces a page and a log under `out/`, checks the page, and
exits 0 only when the check holds. Run it through the harness so the exit code and the artifact
hashes become a record:

    python -m hpp evidence run --id smoke-page --artifact out/report.html --artifact out/smoke.log \
        -- python examples/evidence/smoke_page.py

Pass `--break` to see a failing criterion produce artifacts that are still not evidence.
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

EXPECTED = ("<title>Release report</title>", 'data-status="green"')


def render(status: str) -> str:
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>Release report</title></head>"
            f"<body><main data-status=\"{html.escape(status)}\"><h1>Release report</h1></main></body></html>\n")


def main(argv: list[str]) -> int:
    out = Path("out")
    out.mkdir(exist_ok=True)
    page = render("red" if "--break" in argv else "green")
    (out / "report.html").write_text(page, encoding="utf-8", newline="\n")
    missing = [marker for marker in EXPECTED if marker not in page]
    log = ["checked out/report.html"] + [f"missing: {marker}" for marker in missing] + [
        "result: " + ("fail" if missing else "pass")]
    (out / "smoke.log").write_text("\n".join(log) + "\n", encoding="utf-8", newline="\n")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
