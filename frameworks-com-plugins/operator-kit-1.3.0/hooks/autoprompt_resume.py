#!/usr/bin/env python3
"""
autoprompt_resume (Operator Kit) — Stop hook portátil de retomada cross-sessão.

Generaliza .claude/hooks/autoprompt_resume.py: em vez de paths hardcoded
(00-STATE / PLANO-MESTRE), lê `paths.state_ssot`, `paths.boot_doc` e
`paths.resume_pointer` do operator-profile.yaml (fallback p/ defaults seguros).
Quando a sessão PARA, grava o ponteiro de retomada: aponta o boot-doc, extrai as
pendências ABERTAS ('- [ ]') do SSoT e os últimos commits. A próxima sessão (ou
um ScheduleWakeup) lê e re-entra onde parou.

NÃO inventa estado — só AGREGA o que existe (SSoT + git). Honesto por construção.
NUNCA bloqueia (exit 0 sempre). Idempotente (sobrescreve o ponteiro).

Wire: settings.local.json hooks.Stop (timeout 30). Ver SETTINGS-WIRE.md.
⚠️ Ao wirar, adicionar o `paths.resume_pointer` ao `.gitignore`.

v1.0.0 — 2026-06-19 (Operator Kit · Tier 1 · Stop hook portatil de retomada)
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# loader compartilhado: .../operator-kit/hooks/ -> parents[1] = operator-kit/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from _lib.profile_loader import load_profile, get, profile_path
except Exception:  # noqa: BLE001
    load_profile = None  # type: ignore[assignment]

_BRT = timezone(timedelta(hours=-3))

# Defaults seguros se não houver profile
_DEF_STATE = "docs/plans/execucao/00-STATE.md"
_DEF_BOOT = "docs/plans/execucao/00-STATE.md"
_DEF_POINTER = ".claude/RESUME-NEXT.md"


def _project_root() -> Path:
    """Raiz = onde vive o operator-profile.yaml; senão sobe até achar .git; senão cwd."""
    if load_profile is not None:
        p = profile_path()
        if p is not None:
            # profile na raiz do projeto OU em (staging/)operator-kit/ -> sobe até a raiz real
            d = p.parent
            for cand in (d, *d.parents):
                if (cand / ".git").exists():
                    return cand
            return d
    cur = Path.cwd().resolve()
    for cand in (cur, *cur.parents):
        if (cand / ".git").exists():
            return cand
    return cur


def _cfg(root: Path):
    prof = load_profile() if load_profile is not None else {}
    state = get(prof, "paths.state_ssot", _DEF_STATE) if prof else _DEF_STATE
    boot = get(prof, "paths.boot_doc", _DEF_BOOT) if prof else _DEF_BOOT
    pointer = get(prof, "paths.resume_pointer", _DEF_POINTER) if prof else _DEF_POINTER
    lang = get(prof, "idioma", "pt-BR") if prof else "pt-BR"
    return (root / state, root / boot, root / pointer, lang)


def _open_pendencias(state: Path, limit: int = 25) -> list[str]:
    """Linhas '- [ ]' (pendências abertas) do SSoT. [] se ausente/erro."""
    if not state.exists():
        return []
    out: list[str] = []
    try:
        for line in state.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if s.startswith("- [ ]"):
                out.append(s)
                if len(out) >= limit:
                    break
    except OSError:
        return []
    return out


def _recent_commits(root: Path, n: int = 5) -> list[str]:
    try:
        r = subprocess.run(
            ["git", "log", "--oneline", f"-{n}"],
            cwd=str(root), capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return [ln for ln in r.stdout.splitlines() if ln.strip()]
    except Exception:
        pass
    return []


def _build() -> str:
    root = _project_root()
    state, boot, _pointer, _lang = _cfg(root)
    now = datetime.now(_BRT).strftime("%Y-%m-%d %H:%M BRT")
    pend = _open_pendencias(state)
    commits = _recent_commits(root)
    boot_rel = boot.relative_to(root) if boot.is_relative_to(root) else boot
    state_rel = state.relative_to(root) if state.is_relative_to(root) else state
    lines = [
        "# RESUME-NEXT — retomada automática (autoprompt cross-sessão)",
        "",
        f"> Gerado pelo Stop hook `autoprompt_resume.py` (Operator Kit) em {now}. SOBRESCRITO a cada parada.",
        f"> **Boot-doc canônico:** `{boot_rel}` · **SSoT:** `{state_rel}`. Este arquivo é só o atalho.",
        "",
        "## PASSO 0 (re-verificar AO VIVO — LC-1)",
        "```bash",
        "git log --oneline -3",
        f"# revise as pendências abertas em {state_rel}",
        "```",
        "",
        f"## Pendências ABERTAS no SSoT ({len(pend)})",
    ]
    lines += ["- (nenhuma '- [ ]' aberta encontrada — ver o SSoT)"] if not pend else pend
    lines += ["", "## Últimos commits"]
    lines += ["- (git indisponível)"] if not commits else [f"- {c}" for c in commits]
    lines += ["", "*Para continuar: leia o boot-doc + PASSO 0 ao vivo, depois execute a próxima pendência.*", ""]
    return "\n".join(lines)


def main() -> None:
    try:
        try:
            sys.stdin.read()  # Stop hook envia JSON; só precisamos do trigger
        except Exception:
            pass
        root = _project_root()
        _, _, pointer, _ = _cfg(root)
        pointer.parent.mkdir(parents=True, exist_ok=True)
        pointer.write_text(_build(), encoding="utf-8")
    except Exception:
        pass  # hook de retomada jamais quebra o fluxo
    sys.exit(0)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg in ("--self-test", "-t"):
        txt = _build()
        assert "RESUME-NEXT" in txt and "PASSO 0" in txt, "build incompleto"
        print("self-test OK")
    elif arg == "--print":
        print(_build())
    else:
        main()
