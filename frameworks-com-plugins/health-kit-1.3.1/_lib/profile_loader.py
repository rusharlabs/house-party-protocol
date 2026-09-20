#!/usr/bin/env python3
"""
profile_loader — acha e lê o operator-profile.yaml do projeto.

É o ponto único que TODO mecanismo do Operator Kit usa para ler config. Sem
profile, os mecanismos degradam para defaults seguros (nunca quebram).

Resolução (primeira que existir):
  1. env OPERATOR_PROFILE=/caminho/explicito.yaml
  2. operator-profile.yaml subindo da cwd até a raiz
  3. <dir>/operator-kit/operator-profile.yaml subindo da cwd (kit aninhado)
  4. operator-profile.yaml ao lado deste _lib/ (fallback do próprio kit)

API:
  load_profile(start=None) -> dict          # {} se não achar ou PyYAML ausente
  get(profile, "a.b.c", default=None)        # navegação por dot-path, à prova de None
  profile_path(start=None) -> Path | None

stdlib + PyYAML. Cross-platform (pathlib). Nunca levanta exceção para o chamador.

v1.0.0 — 2026-06-19 (Operator Kit · Tier 1)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import yaml  # PyYAML
except ImportError:  # degrade silencioso — quem chama trata {}
    yaml = None  # type: ignore[assignment]

_NAMES = ("operator-profile.yaml", "operator-profile.yml")
_KIT_DIR = Path(__file__).resolve().parent.parent  # .../operator-kit


def profile_path(start: str | os.PathLike | None = None) -> Path | None:
    """Retorna o Path do profile resolvido, ou None se nenhum existir."""
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
    for name in _NAMES:  # fallback: ao lado do próprio kit
        cand = _KIT_DIR / name
        if cand.exists():
            return cand
    return None


def load_profile(start: str | os.PathLike | None = None) -> dict:
    """Lê e parseia o profile. {} se ausente, ilegível, ou PyYAML indisponível."""
    p = profile_path(start)
    if p is None or yaml is None:
        return {}
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 — loader jamais quebra o chamador
        return {}


def get(profile: dict, dotted: str, default=None):
    """profile['a']['b']['c'] tolerante a None/ausência. Ex.: get(p, 'concorrencia.teto', 3)."""
    cur = profile
    for key in dotted.split("."):
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return default
    return cur


def _self_test() -> None:
    assert get({"a": {"b": 1}}, "a.b") == 1
    assert get({"a": {"b": 1}}, "a.x", 9) == 9
    assert get({}, "a.b.c", "d") == "d"
    assert get({"a": None}, "a.b", "fallback") == "fallback"
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
            print("nenhum operator-profile.yaml encontrado (ou PyYAML ausente) — usando defaults")
        else:
            import json
            print(f"# profile: {path}")
            print(json.dumps(prof, ensure_ascii=False, indent=2, default=str))
