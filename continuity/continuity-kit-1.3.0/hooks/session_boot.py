#!/usr/bin/env python3
"""
session_boot — SessionStart genérico e despersonalizado (sem persona/identidade de agente).

Fusão de um padrão real de session-start (963L, rico demais — persona embutida) com o
`session_start.py` de um projeto de referência (88L, enxuto, `MAX_SECTION=3500`, fail-open). Este é o canônico
DESPERSONALIZADO: git HEAD/branch/tags + seções vivas do state-doc (config-driven, não
hardcoded) + delega ao `handoff_inject.py` a leitura do handoff-v1 (fecha o gap: escrita
automática via handoff_guard.py + leitura automática aqui — nenhum kit anterior fazia as
duas pontas antes da FASE 5).

Config (via profile, chave `paths.state_doc`; default `docs/plans/execution/00-STATE.md`).

Uso (hook): echo '{"hook_event_name":"SessionStart","session_id":"..."}' | python session_boot.py
Exit: sempre 0 (fail-open total — nunca derruba o boot da sessão).

stdlib only. v1.0.0 — 2026-07-10 (continuity-kit · Tier 2 · TEMPLATE-SET item 14)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import _handoff_io
except Exception:  # noqa: BLE001 — funciona sem o handoff se o kit não estiver completo
    _handoff_io = None  # type: ignore[assignment]

MAX_SECTION = 3500  # padrão de referência, provado em produção — cap por seção, não pelo total
_PROJECT_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
_DEFAULT_STATE_DOC = "docs/plans/execution/00-STATE.md"
# Why: the generated directory was renamed to English. A repo that already holds the old
# spelling must keep booting with zero action, so the default path is DUAL-READ for one
# version: the English name wins, the legacy one is read with a deprecation notice.
_LEGACY_STATE_DOC = "docs/plans/execucao/00-STATE.md"


def _resolve_state_doc(state_doc_rel: str) -> str:
    """Dual read of the DEFAULT path only — an explicit `paths.state_doc` is never rewritten."""
    if state_doc_rel != _DEFAULT_STATE_DOC:
        return state_doc_rel
    if (_PROJECT_ROOT / _DEFAULT_STATE_DOC).exists():
        return _DEFAULT_STATE_DOC
    if (_PROJECT_ROOT / _LEGACY_STATE_DOC).exists():
        print(
            f"[session_boot] deprecated: read '{_LEGACY_STATE_DOC}'; rename it to "
            f"'{_DEFAULT_STATE_DOC}' — the old spelling is accepted for one version only.",
            file=sys.stderr,
        )
        return _LEGACY_STATE_DOC
    return _DEFAULT_STATE_DOC


def _read_section(text: str, start_marker: str, end_markers: list) -> str:
    i = text.find(start_marker)
    if i == -1:
        return ""
    end = len(text)
    for m in end_markers:
        j = text.find(m, i + len(start_marker))
        if j != -1:
            end = min(end, j)
    return text[i:end].strip()[:MAX_SECTION]


def _git(args: list, timeout: int = 10) -> str:
    try:
        r = subprocess.run(["git", "-C", str(_PROJECT_ROOT)] + args, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def build_context(state_doc_rel: str = _DEFAULT_STATE_DOC) -> str:
    out = []
    state_doc_rel = _resolve_state_doc(state_doc_rel)
    state_path = _PROJECT_ROOT / state_doc_rel

    if state_path.exists():
        age_h = (time.time() - state_path.stat().st_mtime) / 3600.0
        stale = " — ⚠️ STALE (>48h): treat as historical reference, reconfirm at the live source before acting" if age_h > 48 else ""
        out.append(f"[AUTO ANCHOR — session_boot] {state_doc_rel} is {age_h:.0f}h old{stale}.")
        text = state_path.read_text(encoding="utf-8", errors="replace")
        agora = _read_section(text, "## Agora", ["## PENDÊNCIAS", "## Log"])
        pend = _read_section(text, "## PENDÊNCIAS ABERTAS", ["## Log", "## Agora"])
        if agora:
            out.append(agora)
        if pend:
            out.append(pend)

    head = _git(["log", "--oneline", "-1"])
    branch = _git(["branch", "--show-current"])
    if head:
        out.append(f"repo: branch={branch} · HEAD={head}")

    if _handoff_io is not None:
        try:
            h = _handoff_io.newest_handoff(None)
            if h:
                out.append(_handoff_io.render(h, cap_bytes=MAX_SECTION))
        except Exception:  # noqa: BLE001 — fail-open: handoff quebrado não derruba o boot
            pass

    out.append(
        "RULE stale-replay-guard (LC-4): restored/injected context is HISTORICAL REFERENCE, "
        "NOT an execution queue — before re-running any action, reconfirm at the live source."
    )
    return "\n\n".join(out)


def _self_test() -> int:
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="session_boot_selftest_"))
    global _PROJECT_ROOT
    orig = _PROJECT_ROOT
    try:
        _PROJECT_ROOT = tmp
        state_path = tmp / _DEFAULT_STATE_DOC
        state_path.parent.mkdir(parents=True)
        state_path.write_text("## Agora\ntest focus\n\n## PENDÊNCIAS ABERTAS\n- [ ] x\n\n## Log\nobsolete-log-line\n", encoding="utf-8")

        ctx = build_context()
        assert "test focus" in ctx and "PENDÊNCIAS" in ctx and "LC-4" in ctx, f"incomplete context: {ctx}"
        assert "obsolete-log-line" not in ctx, "the Log section should not leak (cut by the end_marker)"

        # dual read: a repo that only has the legacy spelling still boots
        legacy_path = tmp / _LEGACY_STATE_DOC
        legacy_path.parent.mkdir(parents=True)
        legacy_path.write_text("## Agora\nlegacy focus\n\n## Log\nx\n", encoding="utf-8")
        assert "test focus" in build_context(), "the English path must win when both exist"
        state_path.unlink()
        assert "legacy focus" in build_context(), "the legacy path must still be read"

        legacy_path.unlink()
        ctx2 = build_context()
        assert "LC-4" in ctx2, "without a state-doc it should still work (partial fail-open)"

        print("self-test OK — extracts Agora+PENDÊNCIAS with a per-section cap, cuts at the right end_marker, "
              "dual read (English path wins, legacy path still read), works without a state-doc")
        return 0
    finally:
        _PROJECT_ROOT = orig
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv) -> int:
    if argv and argv[0] in ("--self-test", "-t"):
        return _self_test()
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        state_doc = os.environ.get("SESSION_BOOT_STATE_DOC", _DEFAULT_STATE_DOC)
        ctx = build_context(state_doc)
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}}, ensure_ascii=False))
    except Exception:  # noqa: BLE001 — fail-open total, igual ao padrão de referência original
        pass
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
