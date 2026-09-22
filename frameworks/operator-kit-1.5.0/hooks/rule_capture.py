#!/usr/bin/env python3
"""
rule_capture (Operator Kit) - UserPromptSubmit hook that CAPTURES emphatic instructions.

Implements the trigger for RULE #10 (self-update) without ACTING on CLAUDE.md:
when the operator gives an instruction with an emphasis marker
(memory.emphasis_markers from the profile - the default list is in the operator's own
language, `SEMPRE`/`NUNCA`/`ja falei`/`toda vez`/`pare de`; replace it with yours), the
hook APPENDS the LITERAL text of the instruction + a BRT timestamp to a
durable file at `paths.memory_dir` (default .claude/memory/_captured-rules.md). This
preserves the rule across sessions so that `distill_corrections.py` / the agent can
later decide whether it becomes a canonical rule.

NEVER interprets or rewrites the instruction - records it verbatim (AGENT-INTEGRITY).
WARN-only: prints a note to stderr confirming the capture; NEVER blocks (exit 0).
Defensive: any error -> exit 0 with no effect. Append idempotent-ish (de-dup by
literal line already present in the file, to avoid spamming the same repeated rule).

Wire: settings.local.json hooks.UserPromptSubmit (timeout 30). See SETTINGS-WIRE.md.

v1.0.0 - 2026-06-19 (Operator Kit - Tier 2 - RULE #10 trigger without acting)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# shared loader: .../operator-kit/hooks/ -> parents[1] = operator-kit/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from _lib.profile_loader import load_profile, get, profile_path
except Exception:  # noqa: BLE001 - no loader, falls back to safe defaults
    load_profile = None  # type: ignore[assignment]
    get = None  # type: ignore[assignment]
    profile_path = None  # type: ignore[assignment]

_BRT = timezone(timedelta(hours=-3))

_DEF_MEMORY_DIR = ".claude/memory/"
_DEF_CAPTURE_FILE = "_captured-rules.md"
_DEF_MARCADORES = ["SEMPRE", "NUNCA", "ja falei", "toda vez", "pare de"]


def _read_prompt_from_stdin() -> str:
    """Reads the hook's JSON and extracts the prompt text. '' if anything fails."""
    try:
        raw = sys.stdin.read()
    except Exception:  # noqa: BLE001
        return ""
    if not raw or not raw.strip():
        return ""
    try:
        data = json.loads(raw)
    except Exception:  # noqa: BLE001 - non-JSON payload: treat the raw text as the prompt itself
        return raw.strip()
    if isinstance(data, dict):
        for key in ("prompt", "user_prompt", "userPrompt", "message", "text", "content"):
            v = data.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return ""


def detect_markers(prompt: str, marcadores) -> list[str]:
    """Which emphasis markers appear in the prompt (case-insensitive). Order from the profile."""
    low = prompt.lower()
    return [m for m in marcadores if str(m).strip() and str(m).lower() in low]


def _already_captured(capture_file: Path, prompt: str) -> bool:
    """True if the prompt's literal text is already in the file (best-effort de-dup)."""
    if not capture_file.exists():
        return False
    try:
        existing = capture_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    needle = " ".join(prompt.split())  # normalizes whitespace for comparison
    return needle != "" and needle in " ".join(existing.split())


def build_entry(prompt: str, hits: list[str], now: str) -> str:
    """Block to append: timestamp + markers + LITERAL text (in blockquote, uninterpreted)."""
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
    Detects markers; if there are any, appends the entry. Returns the list of matched markers
    (empty = nothing captured). Does not write an exact duplicate. Best-effort (error -> []).
    """
    if not prompt.strip():
        return []
    hits = detect_markers(prompt, marcadores)
    if not hits:
        return []
    try:
        _ensure_header(capture_file)
        if _already_captured(capture_file, prompt):
            return hits  # already recorded: reports the match but does not re-append
        now = datetime.now(_BRT).strftime("%Y-%m-%d %H:%M BRT")
        with capture_file.open("a", encoding="utf-8") as fh:
            fh.write(build_entry(prompt, hits, now))
    except OSError:
        return hits  # an IO failure should not hide that a match happened
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
    except Exception:  # noqa: BLE001 - hook must never break the flow
        pass
    sys.exit(0)


# ---------------------------------------------------------------------------
# self-test (no network, no real profile - writes only to tmp)
# ---------------------------------------------------------------------------
def _self_test() -> None:
    import tempfile

    marc = list(_DEF_MARCADORES)
    assert detect_markers("NUNCA faca X", marc) == ["NUNCA"]
    assert detect_markers("nunca mais (lowercase)", marc) == ["NUNCA"]
    assert detect_markers("processar batch 3", marc) == [], "without a marker it must not detect"
    assert "SEMPRE" in detect_markers("voce SEMPRE esquece e ja falei isso", marc)

    # JSON from stdin parsed across the several fields
    with tempfile.TemporaryDirectory() as td:
        cap = Path(td) / "mem" / "_captured-rules.md"

        hits = capture("NUNCA faca git push direto na main", cap, marc)
        assert hits == ["NUNCA"], f"expected detection of NUNCA, got {hits}"
        assert cap.exists(), "capture file should be created"
        body = cap.read_text(encoding="utf-8")
        assert "> NUNCA faca git push direto na main" in body, "literal text should be appended"
        assert "capture" in body

        # de-dup: the same instruction does not get re-appended
        capture("NUNCA faca git push direto na main", cap, marc)
        body2 = cap.read_text(encoding="utf-8")
        assert body2.count("> NUNCA faca git push direto na main") == 1, "should not duplicate"

        # a prompt with no marker writes nothing new
        n_antes = len(cap.read_text(encoding="utf-8"))
        assert capture("apenas continue o trabalho normal", cap, marc) == []
        assert len(cap.read_text(encoding="utf-8")) == n_antes, "no marker, no write"

        # build_entry preserves line breaks verbatim
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
