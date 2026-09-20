#!/usr/bin/env python3
"""
drift_check (Operator Kit) — confronta INTENÇÃO (doc) x REALIDADE (sondas).

Materializa LC-1 (auditar a fonte AO VIVO) e feedback_plans_lag_reality no nível
de runtime: um doc DIZ que algo está no ar / implementado / por-design — esta
ferramenta SONDA a realidade e rotula cada afirmação. Toda sonda compara o que
o doc ESPERA com o que de fato acontece:

    bug          = o doc espera funcionando, mas a sonda falhou (drift real)
    by-design    = o doc e a realidade concordam (ok — intencional)
    aspiracional = o doc descreve algo NÃO esperado funcionar ainda (espera=False)
                   e a realidade confirma que não funciona (sem drift; é roadmap)

Cada sonda: {nome, tipo, alvo, espera}
    tipo cmd   -> roda o comando (subprocess); real = (exit code 0)
    tipo http  -> GET via urllib.request; real = (status 200)   [NUNCA curl/wget]
    tipo glob  -> arquivo/pattern existe no disco; real = (achou algo)
    espera     -> bool: o doc afirma que ISSO deve estar verdadeiro? (default True)

Sondas vêm de um YAML (--sondas arquivo.yaml) ou inline (--sonda nome=...).

Uso:
    python drift_check.py doc.md --sondas sondas.yaml
    python drift_check.py doc.md --sonda "health=http:http://127.0.0.1:8080/health"
    python drift_check.py doc.md --sonda "engine=cmd:python -c pass" --json
    python drift_check.py doc.md --sonda "cfg=glob:core/paths.py:espera=true"
    python drift_check.py --self-test

Formato inline:  nome=TIPO:ALVO[:espera=true|false]
    health=http:http://127.0.0.1:8080/health
    suite=cmd:python -m pytest -q:espera=true
    legado=glob:old/removido.py:espera=false

YAML (--sondas):
    sondas:
      - { nome: health, tipo: http, alvo: "http://127.0.0.1:8080/health", espera: true }
      - { nome: paths,  tipo: glob, alvo: "core/paths.py",                espera: true }

Exit: 0 = rodou (independe de haver drift) · 2 = uso inválido.
stdlib + PyYAML (só p/ --sondas). Cross-platform. HTTP por urllib (nunca curl/wget).

v1.0.0 — 2026-06-19 (Operator Kit · Tier 1 · materializa LC-1 + plans_lag_reality)
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# loader compartilhado do kit (.../operator-kit/_lib/profile_loader.py)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from _lib.profile_loader import load_profile, get  # noqa: F401 (disponível p/ extensão)
except Exception:  # noqa: BLE001 — degrade seguro
    load_profile = None  # type: ignore[assignment]
    get = None  # type: ignore[assignment]

try:
    import yaml  # PyYAML — só necessário p/ --sondas YAML
except Exception:  # noqa: BLE001
    yaml = None  # type: ignore[assignment]

_TIPOS = ("cmd", "http", "glob")


# ── execução de sondas ──────────────────────────────────────────────────────

def probe_cmd(alvo: str, timeout: int = 60) -> dict:
    """Roda comando shell. real=True se exit 0. Nunca crasha."""
    try:
        r = subprocess.run(alvo, shell=True, capture_output=True, text=True, timeout=timeout)
        tail = ((r.stdout or "") + (r.stderr or "")).strip()[-200:]
        return {"real": r.returncode == 0, "detalhe": f"exit {r.returncode}", "tail": tail}
    except subprocess.TimeoutExpired:
        return {"real": False, "detalhe": f"timeout {timeout}s", "tail": ""}
    except Exception as e:  # noqa: BLE001
        return {"real": False, "detalhe": f"erro: {e}", "tail": ""}


def probe_http(alvo: str, timeout: int = 10) -> dict:
    """GET via urllib. real=True se status 200. NUNCA usa curl/wget. Nunca crasha."""
    req = urllib.request.Request(alvo, method="GET", headers={"User-Agent": "operator-kit-drift_check/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (URL controlada pelo operador)
            status = getattr(resp, "status", None) or resp.getcode()
            return {"real": status == 200, "detalhe": f"HTTP {status}", "tail": ""}
    except urllib.error.HTTPError as e:
        return {"real": e.code == 200, "detalhe": f"HTTP {e.code}", "tail": ""}
    except Exception as e:  # noqa: BLE001 — conexão recusada, DNS, timeout...
        return {"real": False, "detalhe": f"sem resposta: {type(e).__name__}", "tail": ""}


def probe_glob(alvo: str, repo_root: Path | None = None) -> dict:
    """Arquivo/pattern existe? real=True se achar algo. Nunca crasha."""
    root = repo_root or Path.cwd()
    try:
        p = Path(alvo)
        # caminho direto (abs ou relativo ao repo)
        if p.is_absolute() and p.exists():
            return {"real": True, "detalhe": "existe (abs)", "tail": str(p)}
        if (root / p).exists():
            return {"real": True, "detalhe": "existe", "tail": str(root / p)}
        # glob (wildcards)
        if any(ch in alvo for ch in "*?[]"):
            hits = list(root.glob(alvo))
            if hits:
                return {"real": True, "detalhe": f"glob {len(hits)} match", "tail": str(hits[0])}
        return {"real": False, "detalhe": "não existe", "tail": ""}
    except (OSError, ValueError) as e:
        return {"real": False, "detalhe": f"erro: {e}", "tail": ""}


def run_probe(sonda: dict, repo_root: Path | None = None) -> dict:
    """Executa uma sonda e rotula bug/by-design/aspiracional."""
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
        res = {"real": False, "detalhe": f"tipo inválido: {tipo!r}", "tail": ""}

    rotulo = rotular(espera, res["real"])
    return {
        "nome": nome, "tipo": tipo, "alvo": alvo, "espera": espera,
        "real": res["real"], "rotulo": rotulo,
        "detalhe": res["detalhe"], "tail": res.get("tail", ""),
    }


def rotular(espera: bool, real: bool) -> str:
    """
    espera (doc afirma funcionar?) x real (sonda confirmou?):
        espera=True,  real=True   -> by-design   (doc bate com realidade)
        espera=True,  real=False  -> bug         (doc mente: prometeu e não tem)
        espera=False, real=False  -> aspiracional (doc descreve roadmap; ok não ter)
        espera=False, real=True   -> by-design   (existe e não era exigido; sem drift)
    """
    if espera and real:
        return "by-design"
    if espera and not real:
        return "bug"
    if not espera and not real:
        return "aspiracional"
    return "by-design"  # not espera and real


# ── parsing de sondas ───────────────────────────────────────────────────────

def parse_inline(spec: str) -> dict:
    """
    'nome=TIPO:ALVO[:espera=true|false]' -> dict sonda.
    Levanta ValueError se malformado (uso inválido -> exit 2 no main).
    """
    if "=" not in spec:
        raise ValueError(f"sonda inline sem '=': {spec!r}")
    nome, rest = spec.split("=", 1)
    if ":" not in rest:
        raise ValueError(f"sonda inline sem TIPO:ALVO: {spec!r}")
    tipo, alvo = rest.split(":", 1)
    tipo = tipo.strip().lower()
    espera = True
    # sufixo opcional ':espera=true|false' (só se o alvo não for http://)
    low = alvo.lower()
    marker = ":espera="
    idx = low.rfind(marker)
    if idx != -1:
        val = alvo[idx + len(marker):].strip().lower()
        if val in ("true", "false", "1", "0", "sim", "nao", "não"):
            espera = val in ("true", "1", "sim")
            alvo = alvo[:idx]
    if tipo not in _TIPOS:
        raise ValueError(f"tipo inválido {tipo!r} em {spec!r} (use {_TIPOS})")
    return {"nome": nome.strip(), "tipo": tipo, "alvo": alvo.strip(), "espera": espera}


def load_sondas_yaml(path: Path) -> list[dict]:
    """Lê sondas de um YAML. [] se PyYAML ausente ou arquivo ilegível."""
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


# ── orquestração ────────────────────────────────────────────────────────────

def drift_check(doc_path: Path | None, sondas: list[dict],
                repo_root: Path | None = None) -> dict:
    """Roda todas as sondas e agrega o rótulo de drift."""
    rows = [run_probe(s, repo_root) for s in sondas]
    resumo = {"bug": 0, "by-design": 0, "aspiracional": 0}
    for r in rows:
        resumo[r["rotulo"]] = resumo.get(r["rotulo"], 0) + 1
    return {
        "doc": str(doc_path) if doc_path else None,
        "total": len(rows),
        "drift": resumo["bug"] > 0,
        "resumo": resumo,
        "sondas": rows,
    }


def render_markdown(result: dict) -> str:
    out: list[str] = []
    titulo = Path(result["doc"]).name if result.get("doc") else "(sem doc)"
    out.append(f"# Drift check — {titulo}")
    out.append("")
    r = result["resumo"]
    veredito = "DRIFT (há bug)" if result["drift"] else "sem drift"
    out.append(f"Sondas: **{result['total']}** · {veredito} · "
               f"bug {r.get('bug', 0)} · by-design {r.get('by-design', 0)} · "
               f"aspiracional {r.get('aspiracional', 0)}")
    out.append("")
    if not result["sondas"]:
        out.append("_Nenhuma sonda fornecida (use --sondas ou --sonda)._")
        return "\n".join(out)
    out.append("| Rótulo | Sonda | Tipo | Espera | Real | Detalhe |")
    out.append("|--------|-------|------|:------:|:----:|---------|")
    for s in result["sondas"]:
        det = (s.get("detalhe") or "").replace("|", "\\|")
        if len(det) > 40:
            det = det[:37] + "..."
        out.append(
            f"| {s['rotulo']} | {s['nome']} | {s['tipo']} | "
            f"{'sim' if s['espera'] else 'não'} | {'sim' if s['real'] else 'não'} | {det} |"
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
            print(f"drift_check: --sondas não encontrado: {sondas_yaml}", file=sys.stderr)
            return 2
        carregadas = load_sondas_yaml(sondas_yaml)
        if not carregadas and yaml is None:
            print("drift_check: PyYAML ausente — --sondas YAML indisponível", file=sys.stderr)
            return 2
        sondas.extend(carregadas)

    if not sondas:
        print('uso: drift_check.py [doc.md] --sondas <yaml> | --sonda "nome=TIPO:ALVO[:espera=bool]" [...]',
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


# ── self-test (sem rede; só cmd + glob locais) ──────────────────────────────

def _self_test() -> None:
    import tempfile

    # rotulagem (matriz espera x real)
    assert rotular(True, True) == "by-design"
    assert rotular(True, False) == "bug"
    assert rotular(False, False) == "aspiracional"
    assert rotular(False, True) == "by-design"

    # parse inline
    s = parse_inline("health=http:http://127.0.0.1:8080/health")
    assert s["tipo"] == "http" and s["alvo"] == "http://127.0.0.1:8080/health" and s["espera"] is True
    s2 = parse_inline("legado=glob:old/x.py:espera=false")
    assert s2["tipo"] == "glob" and s2["alvo"] == "old/x.py" and s2["espera"] is False
    s3 = parse_inline("suite=cmd:python -m pytest -q:espera=true")
    assert s3["tipo"] == "cmd" and s3["alvo"] == "python -m pytest -q" and s3["espera"] is True
    try:
        parse_inline("malformado-sem-igual")
        raise AssertionError("deveria levantar ValueError")
    except ValueError:
        pass

    # sondas cmd locais (sem rede)
    ok = run_probe({"nome": "exit0", "tipo": "cmd", "alvo": f'"{sys.executable}" -c "import sys; sys.exit(0)"', "espera": True})
    assert ok["real"] is True and ok["rotulo"] == "by-design", "cmd exit0 esperado = by-design"

    bug = run_probe({"nome": "exit1", "tipo": "cmd", "alvo": f'"{sys.executable}" -c "import sys; sys.exit(1)"', "espera": True})
    assert bug["real"] is False and bug["rotulo"] == "bug", "cmd exit1 esperado-true = bug"

    asp = run_probe({"nome": "exit1-asp", "tipo": "cmd", "alvo": f'"{sys.executable}" -c "import sys; sys.exit(1)"', "espera": False})
    assert asp["real"] is False and asp["rotulo"] == "aspiracional", "falha não-esperada = aspiracional"

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "existe.txt").write_text("x", encoding="utf-8")

        g_ok = run_probe({"nome": "g1", "tipo": "glob", "alvo": "existe.txt", "espera": True}, repo_root=root)
        assert g_ok["real"] is True and g_ok["rotulo"] == "by-design", "glob existente = by-design"

        g_bug = run_probe({"nome": "g2", "tipo": "glob", "alvo": "nao_existe.txt", "espera": True}, repo_root=root)
        assert g_bug["real"] is False and g_bug["rotulo"] == "bug", "glob ausente esperado = bug"

        g_asp = run_probe({"nome": "g3", "tipo": "glob", "alvo": "removido.py", "espera": False}, repo_root=root)
        assert g_asp["rotulo"] == "aspiracional", "glob ausente não-esperado = aspiracional"

        # tipo inválido não crasha, vira bug se esperado
        inv = run_probe({"nome": "bad", "tipo": "xyz", "alvo": "z", "espera": True})
        assert inv["real"] is False and inv["rotulo"] == "bug", "tipo inválido esperado = bug"

        # agregação + render
        sondas = [
            {"nome": "g1", "tipo": "glob", "alvo": "existe.txt", "espera": True},
            {"nome": "g2", "tipo": "glob", "alvo": "nao_existe.txt", "espera": True},
        ]
        res = drift_check(None, sondas, repo_root=root)
        assert res["total"] == 2
        assert res["resumo"]["by-design"] == 1 and res["resumo"]["bug"] == 1
        assert res["drift"] is True
        md = render_markdown(res)
        assert "Drift check" in md and "| Rótulo |" in md

        # sem sondas: render avisa, não crasha
        vazio = drift_check(None, [], repo_root=root)
        assert vazio["total"] == 0 and vazio["drift"] is False
        assert "Nenhuma sonda" in render_markdown(vazio)

    print("self-test OK")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
