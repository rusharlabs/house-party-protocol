#!/usr/bin/env python3
"""catalog_md.py — bilingual module catalogue of a marketplace, derived from its emitted tree.

Reads `marketplace.json` at the root and, for each plugin, lists what it ships: skills (name +
frontmatter description), commands, agents, hooks (event -> script), rules, templates, scripts
and documents. ONE pass over the tree feeds FOUR derived files — none of them hand-written, so
re-emit the kits, run this again, and the catalogue follows:

    docs/CATALOG.md          English Markdown (the source-of-truth language)
    docs/CATALOG.pt-BR.md    Portuguese Markdown — same headings order, same tables, same code
    docs/CATALOG.html        English HTML page: the four brand tokens, zero external requests
    docs/CATALOG.pt-BR.html  Portuguese HTML page, language switch + hreflang like MANUAL.html

Kit descriptions come from `marketplace.json`: `plugins[].description` — the field Claude Code's
`/plugin` UI shows, so it is English — feeds the English side and `plugins[].description_pt` the
Portuguese one. A kit without `description_pt` falls back to `description`, so the gap is visible
on the Portuguese page instead of silently hidden.

The HTML pair opens with the same lockup MANUAL.html opens with (`../assets/hpp-logo-dark.svg`,
relative to `docs/`) and closes with the five words — the catalogue is a page of the product and
looks like one.

Usage:
    python tools/catalog_md.py <marketplace-root>            # prints the English Markdown
    python tools/catalog_md.py <marketplace-root> --write    # writes the four files under docs/
    python tools/catalog_md.py --self-test

Exit: 0 ok · 2 root without marketplace.json · 3 internal error.
"""
from __future__ import annotations

import html
import json
import re
import sys
import tempfile
from pathlib import Path

_FRONT = re.compile(r"^---\s*\n(.*?)\n---", re.S)
_INLINE_CODE = re.compile(r"`([^`]+)`")

LANGS = ("en", "pt-BR")
# Why: the four outputs are the catalogue itself — they never appear in their own "shared
# resources" list, otherwise every re-run would grow the list by one self-reference.
OUTPUTS = {
    "en": {"md": "CATALOG.md", "html": "CATALOG.html"},
    "pt-BR": {"md": "CATALOG.pt-BR.md", "html": "CATALOG.pt-BR.html"},
}
OWN_FILES = frozenset(name for lang in OUTPUTS.values() for name in lang.values())
# Why: BRAND.md declares exactly four tokens; any other hex in the page is palette drift.
BRAND = {"black": "#000000", "ink": "#0F1113", "paper": "#F4F1EB", "signal": "#FF6A00"}
# Why: the pair link and the regeneration command are identical on both sides on purpose — the
# bilingual gate compares code and the reader switches language by the same two words.
PAIR_LINKS = f"[English]({OUTPUTS['en']['md']}) · [Português]({OUTPUTS['pt-BR']['md']})"
REGEN_CMD = "python installers/kit-forge-*/tools/catalog_md.py . --write"
COUNT_KEYS = ("skills", "commands", "agents", "hooks", "rules", "templates", "scripts")
# Why: the header is the MANUAL's header — the lockup is read from `docs/MANUAL.html` next to the
# outputs, so the two pages cannot drift apart, and this tool (which ships inside every copy of
# kit-forge) never carries the brand credit itself: the IP gate bans that string here, while the
# product page next to it declares the exception. Only a sibling `../assets/` path qualifies — an
# absolute URL in the MANUAL would not be imported as a request into the catalogue.
LOCKUP_SRC = "../assets/hpp-logo-dark.svg"
_LOCKUP = re.compile(r'<img\s[^>]*src="\.\./assets/[^"]+"[^>]*>')
# Why: the five words are a label (BRAND.md), upper case and spaced, never a sentence.
FIVE_WORDS = "AGENTS · EVIDENCE · MEMORY · PROTOCOL · CONTINUITY"
_HOOK_SCRIPT = re.compile(r"hooks/([A-Za-z0-9_.-]+\.(?:py|sh))\"?")

_T: dict[str, dict[str, object]] = {
    "en": {
        "title": "Catalogue — {name}",
        "lead": "Derived from the emitted tree: what each kit installs, resource by resource. Regenerate with",
        "shared_h": "Shared resources",
        "shared_lead": "Documents that apply to every kit: ",
        "th": ("kit", "version") + COUNT_KEYS,
        "total": "total",
        "skills_h": "Skills", "skills_th": ("skill", "what it does"),
        "commands_h": "Commands", "agents_h": "Agents",
        "hooks_h": "Hooks", "hooks_th": ("event", "script"), "wiring": "(wired by the installer)",
        "rules_h": "Rules", "templates_h": "Templates", "scripts_h": "Scripts",
        "docs_h": "Documents and records",
        "html_title": "Module catalogue",
        "html_eyebrow": "{display} · modules",
        "html_meta": "Module catalogue of {display}: what each kit installs, resource by resource, derived from the emitted tree.",
        "summary_h": "Kits at a glance",
        "manual": "Harness manual", "manual_href": "MANUAL.html",
        "readme_href": "../README.md",
        "markdown": "Markdown catalogue",
    },
    "pt-BR": {
        "title": "Catálogo — {name}",
        "lead": "Derivado da árvore emitida: o que cada kit instala, recurso por recurso. Regenerar com",
        "shared_h": "Recursos transversais",
        "shared_lead": "Documentos válidos para todos os kits: ",
        "th": ("kit", "versão") + COUNT_KEYS,
        "total": "total",
        "skills_h": "Skills", "skills_th": ("skill", "o que faz"),
        "commands_h": "Commands", "agents_h": "Agents",
        "hooks_h": "Hooks", "hooks_th": ("evento", "script"), "wiring": "(wiring pelo instalador)",
        "rules_h": "Rules", "templates_h": "Templates", "scripts_h": "Scripts",
        "docs_h": "Documentos e registros",
        "html_title": "Catálogo de módulos",
        "html_eyebrow": "{display} · módulos",
        "html_meta": "Catálogo de módulos do {display}: o que cada kit instala, recurso por recurso, derivado da árvore emitida.",
        "summary_h": "Kits em resumo",
        "manual": "Manual do harness", "manual_href": "MANUAL.pt-BR.html",
        "readme_href": "../README.pt-BR.md",
        "markdown": "Catálogo em Markdown",
    },
}


# ----------------------------------------------------------------------------- tree reading

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


def _hooks(kit: Path) -> list[tuple[str | None, str | None, str]]:
    """(event, matcher, script) per wired hook; (None, None, script) when the kit wires by
    installer settings block and only the scripts on disk can be listed."""
    hj = kit / "hooks" / "hooks.json"
    if not hj.exists():
        if not (kit / "hooks").is_dir():
            return []
        return [(None, None, h.name) for h in sorted((kit / "hooks").glob("*.py"))
                if not h.name.startswith("_")]
    try:
        data = json.loads(hj.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows: list[tuple[str | None, str | None, str]] = []
    for event, blocks in (data.get("hooks") or {}).items():
        for block in blocks or []:
            for h in block.get("hooks") or []:
                cmd = h.get("command", "")
                # Why: the last `hooks/<name>.py|.sh` in the command is the hook (the first may be
                # the pyrun.sh shim), and whatever follows it is an explicit argument that belongs
                # in the listing — lane-kit wires `lane_register.py --heartbeat`. An end-anchored
                # regex missed that command and printed the whole shell line instead.
                matches = list(_HOOK_SCRIPT.finditer(cmd))
                name = (matches[-1].group(1) + cmd[matches[-1].end():].rstrip()) if matches else cmd
                rows.append((event, block.get("matcher") or "*", name))
    return rows


def _lista(kit: Path, rel: str, pattern: str) -> list[Path]:
    return sorted((kit / rel).glob(pattern)) if (kit / rel).is_dir() else []


def _documents(kit: Path) -> list[Path]:
    docs = kit / "docs"
    return sorted(path for path in docs.rglob("*") if path.is_file()) if docs.is_dir() else []


def _lockup(root: Path, display: str) -> str:
    """The `<img>` MANUAL.html opens with; without a MANUAL, the same asset with the plain name."""
    manual = root / "docs" / "MANUAL.html"
    if manual.is_file():
        m = _LOCKUP.search(manual.read_text(encoding="utf-8", errors="replace"))
        if m:
            return m.group(0)
    return f'<img src="{LOCKUP_SRC}" alt="{html.escape(display)}">'


def build_model(root: Path) -> dict:
    """Everything the four renderers need, read once. Language-neutral except `description`."""
    mk = json.loads((root / "marketplace.json").read_text(encoding="utf-8"))
    shared = sorted(
        path.name for path in (root / "docs").glob("*")
        if path.is_file() and path.name not in OWN_FILES
    ) if (root / "docs").is_dir() else []
    kits: list[dict] = []
    totals = dict.fromkeys(COUNT_KEYS, 0)
    for pl in mk.get("plugins", []):
        kit = root / pl["source"].lstrip("./")
        skills = [(fm.get("name", s.parent.name), fm.get("description", ""))
                  for s in _lista(kit, "skills", "*/SKILL.md") for fm in (_frontmatter(s),)]
        entry = {
            "name": pl["name"],
            "version": pl.get("version", ""),
            "description": {
                # Why: the fallback is deliberate — a Portuguese page showing English is a
                # visible gap; an empty paragraph would hide it.
                "en": pl.get("description", "").strip(),
                "pt-BR": (pl.get("description_pt") or pl.get("description", "")).strip(),
            },
            "skills": skills,
            "commands": [c.stem for c in _lista(kit, "commands", "*.md")],
            "agents": [a.stem for a in _lista(kit, "agents", "*.md") if not a.name.startswith("NOTICE-")],
            "hooks": _hooks(kit),
            "rules": [r.stem for r in _lista(kit, "rules", "*.md")],
            "templates": [t.name for t in _lista(kit, "templates", "*")],
            "scripts": [s.name for s in _lista(kit, "scripts", "*.py")],
            "documents": [doc.relative_to(kit).as_posix() for doc in _documents(kit)],
        }
        entry["counts"] = {k: len(entry[k]) for k in COUNT_KEYS}
        for k, v in entry["counts"].items():
            totals[k] += v
        kits.append(entry)
    name = mk.get("name", "marketplace")
    display = " ".join(part.capitalize() for part in name.split("-"))
    return {
        "name": name,
        "display": display,
        "lockup": _lockup(root, display),
        "shared": shared,
        "kits": kits,
        "totals": totals,
    }


# ----------------------------------------------------------------------------- markdown

def render_md(model: dict, lang: str) -> str:
    t = _T[lang]
    lines: list[str] = []
    w = lines.append
    w(PAIR_LINKS)
    w("")
    w("# " + str(t["title"]).format(name=model["name"]))
    w("")
    w(str(t["lead"]))
    w(f"`{REGEN_CMD}`.")
    w("")
    if model["shared"]:
        w("## " + str(t["shared_h"]))
        w("")
        w(str(t["shared_lead"]) + " · ".join(f"[`{n}`]({n})" for n in model["shared"]))
        w("")
    w("| " + " | ".join(t["th"]) + " |")
    w("|---|---|" + "---:|" * len(COUNT_KEYS))
    for kit in model["kits"]:
        w(f"| [{kit['name']}](#{kit['name']}) | {kit['version']} | "
          + " | ".join(str(kit["counts"][k]) for k in COUNT_KEYS) + " |")
    w(f"| **{t['total']}** | | " + " | ".join(f"**{model['totals'][k]}**" for k in COUNT_KEYS) + " |")
    w("")
    for kit in model["kits"]:
        w(f"## {kit['name']}")
        w("")
        w(kit["description"][lang])
        w("")
        if kit["skills"]:
            w(f"**{t['skills_h']}**")
            w("")
            w("| " + " | ".join(t["skills_th"]) + " |")
            w("|---|---|")
            for name, desc in kit["skills"]:
                w(f"| `{name}` | {desc} |")
            w("")
        if kit["commands"]:
            w(f"**{t['commands_h']}** — " + " · ".join(f"`/{c}`" for c in kit["commands"]))
            w("")
        if kit["agents"]:
            w(f"**{t['agents_h']}** — " + " · ".join(f"`{a}`" for a in kit["agents"]))
            w("")
        if kit["hooks"]:
            w(f"**{t['hooks_h']}**")
            w("")
            w("| " + " | ".join(t["hooks_th"]) + " |")
            w("|---|---|")
            for event, matcher, script in kit["hooks"]:
                ev = str(t["wiring"]) if event is None else f"{event} · `{matcher}`"
                w(f"| {ev} | `{script}` |")
            w("")
        if kit["rules"]:
            w(f"**{t['rules_h']}** — " + " · ".join(f"`{r}`" for r in kit["rules"]))
            w("")
        if kit["templates"]:
            w(f"**{t['templates_h']}** — " + " · ".join(f"`{x}`" for x in kit["templates"]))
            w("")
        if kit["scripts"]:
            w(f"**{t['scripts_h']}** — " + " · ".join(f"`{s}`" for s in kit["scripts"]))
            w("")
        if kit["documents"]:
            w(f"**{t['docs_h']}** — " + " · ".join(f"`{d}`" for d in kit["documents"]))
            w("")
    return "\n".join(lines).rstrip() + "\n"


# ----------------------------------------------------------------------------- html

_CSS = (
    ":root{--hpp-black: " + BRAND["black"] + ";--hpp-ink: " + BRAND["ink"] + ";--hpp-paper: " + BRAND["paper"]
    + ";--hpp-signal: " + BRAND["signal"]
    + ";--line:rgba(15,17,19,.18);--surface:rgba(15,17,19,.04);--muted:rgba(15,17,19,.72);--max:1120px}\n"
    "*{box-sizing:border-box}\n"
    "html{scroll-behavior:smooth}\n"
    "body{margin:0;background:var(--hpp-paper);color:var(--hpp-ink);font:16px/1.6 Inter,\"Segoe UI\",Arial,sans-serif}\n"
    "a{color:var(--hpp-ink);text-decoration:underline;text-decoration-color:var(--hpp-signal);"
    "text-decoration-thickness:2px;text-underline-offset:3px}\n"
    "a:hover{color:var(--hpp-signal)}\n"
    "a:focus-visible{outline:4px solid var(--hpp-signal);outline-offset:3px}\n"
    ".wrap{width:min(var(--max),calc(100% - 40px));margin:auto}\n"
    ".lang{background:var(--hpp-black);color:var(--hpp-paper);font-size:.9rem;padding:10px 0}\n"
    ".lang a{color:var(--hpp-paper)}\n"
    ".lang a[aria-current]{text-decoration:none;font-weight:700}\n"
    ".hero{background:var(--hpp-ink);color:var(--hpp-paper);padding:44px 0 50px;border-bottom:8px solid var(--hpp-signal)}\n"
    ".hero img{width:min(720px,100%);display:block}\n"
    ".hero h1{font:800 clamp(2.2rem,6vw,4.6rem)/.95 Sora,Inter,\"Segoe UI\",sans-serif;letter-spacing:-.02em;margin:.35em 0}\n"
    ".hero p{max-width:760px;font-size:1.1rem;color:rgba(244,241,235,.82)}\n"
    ".hero code{color:var(--hpp-paper)}\n"
    ".eyebrow,code,.mono{font-family:\"JetBrains Mono\",\"Cascadia Code\",Consolas,monospace}\n"
    ".eyebrow{display:inline-block;letter-spacing:.13em;text-transform:uppercase;font-size:.78rem;"
    "border-left:4px solid var(--hpp-signal);padding-left:.6em;margin:0 0 .6em;color:var(--hpp-paper)}\n"
    "main{padding:24px 0 56px}\n"
    "section{padding:36px 0;border-bottom:1px solid var(--line)}\n"
    "h2{font:800 clamp(1.5rem,3vw,2.2rem)/1.1 Sora,Inter,\"Segoe UI\",sans-serif;letter-spacing:-.01em;margin:0 0 .5em}\n"
    "h2 .version{font:700 .8rem/1 \"JetBrains Mono\",Consolas,monospace;color:var(--hpp-paper);"
    "background:var(--hpp-ink);border-radius:999px;padding:.35em .7em;vertical-align:middle;margin-left:.5em}\n"
    "h3{margin:1.4em 0 .4em;font-size:1rem;letter-spacing:.04em;text-transform:uppercase;color:var(--muted)}\n"
    ".lead{max-width:780px;color:var(--muted)}\n"
    "table{border-collapse:collapse;width:100%;font-size:.95rem;background:var(--surface);border:1px solid var(--line)}\n"
    "th,td{text-align:left;padding:.55em .8em;border-bottom:1px solid var(--line);vertical-align:top}\n"
    "th{font-size:.78rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}\n"
    "td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}\n"
    "tr.total td{font-weight:700;border-top:2px solid var(--hpp-ink)}\n"
    ".chips code{display:inline-block;background:var(--surface);border:1px solid var(--line);"
    "border-radius:6px;padding:.15em .5em;margin:.15em .35em .15em 0}\n"
    "footer{padding:48px 0;background:var(--hpp-black);color:var(--hpp-paper);font-size:.9rem}\n"
    "footer a{color:var(--hpp-paper)}\n"
    "footer .five{letter-spacing:.2em;font-size:.8rem;color:rgba(244,241,235,.72)}\n"
    "@media(max-width:700px){.wrap{width:calc(100% - 26px)}table{display:block;overflow-x:auto}}\n"
)


def _inline(text: str) -> str:
    """Escape for HTML, then honour the Markdown inline code the descriptions already carry."""
    return _INLINE_CODE.sub(r"<code>\1</code>", html.escape(text, quote=False))


def _chips(items: list[str], prefix: str = "") -> str:
    return " ".join(f"<code>{html.escape(prefix + item)}</code>" for item in items)


def render_html(model: dict, lang: str) -> str:
    t = _T[lang]
    other = "pt-BR" if lang == "en" else "en"
    esc = html.escape
    display = model["display"]
    lines: list[str] = []
    w = lines.append
    w("<!doctype html>")
    w(f'<html lang="{lang}">')
    w("<head>")
    w('  <meta charset="utf-8">')
    w('  <meta name="viewport" content="width=device-width, initial-scale=1">')
    w(f"  <title>{esc(display)} — {esc(str(t['html_title']))}</title>")
    w(f'  <meta name="description" content="{esc(str(t["html_meta"]).format(display=display))}">')
    for code in LANGS:
        w(f'  <link rel="alternate" hreflang="{code}" href="{OUTPUTS[code]["html"]}">')
    w("  <style>")
    w(_CSS.rstrip())
    w("  </style>")
    w("</head>")
    w("<body>")
    # Why: same switch as MANUAL.html — the current page is marked, the other side is linked,
    # both carry hreflang so a reader (or a crawler) can tell the pair apart.
    switch = {
        "en": f'<a href="{OUTPUTS["en"]["html"]}" hreflang="en">English</a>',
        "pt-BR": f'<a href="{OUTPUTS["pt-BR"]["html"]}" hreflang="pt-BR" lang="pt-BR">Português</a>',
    }
    switch[lang] = switch[lang].replace('" hreflang=', '" aria-current="page" hreflang=', 1)
    w(f'  <div class="lang"><div class="wrap">{switch["en"]} · {switch["pt-BR"]}</div></div>')
    w('  <header class="hero"><div class="wrap">')
    w(f"    {model['lockup']}")
    w(f'    <p class="eyebrow">{esc(str(t["html_eyebrow"]).format(display=display))}</p>')
    w(f"    <h1>{esc(str(t['html_title']))}</h1>")
    w(f"    <p>{esc(str(t['lead']))} <code>{esc(REGEN_CMD)}</code>.</p>")
    w("  </div></header>")
    w('  <main class="wrap">')
    w('    <section id="summary">')
    w(f"      <h2>{esc(str(t['summary_h']))}</h2>")
    w("      <table>")
    # Why: the two label columns stay left-aligned; every count column is numeric.
    ths = [f"<th>{esc(h)}</th>" for h in list(t["th"])[:2]]
    ths += [f'<th class="n">{esc(h)}</th>' for h in list(t["th"])[2:]]
    w("        <thead><tr>" + "".join(ths) + "</tr></thead>")
    w("        <tbody>")
    for kit in model["kits"]:
        cells = "".join(f'<td class="n">{kit["counts"][k]}</td>' for k in COUNT_KEYS)
        w(f'          <tr><td><a href="#{esc(kit["name"])}">{esc(kit["name"])}</a></td>'
          f'<td class="mono">{esc(kit["version"])}</td>{cells}</tr>')
    w(f'          <tr class="total"><td>{esc(str(t["total"]))}</td><td></td>'
      + "".join(f'<td class="n">{model["totals"][k]}</td>' for k in COUNT_KEYS) + "</tr>")
    w("        </tbody>")
    w("      </table>")
    w("    </section>")
    if model["shared"]:
        w('    <section id="shared">')
        w(f"      <h2>{esc(str(t['shared_h']))}</h2>")
        w(f"      <p>{esc(str(t['shared_lead']))}"
          + " · ".join(f'<a href="{esc(n)}"><code>{esc(n)}</code></a>' for n in model["shared"]) + "</p>")
        w("    </section>")
    for kit in model["kits"]:
        w(f'    <section id="{esc(kit["name"])}" class="kit">')
        w(f'      <h2>{esc(kit["name"])} <span class="version">{esc(kit["version"])}</span></h2>')
        if kit["description"][lang]:
            w(f'      <p class="lead">{_inline(kit["description"][lang])}</p>')
        if kit["skills"]:
            w(f"      <h3>{esc(str(t['skills_h']))}</h3>")
            w("      <table>")
            w("        <thead><tr>" + "".join(f"<th>{esc(h)}</th>" for h in t["skills_th"]) + "</tr></thead>")
            w("        <tbody>")
            for name, desc in kit["skills"]:
                w(f"          <tr><td><code>{esc(name)}</code></td><td>{_inline(desc)}</td></tr>")
            w("        </tbody>")
            w("      </table>")
        if kit["commands"]:
            w(f"      <h3>{esc(str(t['commands_h']))}</h3>")
            w(f'      <p class="chips">{_chips(kit["commands"], "/")}</p>')
        if kit["agents"]:
            w(f"      <h3>{esc(str(t['agents_h']))}</h3>")
            w(f'      <p class="chips">{_chips(kit["agents"])}</p>')
        if kit["hooks"]:
            w(f"      <h3>{esc(str(t['hooks_h']))}</h3>")
            w("      <table>")
            w("        <thead><tr>" + "".join(f"<th>{esc(h)}</th>" for h in t["hooks_th"]) + "</tr></thead>")
            w("        <tbody>")
            for event, matcher, script in kit["hooks"]:
                ev = esc(str(t["wiring"])) if event is None else f"{esc(event)} · <code>{esc(matcher or '*')}</code>"
                w(f"          <tr><td>{ev}</td><td><code>{esc(script)}</code></td></tr>")
            w("        </tbody>")
            w("      </table>")
        for key, label in (("rules", "rules_h"), ("templates", "templates_h"),
                           ("scripts", "scripts_h"), ("documents", "docs_h")):
            if kit[key]:
                w(f"      <h3>{esc(str(t[label]))}</h3>")
                w(f'      <p class="chips">{_chips(kit[key])}</p>')
        w("    </section>")
    w("  </main>")
    w('  <footer><div class="wrap">')
    w(f'    <p class="five">{FIVE_WORDS}</p>')
    w(f'    <p><a href="{t["manual_href"]}">{esc(str(t["manual"]))}</a> · '
      f'<a href="{t["readme_href"]}">README</a> · '
      f'<a href="{OUTPUTS[lang]["md"]}">{esc(str(t["markdown"]))}</a> · '
      f'<a href="{OUTPUTS[other]["html"]}" hreflang="{other}">{"Português" if other == "pt-BR" else "English"}</a></p>')
    w("  </div></footer>")
    w("</body>")
    w("</html>")
    return "\n".join(lines) + "\n"


def render_all(root: Path) -> dict[str, str]:
    """{file name: content} for the four outputs, from one read of the tree."""
    model = build_model(root)
    out: dict[str, str] = {}
    for lang in LANGS:
        out[OUTPUTS[lang]["md"]] = render_md(model, lang)
        out[OUTPUTS[lang]["html"]] = render_html(model, lang)
    return out


# ----------------------------------------------------------------------------- self-test

def write_fixture_tree(root: Path) -> None:
    """A two-kit marketplace with every resource kind — shared by the self-test and the suite.

    `demo-kit` carries `description_pt`; `lone-kit` does not, so the fallback is observable.
    `demo-kit` also wires one hook with an argument after the script (`beat.py --heartbeat`)."""
    kit = root / "cat" / "demo-kit-1.0.0"
    (kit / "skills" / "ola").mkdir(parents=True)
    (kit / "skills" / "ola" / "SKILL.md").write_text("---\nname: ola\ndescription: diz ola\n---\n# ola\n", encoding="utf-8")
    (kit / "hooks").mkdir()
    (kit / "hooks" / "hooks.json").write_text(json.dumps({"hooks": {
        "PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": 'bash "${CLAUDE_PLUGIN_ROOT}/hooks/pyrun.sh" "${CLAUDE_PLUGIN_ROOT}/hooks/guard.py"'}]}],
        "PostToolUse": [{"matcher": "*", "hooks": [
            {"type": "command", "command": 'bash "${CLAUDE_PLUGIN_ROOT}/hooks/pyrun.sh" "${CLAUDE_PLUGIN_ROOT}/hooks/beat.py" --heartbeat'}]}],
    }}), encoding="utf-8")
    (kit / "rules").mkdir()
    (kit / "rules" / "r1.md").write_text("# r1\n", encoding="utf-8")
    (kit / "agents").mkdir()
    (kit / "agents" / "checker.md").write_text("---\nname: checker\ndescription: fixture\ntools: [Read]\n---\n", encoding="utf-8")
    (kit / "agents" / "NOTICE-ECC.md").write_text("# notice\n", encoding="utf-8")
    (kit / "docs").mkdir()
    (kit / "docs" / "RUNBOOK.md").write_text("# runbook\n", encoding="utf-8")
    lone = root / "cat" / "lone-kit-0.1.0"
    (lone / "hooks").mkdir(parents=True)
    (lone / "hooks" / "wired_by_installer.py").write_text("print('hi')\n", encoding="utf-8")
    (lone / "commands").mkdir()
    (lone / "commands" / "go.md").write_text("# go\n", encoding="utf-8")
    (lone / "templates").mkdir()
    (lone / "templates" / "t.md").write_text("# t\n", encoding="utf-8")
    (lone / "scripts").mkdir()
    (lone / "scripts" / "s.py").write_text("x = 1\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "TIPS.md").write_text("# tips\n", encoding="utf-8")
    # Why: a stale copy of the catalogue itself must not be listed as a shared resource.
    (root / "docs" / "CATALOG.html").write_text("<!doctype html>\n", encoding="utf-8")
    # the MANUAL the catalogue borrows its header from — the alt text is the MANUAL's, not ours
    (root / "docs" / "MANUAL.html").write_text(
        '<!doctype html>\n<header class="hero"><div class="wrap">\n'
        f'      <img src="{LOCKUP_SRC}" alt="Demo Market — the approved art">\n'
        "      <h1>Manual</h1>\n</div></header>\n", encoding="utf-8")
    (root / "marketplace.json").write_text(json.dumps({"name": "demo-market", "plugins": [
        {"name": "demo-kit", "version": "1.0.0", "source": "./cat/demo-kit-1.0.0",
         "description": "test kit <with> & signs", "description_pt": "kit de teste <com> & sinais"},
        {"name": "lone-kit", "version": "0.1.0", "source": "./cat/lone-kit-0.1.0",
         "description": "kit without translation"},
    ]}), encoding="utf-8")


def _self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture_tree(root)
        out = render_all(root)
        assert set(out) == OWN_FILES, sorted(out)
        pt, en = out["CATALOG.pt-BR.md"], out["CATALOG.md"]
        for md in (pt, en):
            assert md.startswith(PAIR_LINKS + "\n\n# "), md[:80]
            assert "| [demo-kit](#demo-kit) | 1.0.0 | 1 | 0 | 1 | 2 | 1 | 0 | 0 |" in md, md
            assert "| [lone-kit](#lone-kit) | 0.1.0 | 0 | 1 | 0 | 1 | 0 | 1 | 1 |" in md, md
            assert "| `ola` | diz ola |" in md and "| PreToolUse · `Bash` | `guard.py` |" in md and "`r1`" in md, md
            # the argument after the script survives; the shim never shows as the hook
            assert "| PostToolUse · `*` | `beat.py --heartbeat` |" in md and "`pyrun.sh`" not in md, md
            assert "`TIPS.md`" in md and "`CATALOG.html`" not in md, md
            assert "`checker`" in md and "NOTICE-ECC" not in md
            assert "`docs/RUNBOOK.md`" in md and "`/go`" in md and "`t.md`" in md and "`s.py`" in md, md
        assert "## Recursos transversais" in pt and "**Documentos e registros**" in pt and "(wiring pelo instalador)" in pt
        assert "## Shared resources" in en and "**Documents and records**" in en and "(wired by the installer)" in en
        assert "test kit <with> & signs" in en and "kit de teste <com> & sinais" not in en
        assert "kit de teste <com> & sinais" in pt and "test kit" not in pt
        # control: the kit without description_pt falls back instead of going blank
        assert "kit without translation" in en and "kit without translation" in pt
        # control: a kit with nothing does not grow a section
        assert "**Commands**" not in en.split("## lone-kit")[0].split("## demo-kit")[1]
        # same headings, same order — the bilingual gate's rule, applied here first
        heads = lambda md: [ln for ln in md.splitlines() if ln.startswith("#")]  # noqa: E731
        assert [h.count("#") for h in heads(en)] == [h.count("#") for h in heads(pt)]
        for lang in LANGS:
            page = out[OUTPUTS[lang]["html"]]
            assert page.startswith("<!doctype html>\n<html lang=\"" + lang + '">'), page[:60]
            assert set(re.findall(r"#[0-9A-Fa-f]{6}", page)) == set(BRAND.values()), re.findall(r"#[0-9A-Fa-f]{6}", page)
            assert 'hreflang="en" href="CATALOG.html"' in page and 'hreflang="pt-BR" href="CATALOG.pt-BR.html"' in page
            assert not re.search(r'(?:src|href)="[a-z]+://', page) and "<script" not in page and "@import" not in page, "external request"
            assert "test kit &lt;with&gt; &amp; signs" in page or "kit de teste &lt;com&gt; &amp; sinais" in page
            assert 'id="demo-kit"' in page and 'href="#lone-kit"' in page and "Demo Market" in page
            # the same opening as MANUAL.html: ITS lockup (alt text included) before the <h1>,
            # the five words in the footer, and no other image on the page
            lockup = f'<img src="{LOCKUP_SRC}" alt="Demo Market — the approved art">'
            assert page.count(lockup) == 1 and page.index(lockup) < page.index("<h1>") and FIVE_WORDS in page
            assert re.findall(r'<img\s[^>]*src="([^"]*)"', page) == [LOCKUP_SRC]
        # control: without a MANUAL the header still opens with the asset, under the plain name
        (root / "docs" / "MANUAL.html").unlink()
        page = render_all(root)["CATALOG.html"]
        assert f'<img src="{LOCKUP_SRC}" alt="Demo Market">' in page and "approved art" not in page
        # control: an absolute URL in the MANUAL is not imported as a request into the catalogue
        (root / "docs" / "MANUAL.html").write_text('<img src="https://cdn.example/logo.svg" alt="x">\n', encoding="utf-8")
        page = render_all(root)["CATALOG.html"]
        assert "cdn.example" not in page and f'<img src="{LOCKUP_SRC}" alt="Demo Market">' in page
        assert 'aria-current="page" hreflang="en"' in out["CATALOG.html"]
        assert 'aria-current="page" hreflang="pt-BR"' in out["CATALOG.pt-BR.html"]
    print("self-test OK")
    return 0


# ----------------------------------------------------------------------------- cli

def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return _self_test()
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    root = Path(argv[0]).resolve()
    if not (root / "marketplace.json").exists():
        print(f"catalog_md: no marketplace.json in {root}", file=sys.stderr)
        return 2
    try:
        out = render_all(root)
    except Exception as exc:  # noqa: BLE001 -- Why: a read error becomes exit 3 with its cause, never a half catalogue
        print(f"catalog_md: error: {exc}", file=sys.stderr)
        return 3
    if "--write" in argv:
        docs = root / "docs"
        docs.mkdir(exist_ok=True)
        total = 0
        for name, text in out.items():
            (docs / name).write_text(text, encoding="utf-8", newline="\n")
            total += len(text.encode("utf-8"))
        print(f"written: {docs} — {', '.join(out)} ({total} bytes)")
    else:
        sys.stdout.write(out[OUTPUTS["en"]["md"]])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
