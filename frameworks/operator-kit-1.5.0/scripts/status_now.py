#!/usr/bin/env python3
"""
status_now (Operator Kit) -- answers "where are we?" in a fixed template.

Reads `paths.state_ssot` from operator-profile.yaml and extracts, from the SSoT markdown:
  - STAGE / PHASE   (line starting with '#', '## Fase', 'Etapa:', 'Fase:'...)
  - PROGRESS %      (first 'NN%' found in the doc)
  - BLOCKERS        (count of open pending items '- [ ]')
  - NEXT ACTION     (text of the 1st open pending item '- [ ]')

UNBREAKABLE RULE (AGENT-INTEGRITY / LC-1): a field not found becomes '--' with
an explicit note -- NEVER invents a number, stage or next action. Without a profile
or SSoT, it degrades to an honest template that points out what's missing to configure.

Usage:
    python status_now.py            # prints the "where are we?" template
    python status_now.py --json     # same info, stable JSON for programmatic consumption
    python status_now.py --self-test

Exit: 0 always (a status report is never a gate). stdlib + PyYAML (via loader).

v1.0.0 -- 2026-06-19 (Operator Kit -- Tier 1)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# import the shared kit loader (.../operator-kit/_lib/profile_loader.py)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from _lib.profile_loader import load_profile, get, profile_path
except Exception:  # noqa: BLE001 -- without the loader, degrade to safe defaults (NEVER crashes)
    load_profile = None  # type: ignore[assignment]
    get = None  # type: ignore[assignment]
    profile_path = None  # type: ignore[assignment]

# honest marker for a field not found (never make one up)
_NA = "--"

# extraction regexes
_RE_PCT = re.compile(r"(\d{1,3})\s*%")
_RE_OPEN_TODO = re.compile(r"^\s*[-*]\s+\[\s\]\s+(.*\S)?\s*$")
_RE_DONE_TODO = re.compile(r"^\s*[-*]\s+\[[xX]\]\s")
# labels that usually carry the current stage/phase.
# Captures the WHOLE phrase starting at the label (including the word "Fase"/"Etapa"),
# tolerating a markdown heading (#) and an optional ':' right after the label.
_RE_STAGE_LABEL = re.compile(
    r"^\s*#{0,6}\s*((?:etapa|fase|stage|phase|sprint|milestone)\b\s*:?\s*.*\S)",
    re.IGNORECASE,
)


def _resolve_ssot_path(profile: dict, base: Path) -> Path | None:
    """Resolves the SSoT's absolute path from paths.state_ssot (relative to the project root)."""
    if get is None:
        return None
    rel = get(profile, "paths.state_ssot", None)
    if not rel:
        return None
    # project root = folder that contains the profile, going up from staging/operator-kit if that's the case
    root = base
    if profile_path is not None:
        p = profile_path()
        if p is not None:
            root = p.resolve().parent
            # if the profile lives in .../staging/operator-kit, the project root is 2 levels up
            parts = root.parts
            if len(parts) >= 2 and parts[-1] == "operator-kit" and parts[-2] == "staging":
                root = root.parents[1]
            elif parts and parts[-1] == "operator-kit":
                root = root.parent
    cand = (root / rel)
    return cand


def extract_status(text: str) -> dict:
    """Extracts stage/%/blockers/next-action from the SSoT markdown. Missing fields => _NA + note."""
    stage = _NA
    pct = _NA
    open_todos: list[str] = []
    notes: list[str] = []

    lines = text.splitlines()

    # STAGE: first explicit label (Etapa:/Fase:/##Fase...) with content; otherwise the 1st non-empty heading
    for ln in lines:
        m = _RE_STAGE_LABEL.match(ln)
        if m and (m.group(1) or "").strip():
            stage = re.sub(r"\s+", " ", m.group(1).strip())
            break
    if stage is _NA:
        for ln in lines:
            s = ln.strip()
            if s.startswith("#"):
                h = s.lstrip("#").strip()
                if h:
                    stage = h
                    break
    if stage is _NA:
        notes.append("stage not found in the SSoT (no heading/label Fase|Etapa|Stage|Phase)")

    # PROGRESS %: first occurrence of 'NN%'
    mpct = _RE_PCT.search(text)
    if mpct:
        pct = f"{int(mpct.group(1))}%"
    else:
        notes.append("progress % not found in the SSoT")

    # BLOCKERS / NEXT ACTION: open pending items '- [ ]'
    for ln in lines:
        m = _RE_OPEN_TODO.match(ln)
        if m:
            open_todos.append((m.group(1) or "(no description)").strip())

    next_action = open_todos[0] if open_todos else _NA
    if not open_todos:
        notes.append("no open '- [ ]' item in the SSoT (next action undefined)")

    return {
        "etapa": stage,
        "progresso": pct,
        "bloqueios_abertos": len(open_todos),
        "proxima_acao": next_action,
        "todos_abertos": open_todos,
        "notas": notes,
    }


def build_status(start: Path | None = None) -> dict:
    """Builds the complete status: resolves profile -> SSoT -> extracts. Degrades without crashing."""
    base = Path(start or Path.cwd())
    profile = load_profile() if load_profile is not None else {}
    ssot_rel = get(profile, "paths.state_ssot", None) if get is not None else None
    ssot = _resolve_ssot_path(profile, base) if profile else None

    data = {
        "projeto": (get(profile, "project", _NA) if get is not None else _NA) or _NA,
        "ssot_path": str(ssot) if ssot else _NA,
        "ssot_rel": ssot_rel or _NA,
        "etapa": _NA,
        "progresso": _NA,
        "bloqueios_abertos": _NA,
        "proxima_acao": _NA,
        "todos_abertos": [],
        "notas": [],
    }

    if not profile:
        data["notas"].append("operator-profile.yaml missing (or PyYAML unavailable) — configure paths.state_ssot")
        return data
    if not ssot_rel:
        data["notas"].append("paths.state_ssot not defined in operator-profile.yaml")
        return data
    if ssot is None or not ssot.exists():
        data["notas"].append(f"SSoT not found on disk: {ssot_rel}")
        return data

    try:
        text = ssot.read_text(encoding="utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001 -- never crashes
        data["notas"].append(f"failed to read the SSoT: {e}")
        return data

    ext = extract_status(text)
    data.update(ext)
    return data


def render_template(data: dict) -> str:
    """Renders the fixed 'where are we?' template."""
    proj = data.get("projeto", _NA)
    stage = data.get("etapa", _NA)
    pct = data.get("progresso", _NA)
    blockers = data.get("bloqueios_abertos", _NA)
    next_action = data.get("proxima_acao", _NA)
    ssot = data.get("ssot_rel", _NA)
    notes = data.get("notas", []) or []

    lines = [
        "+-----------------------------------------------------------+",
        "|  WHERE ARE WE?                                            |",
        "+-----------------------------------------------------------+",
        f"  PROJECT     : {proj}",
        f"  STAGE       : {stage}",
        f"  PROGRESS    : {pct}",
        f"  BLOCKERS    : {blockers} open item(s)" if blockers != _NA else f"  BLOCKERS    : {_NA}",
        f"  NEXT ACTION : {next_action}",
        f"  SOURCE (SSoT): {ssot}",
    ]
    if notes:
        lines.append("  ---")
        lines.append("  NOTES (fields '--' = not found, NOT invented):")
        for n in notes:
            lines.append(f"    - {n}")
    return "\n".join(lines)


def _self_test() -> None:
    import tempfile

    # fixture: SSoT with a stage, %, and pending items
    ssot_text = (
        "# Demo Project\n"
        "## Phase 2 - Pipeline\n"
        "Current progress: 37% complete\n\n"
        "- [x] Initial setup\n"
        "- [ ] Process BATCH-004\n"
        "- [ ] Validate dossiers\n"
    )
    parsed = extract_status(ssot_text)
    assert parsed["etapa"] == "Phase 2 - Pipeline", parsed["etapa"]
    assert parsed["progresso"] == "37%", parsed["progresso"]
    assert parsed["bloqueios_abertos"] == 2, parsed["bloqueios_abertos"]
    assert parsed["proxima_acao"] == "Process BATCH-004", parsed["proxima_acao"]

    # empty fixture: everything '--' + notes (NEVER invents)
    parsed2 = extract_status("text with nothing structured in it\n")
    assert parsed2["etapa"] == _NA
    assert parsed2["progresso"] == _NA
    assert parsed2["proxima_acao"] == _NA
    assert parsed2["bloqueios_abertos"] == 0
    assert len(parsed2["notas"]) >= 2

    # build_status without a profile (isolated tmp cwd) degrades without crashing
    with tempfile.TemporaryDirectory() as td:
        import os
        env_bak = os.environ.pop("OPERATOR_PROFILE", None)
        try:
            data = build_status(start=Path(td))
            assert isinstance(data, dict)
            assert "notas" in data
            # render never crashes
            out = render_template(data)
            assert "WHERE ARE WE?" in out
        finally:
            if env_bak is not None:
                os.environ["OPERATOR_PROFILE"] = env_bak

    # render of a complete fixture contains the extracted values
    data_full = {
        "projeto": "demo", "ssot_rel": "x.md", "etapa": "Phase 2",
        "progresso": "37%", "bloqueios_abertos": 2, "proxima_acao": "do X", "notas": [],
    }
    out_full = render_template(data_full)
    assert "Phase 2" in out_full and "37%" in out_full and "do X" in out_full

    print("self-test OK")


def main(argv) -> int:
    if argv and argv[0] in ("--self-test", "-t"):
        _self_test()
        return 0
    data = build_status()
    if "--json" in argv:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        print(render_template(data))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
