#!/usr/bin/env python3
"""
rule_capture (Operator Kit) — UserPromptSubmit hook que CAPTURA instrucoes enfaticas.

Implementa o gatilho da REGRA #10 (auto-atualizacao) sem AGIR sobre o CLAUDE.md:
quando o operador da uma instrucao com marcador de enfase
(memory.emphasis_markers do profile — default SEMPRE/NUNCA/ja falei/toda vez/
pare de), o hook ANEXA o texto LITERAL da instrucao + timestamp BRT a um arquivo
duravel em `paths.memory_dir` (default .claude/memory/_captured-rules.md). Isso
preserva a regra entre sessoes p/ depois o `distill_corrections.py` / o agente
decidirem se ela vira regra canonica.

NUNCA interpreta nem reescreve a instrucao — grava verbatim (AGENT-INTEGRITY).
WARN-only: imprime nota em stderr confirmando a captura; NUNCA bloqueia (exit 0).
Defensivo: qualquer erro -> exit 0 sem efeito. Append idempotente-ish (de-dup
por linha literal ja presente no arquivo, p/ nao spammar a mesma regra repetida).

Wire: settings.local.json hooks.UserPromptSubmit (timeout 30). Ver SETTINGS-WIRE.md.

v1.0.0 — 2026-06-19 (Operator Kit · Tier 2 · gatilho da REGRA #10 sem agir)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# loader compartilhado: .../operator-kit/hooks/ -> parents[1] = operator-kit/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from _lib.profile_loader import load_profile, get, profile_path
except Exception:  # noqa: BLE001 — sem loader, cai p/ defaults seguros
    load_profile = None  # type: ignore[assignment]
    get = None  # type: ignore[assignment]
    profile_path = None  # type: ignore[assignment]

_BRT = timezone(timedelta(hours=-3))

_DEF_MEMORY_DIR = ".claude/memory/"
_DEF_CAPTURE_FILE = "_captured-rules.md"
_DEF_MARCADORES = ["SEMPRE", "NUNCA", "ja falei", "toda vez", "pare de"]


def _read_prompt_from_stdin() -> str:
    """Le o JSON do hook e extrai o texto do prompt. '' se algo falhar."""
    try:
        raw = sys.stdin.read()
    except Exception:  # noqa: BLE001
        return ""
    if not raw or not raw.strip():
        return ""
    try:
        data = json.loads(raw)
    except Exception:  # noqa: BLE001 — payload nao-JSON: trata o raw como o proprio prompt
        return raw.strip()
    if isinstance(data, dict):
        for key in ("prompt", "user_prompt", "userPrompt", "message", "text", "content"):
            v = data.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return ""


def detect_markers(prompt: str, marcadores) -> list[str]:
    """Quais marcadores de enfase aparecem no prompt (case-insensitive). Ordem do profile."""
    low = prompt.lower()
    return [m for m in marcadores if str(m).strip() and str(m).lower() in low]


def _already_captured(capture_file: Path, prompt: str) -> bool:
    """True se o texto literal do prompt ja consta no arquivo (de-dup best-effort)."""
    if not capture_file.exists():
        return False
    try:
        existing = capture_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    needle = " ".join(prompt.split())  # normaliza whitespace p/ comparacao
    return needle != "" and needle in " ".join(existing.split())


def build_entry(prompt: str, hits: list[str], now: str) -> str:
    """Bloco a anexar: timestamp + marcadores + texto LITERAL (em blockquote, sem interpretar)."""
    quoted = "\n".join(f"> {ln}" for ln in prompt.splitlines()) or "> (empty)"
    return (
        f"\n## {now} — capture (markers: {', '.join(hits)})\n"
        f"{quoted}\n"
    )


def _ensure_header(capture_file: Path) -> None:
    if capture_file.exists():
        return
    capture_file.parent.mkdir(parents=True, exist_ok=True)
    capture_file.write_text(
        "# CAPTURED rules (verbatim) — trigger RULE #10\n\n"
        "> Appended by `rule_capture.py` (Operator Kit) whenever the operator uses an\n"
        "> emphasis marker (SEMPRE/NUNCA/...). LITERAL text, never interpreted.\n"
        "> Review periodically and promote to a canonical rule whatever deserves it.\n",
        encoding="utf-8",
    )


def _resolve(root: Path):
    prof = load_profile() if load_profile is not None else {}
    mem_dir = get(prof, "paths.memory_dir", _DEF_MEMORY_DIR) if (prof and get) else _DEF_MEMORY_DIR
    marcadores = get(prof, "memory.emphasis_markers", _DEF_MARCADORES) if (prof and get) else _DEF_MARCADORES
    ativo = get(prof, "memory.rule_capture", "on") if (prof and get) else "on"
    if not isinstance(marcadores, list) or not marcadores:
        marcadores = _DEF_MARCADORES
    return (root / mem_dir / _DEF_CAPTURE_FILE, marcadores, str(ativo).lower() not in ("off", "false", "0", "no"))


def _project_root() -> Path:
    if profile_path is not None:
        try:
            p = profile_path()
            if p is not None:
                d = p.parent
                for cand in (d, *d.parents):
                    if (cand / ".git").exists():
                        return cand
                return d
        except Exception:  # noqa: BLE001
            pass
    cur = Path.cwd().resolve()
    for cand in (cur, *cur.parents):
        if (cand / ".git").exists():
            return cand
    return cur


def capture(prompt: str, capture_file: Path, marcadores) -> list[str]:
    """
    Detecta marcadores; se houver, anexa a entry. Retorna a lista de marcadores casados
    (vazia = nada capturado). Nao escreve duplicata exata. Best-effort (erro -> []).
    """
    if not prompt.strip():
        return []
    hits = detect_markers(prompt, marcadores)
    if not hits:
        return []
    try:
        _ensure_header(capture_file)
        if _already_captured(capture_file, prompt):
            return hits  # ja registrado: reporta o match mas nao re-anexa
        now = datetime.now(_BRT).strftime("%Y-%m-%d %H:%M BRT")
        with capture_file.open("a", encoding="utf-8") as fh:
            fh.write(build_entry(prompt, hits, now))
    except OSError:
        return hits  # falha de IO nao deve esconder que houve match
    return hits


def main() -> None:
    try:
        prompt = _read_prompt_from_stdin()
        if prompt:
            root = _project_root()
            capture_file, marcadores, ativo = _resolve(root)
            if ativo:
                hits = capture(prompt, capture_file, marcadores)
                if hits:
                    print(
                        f"[rule_capture] emphatic instruction captured (markers: {', '.join(hits)}) "
                        f"-> {capture_file}",
                        file=sys.stderr,
                    )
    except Exception:  # noqa: BLE001 — hook jamais quebra o fluxo
        pass
    sys.exit(0)


# ---------------------------------------------------------------------------
# self-test (sem rede, sem profile real — escreve so em tmp)
# ---------------------------------------------------------------------------
def _self_test() -> None:
    import tempfile

    marc = list(_DEF_MARCADORES)
    assert detect_markers("NUNCA faca X", marc) == ["NUNCA"]
    assert detect_markers("nunca mais (lowercase)", marc) == ["NUNCA"]
    assert detect_markers("processar batch 3", marc) == [], "without a marker it must not detect"
    assert "SEMPRE" in detect_markers("voce SEMPRE esquece e ja falei isso", marc)

    # JSON de stdin parseado nos varios campos
    with tempfile.TemporaryDirectory() as td:
        cap = Path(td) / "mem" / "_captured-rules.md"

        hits = capture("NUNCA faca git push direto na main", cap, marc)
        assert hits == ["NUNCA"], f"expected detection of NUNCA, got {hits}"
        assert cap.exists(), "capture file should be created"
        body = cap.read_text(encoding="utf-8")
        assert "> NUNCA faca git push direto na main" in body, "literal text should be appended"
        assert "capture" in body

        # de-dup: mesma instrucao nao re-anexa
        capture("NUNCA faca git push direto na main", cap, marc)
        body2 = cap.read_text(encoding="utf-8")
        assert body2.count("> NUNCA faca git push direto na main") == 1, "should not duplicate"

        # prompt sem marcador nao escreve nada novo
        n_antes = len(cap.read_text(encoding="utf-8"))
        assert capture("apenas continue o trabalho normal", cap, marc) == []
        assert len(cap.read_text(encoding="utf-8")) == n_antes, "no marker, no write"

        # build_entry preserva quebras de linha verbatim
        entry = build_entry("linha1\nNUNCA linha2", ["NUNCA"], "2026-06-19 10:00 BRT")
        assert "> linha1" in entry and "> NUNCA linha2" in entry

    print("self-test OK")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    if len(sys.argv) > 1 and sys.argv[1] in ("--self-test", "-t"):
        _self_test()
        sys.exit(0)
    main()
