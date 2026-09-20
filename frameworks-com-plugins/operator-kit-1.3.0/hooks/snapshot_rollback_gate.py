#!/usr/bin/env python3
"""
snapshot_rollback_gate (Operator Kit) — PreToolUse WARN-only: ao detectar um
VERBO DESTRUTIVO num comando Bash, imprime um checklist de segurança
(houve snapshot? plano de rollback? verify pós-ação?) — a menos que o operador
já tenha confirmado via env SNAPSHOT_CONFIRMED=1.

Por que existe: toda ação
destrutiva exige SNAPSHOT + ROLLBACK + VERIFY. Este hook é o LEMBRETE no momento
da ação. v1 NÃO detecta automaticamente se há backup (sem heurística de backup);
apenas reconhece o verbo destrutivo e pede o checklist.

Lê JSON do stdin: tool_input.command.
Verbos destrutivos reconhecidos (configurável):
  rm -rf · git reset --hard · drop table · truncate · docker rm -f.

Config (operator-profile.yaml):
  guardrails.destructive_verbs: [lista de regex extra]  (opcional, ADICIONA aos defaults)

Bypass: env SNAPSHOT_CONFIRMED=1.

WARN em stderr · exit 0 SEMPRE · qualquer erro -> exit 0 (defensivo).

v1.0.0 — 2026-06-19 (Operator Kit · cluster guard-distinct)
"""
from __future__ import annotations

import json
import os
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


# (rótulo legível, regex). Regex case-insensitive sobre o command.
_DEFAULT_VERBS: list[tuple[str, str]] = [
    ("rm -rf",            r"\brm\b[^\n|;&]*-[a-zA-Z]*r[a-zA-Z]*f|\brm\b[^\n|;&]*-[a-zA-Z]*f[a-zA-Z]*r"),
    ("git reset --hard",  r"\bgit\s+reset\b[^\n|;&]*--hard\b"),
    ("git clean -fd",     r"\bgit\s+clean\b[^\n|;&]*-[a-zA-Z]*f"),
    ("drop table",        r"\bdrop\s+table\b"),
    ("drop database",     r"\bdrop\s+database\b"),
    ("truncate",          r"\btruncate\b"),
    ("docker rm -f",      r"\bdocker\s+rm\b[^\n|;&]*-[a-zA-Z]*f"),
    ("docker volume rm",  r"\bdocker\s+volume\s+rm\b"),
]


def _verbs(prof: dict) -> list[tuple[str, re.Pattern]]:
    out: list[tuple[str, re.Pattern]] = []
    for label, pat in _DEFAULT_VERBS:
        try:
            out.append((label, re.compile(pat, re.IGNORECASE)))
        except re.error:
            continue
    extra = get(prof, "guardrails.destructive_verbs", None)
    if isinstance(extra, list):
        for item in extra:
            try:
                out.append((str(item), re.compile(str(item), re.IGNORECASE)))
            except re.error:
                continue
    return out


def detect(command: str, verbs: list[tuple[str, re.Pattern]]) -> list[str]:
    """Retorna os rótulos de verbos destrutivos encontrados no command."""
    if not command:
        return []
    hits: list[str] = []
    for label, pat in verbs:
        if pat.search(command):
            hits.append(label)
    return hits


def _confirmed() -> bool:
    return os.environ.get("SNAPSHOT_CONFIRMED") == "1"


def _warn(hits: list[str]) -> None:
    uniq = sorted(set(hits))
    sys.stderr.write(
        f"[snapshot_rollback_gate] AVISO: ação destrutiva detectada ({', '.join(uniq)}).\n"
        "  Antes de executar, confirme o protocolo SNAPSHOT + ROLLBACK + VERIFY:\n"
        "    [ ] Houve SNAPSHOT/backup do que será destruído?\n"
        "    [ ] Existe PLANO DE ROLLBACK se der errado?\n"
        "    [ ] Há um passo de VERIFY pós-ação (testar que o sistema segue OK)?\n"
        "  Se já garantiu os 3, defina SNAPSHOT_CONFIRMED=1 para silenciar. "
        "WARN-only — não estou bloqueando.\n"
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
        if _confirmed():
            sys.exit(0)
        prof = load_profile() if load_profile is not None else {}
        tool_input = data.get("tool_input") or {}
        if not isinstance(tool_input, dict):
            sys.exit(0)
        command = str(tool_input.get("command") or "")
        hits = detect(command, _verbs(prof))
        if hits:
            _warn(hits)
    except Exception:  # noqa: BLE001
        pass
    sys.exit(0)


def _self_test() -> None:
    verbs = _verbs({})
    # 1. rm -rf -> detecta
    assert detect("rm -rf build/", verbs) == ["rm -rf"], detect("rm -rf build/", verbs)
    # 2. rm -fr (ordem trocada) -> detecta
    assert "rm -rf" in detect("rm -fr /tmp/x", verbs)
    # 3. git reset --hard -> detecta
    assert "git reset --hard" in detect("git reset --hard origin/main", verbs)
    # 4. drop table -> detecta (case-insensitive)
    assert "drop table" in detect("DROP TABLE insights;", verbs)
    # 5. truncate -> detecta
    assert "truncate" in detect("truncate -s 0 log.txt", verbs)
    # 6. docker rm -f -> detecta
    assert "docker rm -f" in detect("docker rm -f app-prod", verbs)
    # 7. comando inofensivo -> nada
    assert detect("ls -la && git status", verbs) == [], detect("ls -la && git status", verbs)
    # 8. rm sem -rf (só um arquivo) -> não casa o padrão -rf
    assert detect("rm arquivo.txt", verbs) == [], detect("rm arquivo.txt", verbs)
    # 9. verbo extra via profile (regex custom)
    verbs_x = _verbs({"guardrails": {"destructive_verbs": [r"\bmkfs\b"]}})
    assert "\\bmkfs\\b" in detect("mkfs.ext4 /dev/sdb", verbs_x)
    # 10. múltiplos verbos num comando encadeado
    multi = detect("git clean -fd && rm -rf node_modules", verbs)
    assert "rm -rf" in multi and "git clean -fd" in multi, multi
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
