#!/usr/bin/env python3
"""
guard_origins — protege fontes vivas de escrita acidental, em 2 modos.

MODO BIBLIOTECA (mecanismo principal — usado pelo próprio kit_assembler.py):
  sweep(root, files)          -> {relpath: mtime} ANTES de copiar
  verify(before, root, files) -> [relpath drifted/sumiu] DEPOIS de copiar
  Detecta se algo na FONTE mudou durante a montagem (outra sessão editando o mesmo
  staging enquanto o assembler lia) — falha de integridade de supply-chain, não de
  permissão. kit_assembler chama sweep() antes do loop de cópia e verify() depois
  (e de novo antes do swap final) — se houver drift, ABORTA a emissão.

MODO --hook (opcional — para sessões agênticas de extração/porting):
  PreToolUse hook (stdin JSON -> exit code) que BLOQUEIA Edit/Write/MultiEdit/
  NotebookEdit e comandos Bash destrutivos que alvejam um path listado em
  `origins` (config/env — NUNCA hardcoded, diferente do guard-origens.js de
  referência que tinha 4 paths fixos de um projeto específico).

Config das origens (modo --hook, primeira que existir):
  1. --config <arquivo.json ou .yaml> com {"origins": ["path/substring", ...]}
  2. env GUARD_ORIGINS="path1,path2" (separado por vírgula ou quebra de linha)
  3. sem nenhuma -> lista vazia -> hook nunca bloqueia (fail-open, documentado)

Uso:
    from guard_origins import sweep, verify                          # modo biblioteca
    echo '{"tool_name":"Write","tool_input":{...}}' | python guard_origins.py --hook
    python guard_origins.py --self-test

Exit (modo --hook): 0 permitido · 2 bloqueado (PreToolUse). Modo biblioteca não usa
exit code (retorna dict/list para o chamador decidir).
stdlib only (+ PyYAML opcional só p/ --config .yaml). v1.0.0 — 2026-07-10 (kit-forge)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml  # PyYAML — só para --config *.yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

_DESTRUCTIVE_BASH = re.compile(
    r"(\brm\b|\bmv\b|\bsed\s+-i\b|\btee\b|>>?(?!\d)|\bgit\b[^|]*\b(commit|checkout|reset|clean|rebase|merge|restore)\b)"
)
_WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


# ---------------------------------------------------------------------------
# MODO BIBLIOTECA — usado por kit_assembler.py
# ---------------------------------------------------------------------------

def sweep(root: Path, files: list) -> dict:
    """Snapshot de mtime (ns) de cada arquivo em `files` (paths relativos a `root`).
    Arquivo ausente no momento do sweep = None (comparado depois em verify)."""
    out = {}
    for rel in files:
        p = root / rel
        try:
            out[rel] = p.stat().st_mtime_ns
        except OSError:
            out[rel] = None
    return out


def verify(before: dict, root: Path, files: list) -> list:
    """Retorna a lista de relpaths cujo mtime mudou (ou que sumiram/apareceram)
    entre o `sweep()` anterior e agora. Lista vazia = fonte estável durante a janela."""
    drifted = []
    for rel in files:
        p = root / rel
        try:
            now = p.stat().st_mtime_ns
        except OSError:
            now = None
        if now != before.get(rel):
            drifted.append(rel)
    return drifted


# ---------------------------------------------------------------------------
# MODO --hook — PreToolUse standalone
# ---------------------------------------------------------------------------

def _norm(s) -> str:
    return str(s or "").replace("\\", "/")


def _hits_origin(path_or_cmd: str, origins: list) -> bool:
    n = _norm(path_or_cmd)
    return any(o in n for o in origins)


def load_origins(config_path: str | None) -> list:
    if config_path:
        p = Path(config_path)
        if p.exists():
            text = p.read_text(encoding="utf-8")
            if p.suffix in (".yaml", ".yml") and yaml is not None:
                data = yaml.safe_load(text) or {}
            else:
                data = json.loads(text) if text.strip() else {}
            origins = data.get("origins") if isinstance(data, dict) else None
            if isinstance(origins, list):
                return [str(o) for o in origins]
    env = os.environ.get("GUARD_ORIGINS", "")
    if env:
        parts = re.split(r"[,\n]", env)
        return [p.strip() for p in parts if p.strip()]
    return []


def decide(payload: dict, origins: list) -> tuple:
    """Retorna (exit_code, mensagem). Logica isolada de stdin/exit p/ testar sem processo real."""
    if not origins:
        return 0, ""

    tool = payload.get("tool_name") or ""
    ti = payload.get("tool_input") or {}

    if tool in _WRITE_TOOLS:
        file_path = ti.get("file_path")
        if file_path and _hits_origin(file_path, origins):
            return 2, f"[guard_origins] BLOQUEADO — escrita em fonte viva: {file_path}. Use Read/Grep/Glob, ou escreva no repo de destino."
        return 0, ""

    if tool == "Bash":
        command = ti.get("command") or ""
        if _DESTRUCTIVE_BASH.search(_norm(command)) and _hits_origin(command, origins):
            return 2, "[guard_origins] BLOQUEADO — comando potencialmente destrutivo numa fonte viva."
        return 0, ""

    return 0, ""


def main(argv) -> int:
    p = argparse.ArgumentParser(prog="guard_origins.py")
    p.add_argument("--hook", action="store_true")
    p.add_argument("--config", default=None)
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args(argv)

    if args.self_test:
        return _self_test()

    if not args.hook:
        print("uso: guard_origins.py --hook [--config origins.json]  (ou importe sweep/verify)", file=sys.stderr)
        return 3

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return 0  # payload malformado nunca bloqueia — fail-safe

    origins = load_origins(args.config)
    code, message = decide(payload, origins)
    if message:
        print(message, file=sys.stderr if code == 2 else sys.stdout)
    return code


def _self_test() -> int:
    import shutil
    import tempfile
    import time

    # --- modo biblioteca ---
    tmp = Path(tempfile.mkdtemp(prefix="guard_origins_selftest_"))
    try:
        (tmp / "a.txt").write_text("A", encoding="utf-8")
        (tmp / "b.txt").write_text("B", encoding="utf-8")
        files = ["a.txt", "b.txt"]

        before = sweep(tmp, files)
        assert verify(before, tmp, files) == [], "sem mudanca -> sem drift"

        time.sleep(0.05)
        (tmp / "a.txt").write_text("A-MUDOU", encoding="utf-8")
        drift = verify(before, tmp, files)
        assert drift == ["a.txt"], f"deveria detectar drift em a.txt: {drift}"

        (tmp / "a.txt").write_text("A", encoding="utf-8")
        before2 = sweep(tmp, files)
        (tmp / "b.txt").unlink()
        drift2 = verify(before2, tmp, files)
        assert drift2 == ["b.txt"], f"arquivo sumido deveria contar como drift: {drift2}"

        before3 = sweep(tmp, ["a.txt", "c-nao-existe.txt"])
        assert before3["c-nao-existe.txt"] is None
        assert verify(before3, tmp, ["a.txt", "c-nao-existe.txt"]) == []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # --- modo --hook ---
    origins = ["Desktop/FONTE-VIVA"]
    code1, msg1 = decide({"tool_name": "Write", "tool_input": {"file_path": "Desktop/FONTE-VIVA/x.py"}}, origins)
    assert code1 == 2 and "BLOQUEADO" in msg1, (code1, msg1)

    code2, msg2 = decide({"tool_name": "Write", "tool_input": {"file_path": "Desktop/OUTRO-REPO/x.py"}}, origins)
    assert code2 == 0 and msg2 == "", (code2, msg2)

    code3, msg3 = decide({"tool_name": "Bash", "tool_input": {"command": "rm -rf Desktop/FONTE-VIVA/tmp"}}, origins)
    assert code3 == 2, (code3, msg3)

    code4, msg4 = decide({"tool_name": "Bash", "tool_input": {"command": "ls Desktop/FONTE-VIVA"}}, origins)
    assert code4 == 0, (code4, msg4)  # ls não é destrutivo -> passa mesmo mirando a origem

    code5, _ = decide({"tool_name": "Write", "tool_input": {"file_path": "Desktop/FONTE-VIVA/x.py"}}, [])
    assert code5 == 0, "sem origins configuradas -> fail-open (nunca bloqueia)"

    print("self-test OK — biblioteca (sweep/verify: estavel/drift/sumico/ausente) + hook (bloqueia escrita/destrutivo, libera resto, fail-open sem config)")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
