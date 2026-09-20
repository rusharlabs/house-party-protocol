#!/usr/bin/env python3
"""
distill_corrections (Operator Kit) — minera session logs e PROPOE regras destiladas.

Generaliza o padrao de minerar sessoes p/ regras destiladas (workflow que ja gerou a
`learned-corrections.md`): lê os ultimos N session logs de `paths.logs_dir`
(default .claude/sessions/), extrai linhas que parecem CORRECOES do operador
(marcadores tipo NUNCA/SEMPRE/na verdade/errado/corrige/pare de), agrupa por
similaridade simples (normalizacao + chave de tokens), e mantem SO as correcoes
que recorrem em >= K sessoes DISTINTAS (distill.limiar_recorrencia, default 3).

Emite candidatas a regra (1 linha + evidencia de quais sessoes) e atualiza um
ledger de REJEITADAS (distill.ledger_rejeitadas) p/ nao re-propor o que ja foi
descartado antes — as chaves que JA estao no ledger sao filtradas das candidatas.

NAO aplica nada. NAO escreve na regra-alvo. So PROPOE (o agente/operador decide).
Honesto por construcao: so agrega o que existe nos logs; nunca inventa correcao.

Uso:
    python distill_corrections.py                 # tabela legivel
    python distill_corrections.py --n 30 --k 4    # janela e limiar custom
    python distill_corrections.py --json          # saida JSON p/ pipeline
    python distill_corrections.py --self-test

Exit: 0 sempre (ferramenta de proposta — nunca quebra o fluxo).
stdlib + PyYAML (so p/ ler o profile). Cross-platform (pathlib).

v1.0.0 — 2026-06-19 (Operator Kit · Tier 2 · generaliza recurring-corrections-to-rules)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# loader compartilhado: .../operator-kit/scripts/ -> parents[1] = operator-kit/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from _lib.profile_loader import load_profile, get, profile_path
except Exception:  # noqa: BLE001 — sem loader, cai p/ defaults seguros
    load_profile = None  # type: ignore[assignment]
    get = None  # type: ignore[assignment]
    profile_path = None  # type: ignore[assignment]

_BRT = timezone(timedelta(hours=-3))

# Defaults seguros se nao houver profile
_DEF_LOGS_DIR = ".claude/sessions/"
_DEF_LEDGER = ".claude/memory/_distill-rejeitadas.md"
_DEF_N = 50
_DEF_K = 3

# Marcadores heuristicos de correcao do operador (case-insensitive).
# Inclui os de feedback/enfase + verbos de correcao explicita.
_MARCADORES = (
    "nunca", "sempre", "na verdade", "errado", "errei", "corrige", "corrigir",
    "corrija", "pare de", "para de", "ja falei", "ja te falei", "toda vez",
    "nao faca", "nao faz", "nao e", "deixa de", "exijo", "odeio",
    "voce errou", "ta errado", "esta errado", "isso nao", "de novo",
)
_MARCADOR_RE = re.compile("|".join(re.escape(m) for m in _MARCADORES), re.IGNORECASE)

# Stopwords pt-BR p/ a chave de agrupamento (reduz ruido na similaridade).
_STOP = {
    "a", "o", "as", "os", "um", "uma", "de", "da", "do", "das", "dos", "e",
    "ou", "que", "para", "pra", "por", "com", "sem", "em", "no", "na", "nos",
    "nas", "se", "ao", "aos", "the", "is", "to", "of", "ja", "voce", "vc",
    "eu", "isso", "isto", "esse", "essa", "este", "esta", "nao", "sim", "me",
    "te", "lhe", "ser", "estar", "foi", "tem", "ter", "fazer", "faz", "feito",
}


def _normalize(text: str) -> str:
    """Minuscula, sem acento, sem pontuacao, espacos colapsados."""
    text = text.lower().strip()
    # remocao de acentos sem dependencia externa (mapa basico pt-BR)
    acentos = str.maketrans(
        "áàâãäéèêëíìîïóòôõöúùûüçñ",
        "aaaaaeeeeiiiiooooouuuucn",
    )
    text = text.translate(acentos)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _key(text: str, ntokens: int = 6) -> str:
    """Chave de agrupamento: top tokens significativos ordenados (similaridade simples)."""
    norm = _normalize(text)
    toks = [t for t in norm.split() if len(t) > 2 and t not in _STOP]
    if not toks:
        return ""
    # ordena alfabeticamente p/ que "X errado" e "errado X" colidam, pega os primeiros
    return " ".join(sorted(set(toks))[:ntokens])


def _strip_log_prefix(line: str) -> str:
    """Remove prefixos comuns de log (timestamp, bullet, '> ', 'Operador:', etc.)."""
    s = line.strip()
    s = re.sub(r"^[-*>#\s]+", "", s)
    s = re.sub(r"^\[?\d{4}-\d{2}-\d{2}[^\]]*\]?\s*", "", s)
    s = re.sub(r"^(max|user|usuario|operador)\s*[:>-]\s*", "", s, flags=re.IGNORECASE)
    return s.strip()


def _is_correction(line: str) -> bool:
    """True se a linha parece uma correcao (tem marcador e e curta o suficiente p/ ser uma instrucao)."""
    if not (3 < len(line) <= 400):
        return False
    return bool(_MARCADOR_RE.search(line))


def _session_files(logs_dir: Path, n: int) -> list[Path]:
    """Os N session logs mais recentes (.md/.jsonl), excluindo ponteiros/indices."""
    if not logs_dir.exists():
        return []
    skip_substr = ("INDEX", "POINTER", "LATEST", "CURRENT", "NEXT", "_archive", "archive")
    files: list[Path] = []
    for p in logs_dir.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".md", ".jsonl", ".txt"):
            continue
        if any(s in p.name for s in skip_substr):
            continue
        files.append(p)
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return files[:n]


def _extract_from_file(path: Path) -> list[str]:
    """Correcoes (texto limpo) achadas num arquivo de sessao."""
    out: list[str] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in raw.splitlines():
        clean = _strip_log_prefix(line)
        if _is_correction(clean):
            out.append(clean)
    return out


def _load_ledger_keys(ledger: Path) -> set[str]:
    """Le as chaves ja rejeitadas (marcadas como '<!-- key: ... -->' no ledger). set() se ausente."""
    keys: set[str] = set()
    if not ledger.exists():
        return keys
    try:
        for line in ledger.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.search(r"<!--\s*key:\s*(.+?)\s*-->", line)
            if m:
                k = m.group(1).strip()
                # ignora o placeholder de documentacao do cabecalho ('... ')
                if k and k != "...":
                    keys.add(k)
    except OSError:
        pass
    return keys


def distill(logs_dir: Path, n: int, k: int, ledger_keys: set[str] | None = None) -> list[dict]:
    """
    Retorna candidatas a regra ordenadas por recorrencia desc.
    Cada item: {key, exemplo, n_sessoes, sessoes:[...], ocorrencias}.
    So entram chaves que recorrem em >= k sessoes DISTINTAS e nao estao no ledger.
    """
    ledger_keys = ledger_keys or set()
    files = _session_files(logs_dir, n)
    # chave -> {sessoes:set, exemplo:str, ocorrencias:int}
    grupos: dict[str, dict] = {}
    for f in files:
        sess_name = f.name
        seen_in_file: set[str] = set()
        for corr in _extract_from_file(f):
            key = _key(corr)
            if not key:
                continue
            g = grupos.setdefault(key, {"sessoes": set(), "exemplo": corr, "ocorrencias": 0})
            g["ocorrencias"] += 1
            g["sessoes"].add(sess_name)
            # mantem o exemplo mais curto (tende a ser a instrucao mais limpa)
            if len(corr) < len(g["exemplo"]):
                g["exemplo"] = corr
            seen_in_file.add(key)

    candidatas: list[dict] = []
    for key, g in grupos.items():
        if key in ledger_keys:
            continue
        n_sessoes = len(g["sessoes"])
        if n_sessoes >= k:
            candidatas.append({
                "key": key,
                "exemplo": g["exemplo"],
                "n_sessoes": n_sessoes,
                "sessoes": sorted(g["sessoes"]),
                "ocorrencias": g["ocorrencias"],
            })
    candidatas.sort(key=lambda c: (c["n_sessoes"], c["ocorrencias"]), reverse=True)
    return candidatas


def _ensure_ledger(ledger: Path) -> None:
    """Cria o ledger de rejeitadas com cabecalho se ainda nao existir."""
    if ledger.exists():
        return
    try:
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(
            "# Distill — candidatas REJEITADAS (nao re-propor)\n\n"
            "> Ledger do `distill_corrections.py`. Cada item rejeitado leva um marcador\n"
            "> `<!-- key: ... -->` que o distill usa p/ NUNCA re-propor a mesma correcao.\n"
            "> Adicione aqui (com o marcador `key:`) o que voce decidiu NAO virar regra.\n\n",
            encoding="utf-8",
        )
    except OSError:
        pass  # ledger e best-effort; ausencia nao quebra o distill


def _resolve_paths(root: Path):
    prof = load_profile() if load_profile is not None else {}
    logs_dir = get(prof, "paths.logs_dir", _DEF_LOGS_DIR) if (prof and get) else _DEF_LOGS_DIR
    ledger = get(prof, "distill.ledger_rejeitadas", _DEF_LEDGER) if (prof and get) else _DEF_LEDGER
    k = get(prof, "distill.limiar_recorrencia", _DEF_K) if (prof and get) else _DEF_K
    n = get(prof, "distill.janela_sessoes", _DEF_N) if (prof and get) else _DEF_N
    return (root / logs_dir, root / ledger, int(k), int(n))


def _project_root() -> Path:
    """Raiz = onde vive o profile; senao sobe ate .git; senao cwd."""
    if profile_path is not None:
        try:
            p = profile_path()
            if p is not None:
                d = p.parent
                for cand in (d, *d.parents):
                    if (cand / ".git").exists():
                        return cand
                return d
        except Exception:  # noqa: BLE001
            pass
    cur = Path.cwd().resolve()
    for cand in (cur, *cur.parents):
        if (cand / ".git").exists():
            return cand
    return cur


def main(argv) -> int:
    ap = argparse.ArgumentParser(description="Destila correcoes recorrentes dos session logs (PROPOE, nao aplica).")
    ap.add_argument("--n", type=int, default=None, help="janela de sessoes (default: profile ou 50)")
    ap.add_argument("--k", type=int, default=None, help="limiar de recorrencia em sessoes distintas (default: profile ou 3)")
    ap.add_argument("--json", action="store_true", help="saida JSON")
    args = ap.parse_args(argv)

    root = _project_root()
    logs_dir, ledger, k_prof, n_prof = _resolve_paths(root)
    n = args.n if args.n is not None else n_prof
    k = args.k if args.k is not None else k_prof

    _ensure_ledger(ledger)
    ledger_keys = _load_ledger_keys(ledger)
    candidatas = distill(logs_dir, n=n, k=k, ledger_keys=ledger_keys)

    now = datetime.now(_BRT).strftime("%Y-%m-%d %H:%M BRT")
    if args.json:
        print(json.dumps({
            "gerado": now,
            "logs_dir": str(logs_dir),
            "janela_n": n,
            "limiar_k": k,
            "rejeitadas_no_ledger": len(ledger_keys),
            "candidatas": candidatas,
        }, ensure_ascii=False, indent=2))
        return 0

    print(f"# Distill de correcoes — {now}")
    print(f"# logs: {logs_dir}  | janela N={n}  | limiar K={k} sessoes distintas")
    print(f"# ledger rejeitadas: {ledger}  ({len(ledger_keys)} chaves filtradas)")
    if not logs_dir.exists():
        print(f"\n(sem diretorio de sessoes em {logs_dir} — nada a destilar)")
        return 0
    if not candidatas:
        print(f"\n(nenhuma correcao recorreu em >= {k} sessoes distintas — nada a propor)")
        return 0
    print(f"\n{len(candidatas)} candidata(s) a regra (recorrencia >= {k}):\n")
    for i, c in enumerate(candidatas, 1):
        print(f"{i}. [{c['n_sessoes']} sessoes / {c['ocorrencias']} ocorrencias] {c['exemplo']}")
        print(f"   evidencia: {', '.join(c['sessoes'])}")
        print(f"   <!-- key: {c['key']} -->  (cole no ledger p/ rejeitar)")
        print()
    print("PROPOSTA apenas — nada foi aplicado. Decida quais viram regra em "
          "`distill.regra_alvo`; rejeite o resto no ledger.")
    return 0


# ---------------------------------------------------------------------------
# self-test (sem rede, sem profile real — usa fixture em tmp)
# ---------------------------------------------------------------------------
def _self_test() -> None:
    import tempfile

    # heuristicas puras
    assert _is_correction("NUNCA faca git push direto na main")
    assert _is_correction("na verdade o cliente e o Acme, errado de novo")
    assert not _is_correction("processando batch 3 de 8 com sucesso")
    # ordem-invariante: mesmo conjunto de tokens significativos em ordens diferentes -> mesma chave
    assert _key("git push main NUNCA") == _key("NUNCA main push git"), "chave deve ser ordem-invariante"
    # conjuntos diferentes -> chaves diferentes
    assert _key("git push main") != _key("git push staging"), "tokens distintos -> chaves distintas"
    assert _strip_log_prefix("- [2026-06-19 10:00] Operador: NUNCA faz X") == "NUNCA faz X"

    with tempfile.TemporaryDirectory() as td:
        logs = Path(td) / "sessions"
        logs.mkdir()
        # 3 sessoes distintas repetem a MESMA correcao -> deve virar candidata (k=3)
        for d in ("01", "02", "03"):
            (logs / f"SESSION-2026-06-{d}.md").write_text(
                "fizemos progresso no pipeline\n"
                "Operador: NUNCA usar a porta 8000 pra subir o servidor\n"
                "outro texto qualquer sem marcador\n",
                encoding="utf-8",
            )
        # 1 sessao com correcao unica -> NAO deve passar o limiar
        (logs / "SESSION-2026-06-04.md").write_text(
            "pare de criar arquivos na raiz do docs\n", encoding="utf-8"
        )
        # ponteiro/index deve ser ignorado
        (logs / "SESSION-INDEX.json").write_text("{}", encoding="utf-8")

        cands = distill(logs, n=50, k=3)
        assert len(cands) == 1, f"esperava 1 candidata, veio {len(cands)}"
        assert cands[0]["n_sessoes"] == 3, "deve recorrer em 3 sessoes distintas"
        assert "8000" in cands[0]["exemplo"]

        # k=4 nao deve achar nada (so recorreu em 3)
        assert distill(logs, n=50, k=4) == [], "k=4 nao deveria achar candidatas"

        # ledger filtra a chave -> some das candidatas
        key = cands[0]["key"]
        assert distill(logs, n=50, k=3, ledger_keys={key}) == [], "ledger deveria filtrar a chave"

        # ledger criado e lido corretamente
        ledger = Path(td) / "mem" / "_rej.md"
        _ensure_ledger(ledger)
        assert ledger.exists()
        ledger.write_text(ledger.read_text(encoding="utf-8") + f"\n- descartado <!-- key: {key} -->\n",
                           encoding="utf-8")
        assert key in _load_ledger_keys(ledger), "ledger key deveria ser lida"

    print("self-test OK")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    if len(sys.argv) > 1 and sys.argv[1] in ("--self-test", "-t"):
        _self_test()
        sys.exit(0)
    sys.exit(main(sys.argv[1:]))
