#!/usr/bin/env python3
"""
distill_corrections (Operator Kit) - mines session logs and PROPOSES distilled rules.

Generalizes the pattern of mining sessions for distilled rules (the workflow that already
produced `learned-corrections.md`): reads the last N session logs from `paths.logs_dir`
(default .claude/sessions/), extracts lines that look like CORRECTIONS from the operator
(markers like NEVER/ALWAYS/actually/wrong/fix/stop doing), groups them by simple
similarity (normalization + token key), and keeps ONLY the corrections that recur in
>= K DISTINCT sessions (distill.recurrence_threshold, default 3).

Emits rule candidates (1 line + evidence of which sessions) and updates a
REJECTED ledger (distill.rejected_ledger) so it does not re-propose what has
already been discarded - the keys already in the ledger are filtered out of the candidates.

Applies NOTHING. Writes NOTHING to the target rule. It only PROPOSES (the agent/operator decides).
Honest by construction: it only aggregates what exists in the logs; it never invents a correction.

Usage:
    python distill_corrections.py                 # readable table
    python distill_corrections.py --n 30 --k 4    # custom window and threshold
    python distill_corrections.py --json          # JSON output for a pipeline
    python distill_corrections.py --self-test

Exit: 0 always (proposal tool - never breaks the flow).
stdlib + PyYAML (only to read the profile). Cross-platform (pathlib).

v1.0.0 - 2026-06-19 (Operator Kit - Tier 2 - generalizes recurring-corrections-to-rules)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

# shared loader: .../operator-kit/scripts/ -> parents[1] = operator-kit/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from _lib.profile_loader import load_profile, get, profile_path
except Exception:  # noqa: BLE001 - without the loader, falls back to safe defaults
    load_profile = None  # type: ignore[assignment]
    get = None  # type: ignore[assignment]
    profile_path = None  # type: ignore[assignment]

_BRT = timezone(timedelta(hours=-3))

# Safe defaults if there is no profile
_DEF_LOGS_DIR = ".claude/sessions/"
_DEF_LEDGER = ".claude/memory/_distill-rejeitadas.md"
_DEF_N = 50
_DEF_K = 3

# Heuristic markers of an operator correction (case-insensitive).
# Includes the feedback/emphasis ones + explicit correction verbs.
_MARKERS = (
    "nunca", "sempre", "na verdade", "errado", "errei", "corrige", "corrigir",
    "corrija", "pare de", "para de", "ja falei", "ja te falei", "toda vez",
    "nao faca", "nao faz", "nao e", "deixa de", "exijo", "odeio",
    "voce errou", "ta errado", "esta errado", "isso nao", "de novo",
)
_MARKER_RE = re.compile("|".join(re.escape(m) for m in _MARKERS), re.IGNORECASE)

# pt-BR stopwords for the grouping key (reduces noise in the similarity).
_STOP = {
    "a", "o", "as", "os", "um", "uma", "de", "da", "do", "das", "dos", "e",
    "ou", "que", "para", "pra", "por", "com", "sem", "em", "no", "na", "nos",
    "nas", "se", "ao", "aos", "the", "is", "to", "of", "ja", "voce", "vc",
    "eu", "isso", "isto", "esse", "essa", "este", "esta", "nao", "sim", "me",
    "te", "lhe", "ser", "estar", "foi", "tem", "ter", "fazer", "faz", "feito",
}


def _normalize(text: str) -> str:
    """Lowercase, accents stripped, no punctuation, whitespace collapsed."""
    text = text.lower().strip()
    # Why: a literal table of accented letters only covered the ones somebody remembered; NFD
    # decomposition + dropping the combining marks does the same and covers every letter.
    text = "".join(c for c in unicodedata.normalize("NFD", text)
                   if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _key(text: str, ntokens: int = 6) -> str:
    """Grouping key: top significant tokens, sorted (simple similarity)."""
    norm = _normalize(text)
    toks = [t for t in norm.split() if len(t) > 2 and t not in _STOP]
    if not toks:
        return ""
    # sorts alphabetically so that "X wrong" and "wrong X" collide, takes the first ones
    return " ".join(sorted(set(toks))[:ntokens])


def _strip_log_prefix(line: str) -> str:
    """Removes common log prefixes (timestamp, bullet, '> ', 'Operador:', etc.)."""
    s = line.strip()
    s = re.sub(r"^[-*>#\s]+", "", s)
    s = re.sub(r"^\[?\d{4}-\d{2}-\d{2}[^\]]*\]?\s*", "", s)
    s = re.sub(r"^(max|user|usuario|operador)\s*[:>-]\s*", "", s, flags=re.IGNORECASE)
    return s.strip()


def _is_correction(line: str) -> bool:
    """True if the line looks like a correction (has a marker and is short enough to be an instruction)."""
    if not (3 < len(line) <= 400):
        return False
    return bool(_MARKER_RE.search(line))


def _session_files(logs_dir: Path, n: int) -> list[Path]:
    """The N most recent session logs (.md/.jsonl), excluding pointers/indexes."""
    if not logs_dir.exists():
        return []
    skip_substr = ("INDEX", "POINTER", "LATEST", "CURRENT", "NEXT", "_archive", "archive")
    files: list[Path] = []
    for p in logs_dir.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".md", ".jsonl", ".txt"):
            continue
        if any(s in p.name for s in skip_substr):
            continue
        files.append(p)
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return files[:n]


def _extract_from_file(path: Path) -> list[str]:
    """Corrections (cleaned text) found in a session file."""
    out: list[str] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in raw.splitlines():
        clean = _strip_log_prefix(line)
        if _is_correction(clean):
            out.append(clean)
    return out


def _load_ledger_keys(ledger: Path) -> set[str]:
    """Reads the keys already rejected (marked as '<!-- key: ... -->' in the ledger). set() if absent."""
    keys: set[str] = set()
    if not ledger.exists():
        return keys
    try:
        for line in ledger.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.search(r"<!--\s*key:\s*(.+?)\s*-->", line)
            if m:
                k = m.group(1).strip()
                # ignore the header's documentation placeholder ('... ')
                if k and k != "...":
                    keys.add(k)
    except OSError:
        pass
    return keys


def distill(logs_dir: Path, n: int, k: int, ledger_keys: set[str] | None = None) -> list[dict]:
    """
    Returns rule candidates sorted by recurrence desc.
    Each item: {key, example, n_sessions, sessions:[...], ocorrencias}.
    Only keys that recur in >= k DISTINCT sessions and are not in the ledger are included.
    """
    ledger_keys = ledger_keys or set()
    files = _session_files(logs_dir, n)
    # key -> {sessoes:set, exemplo:str, ocorrencias:int}
    groups: dict[str, dict] = {}
    for f in files:
        sess_name = f.name
        seen_in_file: set[str] = set()
        for corr in _extract_from_file(f):
            key = _key(corr)
            if not key:
                continue
            g = groups.setdefault(key, {"sessions": set(), "example": corr, "ocorrencias": 0})
            g["ocorrencias"] += 1
            g["sessions"].add(sess_name)
            # keeps the shortest exemplo (tends to be the cleanest instruction)
            if len(corr) < len(g["example"]):
                g["example"] = corr
            seen_in_file.add(key)

    candidates: list[dict] = []
    for key, g in groups.items():
        if key in ledger_keys:
            continue
        session_count = len(g["sessions"])
        if session_count >= k:
            candidates.append({
                "key": key,
                "example": g["example"],
                "n_sessions": session_count,
                "sessions": sorted(g["sessions"]),
                "ocorrencias": g["ocorrencias"],
            })
    candidates.sort(key=lambda c: (c["n_sessions"], c["ocorrencias"]), reverse=True)
    return candidates


def _ensure_ledger(ledger: Path) -> None:
    """Creates the rejected-candidates ledger with a header if it does not exist yet."""
    if ledger.exists():
        return
    try:
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(
            "# Distill — candidatas REJEITADAS (nao re-propor)\n\n"
            "> Ledger do `distill_corrections.py`. Cada item rejeitado leva um marcador\n"
            "> `<!-- key: ... -->` que o distill usa p/ NUNCA re-propor a mesma correcao.\n"
            "> Adicione aqui (com o marcador `key:`) o que voce decidiu NAO virar regra.\n\n",
            encoding="utf-8",
        )
    except OSError:
        pass  # the ledger is best-effort; its absence does not break the distill


def _resolve_paths(root: Path):
    prof = load_profile() if load_profile is not None else {}
    logs_dir = get(prof, "paths.logs_dir", _DEF_LOGS_DIR) if (prof and get) else _DEF_LOGS_DIR
    ledger = get(prof, "distill.rejected_ledger", _DEF_LEDGER) if (prof and get) else _DEF_LEDGER
    k = get(prof, "distill.recurrence_threshold", _DEF_K) if (prof and get) else _DEF_K
    n = get(prof, "distill.session_window", _DEF_N) if (prof and get) else _DEF_N
    return (root / logs_dir, root / ledger, int(k), int(n))


def _project_root() -> Path:
    """Root = where the profile lives; otherwise walks up to .git; otherwise cwd."""
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


def main(argv) -> int:
    ap = argparse.ArgumentParser(description="Distills recurring corrections from the session logs (PROPOSES, does not apply).")
    ap.add_argument("--n", type=int, default=None, help="session window (default: profile or 50)")
    ap.add_argument("--k", type=int, default=None, help="recurrence threshold in distinct sessions (default: profile or 3)")
    ap.add_argument("--json", action="store_true", help="JSON output")
    args = ap.parse_args(argv)

    root = _project_root()
    logs_dir, ledger, k_prof, n_prof = _resolve_paths(root)
    n = args.n if args.n is not None else n_prof
    k = args.k if args.k is not None else k_prof

    _ensure_ledger(ledger)
    ledger_keys = _load_ledger_keys(ledger)
    candidates = distill(logs_dir, n=n, k=k, ledger_keys=ledger_keys)

    now = datetime.now(_BRT).strftime("%Y-%m-%d %H:%M BRT")
    if args.json:
        print(json.dumps({
            "generated": now,
            "logs_dir": str(logs_dir),
            "window_n": n,
            "limiar_k": k,
            "rejeitadas_no_ledger": len(ledger_keys),
            "candidatas": candidates,
        }, ensure_ascii=False, indent=2))
        return 0

    print(f"# Corrections distill — {now}")
    print(f"# logs: {logs_dir}  | window N={n}  | threshold K={k} distinct sessions")
    print(f"# rejected-rules ledger: {ledger}  ({len(ledger_keys)} keys filtered out)")
    if not logs_dir.exists():
        print(f"\n(no session directory at {logs_dir} — nothing to distill)")
        return 0
    if not candidates:
        print(f"\n(no correction recurred in >= {k} distinct sessions — nothing to propose)")
        return 0
    print(f"\n{len(candidates)} rule candidate(s) (recurrence >= {k}):\n")
    for i, c in enumerate(candidates, 1):
        print(f"{i}. [{c['n_sessions']} sessions / {c['ocorrencias']} occurrences] {c['example']}")
        print(f"   evidence: {', '.join(c['sessions'])}")
        print(f"   <!-- key: {c['key']} -->  (paste into the ledger to reject)")
        print()
    print("PROPOSAL only — nothing was applied. Decide which ones become rules in "
          "`distill.target_rule`; reject the rest in the ledger.")
    return 0


# ---------------------------------------------------------------------------
# self-test (sem rede, sem profile real — usa fixture em tmp)
# ---------------------------------------------------------------------------
def _self_test() -> None:
    import tempfile

    # pure heuristics
    assert _is_correction("NUNCA faca git push direto na main")
    assert _is_correction("na verdade o cliente e o Acme, errado de novo")
    assert not _is_correction("processando batch 3 de 8 com sucesso")
    # order-invariant: the same set of significant tokens in different orders -> same key
    assert _key("git push main NUNCA") == _key("NUNCA main push git"), "chave deve ser ordem-invariante"
    # different sets -> different keys
    assert _key("git push main") != _key("git push staging"), "tokens distintos -> chaves distintas"
    assert _strip_log_prefix("- [2026-06-19 10:00] Operador: NUNCA faz X") == "NUNCA faz X"

    with tempfile.TemporaryDirectory() as td:
        logs = Path(td) / "sessions"
        logs.mkdir()
        # 3 distinct sessions repeat the SAME correction -> should become a candidate (k=3)
        for d in ("01", "02", "03"):
            (logs / f"SESSION-2026-06-{d}.md").write_text(
                "fizemos progresso no pipeline\n"
                "Operador: NUNCA usar a porta 8000 pra subir o servidor\n"
                "outro texto qualquer sem marcador\n",
                encoding="utf-8",
            )
        # 1 session with a unique correction -> should NOT pass the threshold
        (logs / "SESSION-2026-06-04.md").write_text(
            "pare de criar arquivos na raiz do docs\n", encoding="utf-8"
        )
        # pointer/index should be ignored
        (logs / "SESSION-INDEX.json").write_text("{}", encoding="utf-8")

        cands = distill(logs, n=50, k=3)
        assert len(cands) == 1, f"expected 1 candidate, got {len(cands)}"
        assert cands[0]["n_sessions"] == 3, "must recur across 3 distinct sessions"
        assert "8000" in cands[0]["example"]

        # k=4 should not find anything (it only recurred in 3)
        assert distill(logs, n=50, k=4) == [], "k=4 nao deveria achar candidatas"

        # ledger filters the key -> it disappears from the candidates
        key = cands[0]["key"]
        assert distill(logs, n=50, k=3, ledger_keys={key}) == [], "ledger deveria filtrar a chave"

        # ledger created and read correctly
        ledger = Path(td) / "mem" / "_rej.md"
        _ensure_ledger(ledger)
        assert ledger.exists()
        ledger.write_text(ledger.read_text(encoding="utf-8") + f"\n- descartado <!-- key: {key} -->\n",
                           encoding="utf-8")
        assert key in _load_ledger_keys(ledger), "ledger key deveria ser lida"

    print("self-test OK")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    if len(sys.argv) > 1 and sys.argv[1] in ("--self-test", "-t"):
        _self_test()
        sys.exit(0)
    sys.exit(main(sys.argv[1:]))
