#!/usr/bin/env python3
"""
goal_ledger — leitor/escritor do _GOAL-LEDGER (loop autônomo /goal · 2026-06-27).

SSoT dos goals do ecossistema: docs/plans/_GOAL-LEDGER.md (tabela markdown
goal↔tier↔PRD↔status↔critério↔review). Análogo a loop_state.py, mas no nível de
GOAL (não de lote): reporta o PRÓXIMO goal repo-safe (🟢) não-pronto, o resumo
de progresso, e — opcional — escreve o status de um goal (--set, edição cirúrgica
da célula Status). É a peça que o loop usa p/ saber "qual objetivo atacar agora"
e p/ marcar progresso sem drift.

Uso:
    python scripts/goal_ledger.py                 # próximo goal + resumo
    python scripts/goal_ledger.py --json
    python scripts/goal_ledger.py --next          # só o id do próximo goal
    python scripts/goal_ledger.py --set G-CONT "✅ pronto (LIVE 2026-06-27)"
    python scripts/goal_ledger.py --self-test
Exit: 0 = ok · 1 = --set não encontrou o goal · 2 = ledger ausente/uso inválido.
stdlib-only. Leitura NÃO muta; --set faz edição cirúrgica só da célula Status.

v1.0.0 — 2026-06-27 (G-CONT · PRD-CONTINUIDADE-LOOP)
v1.1.0 — 2026-07-10 (Operator Kit · Tier 2 · embarcado no operator-kit — raiz resolvida via
         CLAUDE_PROJECT_DIR/${CLAUDE_PLUGIN_ROOT}/busca por .git, não mais parents[N] fixo:
         a profundidade do arquivo muda quando o kit é instalado em outro projeto — o mesmo
         off-by-one que já pegou o dual-report-builder. Lógica de parsing/ledger intacta.)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass


def _resolve_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env and Path(env).exists():
        return Path(env)
    here = Path(__file__).resolve().parent
    for d in (here, *here.parents):
        if (d / ".git").exists():
            return d
    return here.parent


_ROOT = _resolve_root()
LEDGER = _ROOT / "docs" / "plans" / "_GOAL-LEDGER.md"


# ───────────────────────── parsing (pure) ──────────────────────────
def _split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(bool(c) and set(c) <= set("-: ") for c in cells)


def parse(text: str) -> dict:
    """Parseia a 1ª tabela markdown com colunas Goal+Status. Retorna {col, goals}."""
    header = None
    col: dict[str, int] = {}
    goals: list[dict] = []
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = _split_row(line)
        if _is_separator(cells):
            continue
        low = [c.lower() for c in cells]
        if header is None:
            if any("goal" in c for c in low) and any("status" in c for c in low):
                header = cells
                for i, c in enumerate(low):
                    if c == "#":
                        col["id"] = i
                    elif "goal" in c:
                        col["name"] = i
                    elif "tier" in c:
                        col["tier"] = i
                    elif "prd" in c:
                        col["prd"] = i
                    elif "status" in c:
                        col["status"] = i
                    elif "crit" in c or "pronto" in c:
                        col["done_when"] = i
                    elif "review" in c:
                        col["review"] = i
                    elif "readiness" in c:
                        col["readiness"] = i
                col.setdefault("id", 0)
            continue
        gid = cells[col["id"]] if col["id"] < len(cells) else ""
        if not gid or gid.startswith("#"):
            continue

        def g(key: str) -> str:
            i = col.get(key)
            return cells[i] if i is not None and i < len(cells) else ""

        goals.append({
            "id": gid, "name": g("name"), "tier": g("tier"), "prd": g("prd"),
            "status": g("status"), "done_when": g("done_when"), "review": g("review"),
            "readiness": g("readiness"),
        })
    return {"col": col, "goals": goals}


def status_kind(status: str) -> str:
    s = status.lower()
    if "✅" in status or "pronto" in s or "done" in s or "pass" in s or "feito" in s:
        return "done"
    if ("🔄" in status or "em-curso" in s or "em curso" in s or "in_progress" in s
            or "in-progress" in s or "andamento" in s):
        return "in_progress"
    return "pending"


def tier_kind(tier: str) -> set[str]:
    k: set[str] = set()
    if "🟢" in tier:
        k.add("repo")
    if "🟠" in tier:
        k.add("vm")
    if "🔴" in tier:
        k.add("gate")
    return k


def actionable(goal: dict) -> bool:
    """Repo-safe (🟢) e ainda não-pronto = o loop pode atacar autônomo (LC-2)."""
    return "repo" in tier_kind(goal["tier"]) and status_kind(goal["status"]) != "done"


def next_goal(goals: list[dict]):
    return next((g for g in goals if actionable(g)), None)


def summary(goals: list[dict]) -> dict:
    done = [g for g in goals if status_kind(g["status"]) == "done"]
    repo_pending = [g for g in goals if actionable(g)]
    gates = [g for g in goals
             if "gate" in tier_kind(g["tier"]) and status_kind(g["status"]) != "done"]
    nxt = next_goal(goals)
    return {
        "total": len(goals), "done": len(done),
        "repo_pending": len(repo_pending), "gates": len(gates),
        "next": ({"id": nxt["id"], "name": nxt["name"], "prd": nxt["prd"],
                  "done_when": nxt["done_when"]} if nxt else None),
        "pct": round(100 * len(done) / max(1, len(goals)), 1),
    }


def set_column(text: str, goal_id: str, column_key: str, new_value: str) -> tuple[str, bool]:
    """Edição cirúrgica genérica: troca SÓ a célula de `column_key` (ex.: 'status',
    'readiness') da linha cujo id == goal_id. Generaliza set_status()."""
    p = parse(text)
    ci = p["col"].get(column_key)
    ii = p["col"].get("id", 0)
    if ci is None:
        raise ValueError(f"coluna '{column_key}' não encontrada no ledger")
    out: list[str] = []
    changed = False
    for line in text.splitlines():
        if line.lstrip().startswith("|"):
            cells = _split_row(line)
            if (not _is_separator(cells) and ii < len(cells)
                    and cells[ii] == goal_id and ci < len(cells)):
                cells[ci] = new_value
                line = "| " + " | ".join(cells) + " |"
                changed = True
        out.append(line)
    tail = "\n" if text.endswith("\n") else ""
    return "\n".join(out) + tail, changed


def set_status(text: str, goal_id: str, new_status: str) -> tuple[str, bool]:
    """Edição cirúrgica: troca SÓ a célula Status da linha cujo id == goal_id."""
    return set_column(text, goal_id, "status", new_status)


# ───────────────────────── escada de prontidao R0->R4 ──────────────────────────
_READINESS_LEVELS = ("R0", "R1", "R2", "R3", "R4")

_READINESS_EVIDENCE_RE = {
    # R0 (Declarado) não exige evidência — é a palavra do maker.
    "R1": re.compile(r"(?i)(self-test|pytest|test).{0,40}(ok|pass|exit\s*=?\s*0|passed)"),
    "R2": re.compile(r"(?i)done_gate.{0,40}(exit\s*=?\s*0|DONE)"),
    "R3": re.compile(r"(?i)REVIEW-[\w\-]+\.md"),
    "R4": re.compile(r"(?i)verdict_by\s*[:=]?\s*max|aprovado\s+pelo\s+max|max\s+aprovou"),
}


def validate_readiness(level: str, evidence: str) -> str | None:
    """Retorna None se a evidência satisfaz o nível, ou a mensagem de recusa (exit 2).

    Regra dura (A.2): ninguém declara readiness maior que a evidência.
    """
    if level not in _READINESS_LEVELS:
        return f"nível inválido: {level!r} (válidos: {_READINESS_LEVELS})"
    if level == "R0":
        return None
    pattern = _READINESS_EVIDENCE_RE[level]
    if not evidence or not pattern.search(evidence):
        hints = {
            "R1": "evidência deve referenciar self-test/pytest com exit 0/passed",
            "R2": "evidência deve referenciar receipt do done_gate (ex.: 'done_gate exit=0')",
            "R3": "evidência deve referenciar um REVIEW-*.md (goal_review.py de outra família)",
            "R4": "evidência deve conter 'verdict_by: max' (só o humano declara R4)",
        }
        return f"{level} recusado — {hints[level]} (evidência recebida: {evidence!r})"
    return None


def set_readiness(text: str, goal_id: str, level: str, evidence: str) -> tuple[str, bool, str | None]:
    """Retorna (novo_texto, changed, error). error != None = recusado, texto inalterado."""
    err = validate_readiness(level, evidence)
    if err:
        return text, False, err
    cell = f"{level} ({evidence[:60]})" if evidence else level
    try:
        new_text, changed = set_column(text, goal_id, "readiness", cell)
    except ValueError as e:
        return text, False, str(e)
    if not changed:
        return text, False, f"goal '{goal_id}' não encontrado no ledger"
    return new_text, True, None


# ───────────────────────── self-test ──────────────────────────
_SAMPLE = (
    "| # | Goal | Tier | PRD-fonte | Status | Critério-de-PRONTO (LIVE) | Review |\n"
    "|---|------|------|-----------|--------|----------------------------|--------|\n"
    "| G-A | foo | 🟢 | PRD-X | ⬜ pendente | crit a | rev a |\n"
    "| G-B | bar | 🔴 gate | PRD-Y | ⬜ gate | crit b | rev b |\n"
    "| G-C | baz | 🟢 | PRD-Z | ✅ pronto | crit c | rev c |\n"
)


def _self_test() -> None:
    p = parse(_SAMPLE)
    assert len(p["goals"]) == 3, p["goals"]
    assert status_kind("✅ pronto") == "done"
    assert status_kind("🔄 em-curso (x)") == "in_progress"
    assert status_kind("⬜ pendente") == "pending"
    assert tier_kind("🟢→deploy") == {"repo"}
    assert tier_kind("🟢(mirror)+🔴(release)") == {"repo", "gate"}
    nxt = next_goal(p["goals"])
    assert nxt and nxt["id"] == "G-A", nxt  # G-A repo+pending; G-B gate; G-C done
    s = summary(p["goals"])
    assert s["done"] == 1 and s["repo_pending"] == 1 and s["gates"] == 1, s
    new, changed = set_status(_SAMPLE, "G-A", "🔄 em-curso")
    assert changed and "🔄 em-curso" in new, "set_status falhou"
    assert "| G-B | bar |" in new.replace("  ", " ") or "G-B" in new, "outras linhas intactas"
    assert parse(new)["goals"][0]["status"] == "🔄 em-curso", "status novo não persistiu"

    # escada R0->R4 (A.2)
    sample_r = _SAMPLE.replace(
        "| # | Goal | Tier | PRD-fonte | Status | Critério-de-PRONTO (LIVE) | Review |",
        "| # | Goal | Tier | PRD-fonte | Status | Critério-de-PRONTO (LIVE) | Review | Readiness |",
    ).replace(
        "|---|------|------|-----------|--------|----------------------------|--------|",
        "|---|------|------|-----------|--------|----------------------------|--------|-----------|",
    )
    # adiciona célula Readiness (R0) em cada linha de dado (goals G-A/G-B/G-C)
    lines_r = []
    for ln in sample_r.splitlines():
        if ln.startswith("| G-"):
            ln = ln.rstrip()[:-1].rstrip() + " | R0 |"
        lines_r.append(ln)
    sample_r = "\n".join(lines_r) + "\n"

    assert validate_readiness("R0", "") is None, "R0 não deveria exigir evidência"
    assert validate_readiness("R2", "só rodei e ficou bom") is not None, "R2 sem receipt deveria recusar"
    assert validate_readiness("R2", "done_gate exit=0 (3/3 criterios)") is None, "R2 com receipt deveria aceitar"
    assert validate_readiness("R3", "revisei e gostei") is not None, "R3 sem REVIEW-*.md deveria recusar"
    assert validate_readiness("R3", "ver REVIEW-G-A-20260710.md") is None, "R3 com REVIEW-*.md deveria aceitar"
    assert validate_readiness("R4", "aprovei") is not None, "R4 sem verdict_by:max deveria recusar"
    assert validate_readiness("R4", "verdict_by: max") is None, "R4 com verdict_by:max deveria aceitar"

    new_r, ok_r, err_r = set_readiness(sample_r, "G-A", "R2", "done_gate exit=0 (2/2 criterios)")
    assert ok_r and err_r is None, f"R2 com receipt deveria gravar: {err_r}"
    assert "R2 (done_gate exit=0" in new_r

    _, ok_r2, err_r2 = set_readiness(sample_r, "G-A", "R4", "sem evidencia formal")
    assert not ok_r2 and err_r2 and "verdict_by" in err_r2, f"R4 sem evidência deveria recusar: {err_r2}"

    _, ok_r3, err_r3 = set_readiness(_SAMPLE, "G-A", "R1", "self-test ok")
    assert not ok_r3 and "readiness" in (err_r3 or ""), "ledger sem coluna readiness deveria recusar com erro claro"

    print("self-test OK")


# ───────────────────────── CLI ──────────────────────────
def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="goal_ledger — driver de goals do loop /goal")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--next", action="store_true", help="imprime só o id do próximo goal repo-safe")
    ap.add_argument("--set", nargs=2, metavar=("GOAL", "STATUS"))
    ap.add_argument("--readiness", nargs=2, metavar=("GOAL", "LEVEL"), help="R0-R4 (escada de prontidao); exige --evidence para R1+")
    ap.add_argument("--evidence", default="", help="evidência textual p/ --readiness (receipt/REVIEW-*.md/verdict_by:max)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)

    if a.self_test:
        _self_test()
        return 0

    if not LEDGER.exists():
        print(f"goal_ledger: ledger ausente: {LEDGER}", file=sys.stderr)
        return 2
    text = LEDGER.read_text(encoding="utf-8", errors="replace")

    if a.readiness:
        gid, level = a.readiness
        new, ok, err = set_readiness(text, gid, level, a.evidence)
        if not ok:
            print(f"goal_ledger: readiness recusada — {err}", file=sys.stderr)
            return 2
        LEDGER.write_text(new, encoding="utf-8")
        print(f"goal_ledger: {gid} -> Readiness = '{level}' (evidência: {a.evidence[:60]!r})")
        return 0

    if a.set:
        gid, new_status = a.set
        new, changed = set_status(text, gid, new_status)
        if not changed:
            print(f"goal_ledger: goal '{gid}' não encontrado no ledger", file=sys.stderr)
            return 1
        LEDGER.write_text(new, encoding="utf-8")
        print(f"goal_ledger: {gid} → Status = '{new_status}' ✅")
        return 0

    p = parse(text)
    s = summary(p["goals"])
    if a.next:
        print(s["next"]["id"] if s["next"] else "")
        return 0
    if a.json:
        print(json.dumps({**s, "goals": p["goals"]}, ensure_ascii=False, indent=2))
        return 0
    print(f"GOAL-LEDGER — {s['done']}/{s['total']} pronto ({s['pct']}%) · "
          f"{s['repo_pending']} repo-safe pendente(s) · {s['gates']} gate(s)")
    if s["next"]:
        print(f"PRÓXIMO (repo-safe): {s['next']['id']} — {s['next']['name']} "
              f"[{s['next']['prd']}]")
        print(f"  pronto-quando: {s['next']['done_when']}")
    else:
        print("PRÓXIMO: (nenhum repo-safe pendente — só restam gates 🔴/humano)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
