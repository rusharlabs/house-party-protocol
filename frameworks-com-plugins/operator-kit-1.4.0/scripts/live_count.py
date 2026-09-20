#!/usr/bin/env python3
"""
live_count (Operator Kit) — re-deriva contagens/métricas AO VIVO (LC-1) de um sources.yaml.

Materializa em código a skill `live-source-prover`: em vez de repetir um número
stale de doc/memória, roda o comando canônico de cada métrica e imprime o valor
rotulado 'live @ HH:MM'. Anti-alucinação: se não há comando, diz 'não verificado',
nunca inventa.

sources.yaml (ver skills/live-source-prover/sources.example.yaml) tem seções
domínio -> { chave: "comando shell" }. live_count roda uma seção (default 'contagens').

CLI:
  live_count.py [--sources <path>] [--section contagens] [--json]
  live_count.py --key agentes            # só uma chave
Resolução do sources.yaml: --sources > profile paths.sources_yaml > <root>/sources.yaml.
exit 0 sempre. stdlib + PyYAML. --self-test em tmp (sem rede).
v1.0.0 — 2026-06-19 (Operator Kit · Tier 2)
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import yaml
except Exception:  # noqa: BLE001
    yaml = None  # type: ignore[assignment]
try:
    from _lib.profile_loader import load_profile, get, profile_path
except Exception:  # noqa: BLE001
    load_profile = None  # type: ignore[assignment]

    def get(_p, _k, default=None):  # type: ignore[misc]
        return default

    def profile_path(_s=None):  # type: ignore[misc]
        return None

_BRT = timezone(timedelta(hours=-3))


def _root() -> Path:
    if load_profile is not None:
        p = profile_path()
        if p is not None:
            d = p.parent
            for cand in (d, *d.parents):
                if (cand / ".git").exists():
                    return cand
            return d
    return Path.cwd().resolve()


def _resolve_sources(root: Path, argv) -> Path | None:
    if "--sources" in argv:
        i = argv.index("--sources")
        if i + 1 < len(argv):
            return Path(argv[i + 1])
    sp = get(load_profile() if load_profile else {}, "paths.sources_yaml", "")
    if sp:
        return root / sp
    cand = root / "sources.yaml"
    return cand if cand.exists() else None


def _run(cmd: str, root: Path, timeout: int = 15) -> tuple[bool, str]:
    try:
        r = subprocess.run(cmd, shell=True, cwd=str(root),  # noqa: S602 — comando do sources.yaml (confiável)
                          capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or r.stderr or "").strip().splitlines()
        return (r.returncode == 0, (out[-1] if out else "").strip()[:80])
    except Exception as e:  # noqa: BLE001
        return (False, f"erro: {e}")


def count_section(sources: dict, section: str, root: Path, only_key: str | None = None) -> dict:
    block = sources.get(section) if isinstance(sources, dict) else None
    results: dict = {}
    if not isinstance(block, dict):
        return results
    for key, cmd in block.items():
        if only_key and key != only_key:
            continue
        if not isinstance(cmd, str) or not cmd.strip():
            results[key] = {"ok": False, "value": "não verificado (sem comando)"}
            continue
        ok, val = _run(cmd, root)
        results[key] = {"ok": ok, "value": val}
    return results


def main(argv) -> int:
    root = _root()
    if yaml is None:
        print("live_count: PyYAML ausente", file=sys.stderr)
        return 0
    src = _resolve_sources(root, argv)
    if src is None or not src.exists():
        print("live_count: sources.yaml não encontrado (use --sources ou defina paths.sources_yaml). "
              "Modelo: skills/live-source-prover/sources.example.yaml", file=sys.stderr)
        return 0
    try:
        data = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        print(f"live_count: sources.yaml inválido: {e}", file=sys.stderr)
        return 0
    section = argv[argv.index("--section") + 1] if "--section" in argv and argv.index("--section") + 1 < len(argv) else "contagens"
    only = argv[argv.index("--key") + 1] if "--key" in argv and argv.index("--key") + 1 < len(argv) else None
    res = count_section(data, section, root, only)
    ts = datetime.now(_BRT).strftime("%Y-%m-%d %H:%M BRT")
    if "--json" in argv:
        print(json.dumps({"section": section, "ts": ts, "results": res}, ensure_ascii=False, indent=2))
    else:
        print(f"📡 live @ {ts} · seção '{section}' · fonte {src.name}")
        if not res:
            print(f"  (seção '{section}' ausente/vazia no sources.yaml)")
        for k, v in res.items():
            mark = "✓" if v["ok"] else "✗"
            print(f"  [{mark}] {k} = {v['value']}")
    return 0


def _self_test() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "sources.yaml").write_text(
            # Why: o fixture usa o interprete vivo (`python` a seco nao existe no macOS), num escalar
            # YAML de aspas simples (barra invertida de caminho Windows nao vira escape) e com o
            # caminho entre aspas (um .venv em pasta com espaco quebrava o comando em dois).
            f"contagens:\n  dois: '\"{sys.executable.replace(chr(92), '/')}\" -c \"print(1+1)\"'\n  vazio: \"\"\n",
            encoding="utf-8",
        )
        data = yaml.safe_load((root / "sources.yaml").read_text(encoding="utf-8"))
        res = count_section(data, "contagens", root)
        assert res["dois"]["ok"] and res["dois"]["value"] == "2", res
        assert res["vazio"]["ok"] is False and "não verificado" in res["vazio"]["value"], res
        assert count_section(data, "inexistente", root) == {}
        only = count_section(data, "contagens", root, only_key="dois")
        assert set(only.keys()) == {"dois"}, only
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
