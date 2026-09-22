#!/usr/bin/env python3
"""
drift_check (Operator Kit) -- compares INTENTION (doc) vs REALITY (probes).

Materializes LC-1 (audit the source LIVE) and feedback_plans_lag_reality at
runtime level: a doc SAYS something is live / implemented / by-design -- this
tool PROBES reality and labels each claim. Every probe compares what the
doc EXPECTS against what actually happens:

    bug          = the doc expects it working, but the probe failed (real drift)
    by-design    = the doc and reality agree (ok -- intentional)
    aspiracional = the doc describes something NOT expected to work yet (espera=False)
                   and reality confirms it doesn't work (no drift; it's a roadmap)

Each probe: {nome, tipo, alvo, espera}
    tipo cmd   -> runs the command (subprocess); real = (exit code 0)
    tipo http  -> GET via urllib.request; real = (status 200)   [NEVER curl/wget]
    tipo glob  -> file/pattern exists on disk; real = (found something)
    espera     -> bool: does the doc claim this should be true? (default True)

Probes come from a YAML (--sondas file.yaml) or inline (--sonda nome=...).

Usage:
    python drift_check.py doc.md --sondas sondas.yaml
    python drift_check.py doc.md --sonda "health=http:http://127.0.0.1:8080/health"
    python drift_check.py doc.md --sonda "engine=cmd:python -c pass" --json
    python drift_check.py doc.md --sonda "cfg=glob:core/paths.py:espera=true"
    python drift_check.py --self-test

Inline format:  nome=TIPO:ALVO[:espera=true|false]
    health=http:http://127.0.0.1:8080/health
    suite=cmd:python -m pytest -q:espera=true
    legado=glob:old/removido.py:espera=false

YAML (--sondas):
    sondas:
      - { nome: health, tipo: http, alvo: "http://127.0.0.1:8080/health", espera: true }
      - { nome: paths,  tipo: glob, alvo: "core/paths.py",                espera: true }

Exit: 0 = ran (regardless of drift) -- 2 = invalid usage.
stdlib + PyYAML (only for --sondas). Cross-platform. HTTP via urllib (never curl/wget).

v1.0.0 -- 2026-06-19 (Operator Kit -- Tier 1 -- materializes LC-1 + plans_lag_reality)
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# shared kit loader (.../operator-kit/_lib/profile_loader.py)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from _lib.profile_loader import load_profile, get  # noqa: F401 (available for extension)
except Exception:  # noqa: BLE001 -- safe degrade
    load_profile = None  # type: ignore[assignment]
    get = None  # type: ignore[assignment]

try:
    import yaml  # PyYAML -- only needed for --sondas YAML
except Exception:  # noqa: BLE001
    yaml = None  # type: ignore[assignment]

_TYPES = ("cmd", "http", "glob")


# ── probe execution ─────────────────────────────────────────────────────────

def probe_cmd(alvo: str, timeout: int = 60) -> dict:
    """Runs a shell command. real=True if exit 0. Never crashes."""
    try:
        r = subprocess.run(alvo, shell=True, capture_output=True, text=True, timeout=timeout)
        tail = ((r.stdout or "") + (r.stderr or "")).strip()[-200:]
        return {"real": r.returncode == 0, "detalhe": f"exit {r.returncode}", "tail": tail}
    except subprocess.TimeoutExpired:
        return {"real": False, "detalhe": f"timeout {timeout}s", "tail": ""}
    except Exception as e:  # noqa: BLE001
        return {"real": False, "detalhe": f"error: {e}", "tail": ""}


def probe_http(alvo: str, timeout: int = 10) -> dict:
    """GET via urllib. real=True if status 200. NEVER uses curl/wget. Never crashes."""
    req = urllib.request.Request(alvo, method="GET", headers={"User-Agent": "operator-kit-drift_check/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (URL controlled by the operator)
            status = getattr(resp, "status", None) or resp.getcode()
            return {"real": status == 200, "detalhe": f"HTTP {status}", "tail": ""}
    except urllib.error.HTTPError as e:
        return {"real": e.code == 200, "detalhe": f"HTTP {e.code}", "tail": ""}
    except Exception as e:  # noqa: BLE001 -- connection refused, DNS, timeout...
        return {"real": False, "detalhe": f"no answer: {type(e).__name__}", "tail": ""}


def probe_glob(alvo: str, repo_root: Path | None = None) -> dict:
    """File/pattern exists? real=True if it finds something. Never crashes."""
    root = repo_root or Path.cwd()
    try:
        p = Path(alvo)
        # direct path (abs or relative to the repo)
        if p.is_absolute() and p.exists():
            return {"real": True, "detalhe": "exists (abs)", "tail": str(p)}
        if (root / p).exists():
            return {"real": True, "detalhe": "exists", "tail": str(root / p)}
        # glob (wildcards)
        if any(ch in alvo for ch in "*?[]"):
            hits = list(root.glob(alvo))
            if hits:
                return {"real": True, "detalhe": f"glob {len(hits)} match", "tail": str(hits[0])}
        return {"real": False, "detalhe": "does not exist", "tail": ""}
    except (OSError, ValueError) as e:
        return {"real": False, "detalhe": f"error: {e}", "tail": ""}


def run_probe(sonda: dict, repo_root: Path | None = None) -> dict:
    """Runs a probe and labels it bug/by-design/aspiracional."""
    nome = str(sonda.get("nome", "sem-nome"))
    tipo = str(sonda.get("tipo", "")).lower()
    alvo = str(sonda.get("alvo", ""))
    espera = bool(sonda.get("espera", True))

    if tipo == "cmd":
        res = probe_cmd(alvo)
    elif tipo == "http":
        res = probe_http(alvo)
    elif tipo == "glob":
        res = probe_glob(alvo, repo_root)
    else:
        res = {"real": False, "detalhe": f"invalid type: {tipo!r}", "tail": ""}

    label = label_for(espera, res["real"])
    return {
        "nome": nome, "tipo": tipo, "alvo": alvo, "espera": espera,
        "real": res["real"], "rotulo": label,
        "detalhe": res["detalhe"], "tail": res.get("tail", ""),
    }


def label_for(espera: bool, real: bool) -> str:
    """
    espera (does the doc claim it works?) x real (did the probe confirm it?):
        espera=True,  real=True   -> by-design   (doc matches reality)
        espera=True,  real=False  -> bug         (doc lies: promised and doesn't have it)
        espera=False, real=False  -> aspiracional (doc describes a roadmap; ok not to have it)
        espera=False, real=True   -> by-design   (exists and wasn't required; no drift)
    """
    if espera and real:
        return "by-design"
    if espera and not real:
        return "bug"
    if not espera and not real:
        return "aspiracional"
    return "by-design"  # not espera and real


# ── probe parsing ────────────────────────────────────────────────────────────

def parse_inline(spec: str) -> dict:
    """
    'nome=TIPO:ALVO[:espera=true|false]' -> probe dict.
    Raises ValueError if malformed (invalid usage -> exit 2 in main).
    """
    if "=" not in spec:
        raise ValueError(f"inline probe without '=': {spec!r}")
    nome, rest = spec.split("=", 1)
    if ":" not in rest:
        raise ValueError(f"inline probe without TYPE:TARGET: {spec!r}")
    tipo, alvo = rest.split(":", 1)
    tipo = tipo.strip().lower()
    espera = True
    # optional suffix ':espera=true|false' (only if the target isn't http://)
    low = alvo.lower()
    marker = ":espera="
    idx = low.rfind(marker)
    if idx != -1:
        val = alvo[idx + len(marker):].strip().lower()
        if val in ("true", "false", "1", "0", "yes", "no"):
            espera = val in ("true", "1", "yes")
            alvo = alvo[:idx]
    if tipo not in _TYPES:
        raise ValueError(f"invalid type {tipo!r} in {spec!r} (use {_TYPES})")
    return {"nome": nome.strip(), "tipo": tipo, "alvo": alvo.strip(), "espera": espera}


def load_sondas_yaml(path: Path) -> list[dict]:
    """Reads probes from a YAML. [] if PyYAML is missing or the file is unreadable."""
    if yaml is None:
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    if isinstance(data, dict):
        data = data.get("sondas", [])
    if not isinstance(data, list):
        return []
    out = []
    for s in data:
        if isinstance(s, dict) and s.get("tipo") and s.get("alvo"):
            out.append({
                "nome": s.get("nome", s.get("alvo")),
                "tipo": str(s["tipo"]).lower(),
                "alvo": str(s["alvo"]),
                "espera": bool(s.get("espera", True)),
            })
    return out


# ── orchestration ────────────────────────────────────────────────────────────

def drift_check(doc_path: Path | None, sondas: list[dict],
                repo_root: Path | None = None) -> dict:
    """Runs all probes and aggregates the drift label."""
    rows = [run_probe(s, repo_root) for s in sondas]
    summary = {"bug": 0, "by-design": 0, "aspiracional": 0}
    for r in rows:
        summary[r["rotulo"]] = summary.get(r["rotulo"], 0) + 1
    return {
        "doc": str(doc_path) if doc_path else None,
        "total": len(rows),
        "drift": summary["bug"] > 0,
        "resumo": summary,
        "sondas": rows,
    }


def render_markdown(result: dict) -> str:
    out: list[str] = []
    title = Path(result["doc"]).name if result.get("doc") else "(sem doc)"
    out.append(f"# Drift check — {title}")
    out.append("")
    r = result["resumo"]
    verdict = "DRIFT (bug present)" if result["drift"] else "no drift"
    out.append(f"Probes: **{result['total']}** · {verdict} · "
               f"bug {r.get('bug', 0)} · by-design {r.get('by-design', 0)} · "
               f"aspiracional {r.get('aspiracional', 0)}")
    out.append("")
    if not result["sondas"]:
        out.append("_No probe given (use --sondas or --sonda)._")
        return "\n".join(out)
    out.append("| Label | Probe | Type | Expects | Real | Detail |")
    out.append("|-------|-------|------|:-------:|:----:|--------|")
    for s in result["sondas"]:
        det = (s.get("detalhe") or "").replace("|", "\\|")
        if len(det) > 40:
            det = det[:37] + "..."
        out.append(
            f"| {s['rotulo']} | {s['nome']} | {s['tipo']} | "
            f"{'yes' if s['espera'] else 'no'} | {'yes' if s['real'] else 'no'} | {det} |"
        )
    return "\n".join(out)


def main(argv) -> int:
    if argv and argv[0] in ("--self-test", "-t"):
        _self_test()
        return 0

    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]

    sondas: list[dict] = []
    sondas_yaml: Path | None = None
    repo_root: Path | None = None
    doc_path: Path | None = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--sondas" and i + 1 < len(argv):
            sondas_yaml = Path(argv[i + 1]); i += 2; continue
        if a == "--sonda" and i + 1 < len(argv):
            try:
                sondas.append(parse_inline(argv[i + 1]))
            except ValueError as e:
                print(f"drift_check: {e}", file=sys.stderr)
                return 2
            i += 2; continue
        if a == "--repo" and i + 1 < len(argv):
            repo_root = Path(argv[i + 1]); i += 2; continue
        if not a.startswith("--") and doc_path is None:
            doc_path = Path(a); i += 1; continue
        i += 1

    if sondas_yaml is not None:
        if not sondas_yaml.exists():
            print(f"drift_check: --sondas not found: {sondas_yaml}", file=sys.stderr)
            return 2
        loaded = load_sondas_yaml(sondas_yaml)
        if not loaded and yaml is None:
            print("drift_check: PyYAML missing — --sondas YAML unavailable", file=sys.stderr)
            return 2
        sondas.extend(loaded)

    if not sondas:
        print('usage: drift_check.py [doc.md] --sondas <yaml> | --sonda "name=TYPE:TARGET[:espera=bool]" [...]',
              file=sys.stderr)
        return 2

    if repo_root is None and doc_path is not None and doc_path.exists():
        repo_root = _detect_repo_root(doc_path)

    result = drift_check(doc_path, sondas, repo_root)

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(result))
    return 0


def _detect_repo_root(p: Path) -> Path:
    base = p.resolve().parent
    for d in (base, *base.parents):
        if (d / ".git").exists():
            return d
    return Path.cwd()


# ── self-test (no network; only local cmd + glob) ───────────────────────────

def _self_test() -> None:
    import tempfile

    # labeling (espera x real matrix)
    assert label_for(True, True) == "by-design"
    assert label_for(True, False) == "bug"
    assert label_for(False, False) == "aspiracional"
    assert label_for(False, True) == "by-design"

    # inline parse
    s = parse_inline("health=http:http://127.0.0.1:8080/health")
    assert s["tipo"] == "http" and s["alvo"] == "http://127.0.0.1:8080/health" and s["espera"] is True
    s2 = parse_inline("legado=glob:old/x.py:espera=false")
    assert s2["tipo"] == "glob" and s2["alvo"] == "old/x.py" and s2["espera"] is False
    s3 = parse_inline("suite=cmd:python -m pytest -q:espera=true")
    assert s3["tipo"] == "cmd" and s3["alvo"] == "python -m pytest -q" and s3["espera"] is True
    try:
        parse_inline("malformado-sem-igual")
        raise AssertionError("should raise ValueError")
    except ValueError:
        pass

    # local cmd probes (no network)
    ok = run_probe({"nome": "exit0", "tipo": "cmd", "alvo": f'"{sys.executable}" -c "import sys; sys.exit(0)"', "espera": True})
    assert ok["real"] is True and ok["rotulo"] == "by-design", "cmd exit0 expected = by-design"

    bug = run_probe({"nome": "exit1", "tipo": "cmd", "alvo": f'"{sys.executable}" -c "import sys; sys.exit(1)"', "espera": True})
    assert bug["real"] is False and bug["rotulo"] == "bug", "cmd exit1 expected-true = bug"

    asp = run_probe({"nome": "exit1-asp", "tipo": "cmd", "alvo": f'"{sys.executable}" -c "import sys; sys.exit(1)"', "espera": False})
    assert asp["real"] is False and asp["rotulo"] == "aspiracional", "unexpected-by-design failure = aspiracional"

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "present.txt").write_text("x", encoding="utf-8")

        g_ok = run_probe({"nome": "g1", "tipo": "glob", "alvo": "present.txt", "espera": True}, repo_root=root)
        assert g_ok["real"] is True and g_ok["rotulo"] == "by-design", "existing glob = by-design"

        g_bug = run_probe({"nome": "g2", "tipo": "glob", "alvo": "absent.txt", "espera": True}, repo_root=root)
        assert g_bug["real"] is False and g_bug["rotulo"] == "bug", "missing glob that was expected = bug"

        g_asp = run_probe({"nome": "g3", "tipo": "glob", "alvo": "removed.py", "espera": False}, repo_root=root)
        assert g_asp["rotulo"] == "aspiracional", "missing glob that was not expected = aspiracional"

        # invalid type doesn't crash, becomes bug if it was expected
        inv = run_probe({"nome": "bad", "tipo": "xyz", "alvo": "z", "espera": True})
        assert inv["real"] is False and inv["rotulo"] == "bug", "invalid type that was expected = bug"

        # aggregation + render
        sondas = [
            {"nome": "g1", "tipo": "glob", "alvo": "present.txt", "espera": True},
            {"nome": "g2", "tipo": "glob", "alvo": "absent.txt", "espera": True},
        ]
        res = drift_check(None, sondas, repo_root=root)
        assert res["total"] == 2
        assert res["resumo"]["by-design"] == 1 and res["resumo"]["bug"] == 1
        assert res["drift"] is True
        md = render_markdown(res)
        assert "Drift check" in md and "| Label |" in md

        # no probes: render warns, doesn't crash
        empty = drift_check(None, [], repo_root=root)
        assert empty["total"] == 0 and empty["drift"] is False
        assert "No probe" in render_markdown(empty)

    print("self-test OK")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
