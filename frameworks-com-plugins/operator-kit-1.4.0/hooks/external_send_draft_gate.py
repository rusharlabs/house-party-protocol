#!/usr/bin/env python3
"""
external_send_draft_gate (Operator Kit) — PreToolUse WARN-only: detecta envio
EXTERNO (mensagem a cliente / Discord / POST HTTP p/ host externo) e lembra de
confirmar explicitamente ou salvar um RASCUNHO no draft_dir antes.

Por que existe: comunicação client-facing fica em rascunho até o operador liberar.
Este hook NÃO tenta provar que houve aprovação prévia (impossível de inferir com
segurança); apenas AVISA que a ação parece um envio externo.

Lê JSON do stdin: tool_name + tool_input (command / url / etc.).
Dispara quando:
  (a) tool_name está em guardrails.external_send_tools (do profile), OU
  (b) command é curl/wget com método POST/PUT para um host EXTERNO
      (não localhost / 127.0.0.1 / *.local).

Config (operator-profile.yaml):
  guardrails.external_send_tools: [lista de nomes de tool MCP]
  paths.draft_dir: "drafts/"  (citado no aviso)

WARN em stderr · exit 0 SEMPRE · qualquer erro -> exit 0 (defensivo).

v1.0.0 — 2026-06-19 (Operator Kit · cluster guard-distinct)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from _lib.profile_loader import load_profile, get
except Exception:  # noqa: BLE001
    load_profile = None  # type: ignore[assignment]

    def get(_p, _d, default=None):  # type: ignore[misc]
        return default


_DEFAULT_SEND_TOOLS = [
    "mcp__discord__discord_send_message",
]

# hosts internos que NÃO contam como envio externo
_INTERNAL_HOST_RE = re.compile(
    r"^(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]|.*\.local|.*\.internal)$",
    re.IGNORECASE,
)

# curl/wget com POST/PUT/PATCH (envio de dados)
_POST_FLAG_RE = re.compile(
    r"(?:-X\s*(?:POST|PUT|PATCH)\b|--request\s+(?:POST|PUT|PATCH)\b|--data\b|-d\b|--data-raw\b|--data-binary\b|--upload-file\b|--method=(?:POST|PUT|PATCH))",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://([^/\s'\"]+)", re.IGNORECASE)


def _send_tools(prof: dict) -> list[str]:
    tools = get(prof, "guardrails.external_send_tools", None)
    if isinstance(tools, list) and tools:
        return [str(t) for t in tools]
    return _DEFAULT_SEND_TOOLS


def _is_external_url(command: str) -> str | None:
    """Se o command tem URL http(s) p/ host externo, devolve o host; senão None."""
    for m in _URL_RE.finditer(command or ""):
        host = m.group(1).split("@")[-1].split(":")[0]
        if not _INTERNAL_HOST_RE.match(host):
            return host
    return None


def evaluate(tool_name: str, tool_input: dict, send_tools: list[str]) -> str | None:
    """
    Retorna a RAZÃO do aviso (str) ou None se não for envio externo.
    Determinístico, testável sem rede.
    """
    if tool_name and tool_name in send_tools:
        return f"tool de envio externo `{tool_name}`"
    command = ""
    if isinstance(tool_input, dict):
        command = str(tool_input.get("command") or "")
    if command:
        head = command.lstrip()
        is_curl_wget = bool(re.match(r"(?:sudo\s+)?(?:curl|wget)\b", head, re.IGNORECASE))
        if is_curl_wget:
            posts = bool(_POST_FLAG_RE.search(command)) or head.lower().startswith("wget")
            host = _is_external_url(command)
            if host and (posts or "curl" in head.lower() and _POST_FLAG_RE.search(command)):
                return f"{'wget' if head.lower().startswith('wget') else 'curl'} POST para host externo `{host}`"
            if host and posts:
                return f"envio HTTP para host externo `{host}`"
    return None


def _warn(reason: str, draft_dir: str) -> None:
    sys.stderr.write(
        f"[external_send_draft_gate] AVISO: {reason} — isso parece um ENVIO EXTERNO.\n"
        f"  -> Confirme EXPLICITAMENTE com o operador antes, ou salve um rascunho em `{draft_dir}` "
        "para revisão. Comunicação client-facing fica em rascunho até liberação. "
        "WARN-only — não estou bloqueando nem assumindo aprovação prévia.\n"
    )


def main() -> None:
    try:
        raw = sys.stdin.read()
    except Exception:  # noqa: BLE001
        sys.exit(0)
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001
        sys.exit(0)
    try:
        prof = load_profile() if load_profile is not None else {}
        draft_dir = get(prof, "paths.draft_dir", "drafts/")
        tool_name = str(data.get("tool_name") or "")
        tool_input = data.get("tool_input") or {}
        if not isinstance(tool_input, dict):
            tool_input = {}
        reason = evaluate(tool_name, tool_input, _send_tools(prof))
        if reason:
            _warn(reason, str(draft_dir))
    except Exception:  # noqa: BLE001
        pass
    sys.exit(0)


def _self_test() -> None:
    tools = _DEFAULT_SEND_TOOLS
    # 1. tool de envio externo configurada -> avisa
    r = evaluate("mcp__discord__discord_send_message", {}, tools)
    assert r and "envio externo" in r, f"deveria avisar discord, got {r}"
    # 2. curl POST p/ host externo -> avisa
    r2 = evaluate("Bash", {"command": "curl -X POST https://api.cliente.com/msg -d 'oi'"}, tools)
    assert r2 and "externo" in r2, f"deveria avisar curl POST externo, got {r2}"
    # 3. curl GET p/ host externo (sem POST/data) -> NÃO avisa (não é envio)
    r3 = evaluate("Bash", {"command": "curl https://api.cliente.com/status"}, tools)
    assert r3 is None, f"GET externo não é envio, não deveria avisar: {r3}"
    # 4. curl POST p/ localhost -> NÃO avisa (interno)
    r4 = evaluate("Bash", {"command": "curl -X POST http://localhost:9000/data -d '{}'"}, tools)
    assert r4 is None, f"POST interno não deveria avisar: {r4}"
    # 5. wget p/ host externo -> avisa (wget baixa/envia)
    r5 = evaluate("Bash", {"command": "wget https://evil.example.com/x"}, tools)
    assert r5 and "externo" in r5, f"deveria avisar wget externo, got {r5}"
    # 6. comando comum -> NÃO avisa
    r6 = evaluate("Bash", {"command": "ls -la docs/"}, tools)
    assert r6 is None, f"ls não deveria avisar: {r6}"
    # 7. tool desconhecida sem command -> NÃO avisa
    r7 = evaluate("Read", {"file_path": "x.md"}, tools)
    assert r7 is None, f"Read não deveria avisar: {r7}"
    # 8. curl POST p/ 127.0.0.1 -> interno, sem aviso
    r8 = evaluate("Bash", {"command": "curl --data 'a=1' http://127.0.0.1:8080/health"}, tools)
    assert r8 is None, f"127.0.0.1 é interno: {r8}"
    print("self-test OK")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    if len(sys.argv) > 1 and sys.argv[1] in ("--self-test", "-t"):
        _self_test()
    else:
        main()
