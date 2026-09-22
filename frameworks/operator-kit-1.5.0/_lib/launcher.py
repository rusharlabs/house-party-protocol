#!/usr/bin/env python3
"""
launcher — resolve o interpretador Python correto (nunca 'py' fora do Windows) + a raiz do
projeto onde o kit foi instalado + um guard de UTF-8 para stdout/stderr.

Escopo: portado de WAVE2 §3.3 (`resolve_python_launcher()`), reduzido ao que o operator-kit
precisa para comandos PERSISTIDOS (scheduler/subprocess/hooks) — decisão C6 do kickoff v2.
Em PROSA de SKILL.md a troca é apenas `py` -> `python` (SKILL-CONTRACT cláusula C5); esta função
é para código que RESOLVE o binário em runtime, não para o texto do comando documentado.

API:
    resolve_repo_root(start=None) -> Path      # CLAUDE_PROJECT_DIR, senão sobe até achar .git/
                                                 # ou operator-profile.yaml, senão pai de _lib/
    resolve_python_launcher(repo_root=None) -> str
    utf8_guard() -> None                        # stdout/stderr -> utf-8, errors=replace

v1.0.0 — 2026-07-10 (Operator Kit · Tier 2 · escopo reduzido)
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def resolve_repo_root(start: Path | None = None) -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and Path(env).exists():
        return Path(env)
    here = (start or Path(__file__).resolve().parent)
    for d in (here, *here.parents):
        if (d / ".git").exists() or (d / "operator-profile.yaml").exists():
            return d
    return here.parent


# Why: `repo_root` mantem o kit configuravel para consumidores externos; o fluxo local usa o default.
def resolve_python_launcher(repo_root: Path | None = None) -> str:
    root = repo_root or resolve_repo_root()
    rels = (".venv/Scripts/python.exe",) if os.name == "nt" else (".venv/bin/python3", ".venv/bin/python")
    for rel in rels:
        cand = root / rel
        if cand.exists():
            return str(cand)
    if sys.executable and Path(sys.executable).exists():
        return sys.executable
    names = ("python", "py") if os.name == "nt" else ("python3", "python")
    for nm in names:
        p = shutil.which(nm)
        if p:
            return p
    raise RuntimeError("no Python found (no venv, no sys.executable, nothing on PATH)")


def utf8_guard() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def _self_test() -> int:
    launcher = resolve_python_launcher()
    assert launcher, "empty launcher"
    name = Path(launcher).name.lower()
    if os.name != "nt":
        assert name not in ("py", "py.exe"), f"launcher 'py' outside Windows: {launcher}"
    assert Path(launcher).exists(), f"resolved launcher does not exist: {launcher}"

    root = resolve_repo_root()
    assert isinstance(root, Path) and root.exists(), f"invalid repo_root: {root}"

    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="launcher_selftest_"))
    try:
        (tmp / ".git").mkdir()
        nested = tmp / "a" / "b" / "_lib"
        nested.mkdir(parents=True)
        found_root = resolve_repo_root(start=nested)
        assert found_root == tmp, f"walking up to .git failed: {found_root} != {tmp}"
    finally:
        import shutil as _sh
        _sh.rmtree(tmp, ignore_errors=True)

    utf8_guard()  # não deve levantar

    print(f"self-test OK — launcher={launcher} root={root}")
    return 0


def main(argv) -> int:
    if argv and argv[0] in ("--self-test", "-t"):
        return _self_test()
    print(resolve_python_launcher())
    return 0


if __name__ == "__main__":
    utf8_guard()
    sys.exit(main(sys.argv[1:]))
