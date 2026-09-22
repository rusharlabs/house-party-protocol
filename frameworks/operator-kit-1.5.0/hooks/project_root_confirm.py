#!/usr/bin/env python3
"""
project_root_confirm (Operator Kit) — PreToolUse WARN-only: detecta ação
(git / Write / Edit) cujo alvo cai FORA da raiz de projeto fixada, sinalizando
possível operação cross-project (ex.: editar outro repo por engano).

Por que existe: quem trabalha com vários repos vizinhos abertos ao mesmo tempo
(ex.: um monorepo + 2-3 repos-satélite no mesmo Desktop) corre o risco de editar
o repo errado por engano — um erro caro e silencioso. Este hook compara a raiz
git do ALVO/cwd com a raiz ESPERADA.

Matcher (no wire): Bash(git) | Write | Edit.
Lê JSON do stdin: tool_input.{file_path, command, cwd}.

Raiz esperada (precedência):
  1. env EXPECTED_ROOT
  2. paths.expected_root do profile
  3. git toplevel da cwd

Bypass: env ALLOW_CROSS_ROOT=1  (ou guardrails.allow_cross_root: true no profile).

WARN em stderr · exit 0 SEMPRE · qualquer erro -> exit 0 (defensivo).

v1.0.0 — 2026-06-19 (Operator Kit · cluster guard-distinct)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from _lib.profile_loader import load_profile, get
except Exception:  # noqa: BLE001
    load_profile = None  # type: ignore[assignment]

    def get(_p, _d, default=None):  # type: ignore[misc]
        return default


def _git_toplevel(start: Path) -> Path | None:
    """git rev-parse --show-toplevel a partir de `start` (dir existente)."""
    try:
        d = start if start.is_dir() else start.parent
        r = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(d), capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip()).resolve()
    except Exception:  # noqa: BLE001
        pass
    return None


def _norm(p: Path | None) -> str:
    return str(p).replace("\\", "/").rstrip("/").lower() if p else ""


def expected_root(prof: dict, cwd: Path) -> Path | None:
    """Raiz esperada por env > profile > git toplevel da cwd."""
    env = os.environ.get("EXPECTED_ROOT")
    if env:
        return Path(env).resolve()
    cfg = get(prof, "paths.expected_root", None)
    if cfg:
        return Path(str(cfg)).resolve()
    return _git_toplevel(cwd)


def target_dir(tool_input: dict, cwd: Path) -> Path:
    """Diretório do alvo: dir do file_path, senão cwd do command, senão cwd."""
    fp = tool_input.get("file_path") or tool_input.get("path")
    if fp:
        p = Path(str(fp))
        if not p.is_absolute():
            p = (cwd / p)
        return p.resolve().parent
    c = tool_input.get("cwd")
    if c:
        return Path(str(c)).resolve()
    return cwd


def evaluate(tool_input: dict, cwd: Path, prof: dict) -> tuple[str, str] | None:
    """
    Compara raiz do alvo vs raiz esperada. Retorna (raiz_esperada, raiz_alvo)
    se divergirem; None se ok ou indeterminado. Determinístico (recebe roots já
    resolvidos via deps), testável sem git através de paths absolutos.
    """
    exp = expected_root(prof, cwd)
    if exp is None:
        return None  # sem âncora confiável -> não avisa (defensivo)
    tgt = target_dir(tool_input, cwd)
    tgt_root = _git_toplevel(tgt) or tgt
    exp_n, tgt_n = _norm(exp), _norm(tgt_root)
    if not exp_n or not tgt_n:
        return None
    # ok se o alvo está dentro da raiz esperada
    if tgt_n == exp_n or tgt_n.startswith(exp_n + "/"):
        return None
    return (str(exp), str(tgt_root))


def _allowed(prof: dict) -> bool:
    if os.environ.get("ALLOW_CROSS_ROOT") == "1":
        return True
    return bool(get(prof, "guardrails.allow_cross_root", False))


def _warn(exp: str, tgt: str) -> None:
    sys.stderr.write(
        "[project_root_confirm] WARNING: target outside the pinned root — possible cross-project write.\n"
        f"  expected root: {exp}\n"
        f"  target root  : {tgt}\n"
        "  -> Confirm this is the right repo. If intentional, set ALLOW_CROSS_ROOT=1. "
        "WARN-only — not blocking.\n"
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
        if _allowed(prof):
            sys.exit(0)
        tool_input = data.get("tool_input") or {}
        if not isinstance(tool_input, dict):
            tool_input = {}
        cwd_raw = data.get("cwd") or os.getcwd()
        cwd = Path(str(cwd_raw)).resolve()
        verdict = evaluate(tool_input, cwd, prof)
        if verdict:
            _warn(*verdict)
    except Exception:  # noqa: BLE001
        pass
    sys.exit(0)


def _self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        base = Path(td).resolve()
        repo_a = base / "repoA"
        repo_b = base / "repoB"
        (repo_a / "sub").mkdir(parents=True)
        repo_b.mkdir()
        prof = {"paths": {"expected_root": str(repo_a)}}
        # 1. alvo DENTRO da raiz esperada -> sem aviso
        v1 = evaluate({"file_path": str(repo_a / "sub" / "x.md")}, repo_a, prof)
        assert v1 is None, f"internal target should not warn: {v1}"
        # 2. alvo em OUTRO repo -> avisa
        v2 = evaluate({"file_path": str(repo_b / "y.md")}, repo_a, prof)
        assert v2 is not None, "cross-root target should warn"
        assert _norm(Path(v2[0])) == _norm(repo_a)
        # 3. sem âncora (sem env/profile/git) -> None (não quebra)
        #    força profile vazio e cwd fora de qualquer git no tmp
        v3 = evaluate({"file_path": str(repo_b / "z.md")}, base, {})
        # base não é git; expected_root cai em git toplevel da cwd (None no tmp)
        assert v3 is None, f"without an anchor it should be None: {v3}"
        # 4. env EXPECTED_ROOT sobrepõe
        os.environ["EXPECTED_ROOT"] = str(repo_a)
        try:
            v4 = evaluate({"file_path": str(repo_b / "y.md")}, base, {})
            assert v4 is not None, "env EXPECTED_ROOT should anchor and warn"
        finally:
            del os.environ["EXPECTED_ROOT"]
        # 5. bypass ALLOW_CROSS_ROOT
        os.environ["ALLOW_CROSS_ROOT"] = "1"
        try:
            assert _allowed({}) is True
        finally:
            del os.environ["ALLOW_CROSS_ROOT"]
        assert _allowed({"guardrails": {"allow_cross_root": True}}) is True
        # 6. target_dir resolve file_path relativo contra cwd
        tdv = target_dir({"file_path": "sub/x.md"}, repo_a)
        assert _norm(tdv) == _norm(repo_a / "sub"), f"wrong relative target_dir: {tdv}"
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
