#!/usr/bin/env python3
"""
goal_review — REVISÃO ADVERSARIAL de um GOAL inteiro (não de lote) · loop /goal.

Enquanto done_gate responde "este LOTE compila/passa?", goal_review responde
"o OBJETIVO entregou o valor prometido, AO VIVO?" (LC-1 · anti-R1 do
MAPA-VERDADE: code-verde ≠ deployado ≠ wirado). Lê os critérios-de-aceitação
(bloco DoD/shell do PRD do goal), roda cada um como probe LIVE (AND, via
done_gate.gate), e emite logs/reviews/REVIEW-<goal>-<ts>.md com PASS/FAIL+gaps.
FAIL = reabrir lotes no 00-STATE.

Uso:
    python scripts/goal_review.py --goal G-CONT
    python scripts/goal_review.py --prd docs/plans/_PRD/PRD-CONTINUIDADE-LOOP.md
    python scripts/goal_review.py "python -m pytest tests/python -q" --goal G-CONT
    python scripts/goal_review.py --self-test
Exit: 0 = PASS · 1 = FAIL · 2 = uso inválido / sem critérios. stdlib-only.

v1.0.0 — 2026-06-27 (G-CONT · PRD-CONTINUIDADE-LOOP)
v1.1.0 — 2026-07-10 (Operator Kit · Tier 2 · embarcado no operator-kit — raiz via
         CLAUDE_PROJECT_DIR/${CLAUDE_PLUGIN_ROOT}/busca .git, não parents[N] fixo)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
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


_HERE = Path(__file__).resolve().parent
_ROOT = _resolve_root()
sys.path.insert(0, str(_HERE))
try:
    from done_gate import gate  # type: ignore  # reuso: AND de probes shell
except Exception:  # noqa: BLE001  # pragma: no cover
    gate = None  # type: ignore
try:
    from goal_ledger import parse as _ledger_parse  # type: ignore
except Exception:  # noqa: BLE001  # pragma: no cover
    _ledger_parse = None  # type: ignore

_BRT = timezone(timedelta(hours=-3))
PRD_DIR = _ROOT / "docs" / "plans" / "_PRD"
LEDGER = _ROOT / "docs" / "plans" / "_GOAL-LEDGER.md"
REVIEW_DIR = _ROOT / "logs" / "reviews"

_DOD_KW = (
    "definition of done", "dod", "review-criteria", "review criteria",
    "critério-de-pronto", "criterio-de-pronto", "critérios", "criterios",
    "aceitação", "aceitacao", "done gate", "done-gate",
)


def extract_criteria(prd_text: str) -> list[str]:
    """Extrai o 1º bloco ``` que segue um heading de DoD/aceitação. Pure/testável."""
    crit: list[str] = []
    in_fence = False
    armed = False
    for line in prd_text.splitlines():
        low = line.lower()
        if line.lstrip().startswith("#"):
            armed = any(k in low for k in _DOD_KW)
            continue
        if line.strip().startswith("```"):
            if not in_fence and armed:
                in_fence = True
                continue
            if in_fence:
                in_fence = False
                armed = False
                if crit:
                    break
                continue
        if in_fence:
            # tira comentário shell trailing (" # ...") — done_gate roda via cmd.exe
            # no Windows, onde '#' NÃO é comentário e viraria argumento.
            s = re.sub(r"\s+#\s.*$", "", line.strip()).strip()
            if s and not s.startswith("#"):
                crit.append(s)
    return crit


def _prd_path_for_goal(goal_id: str) -> Path | None:
    if _ledger_parse is None or not LEDGER.exists():
        return None
    p = _ledger_parse(LEDGER.read_text(encoding="utf-8", errors="replace"))
    for g in p["goals"]:
        if g["id"] == goal_id:
            return _resolve_prd(g.get("prd", ""))
    return None


def _resolve_prd(name: str) -> Path | None:
    name = (name or "").strip()
    if not name:
        return None
    cand = Path(name)
    if cand.is_absolute() and cand.exists():
        return cand
    if not name.endswith(".md"):
        name += ".md"
    for c in (_ROOT / name, PRD_DIR / Path(name).name):
        if c.exists():
            return c
    return None


def _write_review(goal: str, passed: bool, results: list[dict]) -> Path:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(_BRT).strftime("%Y%m%d-%H%M%S")
    p = REVIEW_DIR / f"REVIEW-{goal or 'adhoc'}-{ts}.md"
    lines = [
        f"# REVIEW — {goal or '(ad-hoc)'} · {'PASS ✅' if passed else 'FAIL ❌'}",
        "",
        f"> goal_review.py · {datetime.now(_BRT):%Y-%m-%d %H:%M BRT} · "
        f"LC-1 (probes LIVE, não compile)",
        "",
    ]
    for r in results:
        mark = "x" if r["passed"] else " "
        lines.append(f"- [{mark}] (exit {r['exit_code']}) `{r['cmd']}`")
        if not r["passed"] and r.get("tail"):
            lines.append(f"      ↳ {r['tail'][-200:]}")
    lines += [
        "",
        f"**VEREDITO:** {'PASS — goal aceito ao vivo.' if passed else 'FAIL — reabrir lotes no 00-STATE §GOAL ATIVO.'}",
        "",
    ]
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def review(criteria: list[str], goal: str, timeout: int) -> tuple[bool, list[dict], Path | None]:
    if gate is None:
        raise RuntimeError("done_gate indisponível (import falhou)")
    passed, results = gate(criteria, timeout=timeout)
    path = _write_review(goal, passed, results)
    return passed, results, path


def _self_test() -> None:
    assert gate is not None, "done_gate deve importar"
    ok, _ = gate([f'"{sys.executable}" -c "import sys; sys.exit(0)"'])
    assert ok, "probe exit0 deveria passar"
    bad, _ = gate([f'"{sys.executable}" -c "import sys; sys.exit(2)"'])
    assert bad is False, "probe exit2 deveria falhar"
    sample = (
        "## 5. Definition of Done\n"
        "**DoD:**\n"
        "```\n"
        'python -c "import sys; sys.exit(0)"   # roda ok\n'
        "# comentário ignorado\n"
        'python -c "pass"\n'
        "```\n"
        "- [ ] item de review em prosa (ignorado)\n"
    )
    c = extract_criteria(sample)
    assert c == ['python -c "import sys; sys.exit(0)"', 'python -c "pass"'], c
    assert extract_criteria("sem dod aqui\n```\necho x\n```\n") == [], "sem heading DoD = vazio"
    print("self-test OK")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="goal_review — revisão adversarial de um goal (LIVE)")
    ap.add_argument("criteria", nargs="*", help="critérios shell explícitos (override do PRD)")
    ap.add_argument("--goal", help="id do goal (resolve PRD via _GOAL-LEDGER)")
    ap.add_argument("--prd", help="caminho do PRD (extrai bloco DoD)")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)

    if a.self_test:
        _self_test()
        return 0
    if gate is None:
        print("goal_review: done_gate indisponível", file=sys.stderr)
        return 2

    criteria = list(a.criteria)
    if not criteria:
        prd = None
        if a.prd:
            prd = _resolve_prd(a.prd)
            if prd is None:
                print(f"goal_review: PRD não encontrado: {a.prd}", file=sys.stderr)
                return 2
        elif a.goal:
            prd = _prd_path_for_goal(a.goal)
            if prd is None:
                print(f"goal_review: PRD do goal '{a.goal}' não encontrado no ledger",
                      file=sys.stderr)
                return 2
        if prd is not None:
            criteria = extract_criteria(prd.read_text(encoding="utf-8", errors="replace"))
    if not criteria:
        print("goal_review: nenhum critério (passe critérios, --goal ou --prd com bloco DoD)",
              file=sys.stderr)
        return 2

    passed, results, path = review(criteria, a.goal or "adhoc", a.timeout)
    if a.json:
        print(json.dumps({"goal": a.goal, "pass": passed, "review": str(path),
                          "results": results}, ensure_ascii=False, indent=2))
    else:
        for r in results:
            mark = "OK " if r["passed"] else "FAIL"
            print(f"  [{mark}] (exit {r['exit_code']}) {r['cmd']}")
            if not r["passed"] and r["tail"]:
                print(f"        ^ {r['tail'][-200:]}")
        n_ok = sum(1 for r in results if r["passed"])
        print(f"\nGOAL-REVIEW [{a.goal or 'ad-hoc'}]: "
              f"{'PASS ✅' if passed else 'FAIL ❌'} ({n_ok}/{len(results)}) · review: {path}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
