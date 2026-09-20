#!/usr/bin/env python3
"""
hook-template — scaffold de um hook Claude Code REAL (stdin JSON -> exit code).

Um hook e um EXECUTAVEL (normalmente Python) que o Claude Code invoca para um evento
do ciclo de vida (PreToolUse, PostToolUse, UserPromptSubmit, SessionStart, Stop,
PreCompact, SubagentStop, Notification), passando um payload JSON via STDIN.

Contrato de exit code (o mecanismo REAL — nao e frontmatter .md com trigger:/pattern:):
  0  -> ok. Silencioso, OU imprime JSON com "decision"/"permissionDecision" p/ warn/injetar
        contexto sem bloquear. E o modo WARN-only desta doutrina (nunca bloqueia).
  1  -> erro NAO-bloqueante. Aparece como aviso; a ferramenta/fluxo segue.
  2  -> erro BLOQUEANTE (só faz sentido em PreToolUse). stderr volta pro Claude decidir;
        a ferramenta NAO executa. Use com moderacao — block-mode e a excecao, nao a regra.

Registro (2 formas — nunca frontmatter .md):
  1. Modo PLUGIN: hooks/hooks.json do seu plugin + .claude-plugin/plugin.json referenciando-o.
     Comandos usam ${CLAUDE_PLUGIN_ROOT} (resolvido automaticamente na instalacao).
  2. Modo MANUAL: colar um bloco em .claude/settings.json / settings.local.json:
       "hooks": { "<Evento>": [ { "matcher": "Bash", "hooks": [
         { "type": "command", "command": "python .../este_hook.py", "timeout": 30 }
       ] } ] }

Uso:
    echo '{"tool_name":"Bash","tool_input":{"command":"rm -rf /"}}' | python hook-template.py
    python hook-template.py --self-test

v1.0.0 — 2026-07-10 (claude-dev-kit · scaffold + demo do modo BLOCK)
"""
from __future__ import annotations

import json
import re
import sys

# Padroes que este DEMO bloqueia (troque pela sua logica real).
_DANGEROUS = re.compile(r"\brm\s+-rf\s+/(?:\s|$)")


def decide(payload: dict) -> tuple[int, str]:
    """Retorna (exit_code, mensagem). Isole a LOGICA da leitura de stdin/exit —
    facilita testar sem precisar de um processo real (ver _self_test)."""
    tool_input = payload.get("tool_input") or {}
    command = str(tool_input.get("command") or "")

    if _DANGEROUS.search(command):
        return 2, f"BLOQUEADO: comando destrutivo detectado ({command!r}). Confirme a intenção antes de rodar manualmente."

    return 0, ""


def main(argv) -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        # payload malformado nunca deve travar o fluxo do chamador — degrade seguro.
        return 0

    code, message = decide(payload)
    if message:
        print(message, file=sys.stderr if code == 2 else sys.stdout)
    return code


def _self_test() -> int:
    # 1) comando perigoso -> BLOQUEIA (exit 2)
    code1, msg1 = decide({"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}})
    assert code1 == 2 and "BLOQUEADO" in msg1, (code1, msg1)

    # 2) comando seguro -> passa (exit 0, sem mensagem)
    code2, msg2 = decide({"tool_name": "Bash", "tool_input": {"command": "ls -la"}})
    assert code2 == 0 and msg2 == "", (code2, msg2)

    # 3) payload sem tool_input -> nunca quebra (degrade seguro)
    code3, msg3 = decide({})
    assert code3 == 0

    print("self-test OK — bloqueia comando perigoso (exit 2), libera comando seguro (exit 0), degrada sem tool_input")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    if len(sys.argv) > 1 and sys.argv[1] in ("--self-test", "-t"):
        sys.exit(_self_test())
    else:
        sys.exit(main(sys.argv[1:]))
