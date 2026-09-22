#!/usr/bin/env python3
"""
gate_sheet_panel (Operator Kit) — renderiza a gate-sheet (itens que dependem do humano).

Lê `paths.gate_sheet` do operator-profile.yaml e mostra, num painel, tudo que
está esperando o humano (billing/OAuth/legal/cliente/deploy-go/secret/decisão) —
o "/gates" do kit. Não decide nada; só consolida o que o loop / gate-sheet-collector
já marcou, p/ o humano limpar numa sentada.

Extrai como gate:
  • linhas de checkbox aberto  '- [ ]'
  • linhas de tabela markdown  '| ... |' dentro de uma seção cujo header casa GATE/HUMANO/MAX
  • linhas iniciadas por marcador 🔴/⛔/GATE:

CLI: gate_sheet_panel.py [--json] [--sheet <path>]   ·   --self-test (fixture em tmp)
exit 0 sempre. stdlib + PyYAML (via loader).
v1.0.0 — 2026-06-19 (Operator Kit · Tier 2)
"""
from __future__ import annotations

import json
import re
import sys
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

_GATE_HDR = re.compile(r"^#{1,6}.*\b(GATE|HUMANO|MAX|HUMAN)\b", re.I)


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


def extract_gates(text: str) -> list[str]:
    """Itens de gate a partir do markdown da gate-sheet. Dedup, ordem preservada."""
    gates: list[str] = []
    in_gate_section = False
    for line in text.splitlines():
        s = line.strip()
        if line.lstrip().startswith("#"):
            in_gate_section = bool(_GATE_HDR.match(line.strip()))
            continue
        if re.match(r"^[-*]\s*\[ \]", s):
            gates.append(re.sub(r"^[-*]\s*\[ \]\s*", "", s))
        elif s.startswith(("🔴", "⛔")) or re.match(r"^GATE\s*[:\-]", s, re.I):
            gates.append(s.lstrip("🔴⛔ ").strip())
        elif in_gate_section and s.startswith("|") and s.count("|") >= 2:
            cells = [c.strip() for c in s.strip("|").split("|")]
            if cells and not re.match(r"^[-:\s]+$", cells[0]) and cells[0].lower() not in ("gate", "item", "#"):
                gates.append(" · ".join(c for c in cells if c))
    # dedup preservando ordem
    seen, out = set(), []
    for g in gates:
        if g and g not in seen:
            seen.add(g)
            out.append(g)
    return out


def _sheet_path(root: Path, argv) -> Path | None:
    if "--sheet" in argv:
        i = argv.index("--sheet")
        if i + 1 < len(argv):
            return Path(argv[i + 1])
    gs = get(load_profile() if load_profile else {}, "paths.gate_sheet", "")
    return (root / gs) if gs else None


def render(gates: list[str], src: str) -> str:
    if not gates:
        return f"✅ GATE-SHEET empty (no open human gate)\n   source: {src}"
    lines = [f"🔴 GATE-SHEET — {len(gates)} item(s) waiting on the human", f"   source: {src}", ""]
    lines += [f"  {i:>2}. {g}" for i, g in enumerate(gates, 1)]
    return "\n".join(lines)


def main(argv) -> int:
    root = _root()
    sheet = _sheet_path(root, argv)
    if sheet is None or not sheet.exists():
        print(f"gate_sheet_panel: gate-sheet not found ({sheet}) — set paths.gate_sheet", file=sys.stderr)
        return 0
    try:
        text = sheet.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    gates = extract_gates(text)
    if "--json" in argv:
        print(json.dumps({"count": len(gates), "gates": gates, "source": str(sheet)}, ensure_ascii=False, indent=2))
    else:
        print(render(gates, str(sheet)))
    return 0


def _self_test() -> None:
    import tempfile
    sample = (
        "# Plan\n- [x] done\n- [ ] operator decision pending\n"
        "## HUMAN GATE FORM\n| Gate | Command |\n|---|---|\n| billing | open the panel |\n"
        "🔴 rotate the CF secret\nordinary text ignored\n"
    )
    gates = extract_gates(sample)
    assert "operator decision pending" in gates, gates
    assert any("billing" in g for g in gates), gates
    assert any("rotate the CF secret" in g for g in gates), gates
    assert "ordinary text ignored" not in gates
    assert "done" not in gates  # [x] is not an open gate
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "gates.md"
        f.write_text(sample, encoding="utf-8")
        assert "3 item" in render(extract_gates(f.read_text(encoding="utf-8")), str(f))
    assert "empty" in render([], "x")
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
