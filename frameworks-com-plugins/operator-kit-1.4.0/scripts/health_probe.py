#!/usr/bin/env python3
"""
health_probe (Operator Kit) — connector de saude GENERICO e config-driven.

Sonda uma lista de servicos definida em `health.probes` do operator-profile.yaml,
grava um cache JSON (paths.health_cache) que o segmento `health` da statusline le
SEM tocar a rede, e imprime um resumo. Pensado p/ rodar no SessionStart / cron /
sob demanda — NUNCA no caminho da statusline (que so le o cache).

Tipos de sonda (health.probes = lista de {name, type, target}):
  http -> urllib GET; online se status < 400 (NUNCA usa curl/wget — deny-list)
  cmd  -> subprocess shell; online se exit 0 (comando vem do profile = confiavel)

Cache (schema que a statusline entende):
  {"health": {"services_online": N, "services_total": M}, "services": {name: {"online": bool, ...}}}

CLI: health_probe.py [--json] [--quiet]  ·  --self-test (sonda cmd local, sem rede)
exit 0 sempre (connector nao quebra fluxo). stdlib + PyYAML (via loader).
v1.1.0 — 2026-07-10 (Operator Kit · Tier 2 · rename services/health, remove vocabulario "brains")
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from _lib.profile_loader import load_profile, get, profile_path
except Exception:  # noqa: BLE001
    load_profile = None  # type: ignore[assignment]

    def get(_p, _k, default=None):  # type: ignore[misc]
        return default

    def profile_path(_s=None):  # type: ignore[misc]
        return None

_BRT = timezone(timedelta(hours=-3))
_DEF_HEALTH_CACHE = ".claude/health-cache.json"


def _root() -> Path:
    if load_profile is not None:
        p = profile_path()
        if p is not None:
            d = p.parent
            for cand in (d, *d.parents):
                if (cand / ".git").exists():
                    return cand
            return d
    cur = Path.cwd().resolve()
    for cand in (cur, *cur.parents):
        if (cand / ".git").exists():
            return cand
    return cur


def probe_http(target: str, timeout: int = 5) -> bool:
    try:
        req = urllib.request.Request(target, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — target do profile
            return getattr(r, "status", 200) < 400
    except Exception:
        return False


def probe_cmd(target: str, root: Path, timeout: int = 10) -> bool:
    try:
        r = subprocess.run(target, shell=True, cwd=str(root),  # noqa: S602 — comando do profile (confiavel)
                          capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0
    except Exception:
        return False


def run_probes(probes: list, root: Path) -> dict:
    """Roda cada sonda. Retorna o dict de cache (schema da statusline)."""
    services: dict = {}
    for p in probes:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or "?")
        ptype = str(p.get("type") or "http").lower()
        target = str(p.get("target") or "")
        if not target:
            online = False
        elif ptype == "cmd":
            online = probe_cmd(target, root)
        else:
            online = probe_http(target)
        services[name] = {"online": online, "type": ptype, "target": target}
    up = sum(1 for b in services.values() if b.get("online"))
    return {
        "ts": datetime.now(_BRT).strftime("%Y-%m-%d %H:%M BRT"),
        "health": {"services_online": up, "services_total": len(services)},
        "services": services,
    }


def _probes_cfg() -> list:
    cfg = get(load_profile() if load_profile else {}, "health.probes", [])
    return cfg if isinstance(cfg, list) else []


def main(argv) -> int:
    as_json = "--json" in argv
    quiet = "--quiet" in argv
    root = _root()
    probes = _probes_cfg()
    if not probes:
        if not quiet:
            print("health_probe: nenhuma sonda em health.probes do operator-profile.yaml", file=sys.stderr)
        return 0
    cache = run_probes(probes, root)

    # grava o cache que a statusline le (paths.health_cache)
    cache_path = root / get(load_profile() if load_profile else {}, "paths.health_cache", _DEF_HEALTH_CACHE)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass

    h = cache["health"]
    if as_json:
        print(json.dumps(cache, ensure_ascii=False, indent=2))
    elif not quiet:
        down = [n for n, b in cache["services"].items() if not b.get("online")]
        tail = f" (DOWN: {', '.join(down)})" if down else ""
        print(f"⚕ {h['services_online']}/{h['services_total']} UP{tail}")
    return 0


def _self_test() -> None:
    root = Path.cwd()
    probes = [
        {"name": "ok", "type": "cmd", "target": f'"{sys.executable}" -c "import sys;sys.exit(0)"'},
        {"name": "fail", "type": "cmd", "target": f'"{sys.executable}" -c "import sys;sys.exit(1)"'},
    ]
    cache = run_probes(probes, root)
    assert cache["health"]["services_online"] == 1, cache
    assert cache["health"]["services_total"] == 2
    assert cache["services"]["ok"]["online"] is True
    assert cache["services"]["fail"]["online"] is False
    assert _probes_cfg() == _probes_cfg()  # idempotente / nao crasha
    print("self-test OK")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    if len(sys.argv) > 1 and sys.argv[1] in ("--self-test", "-t"):
        _self_test()
    else:
        sys.exit(main(sys.argv[1:]))
