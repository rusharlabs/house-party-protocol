#!/usr/bin/env python3
"""catalogo_md.py — gera o catálogo Markdown de um marketplace a partir da árvore emitida.

Lê `marketplace.json` na raiz e, para cada plugin, lista o que ele contém: skills (nome +
description do frontmatter), commands, agents, hooks (evento → script), rules, templates e
scripts. O resultado é derivado da árvore, nunca escrito à mão — rode de novo depois de
re-emitir os kits e o catálogo acompanha.

Uso:
    python tools/catalogo_md.py <raiz-do-marketplace>            # imprime em stdout
    python tools/catalogo_md.py <raiz-do-marketplace> --write    # grava docs/CATALOGO.md
    python tools/catalogo_md.py --self-test

Exit: 0 ok · 2 raiz sem marketplace.json · 3 erro interno.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

_FRONT = re.compile(r"^---\s*\n(.*?)\n---", re.S)


def _frontmatter(path: Path) -> dict:
    try:
        m = _FRONT.match(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return {}
    if not m:
        return {}
    out: dict = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _hooks(kit: Path) -> list[tuple[str, str]]:
    hj = kit / "hooks" / "hooks.json"
    if not hj.exists():
        # kit que liga os hooks por bloco de settings (install/wiring.*): lista os scripts do disco
        return [("(wiring pelo instalador)", f"`{h.name}`") for h in sorted((kit / "hooks").glob("*.py"))
                if not h.name.startswith("_")] if (kit / "hooks").is_dir() else []
    try:
        data = json.loads(hj.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows: list[tuple[str, str]] = []
    for evento, blocos in (data.get("hooks") or {}).items():
        for bloco in blocos or []:
            for h in bloco.get("hooks") or []:
                cmd = h.get("command", "")
                script = re.findall(r"hooks/([A-Za-z0-9_.-]+\.(?:py|sh))\"?\s*$", cmd)
                nome = script[-1] if script else cmd
                if nome.endswith("pyrun.sh") and len(script) > 1:
                    nome = script[-1]
                matcher = bloco.get("matcher") or "*"
                rows.append((f"{evento} · `{matcher}`", f"`{nome}`"))
    return rows


def _lista(kit: Path, rel: str, padrao: str) -> list[Path]:
    return sorted((kit / rel).glob(padrao)) if (kit / rel).is_dir() else []


def _documentos(kit: Path) -> list[Path]:
    docs = kit / "docs"
    return sorted(path for path in docs.rglob("*") if path.is_file()) if docs.is_dir() else []


def catalogo(raiz: Path) -> str:
    mk = json.loads((raiz / "marketplace.json").read_text(encoding="utf-8"))
    linhas: list[str] = []
    w = linhas.append
    w(f"# Catálogo — {mk.get('name', 'marketplace')}")
    w("")
    w("Derivado da árvore emitida: o que cada kit instala, recurso por recurso. Regenerar com")
    w("`python instaladores/kit-forge-*/tools/catalogo_md.py . --write`.")
    w("")
    recursos = sorted(
        path for path in (raiz / "docs").glob("*")
        if path.is_file() and path.name != "CATALOGO.md"
    ) if (raiz / "docs").is_dir() else []
    if recursos:
        w("## Recursos transversais")
        w("")
        w("Documentos válidos para todos os kits: " + " · ".join(f"[`{p.name}`]({p.name})" for p in recursos))
        w("")
    totais = dict(skills=0, commands=0, agents=0, hooks=0, rules=0, templates=0, scripts=0)
    w("| kit | versão | skills | commands | agents | hooks | rules | templates | scripts |")
    w("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    detalhes: list[str] = []
    for pl in mk.get("plugins", []):
        kit = raiz / pl["source"].lstrip("./")
        skills = _lista(kit, "skills", "*/SKILL.md")
        commands = _lista(kit, "commands", "*.md")
        agents = [path for path in _lista(kit, "agents", "*.md") if not path.name.startswith("NOTICE-")]
        hooks = _hooks(kit)
        rules = _lista(kit, "rules", "*.md")
        templates = _lista(kit, "templates", "*")
        scripts = _lista(kit, "scripts", "*.py")
        documentos = _documentos(kit)
        n = dict(skills=len(skills), commands=len(commands), agents=len(agents), hooks=len(hooks),
                 rules=len(rules), templates=len(templates), scripts=len(scripts))
        for k, v in n.items():
            totais[k] += v
        w(f"| [{pl['name']}](#{pl['name']}) | {pl.get('version', '')} | " + " | ".join(str(n[k]) for k in totais) + " |")

        d = detalhes.append
        d(f"## {pl['name']}")
        d("")
        d(pl.get("description", "").strip())
        d("")
        if skills:
            d("**Skills**")
            d("")
            d("| skill | o que faz |")
            d("|---|---|")
            for s in skills:
                fm = _frontmatter(s)
                d(f"| `{fm.get('name', s.parent.name)}` | {fm.get('description', '')} |")
            d("")
        if commands:
            d("**Commands** — " + " · ".join(f"`/{c.stem}`" for c in commands))
            d("")
        if agents:
            d("**Agents** — " + " · ".join(f"`{a.stem}`" for a in agents))
            d("")
        if hooks:
            d("**Hooks**")
            d("")
            d("| evento | script |")
            d("|---|---|")
            for ev, sc in hooks:
                d(f"| {ev} | {sc} |")
            d("")
        if rules:
            d("**Rules** — " + " · ".join(f"`{r.stem}`" for r in rules))
            d("")
        if templates:
            d("**Templates** — " + " · ".join(f"`{t.name}`" for t in templates))
            d("")
        if scripts:
            d("**Scripts** — " + " · ".join(f"`{s.name}`" for s in scripts))
            d("")
        if documentos:
            d("**Documentos e registros** — " + " · ".join(
                f"`{doc.relative_to(kit).as_posix()}`" for doc in documentos
            ))
            d("")
    w("| **total** | | " + " | ".join(f"**{totais[k]}**" for k in totais) + " |")
    w("")
    linhas.extend(detalhes)
    return "\n".join(linhas).rstrip() + "\n"


def _self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp)
        kit = raiz / "cat" / "demo-kit-1.0.0"
        (kit / "skills" / "ola").mkdir(parents=True)
        (kit / "skills" / "ola" / "SKILL.md").write_text("---\nname: ola\ndescription: diz ola\n---\n# ola\n", encoding="utf-8")
        (kit / "hooks").mkdir()
        (kit / "hooks" / "hooks.json").write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": 'bash "${CLAUDE_PLUGIN_ROOT}/hooks/pyrun.sh" "${CLAUDE_PLUGIN_ROOT}/hooks/guard.py"'}]}]}}), encoding="utf-8")
        (kit / "rules").mkdir()
        (kit / "rules" / "r1.md").write_text("# r1\n", encoding="utf-8")
        (kit / "agents").mkdir()
        (kit / "agents" / "checker.md").write_text("---\nname: checker\ndescription: fixture\ntools: [Read]\n---\n", encoding="utf-8")
        (kit / "agents" / "NOTICE-ECC.md").write_text("# notice\n", encoding="utf-8")
        (kit / "docs").mkdir()
        (kit / "docs" / "RUNBOOK.md").write_text("# runbook\n", encoding="utf-8")
        (raiz / "docs").mkdir()
        (raiz / "docs" / "TIPS.md").write_text("# tips\n", encoding="utf-8")
        (raiz / "marketplace.json").write_text(json.dumps({"name": "demo", "plugins": [
            {"name": "demo-kit", "version": "1.0.0", "source": "./cat/demo-kit-1.0.0", "description": "kit de teste"}]}), encoding="utf-8")
        md = catalogo(raiz)
        assert "| [demo-kit](#demo-kit) | 1.0.0 | 1 | 0 | 1 | 1 | 1 | 0 | 0 |" in md, md
        assert "| `ola` | diz ola |" in md and "| PreToolUse · `Bash` | `guard.py` |" in md and "`r1`" in md, md
        assert "## Recursos transversais" in md and "`TIPS.md`" in md
        assert "**Documentos e registros**" in md and "`docs/RUNBOOK.md`" in md
        assert "`checker`" in md and "NOTICE-ECC" not in md
        # controle: kit sem nada nao inventa secao
        assert "**Commands**" not in md and "**Templates**" not in md
    print("self-test OK")
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return _self_test()
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    raiz = Path(argv[0]).resolve()
    if not (raiz / "marketplace.json").exists():
        print(f"catalogo_md: sem marketplace.json em {raiz}", file=sys.stderr)
        return 2
    try:
        md = catalogo(raiz)
    except Exception as exc:  # noqa: BLE001 -- Why: erro de leitura vira exit 3 com a causa, nunca um catálogo pela metade
        print(f"catalogo_md: erro: {exc}", file=sys.stderr)
        return 3
    if "--write" in argv:
        alvo = raiz / "docs" / "CATALOGO.md"
        alvo.parent.mkdir(exist_ok=True)
        alvo.write_text(md, encoding="utf-8", newline="\n")
        print(f"gravado: {alvo} ({len(md)} bytes)")
    else:
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
