#!/usr/bin/env python3
"""
secret_scan_on_write (Operator Kit) -- PreToolUse WARN-only: detects secrets
in plaintext being written to PERSISTENT files (memory / CLAUDE.md /
docs/*.md / rules/*.md), and suggests referencing `.env`.

Why it exists: the `no-secrets-in-memory.md` rule forbids raw credentials in
committed/persistent files. The real BLOCK is the responsibility of the
pre-commit (git); this hook is the EARLY warning, at write time -- WARN-only,
never blocks (RULE #29). Complements, does not duplicate, the commit gate.

Matcher: Edit | Write | MultiEdit.
Reads JSON from stdin: tool_input.{file_path, content, new_string, edits[].new_string}.
Only fires when (a) the file_path matches a persistent glob AND (b) the content matches
a secret regex AND (c) the snippet is NOT an allowlisted placeholder (<YOUR_KEY>).

Config (operator-profile.yaml):
  guardrails.secret_scan_on_write: "warn" | "off"   (default "warn")
  guardrails.secret_persistent_globs: [list of globs]  (optional; overrides defaults)

WARN on stderr - exit 0 ALWAYS - any error -> exit 0 (defensive).

v1.0.0 -- 2026-06-19 (Operator Kit - guard-distinct cluster)
"""
from __future__ import annotations

import fnmatch
import json
import re
import sys
from pathlib import Path

# shared loader: .../operator-kit/hooks/ -> parents[1] = operator-kit/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from _lib.profile_loader import load_profile, get
except Exception:  # noqa: BLE001 -- degrade safely
    load_profile = None  # type: ignore[assignment]

    def get(_p, _d, default=None):  # type: ignore[misc]
        return default


# Globs of PERSISTENT files where a raw secret is especially dangerous.
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
    "*.md",  # any committable markdown
]

# Regexes for common secrets (real providers). Conservative to avoid false positives.
_SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),          # Anthropic
    re.compile(r"sk-[A-Za-z0-9]{16,}"),                # OpenAI-style
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),               # GitHub PAT
    re.compile(r"xox[baprs]-[A-Za-z0-9\-]{8,}"),       # Slack token
    re.compile(r"AKIA[0-9A-Z]{12,}"),                  # AWS access key id
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.=]{16,}"),    # Authorization: Bearer ...
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), # PEM private key
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),            # Google API key
]

# Acceptable placeholders (not a real secret). The suppression applies to the OCCURRENCE
# matched, never to the whole line.
# Why: suppressing the whole line let a real secret written next to an
# allowed example slip through; the placeholder mark has to be in the matched snippet itself.
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
    """Gathers all relevant text fields from a write tool_input."""
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


def _occurrence_is_placeholder(line: str, m: re.Match) -> bool:
    """The occurrence is a placeholder if the matched snippet itself carries the mark, or if it is
    inside a template (<...>, ${...}, {{...}})."""
    frag = m.group(0).lower()
    if any(tok in frag for tok in _PLACEHOLDER_TOKENS):
        return True
    antes = line[max(0, m.start() - 2):m.start()]
    depois = line[m.end():m.end() + 2]
    return antes.endswith(("<", "${", "{{")) or depois.startswith((">", "}"))


def scan(file_path: str, texts: list[str], globs: list[str]) -> list[str]:
    """Returns a list of descriptions of secrets found (empty = none)."""
    if not _is_persistent(file_path, globs):
        return []
    hits: list[str] = []
    for text in texts:
        for line in text.splitlines():
            for pat in _SECRET_PATTERNS:
                m = next((c for c in pat.finditer(line) if not _occurrence_is_placeholder(line, c)), None)
                if m:
                    frag = m.group(0)
                    shown = frag[:8] + "..." if len(frag) > 8 else frag
                    hits.append(f"pattern `{shown}`")
                    break  # 1 per line is enough
    return hits


def _warn(file_path: str, hits: list[str]) -> None:
    uniq = sorted(set(hits))
    sys.stderr.write(
        "[secret_scan_on_write] WARNING: possible secret in a persistent file "
        f"`{file_path}` ({', '.join(uniq)}).\n"
        "  -> do NOT commit a raw credential. Reference the `.env` "
        "(e.g. \"key: stored in `.env` as FOO_API_KEY\"). "
        "WARN-only — the real BLOCK belongs to the pre-commit.\n"
    )


def main() -> None:
    try:
        raw = sys.stdin.read()
    except Exception:  # noqa: BLE001
        sys.exit(0)
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001 -- not a valid hook call
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
    except Exception:  # noqa: BLE001 -- hook must never break the flow
        pass
    sys.exit(0)


def _self_test() -> None:
    globs = _DEFAULT_PERSISTENT_GLOBS
    # 1. secret in a persistent file -> hit
    h = scan("docs/notes/MEMORY.md", ["api: sk-ant-abc123DEF456ghi789"], globs)
    assert h, f"should detect the Anthropic secret, got {h}"
    # 2. same secret but a NON-persistent file (code) -> no hit
    h2 = scan("core/intelligence/foo.py", ["api: sk-ant-abc123DEF456ghi789"], globs)
    assert not h2, f".py code is not a persistent md, it should not warn: {h2}"
    # 3. allowlisted placeholder -> no hit
    h3 = scan("CLAUDE.md", ["key: stored in `.env` as FOO; example sk-xxxxxxxxxxxxxxxx"], globs)
    assert not h3, f"a placeholder/.env should not warn: {h3}"
    # 3b. placeholder and a real secret on the SAME line -> the real one is still seen
    h3b = scan("CLAUDE.md", ["example sk-xxxxxxxxxxxxxxxx  e  " + "ghp" + "_EXEMPLOEXEMPLOEXEMPLOEXEMPLO1234"], globs)
    assert h3b and "ghp_EXEM" in h3b[0], f"a real secret next to a placeholder should warn: {h3b}"
    # 4. GitHub PAT in a docs md -> hit
    h4 = scan("docs/x.md", ["token " + "ghp" + "_0123456789abcdefABCD"], globs)
    assert h4, f"should detect ghp_, got {h4}"
    # 5. PEM private key -> hit
    h5 = scan("notes/MEMORY.md", ["-----BEGIN " + "RSA PRIVATE KEY-----"], globs)
    assert h5, f"should detect the PEM, got {h5}"
    # 6. harmless text -> no hit
    h6 = scan("docs/x.md", ["just ordinary text with no secret"], globs)
    assert not h6, f"ordinary text should not warn: {h6}"
    # 7. _extract_texts picks up edits[].new_string
    txts = _extract_texts({"edits": [{"new_string": "sk-ant-zzz999AAA888bbb"}]})
    assert any("sk-ant" in t for t in txts), "extract should pick up edits"
    # 8. non-persistent glob
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
