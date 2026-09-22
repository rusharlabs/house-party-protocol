#!/usr/bin/env python3
"""
concurrency -- max concurrent agents, waves and rate-limit detection (Operator Kit).

Materializes the lesson "waves of <=3 win where 8-16 blow up (rate-limit)". Reads
`concurrency.*` from operator-profile.yaml (max_agents, wave_size, rate_limit_signals,
fallback). Without a profile, safe defaults (max_agents 3, fallback sequential-local).

Programmatic use (in dispatch skills/scripts):
    from _lib.concurrency import max_agents, waves, is_rate_limited, fallback_mode
    for batch in waves(tasks):        # each batch has at most `max_agents` items
        ...
    if is_rate_limited(stderr): ...    # matches "429"/"rate limit"/"quota"/"overloaded"

stdlib + (PyYAML via loader). Never crashes. --self-test with no network/profile.

v1.1.0 -- 2026-09-22 (Operator Kit - Tier 2) -- v1.0.0 2026-06-19
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

_DEF_MAX_AGENTS = 3
_DEF_SIGNALS = ["429", "rate limit", "quota", "overloaded"]


def _profile() -> dict:
    return load_profile() if load_profile is not None else {}


def max_agents() -> int:
    p = _profile()
    v = get(p, "concurrency.max_agents", _DEF_MAX_AGENTS) if (p and get) else _DEF_MAX_AGENTS
    try:
        return max(1, int(v))
    except (TypeError, ValueError):
        return _DEF_MAX_AGENTS


# Why, the rename: the profile key became `concurrency.max_agents`; a function still
# called `teto` would send a skill author grepping for a word the config no longer contains.
# The old name keeps importing for one version, like the legacy keys in the loader.
teto = max_agents  # deprecated alias, removed in v2.7.0


def wave_size() -> int:
    p = _profile()
    v = get(p, "concurrency.wave_size", max_agents()) if (p and get) else max_agents()
    try:
        return max(1, int(v))
    except (TypeError, ValueError):
        return max_agents()


def waves(items, size: int | None = None):
    """Generates batches of size <= `size` (or the profile's wave_size). [] for empty."""
    items = list(items)
    n = max(1, int(size)) if size else wave_size()
    for i in range(0, len(items), n):
        yield items[i:i + n]


def rate_limit_signals() -> list[str]:
    p = _profile()
    sig = get(p, "concurrency.rate_limit_signals", _DEF_SIGNALS) if (p and get) else _DEF_SIGNALS
    return [str(s).lower() for s in sig] if isinstance(sig, list) else list(_DEF_SIGNALS)


def is_rate_limited(text) -> bool:
    t = str(text or "").lower()
    return any(s in t for s in rate_limit_signals())


def fallback_mode() -> str:
    p = _profile()
    return get(p, "concurrency.fallback", "sequential-local") if (p and get) else "sequential-local"


def _self_test() -> None:
    assert list(waves([1, 2, 3, 4, 5, 6, 7], 3)) == [[1, 2, 3], [4, 5, 6], [7]], "ondas de 3"
    assert list(waves([], 3)) == [], "vazio = sem ondas"
    assert list(waves([1], 5)) == [[1]], "1 item"
    assert is_rate_limited("HTTP 429 Too Many Requests") is True
    assert is_rate_limited("rate limit exceeded") is True
    assert is_rate_limited("tudo certo") is False
    assert max_agents() >= 1 and wave_size() >= 1
    assert teto is max_agents, "the deprecated alias must keep importing for one version"
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
        print(f"max_agents={max_agents()} wave_size={wave_size()} fallback={fallback_mode()} "
              f"signals={rate_limit_signals()}")
