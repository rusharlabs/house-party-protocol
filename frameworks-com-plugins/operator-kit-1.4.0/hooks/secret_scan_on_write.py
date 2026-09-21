#!/usr/bin/env python3
"""
secret_scan_on_write (Operator Kit) — PreToolUse WARN-only: detecta segredos
em plaintext sendo escritos em arquivos PERSISTENTES (memory / CLAUDE.md /
docs/*.md / rules/*.md), e sugere referenciar o `.env`.

Por que existe: a regra `no-secrets-in-memory.md` proíbe credenciais cruas em
arquivos commitados/persistentes. O BLOCK de verdade é responsabilidade do
pre-commit (git); este hook é o aviso EARLY, no momento da escrita — WARN-only,
nunca bloqueia (REGRA #29). Complementa, não duplica, o gate de commit.

Matcher: Edit | Write | MultiEdit.
Lê JSON do stdin: tool_input.{file_path, content, new_string, edits[].new_string}.
Só dispara quando (a) o file_path casa um glob persistente E (b) o conteúdo casa
um regex de segredo E (c) o trecho NÃO é um placeholder allowlistado (<YOUR_KEY>).

Config (operator-profile.yaml):
  guardrails.secret_scan_on_write: "warn" | "off"   (default "warn")
  guardrails.secret_persistent_globs: [lista de globs]  (opcional; sobrepõe defaults)

WARN em stderr · exit 0 SEMPRE · qualquer erro -> exit 0 (defensivo).

v1.0.0 — 2026-06-19 (Operator Kit · cluster guard-distinct)
"""
from __future__ import annotations

import fnmatch
import json
import re
import sys
from pathlib import Path

# loader compartilhado: .../operator-kit/hooks/ -> parents[1] = operator-kit/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from _lib.profile_loader import load_profile, get
except Exception:  # noqa: BLE001 — degrade seguro
    load_profile = None  # type: ignore[assignment]

    def get(_p, _d, default=None):  # type: ignore[misc]
        return default


# Globs de arquivos PERSISTENTES onde segredo cru é especialmente perigoso.
_DEFAULT_PERSISTENT_GLOBS = [
    "*MEMORY.md",
    "**/MEMORY.md",
    "**/memory/*.md",
    "**/memory/**/*.md",
    "CLAUDE.md",
    "**/CLAUDE.md",
    "**/.claude/**/*.md",
    "docs/**/*.md",
    "**/docs/**/*.md",
    "**/rules/**/*.md",
    "*.md",  # qualquer markdown commitável
]

# Regexes de segredos comuns (provedores reais). Conservador p/ evitar falso-positivo.
_SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),          # Anthropic
    re.compile(r"sk-[A-Za-z0-9]{16,}"),                # OpenAI-style
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),               # GitHub PAT
    re.compile(r"xox[baprs]-[A-Za-z0-9\-]{8,}"),       # Slack token
    re.compile(r"AKIA[0-9A-Z]{12,}"),                  # AWS access key id
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.=]{16,}"),    # Authorization: Bearer ...
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), # chave privada PEM
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),            # Google API key
]

# Placeholders aceitáveis (não são segredo real) — se o match estiver dentro de
# uma linha que contenha um destes, ignora.
_PLACEHOLDER_TOKENS = [
    "<your_key>", "<your-key>", "your_key_here", "xxxx", "example",
    "placeholder", "<token>", "<api_key>", "redacted", "dummy", "fake",
    "stored in `.env`", "via .env", "${", "process.env", "os.environ",
]


def _persistent_globs(prof: dict) -> list[str]:
    custom = get(prof, "guardrails.secret_persistent_globs", None)
    if isinstance(custom, list) and custom:
        return [str(g) for g in custom]
    return _DEFAULT_PERSISTENT_GLOBS


def _is_persistent(file_path: str, globs: list[str]) -> bool:
    if not file_path:
        return False
    fp = file_path.replace("\\", "/")
    name = fp.rsplit("/", 1)[-1]
    for g in globs:
        if fnmatch.fnmatch(fp, g) or fnmatch.fnmatch(name, g):
            return True
    return False


def _extract_texts(tool_input: dict) -> list[str]:
    """Junta todos os campos textuais relevantes de um tool_input de escrita."""
    out: list[str] = []
    for key in ("content", "new_string", "new_str"):
        v = tool_input.get(key)
        if isinstance(v, str):
            out.append(v)
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for e in edits:
            if isinstance(e, dict):
                v = e.get("new_string") or e.get("new_str")
                if isinstance(v, str):
                    out.append(v)
    return out


def _line_is_placeholder(line: str) -> bool:
    low = line.lower()
    return any(tok in low for tok in _PLACEHOLDER_TOKENS)


def scan(file_path: str, texts: list[str], globs: list[str]) -> list[str]:
    """Retorna lista de descrições de segredo encontrado (vazia = nada)."""
    if not _is_persistent(file_path, globs):
        return []
    hits: list[str] = []
    for text in texts:
        for line in text.splitlines():
            if _line_is_placeholder(line):
                continue
            for pat in _SECRET_PATTERNS:
                m = pat.search(line)
                if m:
                    frag = m.group(0)
                    shown = frag[:8] + "..." if len(frag) > 8 else frag
                    hits.append(f"padrão `{shown}`")
                    break  # 1 por linha basta
    return hits


def _warn(file_path: str, hits: list[str]) -> None:
    uniq = sorted(set(hits))
    sys.stderr.write(
        "[secret_scan_on_write] AVISO: possível segredo em arquivo persistente "
        f"`{file_path}` ({', '.join(uniq)}).\n"
        "  -> NÃO commitar credencial crua. Referencie o `.env` "
        "(ex.: \"key: stored in `.env` as FOO_API_KEY\"). "
        "WARN-only — o BLOCK definitivo é do pre-commit.\n"
    )


def main() -> None:
    try:
        raw = sys.stdin.read()
    except Exception:  # noqa: BLE001
        sys.exit(0)
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001 — não é chamada de hook válida
        sys.exit(0)
    try:
        prof = load_profile() if load_profile is not None else {}
        mode = get(prof, "guardrails.secret_scan_on_write", "warn")
        if str(mode).lower() == "off":
            sys.exit(0)
        tool_input = data.get("tool_input") or {}
        if not isinstance(tool_input, dict):
            sys.exit(0)
        file_path = tool_input.get("file_path") or tool_input.get("path") or ""
        texts = _extract_texts(tool_input)
        if not texts:
            sys.exit(0)
        hits = scan(str(file_path), texts, _persistent_globs(prof))
        if hits:
            _warn(str(file_path), hits)
    except Exception:  # noqa: BLE001 — hook jamais quebra o fluxo
        pass
    sys.exit(0)


def _self_test() -> None:
    globs = _DEFAULT_PERSISTENT_GLOBS
    # 1. segredo em arquivo persistente -> hit
    h = scan("docs/notes/MEMORY.md", ["api: sk-ant-abc123DEF456ghi789"], globs)
    assert h, f"deveria detectar segredo Anthropic, got {h}"
    # 2. mesmo segredo mas arquivo NÃO persistente (código) -> sem hit
    h2 = scan("core/intelligence/foo.py", ["api: sk-ant-abc123DEF456ghi789"], globs)
    assert not h2, f"código .py não é persistente-md, não deveria avisar: {h2}"
    # 3. placeholder allowlistado -> sem hit
    h3 = scan("CLAUDE.md", ["key: stored in `.env` as FOO; example sk-xxxxxxxxxxxxxxxx"], globs)
    assert not h3, f"placeholder/.env não deveria avisar: {h3}"
    # 4. GitHub PAT em md de docs -> hit
    h4 = scan("docs/x.md", ["token " + "ghp" + "_0123456789abcdefABCD"], globs)
    assert h4, f"deveria detectar ghp_, got {h4}"
    # 5. PEM private key -> hit
    h5 = scan("notes/MEMORY.md", ["-----BEGIN " + "RSA PRIVATE KEY-----"], globs)
    assert h5, f"deveria detectar PEM, got {h5}"
    # 6. texto inofensivo -> sem hit
    h6 = scan("docs/x.md", ["apenas um texto comum sem segredo"], globs)
    assert not h6, f"texto comum não deveria avisar: {h6}"
    # 7. _extract_texts pega edits[].new_string
    txts = _extract_texts({"edits": [{"new_string": "sk-ant-zzz999AAA888bbb"}]})
    assert any("sk-ant" in t for t in txts), "extract deveria pegar edits"
    # 8. glob de não-persistente
    assert not _is_persistent("engine/src/app.ts", globs)
    assert _is_persistent("a/b/MEMORY.md", globs)
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
