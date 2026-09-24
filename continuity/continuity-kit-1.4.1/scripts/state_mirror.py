#!/usr/bin/env python3
"""
state_mirror -- mirrors critical gitignored files into a TRACKED folder (durability).

Instead of hardcoding which files to mirror, this script reads `paths.mirror_globs`
from a YAML profile -- each entry = {glob, dest_subdir, keep_latest} -- and works in
any project. DURABILITY (not losing the file if .gitignore drops the original)
is a DIFFERENT problem from RESUMPTION (the continuity-kit's handoff-v1) -- the two
complement each other, they do not replace each other.

Usage:
    python state_mirror.py --profile operator-profile.yaml
    python state_mirror.py --profile operator-profile.yaml --dry-run
    python state_mirror.py --self-test

Config (paths.mirror_dir + paths.mirror_globs in the profile):
    paths:
      mirror_dir: docs/_state-mirror
      mirror_globs:
        - { glob: ".claude/notes/*.md", dest_subdir: "notes" }
        - { glob: ".claude/sessions/SESSION-*.md", dest_subdir: "sessions", keep_latest: 10 }

Exit: 0 ok (even with 0 globs configured -- becomes a documented no-op) - 2 invalid usage.
stdlib + PyYAML (degrades to {} without PyYAML -- profile stays empty, no-op).

v1.0.0 -- 2026-07-10 (continuity-kit - generic durability mirror)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

_PROJECT_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())


def load_profile(path: str | None) -> dict:
    if not path:
        return {}
    p = Path(path)
    if not p.is_absolute():
        p = _PROJECT_ROOT / p
    if not p.exists() or yaml is None:
        return {}
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _get(d: dict, dotted: str, default=None):
    cur = d
    for k in dotted.split("."):
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur


def mirror(profile: dict, root: Path, dry_run: bool = False) -> dict:
    mirror_dir_rel = _get(profile, "paths.mirror_dir", "docs/_state-mirror")
    mirror_dir = root / mirror_dir_rel
    globs = _get(profile, "paths.mirror_globs", []) or []

    copied = []
    for entry in globs:
        pattern = entry.get("glob")
        dest_subdir = entry.get("dest_subdir", "")
        keep_latest = entry.get("keep_latest")
        if not pattern:
            continue
        matches = sorted(root.glob(pattern), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
        matches = [m for m in matches if m.is_file()]
        if keep_latest:
            matches = matches[:keep_latest]
        for m in matches:
            dest = mirror_dir / dest_subdir / m.name
            copied.append(str(dest.relative_to(mirror_dir)))
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(m, dest)

    manifest = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z") or time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": str(root),
        "mirror_dir": str(mirror_dir),
        "files_mirrored": len(copied),
        "note": "Critical state backup for git-ignored files. Mirror IS tracked in git.",
    }
    if not dry_run:
        mirror_dir.mkdir(parents=True, exist_ok=True)
        (mirror_dir / "_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest["copied"] = copied
    return manifest


_STATE_INDEX_THRESHOLD = 65536  # 64KB -- proactive: index the state file well before its size makes boot slow


# The headings of the state document became English in 2.5.2; a repo scaffolded before that
# still carries the Portuguese ones, and it is the user's own document - we read both until
# 2.7.0 rather than rewrite it. Same rule as the reader in `hooks/session_boot.py`.
_SECTION_LEGACY = {"Now": "Agora", "OPEN ITEMS": "PENDÊNCIAS ABERTAS"}
SECTIONS_LEGACY_REMOVED_IN = "2.7.0"


def _section(text: str, title: str, limit: int = 1800) -> str:
    idx = text.find(f"## {title}")
    if idx == -1 and title in _SECTION_LEGACY:
        idx = text.find(f"## {_SECTION_LEGACY[title]}")
    if idx == -1:
        return ""
    rest = text[idx:]
    nxt = rest.find("\n## ", 3)
    return (rest if nxt == -1 else rest[:nxt]).strip()[:limit]


def generate_state_index(state_path: Path, threshold_bytes: int = _STATE_INDEX_THRESHOLD) -> dict | None:
    """If STATE.md exceeds the cap, generates <state>.state-index.json with the live sections
    (`Now`, `OPEN ITEMS`; the legacy spellings are read too) -- proactive: generates BEFORE it
    becomes a slow-boot problem."""
    if not state_path.exists():
        return None
    size = state_path.stat().st_size
    if size <= threshold_bytes:
        return None
    text = state_path.read_text(encoding="utf-8", errors="replace")
    index = {
        "source": str(state_path),
        "size_bytes": size,
        "threshold_bytes": threshold_bytes,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "now": _section(text, "Now"),
        "open_items": _section(text, "OPEN ITEMS"),
    }
    index_path = state_path.with_suffix(state_path.suffix + ".state-index.json")
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return index


def _self_test() -> int:
    import shutil as _sh
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="state_mirror_selftest_"))
    try:
        (tmp / ".claude" / "notes").mkdir(parents=True)
        (tmp / ".claude" / "notes" / "MEMORY.md").write_text("memory", encoding="utf-8")
        (tmp / ".claude" / "sessions").mkdir(parents=True)
        for i in range(5):
            (tmp / ".claude" / "sessions" / f"SESSION-{i}.md").write_text(f"s{i}", encoding="utf-8")
            time.sleep(0.01)

        profile = {
            "paths": {
                "mirror_dir": "docs/_state-mirror",
                "mirror_globs": [
                    {"glob": ".claude/notes/*.md", "dest_subdir": "notes"},
                    {"glob": ".claude/sessions/SESSION-*.md", "dest_subdir": "sessions", "keep_latest": 3},
                ],
            }
        }

        report_dry = mirror(profile, tmp, dry_run=True)
        assert report_dry["files_mirrored"] == 4, f"dry-run should count 1 notes + 3 sessions: {report_dry}"
        assert not (tmp / "docs" / "_state-mirror").exists(), "dry-run should not write anything"

        report = mirror(profile, tmp, dry_run=False)
        assert report["files_mirrored"] == 4
        mirror_dir = tmp / "docs" / "_state-mirror"
        assert (mirror_dir / "notes" / "MEMORY.md").exists()
        assert len(list((mirror_dir / "sessions").glob("SESSION-*.md"))) == 3, "keep_latest=3 should cap the list"
        assert (mirror_dir / "_manifest.json").exists()

        empty_profile: dict = {}
        report_empty = mirror(empty_profile, tmp, dry_run=True)
        assert report_empty["files_mirrored"] == 0, "no mirror_globs configured = no-op, not an error"

        small_state = tmp / "00-STATE-small.md"
        small_state.write_text("## Now\nfocus\n", encoding="utf-8")
        assert generate_state_index(small_state) is None, "below the threshold it should not generate an index"

        big_state = tmp / "00-STATE-big.md"
        big_state.write_text("## Now\ncurrent focus\n\n## OPEN ITEMS\n- [ ] x\n\n" + ("padding " * 10000), encoding="utf-8")
        idx = generate_state_index(big_state, threshold_bytes=1000)
        assert idx is not None and idx["now"] and idx["open_items"], f"above the threshold it should generate an index: {idx}"
        assert big_state.with_suffix(".md.state-index.json").exists()

        # Dual read of the headings: a document scaffolded before 2.5.2 has them in Portuguese,
        # and an index with two empty sections looks exactly like a document with nothing in it.
        legacy_state = tmp / "00-STATE-legacy.md"
        legacy_state.write_text("## Agora\nlegacy focus\n\n## PENDÊNCIAS ABERTAS\n- [ ] y\n\n" + ("padding " * 10000), encoding="utf-8")
        idx_legacy = generate_state_index(legacy_state, threshold_bytes=1000)
        assert idx_legacy is not None and "legacy focus" in idx_legacy["now"], "legacy Now heading must be read"
        assert "- [ ] y" in idx_legacy["open_items"], "legacy OPEN ITEMS heading must be read"
        # CONTROL: a document with neither heading indexes empty - this is what proves the two
        # asserts above measure the HEADINGS, not merely that a big file was read.
        other_state = tmp / "00-STATE-other.md"
        other_state.write_text("## Something Else\nnot parsed\n\n" + ("padding " * 10000), encoding="utf-8")
        idx_other = generate_state_index(other_state, threshold_bytes=1000)
        assert idx_other is not None and not idx_other["now"] and not idx_other["open_items"], \
            f"an unknown heading must not be picked up: {idx_other}"

        print("self-test OK - dry-run counts right without writing, keep_latest caps, manifest generated, "
              "empty profile = no-op, state-index only above the threshold (proactive), headings read "
              "in English AND legacy")
        return 0
    finally:
        _sh.rmtree(tmp, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="state_mirror.py")
    p.add_argument("--profile", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--state-file", default=None, help="generate state-index.json when the file exceeds 64KB")
    p.add_argument("--self-test", action="store_true")
    return p


def main(argv) -> int:
    args = build_parser().parse_args(argv)
    if args.self_test:
        return _self_test()
    profile = load_profile(args.profile)
    report = mirror(profile, _PROJECT_ROOT, args.dry_run)
    if args.state_file and not args.dry_run:
        idx = generate_state_index(_PROJECT_ROOT / args.state_file)
        report["state_index_generated"] = idx is not None
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
