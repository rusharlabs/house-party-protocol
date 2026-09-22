#!/usr/bin/env python3
"""
concurrency — teto de agentes concorrentes, ondas e detecção de rate-limit (Operator Kit).

Materializa a lição "ondas de ≤3 vencem onde 8-16 explodem (rate-limit)". Lê
`concorrencia.*` do operator-profile.yaml (teto, wave_size, rate_limit_signals,
fallback). Sem profile, defaults seguros (teto 3, fallback sequential-local).

Uso programático (em skills/scripts de dispatch):
    from _lib.concurrency import teto, waves, is_rate_limited, fallback_mode
    for lote in waves(tarefas):        # cada lote tem no máx `teto` itens
        ...
    if is_rate_limited(stderr): ...    # casa "429"/"rate limit"/"quota"/"overloaded"

stdlib + (PyYAML via loader). Nunca crasha. --self-test sem rede/profile.

v1.0.0 — 2026-06-19 (Operator Kit · Tier 2)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # .../operator-kit
try:
    from _lib.profile_loader import load_profile, get
except Exception:  # noqa: BLE001
    load_profile = None  # type: ignore[assignment]
    get = None  # type: ignore[assignment]

_DEF_TETO = 3
_DEF_SIGNALS = ["429", "rate limit", "quota", "overloaded"]


def _profile() -> dict:
    return load_profile() if load_profile is not None else {}


def teto() -> int:
    p = _profile()
    v = get(p, "concorrencia.teto", _DEF_TETO) if (p and get) else _DEF_TETO
    try:
        return max(1, int(v))
    except (TypeError, ValueError):
        return _DEF_TETO


def wave_size() -> int:
    p = _profile()
    v = get(p, "concorrencia.wave_size", teto()) if (p and get) else teto()
    try:
        return max(1, int(v))
    except (TypeError, ValueError):
        return teto()


def waves(items, size: int | None = None):
    """Gera lotes de tamanho <= `size` (ou wave_size do profile). [] p/ vazio."""
    items = list(items)
    n = max(1, int(size)) if size else wave_size()
    for i in range(0, len(items), n):
        yield items[i:i + n]


def rate_limit_signals() -> list[str]:
    p = _profile()
    sig = get(p, "concorrencia.rate_limit_signals", _DEF_SIGNALS) if (p and get) else _DEF_SIGNALS
    return [str(s).lower() for s in sig] if isinstance(sig, list) else list(_DEF_SIGNALS)


def is_rate_limited(text) -> bool:
    t = str(text or "").lower()
    return any(s in t for s in rate_limit_signals())


def fallback_mode() -> str:
    p = _profile()
    return get(p, "concorrencia.fallback", "sequential-local") if (p and get) else "sequential-local"


def _self_test() -> None:
    assert list(waves([1, 2, 3, 4, 5, 6, 7], 3)) == [[1, 2, 3], [4, 5, 6], [7]], "ondas de 3"
    assert list(waves([], 3)) == [], "vazio = sem ondas"
    assert list(waves([1], 5)) == [[1]], "1 item"
    assert is_rate_limited("HTTP 429 Too Many Requests") is True
    assert is_rate_limited("rate limit exceeded") is True
    assert is_rate_limited("tudo certo") is False
    assert teto() >= 1 and wave_size() >= 1
    assert isinstance(fallback_mode(), str)
    print("self-test OK")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    if len(sys.argv) > 1 and sys.argv[1] in ("--self-test", "-t"):
        _self_test()
    else:
        print(f"teto={teto()} wave_size={wave_size()} fallback={fallback_mode()} "
              f"signals={rate_limit_signals()}")
