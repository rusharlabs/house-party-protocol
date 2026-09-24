#!/usr/bin/env python3
"""
profile_loader — finds and reads the project's `operator-profile.yaml`.

It is the single point through which EVERY mechanism of the kit reads config. With no profile
the mechanisms degrade to safe defaults (they never break).

Resolution (first one that exists):
  1. env OPERATOR_PROFILE=/explicit/path.yaml
  2. operator-profile.yaml walking up from the cwd to the root
  3. <dir>/operator-kit/operator-profile.yaml walking up from the cwd (nested kit)
  4. operator-profile.yaml next to this _lib/ (the kit's own fallback)

API:
  load_profile(start=None) -> dict          # {} if not found or PyYAML is missing
  get(profile, "a.b.c", default=None)        # dot-path walk, None-proof, dual read (below)
  profile_path(start=None) -> Path | None

Dual read of the renamed keys (deprecation, until v2.7.0)
  Up to v2.5.0 the profile asked the user to type Portuguese keys (`projeto`, `verificacao`,
  `memoria`, ...). They are English now. `get()` reads the ENGLISH key first and falls back to
  the legacy spelling at ANY depth of the dotted path, so a repo whose file was written before
  the rename keeps working with zero action. The first time a legacy key is used, one line on
  stderr says so; the exit code never moves. An explicit new key always wins over a stale
  legacy one. From v2.7.0 the legacy spelling stops being read.

stdlib + PyYAML. Cross-platform (pathlib). Never raises for the caller.

v1.1.0 — 2026-09-22 (Operator Kit · Tier 1) — v1.0.0 2026-06-19
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import yaml  # PyYAML
except ImportError:  # silent degradation — the caller handles {}
    yaml = None  # type: ignore[assignment]

_NAMES = ("operator-profile.yaml", "operator-profile.yml")
_KIT_DIR = Path(__file__).resolve().parent.parent  # .../operator-kit

# Why, the rename of the profile keys: the product's docs, runtime and layout are
# English and the one file the user EDITS still asked for `projeto:` / `verificacao:`. The table
# is keyed by SEGMENT, not by full dotted path, because `get()` walks segment by segment: that is
# what makes `verification.done_criteria.py` fall back on both renamed segments at once. Every
# legacy name here is unique and so is every English one, so a segment-level table cannot collide.
_LEGACY_KEYS = {
    "project": "projeto",
    "language": "idioma",
    "register": "forma_tratamento",
    "autonomy": "autonomia",
    "by_action": "por_acao",
    "rm_live_code": "rm_codigo_vivo",
    "git_push_protected_branch": "git_push_branch_protegida",
    "edit_code": "edit_codigo",
    "sensitive_paths_auto_gate": "paths_sensiveis_auto_gate",
    "intensity": "intensidade",
    "concurrency": "concorrencia",
    "max_agents": "teto",
    "verification": "verificacao",
    "done_criteria": "done_criterios",
    "ladder_required": "ladder_obrigatorios",
    "ladder_min_score": "ladder_score_minimo",
    "stale_source_ttl_days": "fonte_suspeita_ttl_dias",
    "forbidden_boundaries": "fronteiras_proibidas",
    "authorization_triggers": "gatilho_autorizacao",
    "planning": "planejamento",
    "small": "pequeno",
    "medium": "medio",
    "large": "grande",
    "session_window": "janela_sessoes",
    "recurrence_threshold": "limiar_recorrencia",
    "rejected_ledger": "ledger_rejeitadas",
    "target_rule": "regra_alvo",
    "memory": "memoria",
    "emphasis_markers": "marcadores_enfase",
    "internal_style": "estilo_interno",
    "external_style": "estilo_externo",
    "banned_phrases": "frases_banidas",
}
LEGACY_REMOVED_IN = "2.7.0"
_warned: set[str] = set()
# A caller that re-runs on every prompt (a statusline) sets this to True: the fallback still works,
# it just stops shouting. Default is LOUD — silence is what lets a deprecation outlive its version.
QUIET_DEPRECATION = False


def _warn_legacy(legacy: str, new: str, dotted: str) -> None:
    """One line per legacy key, once per process. Stderr only — the exit code is not ours to move."""
    if QUIET_DEPRECATION or legacy in _warned:
        return
    _warned.add(legacy)
    # Why: pure ASCII on purpose. A child process on a cp1252 console encodes an em dash as the
    # byte 0x97, and a parent that reads its stderr as UTF-8 raises mid-read (measured 2026-09-22
    # on the existing `autoprompt_resume` notice, under skill_lint --run-proofs).
    print(f"[operator-profile] deprecated key '{legacy}' read as '{new}' (in '{dotted}'); "
          f"rename it in operator-profile.yaml. The old spelling stops being read in "
          f"v{LEGACY_REMOVED_IN}.", file=sys.stderr)


def profile_path(start: str | os.PathLike | None = None) -> Path | None:
    """Returns the Path of the resolved profile, or None if none exists."""
    env = os.environ.get("OPERATOR_PROFILE")
    if env:
        p = Path(env)
        if p.exists():
            return p
    base = Path(start or os.getcwd()).resolve()
    for d in (base, *base.parents):
        for name in _NAMES:
            cand = d / name
            if cand.exists():
                return cand
            nested = d / "operator-kit" / name
            if nested.exists():
                return nested
            staged = d / "staging" / "operator-kit" / name
            if staged.exists():
                return staged
    for name in _NAMES:  # fallback: next to the kit itself
        cand = _KIT_DIR / name
        if cand.exists():
            return cand
    return None


def load_profile(start: str | os.PathLike | None = None) -> dict:
    """Reads and parses the profile. {} if absent, unreadable, or PyYAML is unavailable."""
    p = profile_path(start)
    if p is None or yaml is None:
        return {}
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 — the loader never breaks the caller
        return {}


def get(profile: dict, dotted: str, default=None):
    """profile['a']['b']['c'], tolerant of None/absence. E.g. get(p, 'concurrency.max_agents', 3).

    Reads the English key first; falls back to the legacy Portuguese spelling of that segment
    (see _LEGACY_KEYS) with one deprecation line on stderr. Never raises.
    """
    cur = profile
    for key in dotted.split("."):
        if isinstance(cur, dict):
            if key in cur:
                cur = cur[key]
                continue
            legacy = _LEGACY_KEYS.get(key)
            if legacy is not None and legacy in cur:
                _warn_legacy(legacy, key, dotted)
                cur = cur[legacy]
                continue
        return default
    return cur


def _self_test() -> None:
    assert get({"a": {"b": 1}}, "a.b") == 1
    assert get({"a": {"b": 1}}, "a.x", 9) == 9
    assert get({}, "a.b.c", "d") == "d"
    assert get({"a": None}, "a.b", "fallback") == "fallback"
    # dual read: the legacy spelling resolves at any depth, and the new key wins when both exist
    _warned.clear()
    assert get({"projeto": "x"}, "project") == "x"
    assert get({"verificacao": {"done_criterios": {"py": ["t"]}}}, "verification.done_criteria.py") == ["t"]
    assert get({"projeto": "old", "project": "new"}, "project") == "new"
    assert "projeto" in _warned and "verificacao" in _warned
    print("self-test OK")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    if len(sys.argv) > 1 and sys.argv[1] in ("--self-test", "-t"):
        _self_test()
    else:
        prof = load_profile()
        path = profile_path()
        if not prof:
            print("no operator-profile.yaml found (or PyYAML missing) — using defaults")
        else:
            import json
            print(f"# profile: {path}")
            print(json.dumps(prof, ensure_ascii=False, indent=2, default=str))
