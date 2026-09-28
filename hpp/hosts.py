"""Host x module x channel matrix, derived from the manifest and rendered for the documents.

`hosts` in each module entry says how a host integrates a module (`native`, `explicit-command`,
`unsupported`); the channels say how the module gets there. Claude Code installs every module from
the plugin marketplace and arms declared hooks once the wiring is pasted. Codex CLI installs a module
that carries skills from the product's Codex plugin marketplace (skills only: the hooks are Claude
Code's, and on Codex the same capabilities stay explicit commands) and any supported module by
verified copy through the module installer. The documents carry the render, and a test keeps them
equal to it.
"""
from __future__ import annotations

from typing import Any

HOSTS = ("claude-code", "codex")
PLUGIN = "plugin"
HOOKS = "hooks"
SKILLS_PLUGIN = "plugin (skills)"
COPY = "copy"

_TEXT: dict[str, dict[str, str]] = {
    "en": {"module": "module", "claude-code": "Claude Code", "codex": "Codex CLI", "none": "—",
           PLUGIN: "plugin", HOOKS: "hooks after the wiring is pasted",
           SKILLS_PLUGIN: "plugin (skills only)", COPY: "verified copy"},
    "pt-BR": {"module": "módulo", "claude-code": "Claude Code", "codex": "Codex CLI", "none": "—",
              PLUGIN: "plugin", HOOKS: "hooks depois de colar o wiring",
              SKILLS_PLUGIN: "plugin (só skills)", COPY: "cópia verificada"},
}


def codex_plugin_eligible(module: dict[str, Any]) -> bool:
    """A module joins the Codex plugin channel when Codex supports it and it carries skills."""
    return module["hosts"].get("codex") != "unsupported" and "skills" in module.get("components", [])


def host_matrix(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for module in manifest["modules"]:
        claude = [PLUGIN] + ([HOOKS] if "hooks" in module.get("components", []) else [])
        codex: list[str] = []
        if codex_plugin_eligible(module):
            codex.append(SKILLS_PLUGIN)
        if module["hosts"].get("codex") != "unsupported":
            codex.append(COPY)
        rows.append({
            "id": module["id"],
            "version": module["version"],
            "claude-code": {"integration": module["hosts"]["claude-code"], "channels": claude},
            "codex": {"integration": module["hosts"]["codex"], "channels": codex},
        })
    return rows


def render_host_matrix(manifest: dict[str, Any], lang: str = "en") -> str:
    """The matrix as a Markdown table, one row per module, in the language asked for."""
    if lang not in _TEXT:
        raise ValueError(f"unknown language {lang!r}; known: {', '.join(_TEXT)}")
    text = _TEXT[lang]
    lines = [f"| {text['module']} | {text['claude-code']} | {text['codex']} |", "|---|---|---|"]
    for row in host_matrix(manifest):
        cells = []
        for host in HOSTS:
            channels = " + ".join(text[channel] for channel in row[host]["channels"]) or text["none"]
            cells.append(f"`{row[host]['integration']}` · {channels}")
        lines.append(f"| `{row['id']}` {row['version']} | {cells[0]} | {cells[1]} |")
    return "\n".join(lines) + "\n"
