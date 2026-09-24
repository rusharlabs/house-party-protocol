#!/usr/bin/env python3
"""
audit_plan (Operator Kit) - plan vs reality auditor.

Materializes LC-3 (rules/learned-corrections.md): a plan NEVER defines the status -
the filesystem + the git log do. This tool takes a markdown plan file, EXTRACTS the
declared deliverables (checkboxes, paths/files cited in backticks, "Deliverable"
sections) and, for EACH one, checks it against reality:

    - does it exist on disk? (direct Path OR glob)
    - does it show up in the git history? (git log --grep <term>)

Returns a `FEITO` / `PARCIAL` / `AUSENTE` table (markdown or --json). It does not invent:
what cannot be confirmed becomes `AUSENTE`, never "probably done". Those three are the
literal status strings the code assigns and compares - they are values, not prose.

Classification:
    `FEITO`   = the file exists on disk (strong confirmation)
    `PARCIAL` = does not exist on disk, but shows up in the git log (mentioned/started)
    `AUSENTE` = does not exist and does not show up in the git log

Usage:
    python audit_plan.py docs/plans/2026-06-19-X.md
    python audit_plan.py plan.md --json
    python audit_plan.py plan.md --no-git               # skip git log (offline)
    python audit_plan.py plan.md --repo /path/to/repo   # root to resolve paths
    python audit_plan.py plan.md  --extra-regex '`([^`]+\\.sql)`'
    python audit_plan.py --self-test

Exit: 0 = ran (independent of the audit result) - 2 = invalid usage.
stdlib ONLY. Cross-platform (pathlib). Never uses curl/wget.

v1.0.0 - 2026-06-19 (Operator Kit - Tier 1 - materializes LC-3)
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

# shared kit loader (.../operator-kit/_lib/profile_loader.py)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from _lib.profile_loader import load_profile, get
except Exception:  # noqa: BLE001 - without the loader the rest still works (safe defaults)
    load_profile = None  # type: ignore[assignment]
    get = None  # type: ignore[assignment]

# ── deliverable extraction ────────────────────────────────────────────────

# checkbox markdown: "- [ ] foo" / "- [x] bar" / "* [X] baz"
RE_CHECKBOX = re.compile(r"^\s*[-*]\s*\[(?P<mark>[ xX])\]\s*(?P<text>.+?)\s*$")
# path/file cited in backticks: `core/paths.py`, `scripts/x.py`
RE_BACKTICK_PATH = re.compile(r"`([^`\n]+)`")
# "Deliverable: ..." / "Entregável: ..." section (line or heading)
RE_DELIVERABLE = re.compile(
    r"^\s*#{0,6}\s*(?:deliverable|entreg[áa]vel|artefato)s?\s*[:\-]\s*(?P<text>.+?)\s*$",
    re.IGNORECASE,
)
# heuristic: does a token look like a path/file? (has / or \ or an extension)
RE_LOOKS_LIKE_PATH = re.compile(r"[\\/]|\.[A-Za-z0-9]{1,6}(\b|$)")
# plausible "file" extensions (avoids capturing `R$100K` or `8-12%`)
_PLAUSIBLE_EXT = {
    "py", "md", "yaml", "yml", "json", "js", "ts", "tsx", "jsx", "sql", "sh",
    "ps1", "bat", "html", "css", "txt", "toml", "ini", "cfg", "env", "jsonl",
}


def _looks_like_path(token: str) -> bool:
    """True if the backticked token looks like a path/file (not a metric/command)."""
    t = token.strip()
    if not t or " " in t.split("/")[-1] and "/" not in t:
        # tokens with a space and no slash are rarely paths (e.g.: `git status`)
        pass
    if "/" in t or "\\" in t:
        return True
    if "." in t:
        ext = t.rsplit(".", 1)[-1].lower()
        return ext in _PLAUSIBLE_EXT
    return False


def extract_deliverables(text: str, extra_regexes=None) -> list[dict]:
    """
    Extracts deliverables from a markdown plan. Each item:
        {kind, text, path (str|None), checked (bool|None)}
    Dedup by (tipo, normalized texto).
    """
    items: list[dict] = []
    seen: set[tuple] = set()

    def add(kind: str, text: str, path: str | None = None, checked=None) -> None:
        text = (text or "").strip()
        key = (kind, (path or text).lower())
        if not text and not path:
            return
        if key in seen:
            return
        seen.add(key)
        items.append({"kind": kind, "text": text, "path": path, "checked": checked})

    for raw in text.splitlines():
        line = raw.rstrip("\n")

        m = RE_CHECKBOX.match(line)
        if m:
            txt = m.group("text").strip()
            checked = m.group("mark").lower() == "x"
            # if the checkbox text contains a backticked path, capture it as path
            path = None
            bt = RE_BACKTICK_PATH.findall(txt)
            for cand in bt:
                if _looks_like_path(cand):
                    path = cand.strip()
                    break
            add("checkbox", txt, path=path, checked=checked)
            continue

        m = RE_DELIVERABLE.match(line)
        if m:
            txt = m.group("text").strip()
            path = None
            for cand in RE_BACKTICK_PATH.findall(txt):
                if _looks_like_path(cand):
                    path = cand.strip()
                    break
            add("deliverable", txt, path=path)
            continue

        # paths cited in backticks on any line
        for cand in RE_BACKTICK_PATH.findall(line):
            cand = cand.strip()
            if _looks_like_path(cand):
                add("path", cand, path=cand)

    # customizable extra regexes (capture group 1 as path)
    for pat in (extra_regexes or []):
        try:
            rx = re.compile(pat)
        except re.error:
            continue
        for m in rx.finditer(text):
            cand = (m.group(1) if m.groups() else m.group(0)).strip()
            if cand:
                add("path", cand, path=cand)

    return items


# ── checking against reality ───────────────────────────────────────────────

def path_exists(path_str: str, repo_root: Path) -> bool:
    """Does it exist on disk? Tries a direct Path (abs and relative to the repo) and glob."""
    if not path_str:
        return False
    p = Path(path_str)
    candidates = [p]
    if not p.is_absolute():
        candidates.append(repo_root / p)
    for c in candidates:
        try:
            if c.exists():
                return True
        except OSError:
            pass
    # glob (supports wildcards and partial match by filename)
    try:
        if any(ch in path_str for ch in "*?[]"):
            if list(repo_root.glob(path_str)):
                return True
        else:
            name = Path(path_str).name
            if name:
                # shallow match by filename, limited so it does not scan the whole world
                hits = 0
                for _ in repo_root.rglob(name):
                    hits += 1
                    break
                if hits:
                    return True
    except (OSError, ValueError):
        pass
    return False


def git_log_mentions(term: str, repo_root: Path, timeout: int = 20) -> bool:
    """Did git log --grep <term> find a commit? False on any failure (no git, etc.)."""
    term = (term or "").strip()
    if not term:
        return False
    # use the filename if it is a path (more likely to show up in a commit)
    needle = Path(term).name if (_looks_like_path(term)) else term
    needle = needle.strip()
    if not needle:
        return False
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "log", "--all", "-i",
             "--grep", needle, "--oneline", "-n", "1"],
            capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:  # noqa: BLE001 - git missing/error => does not mention
        return False


def classify(item: dict, repo_root: Path, use_git: bool) -> dict:
    """Classifies a deliverable as FEITO/PARCIAL/AUSENTE with evidence."""
    probe = item.get("path") or item.get("text") or ""
    on_disk = path_exists(item["path"], repo_root) if item.get("path") else False
    in_git = git_log_mentions(probe, repo_root) if use_git else False

    if on_disk:
        status = "FEITO"
    elif in_git:
        status = "PARCIAL"
    else:
        status = "AUSENTE"

    # checkbox marked [x] but with no evidence on disk/git: flag as suspect
    if item.get("checked") and status == "AUSENTE":
        status = "AUSENTE"  # keep AUSENTE - the point of LC-3 is not to trust the [x]
    return {**item, "status": status, "on_disk": on_disk, "in_git": in_git}


def audit(plan_path: Path, repo_root: Path, use_git: bool = True,
          extra_regexes=None) -> dict:
    """Reads the plan, extracts and classifies all deliverables."""
    text = plan_path.read_text(encoding="utf-8", errors="replace")
    items = extract_deliverables(text, extra_regexes=extra_regexes)
    rows = [classify(it, repo_root, use_git) for it in items]
    summary = {"FEITO": 0, "PARCIAL": 0, "AUSENTE": 0}
    for r in rows:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    return {
        "plano": str(plan_path),
        "repo": str(repo_root),
        "git_consultado": use_git,
        "total": len(rows),
        "summary": summary,
        "itens": rows,
    }


# ── render ──────────────────────────────────────────────────────────────────

def render_markdown(result: dict) -> str:
    out: list[str] = []
    out.append(f"# Plan audit — {Path(result['plano']).name}")
    out.append("")
    r = result["summary"]
    out.append(f"Deliverables: **{result['total']}** · "
               f"FEITO {r.get('FEITO', 0)} · PARCIAL {r.get('PARCIAL', 0)} · "
               f"AUSENTE {r.get('AUSENTE', 0)}"
               + ("" if result["git_consultado"] else "  _(git not consulted)_"))
    out.append("")
    if not result["itens"]:
        out.append("_No deliverable detected in the plan (no checkbox/path/Deliverable section)._")
        return "\n".join(out)
    out.append("| Status | Type | Deliverable | Disk | Git |")
    out.append("|--------|------|-------------|:----:|:---:|")
    for it in result["itens"]:
        target = it.get("path") or it.get("text") or ""
        target = target.replace("|", "\\|")
        if len(target) > 70:
            target = target[:67] + "..."
        disk = "yes" if it["on_disk"] else "—"
        gitm = "yes" if it["in_git"] else "—"
        out.append(f"| {it['status']} | {it['kind']} | {target} | {disk} | {gitm} |")
    return "\n".join(out)


def main(argv) -> int:
    if argv and argv[0] in ("--self-test", "-t"):
        _self_test()
        return 0

    as_json = "--json" in argv
    use_git = "--no-git" not in argv
    argv = [a for a in argv if a not in ("--json", "--no-git")]

    repo_root: Path | None = None
    extra_regexes: list[str] = []
    positional: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--repo" and i + 1 < len(argv):
            repo_root = Path(argv[i + 1]); i += 2; continue
        if a == "--extra-regex" and i + 1 < len(argv):
            extra_regexes.append(argv[i + 1]); i += 2; continue
        positional.append(a); i += 1

    if not positional:
        print('usage: audit_plan.py <plan.md> [--json] [--no-git] '
              '[--repo <dir>] [--extra-regex <re>]', file=sys.stderr)
        return 2

    plan_path = Path(positional[0])
    if not plan_path.exists():
        print(f"audit_plan: plan not found: {plan_path}", file=sys.stderr)
        return 2

    if repo_root is None:
        repo_root = _detect_repo_root(plan_path)

    result = audit(plan_path, repo_root, use_git=use_git, extra_regexes=extra_regexes)

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(result))
    return 0


def _detect_repo_root(plan_path: Path) -> Path:
    """Walks up from the plan until it finds a repo root (.git); fallback = cwd."""
    base = plan_path.resolve().parent
    for d in (base, *base.parents):
        if (d / ".git").exists():
            return d
    return Path.cwd()


# ── self-test (no network; uses tmp + fixture) ─────────────────────────────

def _self_test() -> None:
    import tempfile

    plan_text = (
        "# Fixture plan\n"
        "\n"
        "## Phase 1\n"
        "- [x] Create `existe_no_disco.py`\n"
        "- [ ] Create `nao_existe_jamais_xyz.py`\n"
        "- [ ] Task with no path at all\n"
        "\n"
        "Deliverable: `outro_arquivo_inexistente_abc.md`\n"
        "Loose reference to `R$100K` and `git status` (not paths).\n"
        "Path quoted: `subdir/profundo.txt`\n"
    )

    # extraction
    items = extract_deliverables(plan_text)
    paths = [it["path"] for it in items if it["path"]]
    assert "existe_no_disco.py" in paths, "should extract the checkbox path"
    assert "nao_existe_jamais_xyz.py" in paths, "should extract the 2nd checkbox path"
    assert "outro_arquivo_inexistente_abc.md" in paths, "should extract the Deliverable path"
    assert "subdir/profundo.txt" in paths, "should extract a backticked path"
    # metrics/commands must NOT become a path
    assert "R$100K" not in paths, "R$100K is not a path"
    assert "git status" not in paths, "a command is not a path"
    # a checkbox with no path becomes an item, but without a path
    assert any(it["kind"] == "checkbox" and it["path"] is None for it in items), \
        "a checkbox without a path must still be an item"

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "existe_no_disco.py").write_text("x", encoding="utf-8")
        sub = root / "subdir"
        sub.mkdir()
        (sub / "profundo.txt").write_text("y", encoding="utf-8")
        plan_file = root / "plano.md"
        plan_file.write_text(plan_text, encoding="utf-8")

        res = audit(plan_file, root, use_git=False)
        by_path = {it["path"]: it for it in res["itens"] if it["path"]}
        assert by_path["existe_no_disco.py"]["status"] == "FEITO", "file present = FEITO"
        assert by_path["subdir/profundo.txt"]["status"] == "FEITO", "relative path present = FEITO"
        assert by_path["nao_existe_jamais_xyz.py"]["status"] == "AUSENTE", \
            "missing + no git = AUSENTE (even with [x])"
        assert by_path["outro_arquivo_inexistente_abc.md"]["status"] == "AUSENTE", \
            "missing deliverable = AUSENTE"
        assert res["git_consultado"] is False
        assert res["summary"]["FEITO"] >= 2

        # rendering markdown must not crash and must contain the header
        md = render_markdown(res)
        assert "Plan audit" in md and "| Status |" in md

        # a plan with no deliverables does not crash
        empty = root / "vazio.md"
        empty.write_text("# nothing here\nplain text\n", encoding="utf-8")
        rv = audit(empty, root, use_git=False)
        assert rv["total"] == 0
        assert "No deliverable" in render_markdown(rv)

    print("self-test OK")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
