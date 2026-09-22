#!/usr/bin/env python3
"""
wire_statusline (health-kit) -- arms this kit's statusLine in settings.json/settings.local.json,
IDEMPOTENTLY and REVERSIBLY.

Vendors the proven mechanism from wire_settings.py (kit-forge): it NEVER overwrites a
statusLine belonging to someone else without --force. Automatic backup before writing, JSON
validation afterward (automatic rollback if it breaks), and undo-state written so `--undo`
works without needing to remember the backup's timestamp.

Why a new script instead of the house's legacy `scripts/system/wire_statusline.py`:
that script had the defect of overwriting a statusLine already configured by another
tool without asking. This one NEVER does that (see `apply_spec`).

Usage:
    python wire_statusline.py --target <settings.json> [--force]
    python wire_statusline.py --undo [--target <settings.json>]
    python wire_statusline.py --self-test

The wired command calls `statusline/statusline.py --statusline` (path resolved from
this script's location -- works with or without `${CLAUDE_PLUGIN_ROOT}`).

Exit: 0 ok (wired or no-op) - 1 warn (conflict without --force, nothing overwritten) - 3 error.
stdlib only (no PyYAML -- the wiring spec is fixed, it does not come from external YAML).
v1.0.0 -- 2026-07-10 (health-kit - idempotent/--undo, modeled on kit-forge/wire_settings.py)
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import sys
from pathlib import Path

_MARKER = "--kit=health-kit"


def _statusline_cmd() -> str:
    # marks the origin with a FIXED TOKEN as an extra argument (ignored by statusline.py,
    # which only looks at sys.argv[1]) -- do not use the script's path as the marker: the shipped
    # folder is versioned (health-kit-1.0.0), can be renamed by the user, and a
    # path-substring would collide with the statusline of another kit that also ends in
    # ".../statusline/statusline.py" (e.g. operator-kit). An extra argv works the same
    # in cmd.exe and in POSIX shells -- without depending on env-var-prefix syntax (which
    # cmd.exe does not understand).
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        target = f"{Path(plugin_root).as_posix()}/statusline/statusline.py"
    else:
        script_dir = Path(__file__).resolve().parent.parent  # .../health-kit(-X.Y.Z)
        target = (script_dir / "statusline" / "statusline.py").as_posix()
    return f"python {target} --statusline {_MARKER}"


def _wiring_spec() -> dict:
    return {
        "match_substring": _MARKER,
        "value": {"type": "command", "command": _statusline_cmd(), "padding": 0},
    }


def apply_spec(data: dict, spec: dict, force: bool):
    """Returns (data, changed:bool, warning:str|None). Only touches 'statusLine' (no hooks)."""
    marker = spec["match_substring"]
    cur = data.get("statusLine")
    cur_cmd = (cur or {}).get("command", "") if isinstance(cur, dict) else ""
    if isinstance(cur, dict) and marker in cur_cmd:
        return data, False, None  # already wired -- idempotent
    if not cur or force:
        data["statusLine"] = dict(spec["value"])
        return data, True, None
    return data, False, f"statusLine already taken by another config; use --force to overwrite (current: {cur_cmd!r})"


def _write_json_atomic(target: Path, data: dict, backup: Path, *, expected_bytes: bytes | None = None) -> str:
    """Writes `data` to `target` with no window for corruption. Returns "ok" | "invalid" | "conflict".

    # Why: writing straight to the target leaves a truncated settings.json if the process dies
    # halfway through, and overwrites what another process wrote between the read and the write. The
    # temp file stays in the SAME directory (os.replace is only atomic on the same volume) and the
    # byte-by-byte comparison against what was read refuses the write instead of losing someone else's.
    """
    out = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    try:
        json.loads(out)
    except json.JSONDecodeError:
        return "invalid"
    tmp = target.with_name(f".{target.name}.tmp-{os.getpid()}")
    try:
        tmp.write_text(out, encoding="utf-8")
        with tmp.open("r+b") as fh:
            os.fsync(fh.fileno())
        if expected_bytes is not None and target.read_bytes() != expected_bytes:
            return "conflict"
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    return "ok"


def wire(target: Path, force: bool) -> tuple:
    if not target.exists():
        return 3, {"status": "error", "errors": [f"target does not exist: {target}"]}

    raw_bytes = target.read_bytes()
    raw = raw_bytes.decode("utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return 3, {"status": "error", "errors": [f"invalid JSON in {target}: {e}"]}

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S%f")
    backup = target.with_name(target.name + f".bak-{stamp}")
    shutil.copy2(target, backup)

    new_data, changed, warning = apply_spec(data, _wiring_spec(), force)

    if not changed:
        backup.unlink(missing_ok=True)
        status = "warn" if warning else "no-op"
        return (1 if warning else 0), {"status": status, "warnings": [warning] if warning else []}

    resultado = _write_json_atomic(target, new_data, backup, expected_bytes=raw_bytes)
    if resultado == "conflict":
        return 2, {"status": "conflict", "errors": [
            f"{target} changed between the read and the write — nothing was written. Run it again."]}
    if resultado != "ok":
        return 3, {"status": "error", "errors": ["serialization did not produce valid JSON — nothing was written"]}

    undo_state = target.with_name(target.name + ".wire-undo.json")
    undo_state.write_text(json.dumps({"target": str(target), "backup": str(backup)}), encoding="utf-8")

    return 0, {"status": "wired", "command": new_data["statusLine"]["command"], "backup": str(backup)}


def undo(target: Path | None) -> tuple:
    if target is None:
        return 3, {"status": "error", "errors": ["--undo requires --target"]}

    undo_state_path = target.with_name(target.name + ".wire-undo.json")
    if not undo_state_path.exists():
        return 3, {"status": "error", "errors": [f"no undo state found: {undo_state_path}"]}

    state = json.loads(undo_state_path.read_text(encoding="utf-8"))
    backup = Path(state["backup"])
    tgt = Path(state["target"])
    if not backup.exists():
        return 3, {"status": "error", "errors": [f"backup no longer exists: {backup}"]}

    shutil.copy2(backup, tgt)
    undo_state_path.unlink(missing_ok=True)
    return 0, {"status": "restored", "target": str(tgt), "from_backup": str(backup)}


def _self_test() -> int:
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="wire_statusline_selftest_"))
    try:
        target = tmp / "settings-copy.json"
        target.write_text(json.dumps({"hooks": {}}, indent=2), encoding="utf-8")
        original_bytes = target.read_bytes()

        code1, report1 = wire(target, force=False)
        assert code1 == 0 and report1["status"] == "wired", f"1st run should be wired: {report1}"
        assert _MARKER in report1["command"]
        bytes_after_run1 = target.read_bytes()
        assert bytes_after_run1 != original_bytes, "the 1st run should change the file"

        code2, report2 = wire(target, force=False)
        assert code2 == 0 and report2["status"] == "no-op", f"the 2nd run should be a no-op: {report2}"
        assert target.read_bytes() == bytes_after_run1, "the 2nd run should be byte-stable"

        conflict_target = tmp / "conflict.json"
        conflict_target.write_text(json.dumps({"statusLine": {"command": "outro_dono"}, "hooks": {}}), encoding="utf-8")
        code3, report3 = wire(conflict_target, force=False)
        assert code3 == 1 and report3["warnings"], f"a conflict without --force should warn: {report3}"
        conflict_data = json.loads(conflict_target.read_text(encoding="utf-8"))
        assert conflict_data["statusLine"]["command"] == "outro_dono", "overwrote another owner's statusLine without --force!"

        code4, report4 = wire(conflict_target, force=True)
        assert code4 == 0 and report4["status"] == "wired", f"--force should overwrite: {report4}"
        conflict_data2 = json.loads(conflict_target.read_text(encoding="utf-8"))
        assert _MARKER in conflict_data2["statusLine"]["command"]

        undo_code, undo_report = undo(target)
        assert undo_code == 0 and undo_report["status"] == "restored", f"undo failed: {undo_report}"
        assert target.read_bytes() == original_bytes, "undo did not restore byte-identical to the original"

        print("self-test OK — wire is idempotent, a conflict without --force is preserved, --force overwrites, --undo is byte-identical")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wire_statusline.py")
    p.add_argument("--target", default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--undo", action="store_true")
    p.add_argument("--self-test", action="store_true")
    return p


def main(argv) -> int:
    args = build_parser().parse_args(argv)

    if args.self_test:
        return _self_test()

    if args.undo:
        target = Path(args.target) if args.target else None
        code, report = undo(target)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return code

    if not args.target:
        print("usage: wire_statusline.py --target <settings.json> [--force]", file=sys.stderr)
        return 3

    code, report = wire(Path(args.target), args.force)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
