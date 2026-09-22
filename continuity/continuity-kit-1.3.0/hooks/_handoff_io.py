#!/usr/bin/env python3
"""
_handoff_io — lib única de IO do handoff (write/read/render/consume/validate).

Handoff = 1 artefato JSON por lane (`HANDOFF-CURRENT-<lane_id>.json`) + 1 ledger append-only
(`HANDOFF-LEDGER.jsonl`). Materializa LC-1 (todo número carrega `re_derive_cmd`) e LC-4 (todo
próximo passo carrega `verify_first_cmd` — "contexto restaurado é referência, não fila").

Uso:
    echo '{...}' | python _handoff_io.py write --stdin
    python _handoff_io.py write --demo --lane solo
    python _handoff_io.py read --lane solo
    python _handoff_io.py read --last 5
    python _handoff_io.py render --lane solo
    python _handoff_io.py consume <handoff_id> --session <id>
    python _handoff_io.py --self-test

Exit: 0 ok · 1 validação falhou (segredo detectado, campo obrigatório ausente, schema
inválido) · 2 uso inválido. stdlib + PyYAML opcional (não usado; puro JSON aqui).

v1.0.0 — 2026-07-10 (continuity-kit · Tier 1 · deriva do design formal +
         LOVABLE-PROD-REVIEW/.claude/hooks/{session_start,stop_state_guard}.py — método, não dado)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
_HANDOFF_DIR = _PROJECT_ROOT / ".claude" / "handoff"
LEDGER_PATH = _HANDOFF_DIR / "HANDOFF-LEDGER.jsonl"

_MAX_BYTES = 65536
_REQUIRED_TOP = ("schema_version", "handoff_id", "created_at", "trigger", "quality", "session", "estado", "git", "valid_until")

# Secret patterns — mesmo espírito do ip_pii_linter.py (kit-forge), cópia local: cada kit
# deste marketplace é self-contained (C5 SKILL-CONTRACT), sem import cross-kit.
_SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"sk-proj-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"xox[bap]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"AIza[A-Za-z0-9_\-]{20,}"),
    re.compile(r"sbp_[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*[\"'][A-Za-z0-9_\-]{16,}[\"']"),
]


def _now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%dT%H:%M:%S-03:00")


def _git(args: list) -> str:
    try:
        r = subprocess.run(["git", "-C", str(_PROJECT_ROOT)] + args, capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def git_block(checkpoint_ref: str = "", checkpoint_commit: str = "") -> dict:
    """The git evidence of the handoff. `checkpoint_*` name the turn checkpoint when one was taken.

    Why the checkpoint belongs here (turn_checkpoint.py): `porcelain` and every number derived
    from it read the index, and a shared index reports edits that did not happen and misses ones
    that did. The checkpoint ref is a content-addressed object — it is the half of this block
    that stays true regardless.
    """
    head = _git(["rev-parse", "--short", "HEAD"])
    branch = _git(["branch", "--show-current"])
    porcelain = _git(["status", "--porcelain"])
    untracked = sum(1 for ln in porcelain.splitlines() if ln.startswith("??"))
    block = {"head": head, "branch": branch, "dirty": bool(porcelain.strip()), "untracked": untracked, "porcelain": porcelain[:4000]}
    if checkpoint_ref:
        block["checkpoint_ref"] = checkpoint_ref
    if checkpoint_commit:
        block["checkpoint_commit"] = checkpoint_commit
    return block


def scan_secrets(text: str) -> list:
    hits = []
    for pat in _SECRET_PATTERNS:
        for m in pat.finditer(text):
            hits.append(m.group(0)[:8] + "...")
    return hits


def validate(data: dict) -> list:
    """Retorna lista de erros (vazia = válido). Regras LC-1/LC-4 embutidas no contrato."""
    errors = []
    for field in _REQUIRED_TOP:
        if field not in data:
            errors.append(f"required field missing: {field}")
    if data.get("schema_version") not in ("1.1",):
        errors.append(f"schema_version must be '1.1' (got: {data.get('schema_version')!r})")

    session = data.get("session", {}) or {}
    if not session.get("session_id"):
        errors.append("session.session_id missing")
    if not session.get("lane_id"):
        errors.append("session.lane_id missing (default 'solo' when there is no lane)")

    git = data.get("git", {}) or {}
    for f in ("head", "branch", "dirty", "untracked"):
        if f not in git:
            errors.append(f"git.{f} missing (the git block is required — v1.1)")
    if data.get("quality") == "degraded-auto" and "porcelain" not in git:
        errors.append("quality=degraded-auto requires git.porcelain (v1.1 fix) — even when empty (clean tree), the KEY must exist")

    estado = data.get("estado", {}) or {}
    if not estado.get("resumo"):
        errors.append("estado.resumo missing")
    for i, n in enumerate(estado.get("numeros", []) or []):
        if not n.get("re_derive_cmd"):
            errors.append(f"estado.numeros[{i}] without re_derive_cmd (LC-1: every number needs a re-derivation command)")

    for i, p in enumerate(data.get("proximo_passo", []) or []):
        if not p.get("verify_first_cmd"):
            errors.append(f"proximo_passo[{i}] without verify_first_cmd (LC-4: next step without an idempotency check)")

    text_dump = json.dumps(data, ensure_ascii=False)
    secrets = scan_secrets(text_dump)
    if secrets:
        errors.append(f"secret detected in handoff ({len(secrets)} match(es), redacted: {secrets[:3]}) — REJECTED (no-secrets-in-memory)")

    size = len(text_dump.encode("utf-8"))
    if size > _MAX_BYTES:
        errors.append(f"handoff exceeds max_bytes ({size} > {_MAX_BYTES})")

    if not data.get("valid_until"):
        errors.append("valid_until missing")

    return errors


def append_ledger(event: str, handoff_id: str, lane_id: str = "solo", by_session: str = "", **details) -> None:
    _HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    entry = {"ts": _now_iso(), "event": event, "handoff_id": handoff_id, "lane_id": lane_id, "by_session": by_session, "details": details}
    with open(LEDGER_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def current_path(lane_id: str) -> Path:
    return _HANDOFF_DIR / f"HANDOFF-CURRENT-{lane_id}.json"


def write(data: dict) -> tuple:
    """Valida e grava atomicamente. Retorna (ok, errors_or_path)."""
    errors = validate(data)
    if errors:
        return False, errors

    lane_id = data["session"]["lane_id"]
    _HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    target = current_path(lane_id)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, target)

    append_ledger("written", data["handoff_id"], lane_id=lane_id, by_session=data["session"].get("session_id", ""))
    return True, str(target)


def newest_handoff(lane_id: str | None = None) -> dict | None:
    if not _HANDOFF_DIR.is_dir():
        return None
    if lane_id:
        p = current_path(lane_id)
        candidates = [p] if p.exists() else []
    else:
        candidates = sorted(_HANDOFF_DIR.glob("HANDOFF-CURRENT-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in candidates:
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
    return None


def is_stale(h: dict) -> tuple:
    """(stale, reason). Checa valid_until E stale_when.head_moved (correção v1.1)."""
    valid_until = h.get("valid_until")
    if valid_until:
        try:
            vu = datetime.fromisoformat(valid_until)
            if datetime.now(vu.tzinfo or timezone.utc) > vu:
                return True, "valid_until expired"
        except ValueError:
            pass
    written_head = (h.get("git") or {}).get("head")
    current_head = _git(["rev-parse", "--short", "HEAD"])
    if written_head and current_head and written_head != current_head:
        return True, f"HEAD moved (was {written_head}, now {current_head}) — stale_when.head_moved"
    return False, ""


def render(h: dict, cap_bytes: int = 4096) -> str:
    stale, reason = is_stale(h)
    lines = ["⚠️ RESTORED CONTEXT = HISTORICAL REFERENCE, NOT A QUEUE (LC-4)"]
    lines.append(f"HANDOFF {h.get('handoff_id')} · {h.get('quality')} · lane={h.get('session', {}).get('lane_id')}")
    if stale:
        lines.append(f"⚠️ STALE ({reason}) — re-derive everything via re_derive_cmd; proximo_passo is NOT actionable.")
    else:
        estado = h.get("estado", {})
        lines.append(f"STATE: {estado.get('resumo', '')}")
        for n in estado.get("numeros", []) or []:
            lines.append(f"  · {n['metrica']}={n['valor']} (re-derive: {n['re_derive_cmd']})")
        ja = h.get("ja_executado", []) or []
        if ja:
            lines.append("ALREADY EXECUTED — NEVER REPEAT: " + "; ".join(j["acao"] for j in ja))
        gates = h.get("gates_abertos", []) or []
        if gates:
            lines.append("OPEN GATES: " + "; ".join(g["descricao"] for g in gates))
        proib = h.get("proibicoes", []) or []
        if proib:
            lines.append("PROHIBITIONS: " + "; ".join(proib))
        passos = sorted(h.get("proximo_passo", []) or [], key=lambda p: p.get("ordem", 0))
        if passos:
            p0 = passos[0]
            lines.append(f"NEXT STEP {p0.get('ordem')}: {p0.get('descricao')}")
            lines.append(f"  → BEFORE EXECUTING, RUN: {p0.get('verify_first_cmd')} (if already done: skip and record it)")
    lines.append(f"Full file: {current_path(h.get('session', {}).get('lane_id', 'solo'))}")
    text = "\n".join(lines)
    return text[:cap_bytes]


def consume(handoff_id: str, session_id: str, lane_id: str = "solo") -> None:
    append_ledger("consumed", handoff_id, lane_id=lane_id, by_session=session_id)


def degraded_auto_aggregate(lane_id: str = "solo", session_id: str = "",
                            checkpoint_ref: str = "", checkpoint_commit: str = "") -> dict:
    """Fallback quando a sessão morre sem /pre-clear (usado por handoff_guard.py)."""
    now = _now_iso()
    ts_id = datetime.now().strftime("%Y%m%d-%H%M")
    log = _git(["log", "--oneline", "-5"])
    return {
        "schema_version": "1.1",
        "handoff_id": f"HO-{ts_id}-{lane_id}",
        "created_at": now,
        "trigger": "degraded-auto",
        "quality": "degraded-auto",
        "session": {"session_id": session_id, "lane_id": lane_id},
        "estado": {"resumo": "Session ended without /pre-clear — degraded handoff, automatic aggregation.", "numeros": []},
        "git": git_block(checkpoint_ref=checkpoint_ref, checkpoint_commit=checkpoint_commit),
        "ja_executado": [],
        "proximo_passo": [],
        "gates_abertos": [],
        "proibicoes": ["NEVER treat this degraded handoff as full coverage — reconfirm everything at the live source (LC-1)."],
        "evidencias": [{"tipo": "cmd", "ref": "git log --oneline -5", "valor": log}],
        "valid_until": (datetime.now(timezone(timedelta(hours=-3))) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S-03:00"),
        "boot_docs": [],
    }


def _demo_handoff(lane_id: str = "solo") -> dict:
    now = _now_iso()
    ts_id = datetime.now().strftime("%Y%m%d-%H%M")
    return {
        "schema_version": "1.1",
        "handoff_id": f"HO-{ts_id}-{lane_id}",
        "created_at": now,
        "trigger": "manual",
        "quality": "full",
        "session": {"session_id": "demo-session", "lane_id": lane_id, "role": "solo"},
        "estado": {
            "resumo": "Demo handoff generated by --demo.",
            "numeros": [{"metrica": "example", "valor": "1", "medido_em": now, "re_derive_cmd": "echo 1"}],
        },
        "git": git_block(),
        "ja_executado": [{"acao": "generated the demo", "evidencia": "this very file", "nunca_repetir": True}],
        "proximo_passo": [{"ordem": 1, "descricao": "nothing — it is a demo", "verify_first_cmd": "echo verified"}],
        "gates_abertos": [],
        "proibicoes": [],
        "valid_until": (datetime.now(timezone(timedelta(hours=-3))) + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S-03:00"),
        "boot_docs": [],
    }


def _self_test() -> int:
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="handoff_io_selftest_"))
    global _HANDOFF_DIR, LEDGER_PATH, _PROJECT_ROOT
    orig_dir, orig_ledger, orig_root = _HANDOFF_DIR, LEDGER_PATH, _PROJECT_ROOT
    try:
        _PROJECT_ROOT = tmp
        _HANDOFF_DIR = tmp / ".claude" / "handoff"
        LEDGER_PATH = _HANDOFF_DIR / "HANDOFF-LEDGER.jsonl"

        good = {
            "schema_version": "1.1", "handoff_id": "HO-20260710-1500-solo",
            "created_at": "2026-07-10T15:00:00-03:00", "trigger": "manual", "quality": "full",
            "session": {"session_id": "s1", "lane_id": "solo"},
            "estado": {"resumo": "test", "numeros": [{"metrica": "x", "valor": "1", "medido_em": "2026-07-10T15:00:00-03:00", "re_derive_cmd": "echo 1"}]},
            "git": {"head": "abc123", "branch": "main", "dirty": False, "untracked": 0},
            "proximo_passo": [{"ordem": 1, "descricao": "do x", "verify_first_cmd": "test -f x"}],
            "valid_until": "2099-01-01T00:00:00-03:00",
        }
        ok, result = write(good)
        assert ok, f"a valid handoff should be written: {result}"
        assert current_path("solo").exists(), "file was not created"

        ledger_lines = LEDGER_PATH.read_text(encoding="utf-8").splitlines()
        assert any(json.loads(l)["event"] == "written" for l in ledger_lines), "ledger has no written event"

        no_verify = dict(good, handoff_id="HO-20260710-1501-solo", proximo_passo=[{"ordem": 1, "descricao": "no verify"}])
        ok2, errs2 = write(no_verify)
        assert not ok2 and any("verify_first_cmd" in e for e in errs2), f"should reject without verify_first_cmd: {errs2}"

        no_derive = dict(good, handoff_id="HO-20260710-1502-solo", estado={"resumo": "x", "numeros": [{"metrica": "y", "valor": "2", "medido_em": "2026-07-10T15:00:00-03:00"}]})
        ok3, errs3 = write(no_derive)
        assert not ok3 and any("re_derive_cmd" in e for e in errs3), f"should reject without re_derive_cmd: {errs3}"

        with_secret = dict(good, handoff_id="HO-20260710-1503-solo", estado={"resumo": "token = \"sk-ant-1234567890abcdef1234\"", "numeros": []})
        ok4, errs4 = write(with_secret)
        assert not ok4 and any("secret" in e for e in errs4), f"should reject with a secret: {errs4}"

        degraded_no_porcelain = dict(good, handoff_id="HO-20260710-1504-solo", quality="degraded-auto")
        ok5, errs5 = write(degraded_no_porcelain)
        assert not ok5 and any("porcelain" in e for e in errs5), f"degraded-auto without porcelain should fail: {errs5}"

        h = newest_handoff("solo")
        assert h is not None and h["handoff_id"] == "HO-20260710-1500-solo"

        text = render(h)
        assert "LC-4" in text and "NEXT STEP" in text, f"incomplete render: {text}"

        stale_h = dict(good, valid_until="2020-01-01T00:00:00-03:00")
        stale, reason = is_stale(stale_h)
        assert stale and "expired" in reason

        consume(h["handoff_id"], "session-x", "solo")
        ledger_lines2 = LEDGER_PATH.read_text(encoding="utf-8").splitlines()
        assert any(json.loads(l)["event"] == "consumed" for l in ledger_lines2), "ledger has no consumed event"

        degraded = degraded_auto_aggregate("solo", "s2")
        okd, resd = write(degraded)
        assert okd, f"degraded_auto_aggregate should be valid: {resd}"

        print("self-test OK — valid write+ledger, rejects without verify_first_cmd, rejects without re_derive_cmd, "
              "rejects secret, rejects degraded-auto without porcelain, render with LC-4, staleness, consume, degraded-auto")
        return 0
    finally:
        _HANDOFF_DIR, LEDGER_PATH, _PROJECT_ROOT = orig_dir, orig_ledger, orig_root
        shutil.rmtree(tmp, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="_handoff_io.py")
    sub = p.add_subparsers(dest="cmd")

    w = sub.add_parser("write")
    w.add_argument("--stdin", action="store_true")
    w.add_argument("--demo", action="store_true")
    w.add_argument("--lane", default="solo")

    r = sub.add_parser("read")
    r.add_argument("--lane", default=None)
    r.add_argument("--last", type=int, default=None)

    ren = sub.add_parser("render")
    ren.add_argument("--lane", default="solo")

    c = sub.add_parser("consume")
    c.add_argument("handoff_id")
    c.add_argument("--session", default="")
    c.add_argument("--lane", default="solo")

    p.add_argument("--self-test", action="store_true")
    return p


def main(argv) -> int:
    args = build_parser().parse_args(argv)

    if args.self_test:
        return _self_test()

    if args.cmd == "write":
        if args.demo:
            data = _demo_handoff(args.lane)
        elif args.stdin:
            try:
                data = json.loads(sys.stdin.read())
            except Exception as e:  # noqa: BLE001
                print(f"_handoff_io: invalid JSON on stdin: {e}", file=sys.stderr)
                return 2
        else:
            print("usage: write --stdin | write --demo [--lane X]", file=sys.stderr)
            return 2
        ok, result = write(data)
        if ok:
            print(f"_handoff_io: written to {result}")
            return 0
        for e in result:
            print(f"  [REJECTED] {e}", file=sys.stderr)
        return 1

    if args.cmd == "read":
        if args.last:
            if not LEDGER_PATH.exists():
                print("[]")
                return 0
            lines = LEDGER_PATH.read_text(encoding="utf-8").splitlines()[-args.last:]
            print(json.dumps([json.loads(l) for l in lines], ensure_ascii=False, indent=2))
            return 0
        h = newest_handoff(args.lane)
        print(json.dumps(h, ensure_ascii=False, indent=2) if h else "null")
        return 0

    if args.cmd == "render":
        h = newest_handoff(args.lane)
        if not h:
            print("_handoff_io: no handoff found", file=sys.stderr)
            return 1
        print(render(h))
        return 0

    if args.cmd == "consume":
        consume(args.handoff_id, args.session, args.lane)
        print(f"_handoff_io: consumed recorded for {args.handoff_id}")
        return 0

    print("usage: write|read|render|consume [...] or --self-test", file=sys.stderr)
    return 2


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
