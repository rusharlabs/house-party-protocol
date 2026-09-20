#!/usr/bin/env python3
"""
lane_git_guard — PreToolUse (Bash): impede que uma lane pise no índice git de outra.

Índice git é COMPARTILHADO entre sessões (lanes) rodando no mesmo repositório — um
`git add -A`/`commit -a`/`commit` sem pathspec explícito varre TUDO que está no working
tree, inclusive arquivos que outra lane deixou staged/modificados de propósito. Isto já
causou incidentes reais de trabalho concorrente sendo corrompido por um commit alheio.

Detecta 6 famílias de comando git perigoso quando há outra lane VIVA: `add -A/--all/.`,
`commit -a/-am/--all`, `commit` sem `-- <paths>` explícito, `stash` (exceto list/show),
`reset --hard`, `checkout .`, `commit --amend`. Modo `warn` (default, nunca bloqueia de
verdade) ou `block` (só depois de validar zero falso-positivo em produção — ver
evals/collision-git-guard.sh). Solo ou só lanes mortas = tudo permitido.

Doutrina da casa: SEMPRE exit 0. A decisão viaja via JSON (`decision`/`permissionDecision`),
nunca via exit-code — qualquer exceção interna também fail-open (exit 0, sem decision).

Bypass de emergência: env LANE_GIT_GUARD_BYPASS=1.
Override de modo: env LANE_GIT_GUARD_MODE=warn|block (tem precedência sobre lanes.yaml).

Uso (hook): echo '{"tool_name":"Bash","tool_input":{"command":"git commit -am x"}}' | python lane_git_guard.py
Exit: sempre 0.
stdlib only. v1.0.0 — 2026-07-10 (lane-kit)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lane_io  # noqa: E402

_SEGMENT_SPLIT = re.compile(r"(?:\|\||&&|;|\|)")
_QUOTE_STRIP = re.compile(r'"[^"]*"|\'[^\']*\'')

_FAMILIES: list[tuple[str, re.Pattern]] = [
    ("git add -A/--all/.", re.compile(r"\bgit\s+add\s+(?:-[a-zA-Z]*A[a-zA-Z]*\b|--all\b)")),
    ("git add .", re.compile(r"\bgit\s+add\s+(?:-[a-zA-Z]+\s+)*\.(?=\s|$)")),
    ("git commit -a/-am/--all", re.compile(r"\bgit\s+commit\b[^;|&\n]*\s-(?!-)[a-zA-Z]*a[a-zA-Z]*\b|\bgit\s+commit\b[^;|&\n]*--all\b")),
    ("git stash", re.compile(r"\bgit\s+stash\b(?!\s+(?:list|show)\b)")),
    ("git reset --hard", re.compile(r"\bgit\s+reset\b[^;|&\n]*--hard\b")),
    ("git checkout .", re.compile(r"\bgit\s+checkout\s+(?:--\s+)?\.(?=\s|$)")),
    ("git commit --amend", re.compile(r"\bgit\s+commit\b[^;|&\n]*--amend\b")),
]
_COMMIT_RE = re.compile(r"\bgit\s+commit\b")
_HAS_PATHSPEC_RE = re.compile(r"\s--\s+\S")


def _extra_patterns(cfg: dict) -> list:
    out = []
    for pat in _lane_io.get(cfg, "git_guard.extra_patterns", []) or []:
        try:
            out.append((pat, re.compile(pat)))
        except re.error:
            continue
    return out


def detect(command: str, cfg: dict | None = None) -> list:
    """Retorna os rótulos de famílias perigosas encontradas no comando (dedupe)."""
    if not command or "git" not in command:
        return []
    cfg = cfg if cfg is not None else {}
    hits: list = []
    for seg in _SEGMENT_SPLIT.split(command):
        if not re.search(r"\bgit\b", seg):
            continue
        for label, pat in _FAMILIES:
            if pat.search(seg):
                hits.append(label)
        if _COMMIT_RE.search(seg):
            stripped = _QUOTE_STRIP.sub("", seg)
            if not _HAS_PATHSPEC_RE.search(stripped):
                hits.append("git commit sem pathspec")
        for label, pat in _extra_patterns(cfg):
            if pat.search(seg):
                hits.append(label)
    seen = []
    for h in hits:
        if h not in seen:
            seen.append(h)
    return seen


def _last_commit_age_minutes() -> float | None:
    try:
        r = subprocess.run(
            ["git", "-C", str(_lane_io._PROJECT_ROOT), "log", "-1", "--format=%ct"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return None
        import time as _time
        return (_time.time() - float(r.stdout.strip())) / 60.0
    except Exception:  # noqa: BLE001
        return None


def _my_lane() -> str:
    return os.environ.get("CLAUDE_LANE_ID") or "solo"


def handle(payload: dict) -> dict:
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return {}
    command = str(tool_input.get("command") or "")

    cfg = _lane_io.load_config()
    hits = detect(command, cfg)
    if not hits:
        return {}

    if os.environ.get("LANE_GIT_GUARD_BYPASS") == "1":
        sys.stderr.write("[lane_git_guard] bypass ativo (LANE_GIT_GUARD_BYPASS=1) — não avaliando.\n")
        return {}

    my_lane = _my_lane()
    others = _lane_io.alive_others(my_lane)

    if not others:
        age = _last_commit_age_minutes()
        heuristic_on = _lane_io.get(cfg, "git_guard.fallback_heuristic", True)
        heuristic_minutes = _lane_io.get(cfg, "git_guard.heuristic_minutes", 10)
        if heuristic_on and age is not None and age < heuristic_minutes:
            msg = (
                f"[lane_git_guard] AVISO (heurística, sem registry.json): último commit há "
                f"{age:.0f}min — outra sessão pode estar ativa sem ter registrado lane ainda. "
                f"Comando: {command[:120]!r}. Famílias: {', '.join(hits)}. WARN-only, nunca bloqueia por heurística."
            )
            sys.stderr.write(msg + "\n")
        return {}  # solo (ou heurística) NUNCA bloqueia — no máximo warn acima

    only_suspect = all(state == "suspect" for _lid, _e, state in others)
    mode = os.environ.get("LANE_GIT_GUARD_MODE") or _lane_io.get(cfg, "git_guard.mode", "warn")
    if only_suspect:
        mode = "warn"

    others_str = ", ".join(f"{lid} (heartbeat {_lane_io.age_str(e)})" for lid, e, _ in others)
    msg = (
        f"⛔ LANE-GIT-GUARD: {len(others)} lane(s) viva(s) ({others_str}). Índice git é COMPARTILHADO "
        f"entre lanes — use `git commit -m '...' -- <paths>` (nunca -a / add -A / commit sem pathspec). "
        f"Famílias detectadas: {', '.join(hits)}. Comando: {command[:120]!r}"
    )

    if mode == "block":
        return {
            "decision": "block",
            "reason": msg,
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": msg,
            },
        }

    sys.stderr.write("[lane_git_guard] " + msg + "\n")
    return {}


def main(argv) -> int:
    if argv and argv[0] in ("--self-test", "-t"):
        return _self_test()

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:  # noqa: BLE001
        payload = {}

    try:
        result = handle(payload)
    except Exception:  # noqa: BLE001 — fail-open total
        result = {}

    print(json.dumps(result, ensure_ascii=False))
    return 0


def _self_test() -> int:
    import shutil
    import tempfile

    # --- detect() puro (sem I/O) ---
    positives = {
        "git add -A": "git add -A",
        "git add --all": "git add --all",
        "git add .": "git add .",
        "git commit -am \"x\"": "git commit -am \"x\"",
        "git commit -a -m x": "git commit -a -m x",
        "git commit -m \"x\"": "git commit -m \"x\"",
        "git commit -m \"a -- b\"": "git commit -m \"a -- b\"",
        "git stash": "git stash",
        "git stash pop": "git stash pop",
        "git reset --hard HEAD~1": "git reset --hard HEAD~1",
        "git checkout .": "git checkout .",
        "git checkout -- .": "git checkout -- .",
        "git commit --amend --no-edit": "git commit --amend --no-edit",
    }
    for name, cmd in positives.items():
        assert detect(cmd), f"deveria detectar familia perigosa em: {name!r} -> {cmd!r}"

    negatives = [
        "git commit -m \"fix\" -- src/a.py",
        "git add src/a.py",
        "git status && git log --oneline",
        "git diff",
        "git show HEAD",
        "git stash list",
        "git checkout -b feat/x",
        "npm test",
        "",
    ]
    for cmd in negatives:
        assert not detect(cmd), f"NAO deveria detectar em: {cmd!r} -> {detect(cmd)}"

    # extra_patterns via config
    hits_extra = detect("git restore .", {"git_guard": {"extra_patterns": [r"git\s+restore\s+\."]}})
    assert hits_extra, "extra_patterns deveria pegar git restore ."

    # --- handle() com registry real (isolado em tempdir) ---
    tmp = Path(tempfile.mkdtemp(prefix="lane_git_guard_selftest_"))
    orig = (_lane_io._PROJECT_ROOT, _lane_io._LANES_DIR, _lane_io.REGISTRY_PATH, _lane_io.CONFIG_PATH)
    try:
        _lane_io._PROJECT_ROOT = tmp
        _lane_io._LANES_DIR = tmp / ".claude" / "lanes"
        _lane_io.REGISTRY_PATH = _lane_io._LANES_DIR / "registry.json"
        _lane_io.CONFIG_PATH = _lane_io._LANES_DIR / "lanes.yaml"

        # solo: sem registry nenhum -> sempre {} (sem commit real no repo, heuristica nao dispara)
        os.environ.pop("LANE_GIT_GUARD_MODE", None)
        os.environ.pop("LANE_GIT_GUARD_BYPASS", None)
        os.environ["CLAUDE_LANE_ID"] = "solo"
        out_solo = handle({"tool_input": {"command": "git commit -am x"}})
        assert out_solo == {}, f"solo sem outras lanes deveria liberar: {out_solo}"

        # registra rival vivo
        _lane_io.register("exec-a", "executora", "s1", "claude-opus-4-8")
        os.environ["CLAUDE_LANE_ID"] = "exec-b"

        os.environ["LANE_GIT_GUARD_MODE"] = "warn"
        out_warn = handle({"tool_input": {"command": "git commit -am x"}})
        assert "decision" not in out_warn, f"modo warn nao deveria ter decision: {out_warn}"

        os.environ["LANE_GIT_GUARD_MODE"] = "block"
        out_block = handle({"tool_input": {"command": "git commit -am x"}})
        assert out_block.get("decision") == "block", f"modo block deveria bloquear: {out_block}"
        assert out_block["hookSpecificOutput"]["permissionDecision"] == "deny"

        # comando seguro nao bloqueia mesmo em modo block
        out_safe = handle({"tool_input": {"command": "git commit -m x -- file.py"}})
        assert out_safe == {}, f"pathspec explicito nao deveria bloquear: {out_safe}"

        # bypass
        os.environ["LANE_GIT_GUARD_BYPASS"] = "1"
        out_bypass = handle({"tool_input": {"command": "git commit -am x"}})
        assert out_bypass == {}, "bypass deveria liberar mesmo em modo block"
        os.environ.pop("LANE_GIT_GUARD_BYPASS", None)

        # so lane suspeita -> forca warn mesmo em modo block
        import time as _time
        reg = _lane_io._read_registry()
        from datetime import datetime, timezone
        suspect_ts = datetime.fromtimestamp(_time.time() - 15 * 60, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        reg["lanes"]["exec-a"]["heartbeat_at"] = suspect_ts
        _lane_io._write_registry(reg)
        out_suspect = handle({"tool_input": {"command": "git commit -am x"}})
        assert "decision" not in out_suspect, f"so-suspeita deveria degradar p/ warn mesmo em modo block: {out_suspect}"

        # lane morta -> zero falso positivo
        dead_ts = datetime.fromtimestamp(_time.time() - 35 * 60, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        reg2 = _lane_io._read_registry()
        reg2["lanes"]["exec-a"]["heartbeat_at"] = dead_ts
        _lane_io._write_registry(reg2)
        out_dead = handle({"tool_input": {"command": "git commit -am x"}})
        assert out_dead == {}, f"lane morta nao deveria disparar nada: {out_dead}"

        print("self-test OK — 13 positivos + 8 negativos em detect(), extra_patterns funciona, "
              "solo libera, warn nao bloqueia, block bloqueia, pathspec explicito libera, bypass libera, "
              "so-suspeita forca warn, lane morta = zero falso positivo")
        return 0
    finally:
        os.environ.pop("LANE_GIT_GUARD_MODE", None)
        os.environ.pop("LANE_GIT_GUARD_BYPASS", None)
        os.environ.pop("CLAUDE_LANE_ID", None)
        _lane_io._PROJECT_ROOT, _lane_io._LANES_DIR, _lane_io.REGISTRY_PATH, _lane_io.CONFIG_PATH = orig
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
