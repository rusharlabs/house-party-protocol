#!/usr/bin/env python3
"""
audit_plan (Operator Kit) — auditor de plano vs realidade.

Materializa LC-3 e feedback_plans_lag_reality: um plano NUNCA define o status —
o filesystem + o git log definem. Esta ferramenta recebe um arquivo de plano
markdown, EXTRAI os deliverables declarados (checkboxes, paths/arquivos citados
em backticks, seções "Deliverable") e, para CADA um, confronta com a realidade:

    - existe no disco? (Path direto OU glob)
    - aparece no histórico git? (git log --grep <termo>)

Devolve uma tabela FEITO / PARCIAL / AUSENTE (markdown ou --json). Não inventa:
o que não dá pra confirmar vira AUSENTE, nunca "provavelmente feito".

Classificação:
    FEITO    = arquivo existe no disco (confirmação forte)
    PARCIAL  = não existe no disco, mas aparece no git log (mencionado/iniciado)
    AUSENTE  = não existe e não aparece no git log

Uso:
    python audit_plan.py docs/plans/2026-06-19-X.md
    python audit_plan.py plano.md --json
    python audit_plan.py plano.md --no-git              # pula git log (offline)
    python audit_plan.py plano.md --repo /caminho/repo  # raiz p/ resolver paths
    python audit_plan.py plano.md --extra-regex '`([^`]+\\.sql)`'
    python audit_plan.py --self-test

Exit: 0 = rodou (independe do resultado da auditoria) · 2 = uso inválido.
stdlib SOMENTE. Cross-platform (pathlib). Nunca usa curl/wget.

v1.0.0 — 2026-06-19 (Operator Kit · Tier 1 · materializa LC-3 + plans_lag_reality)
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

# loader compartilhado do kit (.../operator-kit/_lib/profile_loader.py)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from _lib.profile_loader import load_profile, get
except Exception:  # noqa: BLE001 — sem loader o resto funciona (defaults seguros)
    load_profile = None  # type: ignore[assignment]
    get = None  # type: ignore[assignment]

# ── extração de deliverables ────────────────────────────────────────────────

# checkbox markdown: "- [ ] foo" / "- [x] bar" / "* [X] baz"
RE_CHECKBOX = re.compile(r"^\s*[-*]\s*\[(?P<mark>[ xX])\]\s*(?P<text>.+?)\s*$")
# path/arquivo citado em backticks: `core/paths.py`, `scripts/x.py`
RE_BACKTICK_PATH = re.compile(r"`([^`\n]+)`")
# seção "Deliverable: ..." / "Entregável: ..." (linha ou heading)
RE_DELIVERABLE = re.compile(
    r"^\s*#{0,6}\s*(?:deliverable|entreg[áa]vel|artefato)s?\s*[:\-]\s*(?P<text>.+?)\s*$",
    re.IGNORECASE,
)
# heurística: um token parece um path/arquivo? (tem / ou \ ou uma extensão)
RE_LOOKS_LIKE_PATH = re.compile(r"[\\/]|\.[A-Za-z0-9]{1,6}(\b|$)")
# extensões "de arquivo" plausíveis (evita capturar `R$100K` ou `8-12%`)
_PLAUSIBLE_EXT = {
    "py", "md", "yaml", "yml", "json", "js", "ts", "tsx", "jsx", "sql", "sh",
    "ps1", "bat", "html", "css", "txt", "toml", "ini", "cfg", "env", "jsonl",
}


def _looks_like_path(token: str) -> bool:
    """True se o token em backtick parece um path/arquivo (não uma métrica/comando)."""
    t = token.strip()
    if not t or " " in t.split("/")[-1] and "/" not in t:
        # tokens com espaço e sem barra raramente são paths (ex.: `git status`)
        pass
    if "/" in t or "\\" in t:
        return True
    if "." in t:
        ext = t.rsplit(".", 1)[-1].lower()
        return ext in _PLAUSIBLE_EXT
    return False


def extract_deliverables(text: str, extra_regexes=None) -> list[dict]:
    """
    Extrai deliverables de um plano markdown. Cada item:
        {tipo, texto, path (str|None), checked (bool|None)}
    Dedup por (tipo, texto-normalizado).
    """
    items: list[dict] = []
    seen: set[tuple] = set()

    def add(tipo: str, texto: str, path: str | None = None, checked=None) -> None:
        texto = (texto or "").strip()
        key = (tipo, (path or texto).lower())
        if not texto and not path:
            return
        if key in seen:
            return
        seen.add(key)
        items.append({"tipo": tipo, "texto": texto, "path": path, "checked": checked})

    for raw in text.splitlines():
        line = raw.rstrip("\n")

        m = RE_CHECKBOX.match(line)
        if m:
            txt = m.group("text").strip()
            checked = m.group("mark").lower() == "x"
            # se o texto do checkbox contém um path em backtick, captura como path
            path = None
            bt = RE_BACKTICK_PATH.findall(txt)
            for cand in bt:
                if _looks_like_path(cand):
                    path = cand.strip()
                    break
            add("checkbox", txt, path=path, checked=checked)
            continue

        m = RE_DELIVERABLE.match(line)
        if m:
            txt = m.group("text").strip()
            path = None
            for cand in RE_BACKTICK_PATH.findall(txt):
                if _looks_like_path(cand):
                    path = cand.strip()
                    break
            add("deliverable", txt, path=path)
            continue

        # paths citados em backticks em qualquer linha
        for cand in RE_BACKTICK_PATH.findall(line):
            cand = cand.strip()
            if _looks_like_path(cand):
                add("path", cand, path=cand)

    # regex extras customizáveis (capturam grupo 1 como path)
    for pat in (extra_regexes or []):
        try:
            rx = re.compile(pat)
        except re.error:
            continue
        for m in rx.finditer(text):
            cand = (m.group(1) if m.groups() else m.group(0)).strip()
            if cand:
                add("path", cand, path=cand)

    return items


# ── confronto com a realidade ───────────────────────────────────────────────

def path_exists(path_str: str, repo_root: Path) -> bool:
    """Existe no disco? Tenta Path direto (abs e relativo ao repo) e glob."""
    if not path_str:
        return False
    p = Path(path_str)
    candidates = [p]
    if not p.is_absolute():
        candidates.append(repo_root / p)
    for c in candidates:
        try:
            if c.exists():
                return True
        except OSError:
            pass
    # glob (suporta wildcards e match parcial pelo nome do arquivo)
    try:
        if any(ch in path_str for ch in "*?[]"):
            if list(repo_root.glob(path_str)):
                return True
        else:
            name = Path(path_str).name
            if name:
                # match raso por nome de arquivo, limitado p/ não varrer o mundo
                hits = 0
                for _ in repo_root.rglob(name):
                    hits += 1
                    break
                if hits:
                    return True
    except (OSError, ValueError):
        pass
    return False


def git_log_mentions(term: str, repo_root: Path, timeout: int = 20) -> bool:
    """git log --grep <term> achou commit? False em qualquer falha (sem git, etc.)."""
    term = (term or "").strip()
    if not term:
        return False
    # usa o nome do arquivo se for um path (mais provável de aparecer em commit)
    needle = Path(term).name if (_looks_like_path(term)) else term
    needle = needle.strip()
    if not needle:
        return False
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "log", "--all", "-i",
             "--grep", needle, "--oneline", "-n", "1"],
            capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:  # noqa: BLE001 — git ausente/erro => não menciona
        return False


def classify(item: dict, repo_root: Path, use_git: bool) -> dict:
    """Classifica um deliverable em FEITO/PARCIAL/AUSENTE com evidências."""
    probe = item.get("path") or item.get("texto") or ""
    on_disk = path_exists(item["path"], repo_root) if item.get("path") else False
    in_git = git_log_mentions(probe, repo_root) if use_git else False

    if on_disk:
        status = "FEITO"
    elif in_git:
        status = "PARCIAL"
    else:
        status = "AUSENTE"

    # checkbox marcado [x] mas sem evidência no disco/git: sinaliza como suspeito
    if item.get("checked") and status == "AUSENTE":
        status = "AUSENTE"  # mantemos AUSENTE — o ponto do LC-3 é não confiar no [x]
    return {**item, "status": status, "on_disk": on_disk, "in_git": in_git}


def audit(plan_path: Path, repo_root: Path, use_git: bool = True,
          extra_regexes=None) -> dict:
    """Lê o plano, extrai e classifica todos os deliverables."""
    text = plan_path.read_text(encoding="utf-8", errors="replace")
    items = extract_deliverables(text, extra_regexes=extra_regexes)
    rows = [classify(it, repo_root, use_git) for it in items]
    resumo = {"FEITO": 0, "PARCIAL": 0, "AUSENTE": 0}
    for r in rows:
        resumo[r["status"]] = resumo.get(r["status"], 0) + 1
    return {
        "plano": str(plan_path),
        "repo": str(repo_root),
        "git_consultado": use_git,
        "total": len(rows),
        "resumo": resumo,
        "itens": rows,
    }


# ── render ──────────────────────────────────────────────────────────────────

def render_markdown(result: dict) -> str:
    out: list[str] = []
    out.append(f"# Auditoria de plano — {Path(result['plano']).name}")
    out.append("")
    r = result["resumo"]
    out.append(f"Deliverables: **{result['total']}** · "
               f"FEITO {r.get('FEITO', 0)} · PARCIAL {r.get('PARCIAL', 0)} · "
               f"AUSENTE {r.get('AUSENTE', 0)}"
               + ("" if result["git_consultado"] else "  _(git não consultado)_"))
    out.append("")
    if not result["itens"]:
        out.append("_Nenhum deliverable detectado no plano (sem checkbox/path/seção Deliverable)._")
        return "\n".join(out)
    out.append("| Status | Tipo | Deliverable | Disco | Git |")
    out.append("|--------|------|-------------|:-----:|:---:|")
    for it in result["itens"]:
        alvo = it.get("path") or it.get("texto") or ""
        alvo = alvo.replace("|", "\\|")
        if len(alvo) > 70:
            alvo = alvo[:67] + "..."
        disco = "sim" if it["on_disk"] else "—"
        gitm = "sim" if it["in_git"] else "—"
        out.append(f"| {it['status']} | {it['tipo']} | {alvo} | {disco} | {gitm} |")
    return "\n".join(out)


def main(argv) -> int:
    if argv and argv[0] in ("--self-test", "-t"):
        _self_test()
        return 0

    as_json = "--json" in argv
    use_git = "--no-git" not in argv
    argv = [a for a in argv if a not in ("--json", "--no-git")]

    repo_root: Path | None = None
    extra_regexes: list[str] = []
    positional: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--repo" and i + 1 < len(argv):
            repo_root = Path(argv[i + 1]); i += 2; continue
        if a == "--extra-regex" and i + 1 < len(argv):
            extra_regexes.append(argv[i + 1]); i += 2; continue
        positional.append(a); i += 1

    if not positional:
        print('uso: audit_plan.py <plano.md> [--json] [--no-git] '
              '[--repo <dir>] [--extra-regex <re>]', file=sys.stderr)
        return 2

    plan_path = Path(positional[0])
    if not plan_path.exists():
        print(f"audit_plan: plano não encontrado: {plan_path}", file=sys.stderr)
        return 2

    if repo_root is None:
        repo_root = _detect_repo_root(plan_path)

    result = audit(plan_path, repo_root, use_git=use_git, extra_regexes=extra_regexes)

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(result))
    return 0


def _detect_repo_root(plan_path: Path) -> Path:
    """Sobe do plano até achar uma raiz de repo (.git); fallback = cwd."""
    base = plan_path.resolve().parent
    for d in (base, *base.parents):
        if (d / ".git").exists():
            return d
    return Path.cwd()


# ── self-test (sem rede; usa tmp + fixture) ─────────────────────────────────

def _self_test() -> None:
    import tempfile

    plano = (
        "# Plano fixture\n"
        "\n"
        "## Fase 1\n"
        "- [x] Criar `existe_no_disco.py`\n"
        "- [ ] Criar `nao_existe_jamais_xyz.py`\n"
        "- [ ] Tarefa sem path nenhum\n"
        "\n"
        "Deliverable: `outro_arquivo_inexistente_abc.md`\n"
        "Referência solta a `R$100K` e `git status` (não são paths).\n"
        "Caminho citado: `subdir/profundo.txt`\n"
    )

    # extração
    items = extract_deliverables(plano)
    paths = [it["path"] for it in items if it["path"]]
    assert "existe_no_disco.py" in paths, "deveria extrair path do checkbox"
    assert "nao_existe_jamais_xyz.py" in paths, "deveria extrair 2o checkbox path"
    assert "outro_arquivo_inexistente_abc.md" in paths, "deveria extrair Deliverable path"
    assert "subdir/profundo.txt" in paths, "deveria extrair path em backtick"
    # métricas/comandos NÃO devem virar path
    assert "R$100K" not in paths, "R$100K não é path"
    assert "git status" not in paths, "comando não é path"
    # checkbox sem path vira item, mas sem path
    assert any(it["tipo"] == "checkbox" and it["path"] is None for it in items), \
        "checkbox sem path deve existir como item"

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "existe_no_disco.py").write_text("x", encoding="utf-8")
        sub = root / "subdir"
        sub.mkdir()
        (sub / "profundo.txt").write_text("y", encoding="utf-8")
        plan_file = root / "plano.md"
        plan_file.write_text(plano, encoding="utf-8")

        res = audit(plan_file, root, use_git=False)
        by_path = {it["path"]: it for it in res["itens"] if it["path"]}
        assert by_path["existe_no_disco.py"]["status"] == "FEITO", "arquivo presente = FEITO"
        assert by_path["subdir/profundo.txt"]["status"] == "FEITO", "path relativo presente = FEITO"
        assert by_path["nao_existe_jamais_xyz.py"]["status"] == "AUSENTE", \
            "ausente + sem git = AUSENTE (mesmo com [x])"
        assert by_path["outro_arquivo_inexistente_abc.md"]["status"] == "AUSENTE", \
            "deliverable ausente = AUSENTE"
        assert res["git_consultado"] is False
        assert res["resumo"]["FEITO"] >= 2

        # render markdown não pode crashar e deve conter o cabeçalho
        md = render_markdown(res)
        assert "Auditoria de plano" in md and "| Status |" in md

        # plano sem deliverables não crasha
        vazio = root / "vazio.md"
        vazio.write_text("# nada aqui\ntexto puro\n", encoding="utf-8")
        rv = audit(vazio, root, use_git=False)
        assert rv["total"] == 0
        assert "Nenhum deliverable" in render_markdown(rv)

    print("self-test OK")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
