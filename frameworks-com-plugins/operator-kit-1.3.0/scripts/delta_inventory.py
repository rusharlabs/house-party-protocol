#!/usr/bin/env python3
"""
delta_inventory (Operator Kit) — inventario antes/depois/delta com CONTAGEM REAL.

Materializa a preferencia do CLAUDE.md: "tabelas comparativas (antes/depois/delta)"
e "inventario final com contagem de arquivos apos tarefas de geracao em massa".
Conta arquivos por glob no filesystem REAL (LC-1: nunca chuta numero) e compara
contra um snapshot anterior.

Dois modos:
    snapshot <out.json> <glob...>      grava {glob: contagem} do estado atual
    report   <baseline.json> <glob...> compara baseline vs estado atual e imprime
                                       tabela ANTES | DEPOIS | DELTA + total

Globs sao relativos a cwd (use aspas no shell p/ nao expandir antes). Padrao de
glob recursivo suportado via '**' (ex.: "agents/**/AGENT.md").

Uso:
    python delta_inventory.py snapshot before.json "agents/**/*.md" "docs/**/*.md"
    # ... faz o trabalho ...
    python delta_inventory.py report before.json "agents/**/*.md" "docs/**/*.md"
    python delta_inventory.py report before.json "agents/**/*.md" --json
    python delta_inventory.py --self-test

Exit: 0 sempre que conseguir produzir a saida; 2 = uso invalido. stdlib (pathlib + glob).
Independe do profile (opera sobre globs passados) — mas importa o loader p/ consistencia.

v1.0.0 — 2026-06-19 (Operator Kit · Tier 1)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# importa o loader compartilhado (consistencia do kit; aqui nao e obrigatorio)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from _lib.profile_loader import load_profile  # noqa: F401  (disponivel p/ extensoes futuras)
except Exception:  # noqa: BLE001 — nunca crasha por causa do loader
    load_profile = None  # type: ignore[assignment]


def count_glob(pattern: str, root: str | Path | None = None) -> int:
    """Conta arquivos (nao diretorios) que casam com o glob, a partir de root (default cwd)."""
    base = Path(root or Path.cwd())
    try:
        return sum(1 for p in base.glob(pattern) if p.is_file())
    except Exception:  # noqa: BLE001 — glob invalido => 0, sem crashar
        return 0


def snapshot(patterns, root: str | Path | None = None) -> dict:
    """Retorna {glob: contagem} para a lista de globs."""
    return {pat: count_glob(pat, root) for pat in patterns}


def compute_delta(baseline: dict, current: dict) -> list[dict]:
    """Cruza baseline x current por glob. Retorna linhas {glob, antes, depois, delta}."""
    keys = list(dict.fromkeys([*baseline.keys(), *current.keys()]))  # uniao preservando ordem
    linhas = []
    for k in keys:
        antes = int(baseline.get(k, 0) or 0)
        depois = int(current.get(k, 0) or 0)
        linhas.append({"glob": k, "antes": antes, "depois": depois, "delta": depois - antes})
    return linhas


def render_table(linhas: list[dict]) -> str:
    """Renderiza tabela ANTES | DEPOIS | DELTA + totais (pt-BR, ASCII puro)."""
    if not linhas:
        return "INVENTARIO DELTA: (nenhum glob informado)"
    glob_w = max([len("GLOB"), *[len(l["glob"]) for l in linhas]])
    glob_w = min(glob_w, 60)

    def fmt_delta(d: int) -> str:
        return f"+{d}" if d > 0 else (str(d) if d < 0 else "0")

    sep = "+" + "-" * (glob_w + 2) + "+" + "-" * 9 + "+" + "-" * 9 + "+" + "-" * 9 + "+"
    out = [
        "INVENTARIO DELTA (contagem real de arquivos no disco)",
        sep,
        f"| {'GLOB'.ljust(glob_w)} | {'ANTES'.rjust(7)} | {'DEPOIS'.rjust(7)} | {'DELTA'.rjust(7)} |",
        sep,
    ]
    t_antes = t_depois = 0
    for l in linhas:
        g = l["glob"] if len(l["glob"]) <= glob_w else (l["glob"][: glob_w - 1] + "~")
        out.append(
            f"| {g.ljust(glob_w)} | {str(l['antes']).rjust(7)} | "
            f"{str(l['depois']).rjust(7)} | {fmt_delta(l['delta']).rjust(7)} |"
        )
        t_antes += l["antes"]
        t_depois += l["depois"]
    out.append(sep)
    out.append(
        f"| {'TOTAL'.ljust(glob_w)} | {str(t_antes).rjust(7)} | "
        f"{str(t_depois).rjust(7)} | {fmt_delta(t_depois - t_antes).rjust(7)} |"
    )
    out.append(sep)
    return "\n".join(out)


def _load_baseline(path: str | Path) -> dict:
    """Le um snapshot json. {} se ausente/ilegivel (degrade seguro)."""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # estado inicial: 2 .md em docs/
        (root / "docs").mkdir()
        (root / "docs" / "a.md").write_text("x", encoding="utf-8")
        (root / "docs" / "b.md").write_text("y", encoding="utf-8")
        (root / "agents").mkdir()
        (root / "agents" / "z.md").write_text("z", encoding="utf-8")

        snap = snapshot(["docs/*.md", "agents/*.md", "missing/*.txt"], root=root)
        assert snap == {"docs/*.md": 2, "agents/*.md": 1, "missing/*.txt": 0}, snap

        # grava baseline e altera estado: +1 md em docs, -1 em agents
        baseline_path = root / "before.json"
        baseline_path.write_text(json.dumps(snap), encoding="utf-8")
        (root / "docs" / "c.md").write_text("c", encoding="utf-8")
        (root / "agents" / "z.md").unlink()

        current = snapshot(["docs/*.md", "agents/*.md", "missing/*.txt"], root=root)
        linhas = compute_delta(_load_baseline(baseline_path), current)
        by = {l["glob"]: l for l in linhas}
        assert by["docs/*.md"]["delta"] == 1, by["docs/*.md"]
        assert by["agents/*.md"]["delta"] == -1, by["agents/*.md"]
        assert by["missing/*.txt"]["delta"] == 0

        # glob recursivo: docs/ tem a.md, b.md, c.md + sub/d.md = 4
        (root / "docs" / "sub").mkdir()
        (root / "docs" / "sub" / "d.md").write_text("d", encoding="utf-8")
        assert count_glob("docs/**/*.md", root=root) == 4, count_glob("docs/**/*.md", root=root)

        # render nunca crasha + contem totais
        tbl = render_table(linhas)
        assert "INVENTARIO DELTA" in tbl and "TOTAL" in tbl

        # baseline ausente => {} (degrade)
        assert _load_baseline(root / "nao-existe.json") == {}

    # tabela vazia
    assert "nenhum glob" in render_table([])
    print("self-test OK")


def main(argv) -> int:
    if argv and argv[0] in ("--self-test", "-t"):
        _self_test()
        return 0

    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]

    if not argv:
        print('uso: delta_inventory.py snapshot <out.json> <glob...> | report <baseline.json> <glob...>',
              file=sys.stderr)
        return 2

    mode = argv[0]

    if mode == "snapshot":
        if len(argv) < 3:
            print("uso: delta_inventory.py snapshot <out.json> <glob...>", file=sys.stderr)
            return 2
        out_path = Path(argv[1])
        patterns = argv[2:]
        snap = snapshot(patterns)
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            print(f"delta_inventory: falha ao gravar snapshot: {e}", file=sys.stderr)
            return 2
        if as_json:
            print(json.dumps(snap, ensure_ascii=False, indent=2))
        else:
            total = sum(snap.values())
            print(f"snapshot gravado em {out_path} ({len(snap)} glob(s), {total} arquivo(s)):")
            for g, c in snap.items():
                print(f"  {c:>7}  {g}")
        return 0

    if mode == "report":
        if len(argv) < 3:
            print("uso: delta_inventory.py report <baseline.json> <glob...>", file=sys.stderr)
            return 2
        baseline = _load_baseline(argv[1])
        patterns = argv[2:]
        current = snapshot(patterns)
        linhas = compute_delta(baseline, current)
        if as_json:
            total_antes = sum(l["antes"] for l in linhas)
            total_depois = sum(l["depois"] for l in linhas)
            print(json.dumps(
                {
                    "baseline": argv[1],
                    "linhas": linhas,
                    "total": {"antes": total_antes, "depois": total_depois,
                              "delta": total_depois - total_antes},
                },
                ensure_ascii=False, indent=2,
            ))
        else:
            if not baseline:
                print(f"(aviso: baseline '{argv[1]}' ausente/vazio — ANTES=0 em todas as linhas)")
            print(render_table(linhas))
        return 0

    print(f"delta_inventory: modo desconhecido '{mode}' (use snapshot | report)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
