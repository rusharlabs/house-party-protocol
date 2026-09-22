#!/usr/bin/env python3
"""
status_now (Operator Kit) — responde "onde estamos?" num template fixo.

Le `paths.state_ssot` do operator-profile.yaml e extrai, do markdown do SSoT:
  - ETAPA / FASE   (linha que comeca com '#', '## Fase', 'Etapa:', 'Fase:'...)
  - PROGRESSO %    (primeiro 'NN%' encontrado no doc)
  - BLOQUEIOS      (contagem de pendencias abertas '- [ ]')
  - PROXIMA ACAO   (texto da 1a pendencia aberta '- [ ]')

REGRA INQUEBRAVEL (AGENT-INTEGRITY / LC-1): campo nao-encontrado vira '--' com
uma nota explicita — NUNCA inventa numero, etapa ou proxima acao. Sem profile
ou sem SSoT, degrada para um template honesto que aponta o que falta configurar.

Uso:
    python status_now.py            # imprime o template "onde estamos?"
    python status_now.py --json     # mesma info, JSON estavel p/ consumo programatico
    python status_now.py --self-test

Exit: 0 sempre (relatorio de status nunca e um gate). stdlib + PyYAML (via loader).

v1.0.0 — 2026-06-19 (Operator Kit · Tier 1)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# importa o loader compartilhado do kit (.../operator-kit/_lib/profile_loader.py)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from _lib.profile_loader import load_profile, get, profile_path
except Exception:  # noqa: BLE001 — sem loader, degrade para defaults seguros (NUNCA crasha)
    load_profile = None  # type: ignore[assignment]
    get = None  # type: ignore[assignment]
    profile_path = None  # type: ignore[assignment]

# marcador honesto para campo nao-encontrado (nunca inventar)
_NA = "--"

# regex de extracao
_RE_PCT = re.compile(r"(\d{1,3})\s*%")
_RE_OPEN_TODO = re.compile(r"^\s*[-*]\s+\[\s\]\s+(.*\S)?\s*$")
_RE_DONE_TODO = re.compile(r"^\s*[-*]\s+\[[xX]\]\s")
# rotulos que costumam carregar a etapa/fase atual.
# Captura a frase INTEIRA a partir do rotulo (inclusive a palavra "Fase"/"Etapa"),
# tolerando heading markdown (#) e ':' opcional logo apos o rotulo.
_RE_ETAPA_LABEL = re.compile(
    r"^\s*#{0,6}\s*((?:etapa|fase|stage|phase|sprint|milestone)\b\s*:?\s*.*\S)",
    re.IGNORECASE,
)


def _resolve_ssot_path(profile: dict, base: Path) -> Path | None:
    """Resolve o caminho absoluto do SSoT a partir de paths.state_ssot (relativo a raiz do projeto)."""
    if get is None:
        return None
    rel = get(profile, "paths.state_ssot", None)
    if not rel:
        return None
    # raiz do projeto = pasta que contem o profile, subindo de staging/operator-kit se for o caso
    root = base
    if profile_path is not None:
        p = profile_path()
        if p is not None:
            root = p.resolve().parent
            # se o profile vive em .../staging/operator-kit, a raiz do projeto sobe 2 niveis
            parts = root.parts
            if len(parts) >= 2 and parts[-1] == "operator-kit" and parts[-2] == "staging":
                root = root.parents[1]
            elif parts and parts[-1] == "operator-kit":
                root = root.parent
    cand = (root / rel)
    return cand


def extract_status(text: str) -> dict:
    """Extrai etapa/%/bloqueios/proxima-acao do markdown do SSoT. Campos ausentes => _NA + nota."""
    etapa = _NA
    pct = _NA
    open_todos: list[str] = []
    notas: list[str] = []

    lines = text.splitlines()

    # ETAPA: primeiro rotulo explicito (Etapa:/Fase:/##Fase...) com conteudo; senao 1o heading nao-vazio
    for ln in lines:
        m = _RE_ETAPA_LABEL.match(ln)
        if m and (m.group(1) or "").strip():
            etapa = re.sub(r"\s+", " ", m.group(1).strip())
            break
    if etapa is _NA:
        for ln in lines:
            s = ln.strip()
            if s.startswith("#"):
                h = s.lstrip("#").strip()
                if h:
                    etapa = h
                    break
    if etapa is _NA:
        notas.append("stage not found in the SSoT (no heading/label Fase|Etapa|Stage|Phase)")

    # PROGRESSO %: primeira ocorrencia 'NN%'
    mpct = _RE_PCT.search(text)
    if mpct:
        pct = f"{int(mpct.group(1))}%"
    else:
        notas.append("progress % not found in the SSoT")

    # BLOQUEIOS / PROXIMA ACAO: pendencias abertas '- [ ]'
    for ln in lines:
        m = _RE_OPEN_TODO.match(ln)
        if m:
            open_todos.append((m.group(1) or "(no description)").strip())

    proxima = open_todos[0] if open_todos else _NA
    if not open_todos:
        notas.append("no open '- [ ]' item in the SSoT (next action undefined)")

    return {
        "etapa": etapa,
        "progresso": pct,
        "bloqueios_abertos": len(open_todos),
        "proxima_acao": proxima,
        "todos_abertos": open_todos,
        "notas": notas,
    }


def build_status(start: Path | None = None) -> dict:
    """Monta o status completo: resolve profile -> SSoT -> extrai. Degrada sem crashar."""
    base = Path(start or Path.cwd())
    profile = load_profile() if load_profile is not None else {}
    ssot_rel = get(profile, "paths.state_ssot", None) if get is not None else None
    ssot = _resolve_ssot_path(profile, base) if profile else None

    data = {
        "projeto": (get(profile, "project", _NA) if get is not None else _NA) or _NA,
        "ssot_path": str(ssot) if ssot else _NA,
        "ssot_rel": ssot_rel or _NA,
        "etapa": _NA,
        "progresso": _NA,
        "bloqueios_abertos": _NA,
        "proxima_acao": _NA,
        "todos_abertos": [],
        "notas": [],
    }

    if not profile:
        data["notas"].append("operator-profile.yaml missing (or PyYAML unavailable) — configure paths.state_ssot")
        return data
    if not ssot_rel:
        data["notas"].append("paths.state_ssot not defined in operator-profile.yaml")
        return data
    if ssot is None or not ssot.exists():
        data["notas"].append(f"SSoT not found on disk: {ssot_rel}")
        return data

    try:
        text = ssot.read_text(encoding="utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001 — nunca crasha
        data["notas"].append(f"failed to read the SSoT: {e}")
        return data

    ext = extract_status(text)
    data.update(ext)
    return data


def render_template(data: dict) -> str:
    """Renders the fixed 'where are we?' template."""
    proj = data.get("projeto", _NA)
    etapa = data.get("etapa", _NA)
    pct = data.get("progresso", _NA)
    blq = data.get("bloqueios_abertos", _NA)
    prox = data.get("proxima_acao", _NA)
    ssot = data.get("ssot_rel", _NA)
    notas = data.get("notas", []) or []

    linhas = [
        "+-----------------------------------------------------------+",
        "|  WHERE ARE WE?                                            |",
        "+-----------------------------------------------------------+",
        f"  PROJECT     : {proj}",
        f"  STAGE       : {etapa}",
        f"  PROGRESS    : {pct}",
        f"  BLOCKERS    : {blq} open item(s)" if blq != _NA else f"  BLOCKERS    : {_NA}",
        f"  NEXT ACTION : {prox}",
        f"  SOURCE (SSoT): {ssot}",
    ]
    if notas:
        linhas.append("  ---")
        linhas.append("  NOTES (fields '--' = not found, NOT invented):")
        for n in notas:
            linhas.append(f"    - {n}")
    return "\n".join(linhas)


def _self_test() -> None:
    import tempfile

    # fixture: SSoT com etapa, %, e pendencias
    ssot_text = (
        "# Demo Project\n"
        "## Phase 2 - Pipeline\n"
        "Current progress: 37% complete\n\n"
        "- [x] Initial setup\n"
        "- [ ] Process BATCH-004\n"
        "- [ ] Validate dossiers\n"
    )
    parsed = extract_status(ssot_text)
    assert parsed["etapa"] == "Phase 2 - Pipeline", parsed["etapa"]
    assert parsed["progresso"] == "37%", parsed["progresso"]
    assert parsed["bloqueios_abertos"] == 2, parsed["bloqueios_abertos"]
    assert parsed["proxima_acao"] == "Process BATCH-004", parsed["proxima_acao"]

    # fixture vazia: tudo '--' + notas (NUNCA inventa)
    parsed2 = extract_status("text with nothing structured in it\n")
    assert parsed2["etapa"] == _NA
    assert parsed2["progresso"] == _NA
    assert parsed2["proxima_acao"] == _NA
    assert parsed2["bloqueios_abertos"] == 0
    assert len(parsed2["notas"]) >= 2

    # build_status sem profile (cwd tmp isolado) degrada sem crashar
    with tempfile.TemporaryDirectory() as td:
        import os
        env_bak = os.environ.pop("OPERATOR_PROFILE", None)
        try:
            data = build_status(start=Path(td))
            assert isinstance(data, dict)
            assert "notas" in data
            # render nunca crasha
            out = render_template(data)
            assert "WHERE ARE WE?" in out
        finally:
            if env_bak is not None:
                os.environ["OPERATOR_PROFILE"] = env_bak

    # render de fixture completa contem os valores extraidos
    data_full = {
        "projeto": "demo", "ssot_rel": "x.md", "etapa": "Phase 2",
        "progresso": "37%", "bloqueios_abertos": 2, "proxima_acao": "do X", "notas": [],
    }
    out_full = render_template(data_full)
    assert "Phase 2" in out_full and "37%" in out_full and "do X" in out_full

    print("self-test OK")


def main(argv) -> int:
    if argv and argv[0] in ("--self-test", "-t"):
        _self_test()
        return 0
    data = build_status()
    if "--json" in argv:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        print(render_template(data))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
