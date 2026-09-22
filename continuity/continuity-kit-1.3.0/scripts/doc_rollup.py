#!/usr/bin/env python3
"""
doc_rollup (continuity-kit) -- keeps a project's history/evolution docs current
after a significant session, WITHOUT decaying the way the originals decayed.

Generalizes the real pattern of maintaining history documents (changelog +
narrative timeline + state snapshot + lessons + per-session wrapup) scattered via a
`rollup.yaml` config-driven file, instead of hardcoded to one specific project.

Lesson built in from day 1 (not discovered later): manual narrative documents
grow without limit and become junk nobody reads. Above `max_bytes` (default 65536)
OR `max_entries` managed entries, the rollup stops writing the full narrative
and switches to writing just 1 stamp line + pointer to the live state (`pointer` of the target).

Write modes (NEVER overwrite the whole file):
  prepend-after-header  -> inserts right after the file's 1st blank line
  append-section        -> appends at the end of the file
  create-new            -> creates a new file (path can use {date}); if it already
                            exists at the resolved path, it is a NO-OP (never overwrites)
  header-and-section     -> replaces ONLY the content between markers
                            <!-- ROLLUP:SNAPSHOT:BEGIN/END --> (creates the markers if
                            needed); the rest of the file stays untouched.

Guardrails (code, not just doctrine):
  - backup `<path>.bak-rollup-<timestamp>` BEFORE editing an existing file
  - atomic write (tmp + os.replace)
  - collision: same `session_marker` already present in the target -> aborts THAT
    target (not the whole run), LC-4 (idempotency -- do not re-insert what was already inserted)
  - `passive: true` on the target -> REFUSES to write, always, even if the config asks
    (defense in depth for paths like an auto-generated mirror)

Usage:
    echo '{...}' | python doc_rollup.py plan  --stdin --config rollup.yaml
    echo '{...}' | python doc_rollup.py apply --stdin --config rollup.yaml [--dry-run] [--force]
    python doc_rollup.py --self-test

Exit: 0 ok (even with skipped/degraded targets -- that is correct behavior,
not failure) - 1 invalid payload (missing session_marker/resumo/re_derive_cmd of a
metric) - 2 invalid usage (malformed JSON, missing config).
stdlib + PyYAML.
v1.0.0 -- 2026-07-10 (continuity-kit - Tier 2 - generic doc-rollup)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import yaml  # PyYAML
except ImportError:
    yaml = None  # type: ignore[assignment]

_MAX_BYTES_DEFAULT = 65536  # same constant as hooks/_handoff_io.py in this kit
_MAX_ENTRIES_DEFAULT = 30
_SNAPSHOT_BEGIN = "<!-- ROLLUP:SNAPSHOT:BEGIN -->"
_SNAPSHOT_END = "<!-- ROLLUP:SNAPSHOT:END -->"
_VALID_MODES = ("prepend-after-header", "append-section", "create-new", "header-and-section")


def _brt_today() -> str:
    return datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%d")


def load_config(path: Path) -> dict:
    if yaml is None or not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return {}


def validate_payload(payload: dict) -> list:
    """Returns list of errors (empty = valid). LC-1/LC-4 guardrails applied here."""
    errors = []
    if not isinstance(payload, dict):
        return ["payload is not a JSON object"]
    if not str(payload.get("session_marker") or "").strip():
        errors.append("session_marker missing (required for collision/idempotency detection — LC-4)")
    if not str(payload.get("summary") or "").strip():
        errors.append("summary missing")
    for i, m in enumerate(payload.get("metrics") or []):
        if not isinstance(m, dict) or not str(m.get("re_derive_cmd") or "").strip():
            errors.append(f"metricas[{i}] without re_derive_cmd (LC-1: every number needs a command to re-derive it live)")
    return errors


def _bullets(items: list) -> str:
    items = [str(i) for i in (items or []) if str(i).strip()]
    return "\n".join(f"- {i}" for i in items) if items else "- (none recorded)"


def _metrics_table(metrics: list) -> str:
    rows = [m for m in (metrics or []) if isinstance(m, dict)]
    if not rows:
        return "_(no metrics this session)_"
    lines = ["| Metric | Before | After | Re-derive |", "|---|---|---|---|"]
    for m in rows:
        lines.append(f"| {m.get('name', '?')} | {m.get('before', '?')} | {m.get('after', '?')} | `{m.get('re_derive_cmd', '')}` |")
    return "\n".join(lines)


def render_template(template: str, payload: dict) -> str:
    fields = {
        "date": payload.get("date") or _brt_today(),
        "summary": payload.get("summary", ""),
        "shipments_bullets": _bullets(payload.get("shipments")),
        "metricas_table": _metrics_table(payload.get("metrics")),
        "decision_bullets": _bullets(payload.get("decisions")),
        "aprendizados_bullets": _bullets(payload.get("aprendizados")),
    }
    try:
        return template.format(**fields)
    except (KeyError, IndexError):
        # template references an unknown field -- does not break the run, just does not substitute
        out = template
        for k, v in fields.items():
            out = out.replace("{" + k + "}", str(v))
        return out


def render_stamp(payload: dict, pointer: str) -> str:
    date = payload.get("date") or _brt_today()
    summary = str(payload.get("summary", ""))[:160]
    return f"> **Stamp {date}:** {summary} — {pointer or 'see the live state of the project'}.\n"


def _count_entries(text: str, marker: str | None) -> int:
    if not marker or not text:
        return 0
    try:
        return len(re.findall(marker, text, re.M))
    except re.error:
        return 0


def should_degrade(existing_text: str, target: dict) -> bool:
    max_bytes = int(target.get("max_bytes", _MAX_BYTES_DEFAULT))
    max_entries = target.get("max_entries")
    if len(existing_text.encode("utf-8")) > max_bytes:
        return True
    if max_entries is not None and _count_entries(existing_text, target.get("entry_marker")) >= int(max_entries):
        return True
    return False


def _has_collision(existing_text: str, session_marker: str) -> bool:
    return bool(session_marker) and session_marker in existing_text


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _insert_prepend_after_header(existing: str, new_entry: str, session_marker: str) -> str:
    """Inserts the newest entry at the TOP of the stack of managed entries. Marks the
    entry with the session_marker in an invisible HTML comment (for collision detection
    AND to find the start of the stack in future calls -- do not use 'the 1st blank line'
    as the boundary: an entry with a blank line IN ITS OWN BODY (common -- blank title
    before the body) would make the next entry get inserted INSIDE the previous one)."""
    marker_line = f"<!-- rollup:{session_marker} -->\n"
    block = marker_line + new_entry.rstrip("\n") + "\n\n"
    if not existing:
        return block
    idx = existing.find("<!-- rollup:")
    if idx != -1:
        # >=1 managed entry already exists -- stacks the new one IMMEDIATELY before the
        # first one, preserving any human header above them.
        return existing[:idx] + block + existing[idx:]
    # 1st managed entry in this file -- there may be a human header (title/intro)
    # above; inserts after the 1st blank line, or at the top if there is none.
    lines = existing.splitlines(keepends=True)
    for i, ln in enumerate(lines):
        if ln.strip() == "":
            return "".join(lines[: i + 1]) + block + "".join(lines[i + 1:])
    return existing.rstrip("\n") + "\n\n" + block


def _insert_append_section(existing: str, new_entry: str, session_marker: str) -> str:
    marker_line = f"<!-- rollup:{session_marker} -->\n"
    block = marker_line + new_entry.rstrip("\n") + "\n"
    if not existing:
        return block
    return existing.rstrip("\n") + "\n\n" + block


def _insert_header_and_section(existing: str, new_entry: str, session_marker: str) -> str:
    marker_line = f"<!-- rollup:{session_marker} -->\n"
    section = _SNAPSHOT_BEGIN + "\n" + marker_line + new_entry.strip("\n") + "\n" + _SNAPSHOT_END
    if _SNAPSHOT_BEGIN in existing and _SNAPSHOT_END in existing:
        pre, _, rest = existing.partition(_SNAPSHOT_BEGIN)
        _, _, post = rest.partition(_SNAPSHOT_END)
        return pre + section + post
    if not existing:
        return section + "\n"
    return existing.rstrip("\n") + "\n\n" + section + "\n"


def plan_target(target: dict, payload: dict, repo_root: Path) -> dict:
    """Computes the action for a target, WITHOUT touching disk. Returns a report per target."""
    rel_path = str(target.get("path", ""))
    mode = str(target.get("mode", ""))
    result = {"path": rel_path, "mode": mode, "role": target.get("role", "")}

    if target.get("passive"):
        result["status"] = "skipped-passive"
        result["reason"] = "path marked passive: true — doc_rollup.py never writes here"
        return result

    if mode not in _VALID_MODES:
        result["status"] = "error"
        result["reason"] = f"invalid mode: {mode!r} (valid: {', '.join(_VALID_MODES)})"
        return result

    resolved_rel = rel_path.format(date=payload.get("date") or _brt_today())
    full_path = repo_root / resolved_rel
    result["resolved_path"] = str(full_path)

    if mode == "create-new":
        if full_path.exists():
            result["status"] = "skipped-exists"
            result["reason"] = "create-new: resolved path already exists — never overwrites"
            return result
        result["status"] = "would-create"
        result["content_preview"] = render_template(target.get("template", ""), payload)
        return result

    existing = _read(full_path)
    session_marker = str(payload.get("session_marker", ""))

    region = existing
    if mode == "header-and-section" and _SNAPSHOT_BEGIN in existing:
        region = existing.split(_SNAPSHOT_BEGIN, 1)[1].split(_SNAPSHOT_END, 1)[0]

    if _has_collision(region, session_marker):
        result["status"] = "skipped-collision"
        result["reason"] = f"session_marker {session_marker!r} already present in this target (LC-4: do not re-insert)"
        return result

    if mode != "header-and-section" and should_degrade(existing, target):
        result["status"] = "would-stamp-degrade"
        result["reason"] = "target crossed the threshold (max_bytes/max_entries) — writing the stamp only"
        result["content_preview"] = render_stamp(payload, target.get("pointer", ""))
        return result

    result["status"] = f"would-{'prepend' if mode == 'prepend-after-header' else 'append' if mode == 'append-section' else 'update-section'}"
    result["content_preview"] = render_template(target.get("template", ""), payload)
    return result


def apply_target(target: dict, payload: dict, repo_root: Path, dry_run: bool) -> dict:
    plan = plan_target(target, payload, repo_root)
    status = plan["status"]
    if status in ("skipped-passive", "skipped-exists", "skipped-collision", "error"):
        return plan
    if dry_run:
        plan["status"] = f"dry-run:{status}"
        return plan

    mode = plan["mode"]
    session_marker = str(payload.get("session_marker", ""))
    full_path = Path(plan["resolved_path"])

    if status == "would-create":
        full_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = full_path.with_suffix(full_path.suffix + ".tmp")
        tmp.write_text(plan["content_preview"], encoding="utf-8")
        os.replace(tmp, full_path)
        plan["status"] = "created"
        return plan

    existing = _read(full_path)
    if existing:
        backup = full_path.with_name(full_path.name + f".bak-rollup-{_stamp_now()}")
        try:
            shutil.copy2(full_path, backup)
            plan["backup"] = str(backup)
        except OSError:
            pass

    if status == "would-stamp-degrade":
        new_text_body = render_stamp(payload, target.get("pointer", ""))
    else:
        new_text_body = render_template(target.get("template", ""), payload)

    if mode == "prepend-after-header":
        new_text = _insert_prepend_after_header(existing, new_text_body, session_marker)
    elif mode == "append-section":
        new_text = _insert_append_section(existing, new_text_body, session_marker)
    else:  # header-and-section
        new_text = _insert_header_and_section(existing, new_text_body, session_marker)

    full_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = full_path.with_suffix(full_path.suffix + ".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    os.replace(tmp, full_path)
    plan["status"] = "applied:" + status.replace("would-", "")
    return plan


def _stamp_now() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S%f")


def run(config: dict, payload: dict, dry_run: bool) -> dict:
    report = {"repos": []}
    for repo in config.get("repos") or []:
        root = Path(repo.get("root", "."))
        if not root.is_absolute():
            root = Path.cwd() / root
        repo_report = {"name": repo.get("name", "?"), "root": str(root), "targets": []}
        for target in repo.get("targets") or []:
            repo_report["targets"].append(apply_target(target, payload, root, dry_run))
        report["repos"].append(repo_report)
    return report


def _plan_only(config: dict, payload: dict) -> dict:
    report = {"repos": []}
    for repo in config.get("repos") or []:
        root = Path(repo.get("root", "."))
        if not root.is_absolute():
            root = Path.cwd() / root
        repo_report = {"name": repo.get("name", "?"), "root": str(root), "targets": []}
        for target in repo.get("targets") or []:
            repo_report["targets"].append(plan_target(target, payload, root))
        report["repos"].append(repo_report)
    return report


def _self_test() -> int:
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="doc_rollup_selftest_"))
    try:
        payload = {
            "session_marker": "sess-selftest-001",
            "date": "2026-07-10",
            "summary": "doc_rollup self-test",
            "shipments": ["item A", "item B"],
            "metrics": [{"name": "files", "before": "1", "after": "2", "re_derive_cmd": "ls | wc -l"}],
            "decisions": ["use X instead of Y"],
            "aprendizados": ["always validate before applying"],
        }

        # 1) validate_payload: valid payload -> no errors
        assert validate_payload(payload) == []
        # 1b) payload without session_marker/resumo/re_derive_cmd -> rejected
        bad = {"metrics": [{"name": "x"}]}
        errs = validate_payload(bad)
        assert any("session_marker" in e for e in errs)
        assert any("summary" in e for e in errs)
        assert any("re_derive_cmd" in e for e in errs)

        # 2) prepend-after-header correctly creates a new file
        cfg = {
            "repos": [{
                "name": "t", "root": str(tmp),
                "targets": [
                    {"path": "CHANGELOG.md", "role": "changelog", "mode": "prepend-after-header",
                     "entry_marker": r"^## \[", "max_bytes": 65536, "max_entries": 30,
                     "pointer": "see git log", "template": "## [{date}] {summary}\n\n{shipments_bullets}\n"},
                ],
            }],
        }
        rep1 = run(cfg, payload, dry_run=False)
        t1 = rep1["repos"][0]["targets"][0]
        assert t1["status"] == "applied:prepend", t1
        changelog_path = tmp / "CHANGELOG.md"
        text1 = changelog_path.read_text(encoding="utf-8")
        assert "doc_rollup self-test" in text1
        assert "sess-selftest-001" in text1

        # 3) re-applying the SAME session_marker -> collision, does NOT duplicate
        rep2 = run(cfg, payload, dry_run=False)
        t2 = rep2["repos"][0]["targets"][0]
        assert t2["status"] == "skipped-collision", t2
        text2 = changelog_path.read_text(encoding="utf-8")
        assert text2.count("sess-selftest-001") == 1, "collision should have prevented the duplicate"

        # 4) second session (different marker) -> applies again, without erasing the first
        payload3 = dict(payload, session_marker="sess-selftest-002", summary="second session")
        rep3 = run(cfg, payload3, dry_run=False)
        assert rep3["repos"][0]["targets"][0]["status"] == "applied:prepend"
        text3 = changelog_path.read_text(encoding="utf-8")
        assert "sess-selftest-001" in text3 and "sess-selftest-002" in text3
        # prepend: the most recent entry stays BEFORE the oldest one
        assert text3.index("sess-selftest-002") < text3.index("sess-selftest-001")

        # 5) degradation: max_entries=1 already reached -> 3rd session becomes a stamp, not full narrative
        cfg_deg = json.loads(json.dumps(cfg))
        cfg_deg["repos"][0]["targets"][0]["max_entries"] = 1
        payload4 = dict(payload, session_marker="sess-selftest-003", summary="third session (should degrade)")
        rep4 = run(cfg_deg, payload4, dry_run=False)
        t4 = rep4["repos"][0]["targets"][0]
        assert t4["status"] == "applied:stamp-degrade", t4
        text4 = changelog_path.read_text(encoding="utf-8")
        assert "Stamp 2026-07-10" in text4
        assert "third session (should degrade)" in text4

        # 6) path passive: true -> NEVER writes, even if the config asks for it
        cfg_passive = {
            "repos": [{"name": "t", "root": str(tmp), "targets": [
                {"path": "mirror/should-not-exist.md", "role": "mirror-passive", "passive": True, "mode": "append-section"},
            ]}],
        }
        rep5 = run(cfg_passive, payload, dry_run=False)
        t5 = rep5["repos"][0]["targets"][0]
        assert t5["status"] == "skipped-passive", t5
        assert not (tmp / "mirror" / "should-not-exist.md").exists()

        # 7) create-new: 2nd call on the SAME {date} -> no-op (never overwrites)
        cfg_new = {
            "repos": [{"name": "t", "root": str(tmp), "targets": [
                {"path": "sessions/{date}-WRAPUP.md", "role": "session-wrapup", "mode": "create-new",
                 "template": "# Wrapup {date}\n\n{summary}\n"},
            ]}],
        }
        rep6a = run(cfg_new, payload, dry_run=False)
        assert rep6a["repos"][0]["targets"][0]["status"] == "created"
        wrapup_path = tmp / "sessions" / "2026-07-10-WRAPUP.md"
        original_bytes = wrapup_path.read_bytes()
        rep6b = run(cfg_new, dict(payload, summary="overwrite attempt"), dry_run=False)
        assert rep6b["repos"][0]["targets"][0]["status"] == "skipped-exists"
        assert wrapup_path.read_bytes() == original_bytes, "create-new should not overwrite"

        # 8) header-and-section: replaces only the section, preserves content outside it
        section_path = tmp / "STATE.md"
        section_path.write_text("# State\n\ncontent preserved before\n", encoding="utf-8")
        cfg_snap = {
            "repos": [{"name": "t", "root": str(tmp), "targets": [
                {"path": "STATE.md", "role": "snapshot", "mode": "header-and-section",
                 "pointer": "see SSoT", "template": "{summary}\n"},
            ]}],
        }
        run(cfg_snap, payload, dry_run=False)
        text8a = section_path.read_text(encoding="utf-8")
        assert "content preserved before" in text8a
        assert _SNAPSHOT_BEGIN in text8a and _SNAPSHOT_END in text8a
        run(cfg_snap, dict(payload, session_marker="sess-selftest-999", summary="state updated"), dry_run=False)
        text8b = section_path.read_text(encoding="utf-8")
        assert "content preserved before" in text8b, "content outside the section should survive"
        assert "state updated" in text8b
        assert "doc_rollup self-test" not in text8b, "header-and-section should REPLACE the previous section"

        # 9) dry-run never touches disk
        fresh_path = tmp / "DRYRUN.md"
        cfg_dry = {"repos": [{"name": "t", "root": str(tmp), "targets": [
            {"path": "DRYRUN.md", "role": "changelog", "mode": "append-section", "template": "{summary}\n"},
        ]}]}
        run(cfg_dry, payload, dry_run=True)
        assert not fresh_path.exists(), "dry-run should not create a file"

        # 10) isolated plan_target does not touch disk (used by the `plan` subcommand)
        _plan_only(cfg_dry, payload)
        assert not fresh_path.exists()

        print("self-test OK — insertion/collision/degradation/passive/create-new/header-section/dry-run")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="doc_rollup.py")
    sub = p.add_subparsers(dest="cmd")
    for name in ("plan", "apply"):
        sp = sub.add_parser(name)
        sp.add_argument("--stdin", action="store_true")
        sp.add_argument("--config", default="rollup.yaml")
        if name == "apply":
            sp.add_argument("--dry-run", action="store_true")
            sp.add_argument("--force", action="store_true")
    p.add_argument("--self-test", action="store_true")
    return p


def main(argv) -> int:
    args = build_parser().parse_args(argv)

    if args.self_test:
        return _self_test()

    if args.cmd not in ("plan", "apply"):
        print("usage: doc_rollup.py {plan|apply} --stdin --config rollup.yaml [--dry-run]", file=sys.stderr)
        return 2

    if yaml is None:
        print("doc_rollup: PyYAML missing", file=sys.stderr)
        return 2

    if not args.stdin:
        print("usage: --stdin is required (the payload comes from the model, not from a file)", file=sys.stderr)
        return 2

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as e:
        print(f"doc_rollup: invalid JSON on stdin: {e}", file=sys.stderr)
        return 2

    errors = validate_payload(payload)
    if errors and not (args.cmd == "apply" and getattr(args, "force", False)):
        print(json.dumps({"status": "rejected", "errors": errors}, ensure_ascii=False, indent=2))
        return 1

    config_path = Path(args.config)
    config = load_config(config_path)
    if not config:
        print(f"doc_rollup: config missing/empty: {config_path} (copy rollup.example.yaml)", file=sys.stderr)
        return 2

    if args.cmd == "plan":
        report = _plan_only(config, payload)
    else:
        report = run(config, payload, dry_run=getattr(args, "dry_run", False))

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
