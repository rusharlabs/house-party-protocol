#!/usr/bin/env python3
"""
drift_check (Operator Kit) -- compares INTENTION (doc) vs REALITY (probes).

Materializes LC-1 (audit the source LIVE) and feedback_plans_lag_reality at
runtime level: a doc SAYS something is live / implemented / by-design -- this
tool PROBES reality and labels each claim. Every probe compares what the
doc EXPECTS against what actually happens:

    bug          = the doc expects it working, but the probe failed (real drift)
    by-design    = the doc and reality agree (ok -- intentional)
    aspirational = the doc describes something NOT expected to work yet (expect=False)
                   and reality confirms it doesn't work (no drift; it's a roadmap)

Each probe: {name, kind, target, expect}
    tipo cmd   -> runs the command (subprocess); real = (exit code 0)
    tipo http  -> GET via urllib.request; real = (status 200)   [NEVER curl/wget]
    tipo glob  -> file/pattern exists on disk; real = (found something)
    expect     -> bool: does the doc claim this should be true? (default True)

Probes come from a YAML (--probes file.yaml) or inline (--probe nome=...).

Usage:
    python drift_check.py doc.md --probes sondas.yaml
    python drift_check.py doc.md --probe "health=http:http://127.0.0.1:8080/health"
    python drift_check.py doc.md --probe "engine=cmd:python -c pass" --json
    python drift_check.py doc.md --probe "cfg=glob:core/paths.py:expect=true"
    python drift_check.py --self-test

Inline format:  name=KIND:TARGET[:expect=true|false]
    health=http:http://127.0.0.1:8080/health
    suite=cmd:python -m pytest -q:expect=true
    legado=glob:old/removido.py:expect=false

YAML (--probes):
    sondas:
      - { name: health, kind: http, target: "http://127.0.0.1:8080/health", expect: true }
      - { name: paths,  kind: glob, target: "core/paths.py",                expect: true }

Exit: 0 = ran (regardless of drift) -- 2 = invalid usage.
stdlib + PyYAML (only for --probes). Cross-platform. HTTP via urllib (never curl/wget).

v1.0.0 -- 2026-06-19 (Operator Kit -- Tier 1 -- materializes LC-1 + plans_lag_reality)
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# shared kit loader (.../operator-kit/_lib/profile_loader.py)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from _lib.profile_loader import load_profile, get  # noqa: F401 (available for extension)
except Exception:  # noqa: BLE001 -- safe degrade
    load_profile = None  # type: ignore[assignment]
    get = None  # type: ignore[assignment]

try:
    import yaml  # PyYAML -- only needed for --sondas YAML
except Exception:  # noqa: BLE001
    yaml = None  # type: ignore[assignment]

_TYPES = ("cmd", "http", "glob")


# ── probe execution ─────────────────────────────────────────────────────────

def probe_cmd(target: str, timeout: int = 60) -> dict:
    """Runs a shell command. real=True if exit 0. Never crashes."""
    try:
        r = subprocess.run(target, shell=True, capture_output=True, text=True, timeout=timeout)
        tail = ((r.stdout or "") + (r.stderr or "")).strip()[-200:]
        return {"real": r.returncode == 0, "detail": f"exit {r.returncode}", "tail": tail}
    except subprocess.TimeoutExpired:
        return {"real": False, "detail": f"timeout {timeout}s", "tail": ""}
    except Exception as e:  # noqa: BLE001
        return {"real": False, "detail": f"error: {e}", "tail": ""}


def probe_http(target: str, timeout: int = 10) -> dict:
    """GET via urllib. real=True if status 200. NEVER uses curl/wget. Never crashes."""
    req = urllib.request.Request(target, method="GET", headers={"User-Agent": "operator-kit-drift_check/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (URL controlled by the operator)
            status = getattr(resp, "status", None) or resp.getcode()
            return {"real": status == 200, "detail": f"HTTP {status}", "tail": ""}
    except urllib.error.HTTPError as e:
        return {"real": e.code == 200, "detail": f"HTTP {e.code}", "tail": ""}
    except Exception as e:  # noqa: BLE001 -- connection refused, DNS, timeout...
        return {"real": False, "detail": f"no answer: {type(e).__name__}", "tail": ""}


def probe_glob(target: str, repo_root: Path | None = None) -> dict:
    """File/pattern exists? real=True if it finds something. Never crashes."""
    root = repo_root or Path.cwd()
    try:
        p = Path(target)
        # direct path (abs or relative to the repo)
        if p.is_absolute() and p.exists():
            return {"real": True, "detail": "exists (abs)", "tail": str(p)}
        if (root / p).exists():
            return {"real": True, "detail": "exists", "tail": str(root / p)}
        # glob (wildcards)
        if any(ch in target for ch in "*?[]"):
            hits = list(root.glob(target))
            if hits:
                return {"real": True, "detail": f"glob {len(hits)} match", "tail": str(hits[0])}
        return {"real": False, "detail": "does not exist", "tail": ""}
    except (OSError, ValueError) as e:
        return {"real": False, "detail": f"error: {e}", "tail": ""}


def run_probe(probe: dict, repo_root: Path | None = None) -> dict:
    """Runs a probe and labels it bug/by-design/aspirational."""
    name = str(probe.get("name", "sem-nome"))
    kind = str(probe.get("kind", "")).lower()
    target = str(probe.get("target", ""))
    expect = bool(probe.get("expect", True))

    if kind == "cmd":
        res = probe_cmd(target)
    elif kind == "http":
        res = probe_http(target)
    elif kind == "glob":
        res = probe_glob(target, repo_root)
    else:
        res = {"real": False, "detail": f"invalid type: {kind!r}", "tail": ""}

    label = label_for(expect, res["real"])
    return {
        "name": name, "kind": kind, "target": target, "expect": expect,
        "real": res["real"], "label": label,
        "detail": res["detail"], "tail": res.get("tail", ""),
    }


def label_for(expect: bool, real: bool) -> str:
    """
    expect (does the doc claim it works?) x real (did the probe confirm it?):
        expect=True,  real=True   -> by-design   (doc matches reality)
        expect=True,  real=False  -> bug         (doc lies: promised and doesn't have it)
        expect=False, real=False  -> aspirational (doc describes a roadmap; ok not to have it)
        expect=False, real=True   -> by-design   (exists and wasn't required; no drift)
    """
    if expect and real:
        return "by-design"
    if expect and not real:
        return "bug"
    if not expect and not real:
        return "aspirational"
    return "by-design"  # not expect and real


# ── probe parsing ────────────────────────────────────────────────────────────

def parse_inline(spec: str) -> dict:
    """
    'name=KIND:TARGET[:expect=true|false]' -> probe dict.
    Raises ValueError if malformed (invalid usage -> exit 2 in main).
    """
    if "=" not in spec:
        raise ValueError(f"inline probe without '=': {spec!r}")
    name, rest = spec.split("=", 1)
    if ":" not in rest:
        raise ValueError(f"inline probe without TYPE:TARGET: {spec!r}")
    kind, target = rest.split(":", 1)
    kind = kind.strip().lower()
    expect = True
    # optional suffix ':expect=true|false' (only if the target isn't http://)
    low = target.lower()
    marker = ":expect="
    idx = low.rfind(marker)
    if idx != -1:
        val = target[idx + len(marker):].strip().lower()
        if val in ("true", "false", "1", "0", "yes", "no"):
            expect = val in ("true", "1", "yes")
            target = target[:idx]
    if kind not in _TYPES:
        raise ValueError(f"invalid type {kind!r} in {spec!r} (use {_TYPES})")
    return {"name": name.strip(), "kind": kind, "target": target.strip(), "expect": expect}


def load_sondas_yaml(path: Path) -> list[dict]:
    """Reads probes from a YAML. [] if PyYAML is missing or the file is unreadable."""
    if yaml is None:
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    if isinstance(data, dict):
        data = data.get("probes", [])
    if not isinstance(data, list):
        return []
    out = []
    for s in data:
        if isinstance(s, dict) and s.get("kind") and s.get("target"):
            out.append({
                "name": s.get("name", s.get("target")),
                "kind": str(s["kind"]).lower(),
                "target": str(s["target"]),
                "expect": bool(s.get("expect", True)),
            })
    return out


# ── orchestration ────────────────────────────────────────────────────────────

def drift_check(doc_path: Path | None, probes: list[dict],
                repo_root: Path | None = None) -> dict:
    """Runs all probes and aggregates the drift label."""
    rows = [run_probe(s, repo_root) for s in probes]
    summary = {"bug": 0, "by-design": 0, "aspirational": 0}
    for r in rows:
        summary[r["label"]] = summary.get(r["label"], 0) + 1
    return {
        "doc": str(doc_path) if doc_path else None,
        "total": len(rows),
        "drift": summary["bug"] > 0,
        "summary": summary,
        "probes": rows,
    }


def render_markdown(result: dict) -> str:
    out: list[str] = []
    title = Path(result["doc"]).name if result.get("doc") else "(sem doc)"
    out.append(f"# Drift check — {title}")
    out.append("")
    r = result["summary"]
    verdict = "DRIFT (bug present)" if result["drift"] else "no drift"
    out.append(f"Probes: **{result['total']}** · {verdict} · "
               f"bug {r.get('bug', 0)} · by-design {r.get('by-design', 0)} · "
               f"aspirational {r.get('aspirational', 0)}")
    out.append("")
    if not result["probes"]:
        out.append("_No probe given (use --probes or --probe)._")
        return "\n".join(out)
    out.append("| Label | Probe | Type | Expects | Real | Detail |")
    out.append("|-------|-------|------|:-------:|:----:|--------|")
    for s in result["probes"]:
        det = (s.get("detail") or "").replace("|", "\\|")
        if len(det) > 40:
            det = det[:37] + "..."
        out.append(
            f"| {s['label']} | {s['name']} | {s['kind']} | "
            f"{'yes' if s['expect'] else 'no'} | {'yes' if s['real'] else 'no'} | {det} |"
        )
    return "\n".join(out)


def main(argv) -> int:
    if argv and argv[0] in ("--self-test", "-t"):
        _self_test()
        return 0

    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]

    probes: list[dict] = []
    sondas_yaml: Path | None = None
    repo_root: Path | None = None
    doc_path: Path | None = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--probes" and i + 1 < len(argv):
            sondas_yaml = Path(argv[i + 1]); i += 2; continue
        if a == "--probe" and i + 1 < len(argv):
            try:
                probes.append(parse_inline(argv[i + 1]))
            except ValueError as e:
                print(f"drift_check: {e}", file=sys.stderr)
                return 2
            i += 2; continue
        if a == "--repo" and i + 1 < len(argv):
            repo_root = Path(argv[i + 1]); i += 2; continue
        if not a.startswith("--") and doc_path is None:
            doc_path = Path(a); i += 1; continue
        i += 1

    if sondas_yaml is not None:
        if not sondas_yaml.exists():
            print(f"drift_check: --sondas not found: {sondas_yaml}", file=sys.stderr)
            return 2
        loaded = load_sondas_yaml(sondas_yaml)
        if not loaded and yaml is None:
            print("drift_check: PyYAML missing — --probes YAML unavailable", file=sys.stderr)
            return 2
        probes.extend(loaded)

    if not probes:
        print('usage: drift_check.py [doc.md] --probes <yaml> | --probe "name=TYPE:TARGET[:expect=bool]" [...]',
              file=sys.stderr)
        return 2

    if repo_root is None and doc_path is not None and doc_path.exists():
        repo_root = _detect_repo_root(doc_path)

    result = drift_check(doc_path, probes, repo_root)

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(result))
    return 0


def _detect_repo_root(p: Path) -> Path:
    base = p.resolve().parent
    for d in (base, *base.parents):
        if (d / ".git").exists():
            return d
    return Path.cwd()


# ── self-test (no network; only local cmd + glob) ───────────────────────────

def _self_test() -> None:
    import tempfile

    # labeling (expect x real matrix)
    assert label_for(True, True) == "by-design"
    assert label_for(True, False) == "bug"
    assert label_for(False, False) == "aspirational"
    assert label_for(False, True) == "by-design"

    # inline parse
    s = parse_inline("health=http:http://127.0.0.1:8080/health")
    assert s["kind"] == "http" and s["target"] == "http://127.0.0.1:8080/health" and s["expect"] is True
    s2 = parse_inline("legado=glob:old/x.py:expect=false")
    assert s2["kind"] == "glob" and s2["target"] == "old/x.py" and s2["expect"] is False
    s3 = parse_inline("suite=cmd:python -m pytest -q:expect=true")
    assert s3["kind"] == "cmd" and s3["target"] == "python -m pytest -q" and s3["expect"] is True
    try:
        parse_inline("malformado-sem-igual")
        raise AssertionError("should raise ValueError")
    except ValueError:
        pass

    # local cmd probes (no network)
    ok = run_probe({"name": "exit0", "kind": "cmd", "target": f'"{sys.executable}" -c "import sys; sys.exit(0)"', "expect": True})
    assert ok["real"] is True and ok["label"] == "by-design", "cmd exit0 expected = by-design"

    bug = run_probe({"name": "exit1", "kind": "cmd", "target": f'"{sys.executable}" -c "import sys; sys.exit(1)"', "expect": True})
    assert bug["real"] is False and bug["label"] == "bug", "cmd exit1 expected-true = bug"

    asp = run_probe({"name": "exit1-asp", "kind": "cmd", "target": f'"{sys.executable}" -c "import sys; sys.exit(1)"', "expect": False})
    assert asp["real"] is False and asp["label"] == "aspirational", "unexpected-by-design failure = aspirational"

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "present.txt").write_text("x", encoding="utf-8")

        g_ok = run_probe({"name": "g1", "kind": "glob", "target": "present.txt", "expect": True}, repo_root=root)
        assert g_ok["real"] is True and g_ok["label"] == "by-design", "existing glob = by-design"

        g_bug = run_probe({"name": "g2", "kind": "glob", "target": "absent.txt", "expect": True}, repo_root=root)
        assert g_bug["real"] is False and g_bug["label"] == "bug", "missing glob that was expected = bug"

        g_asp = run_probe({"name": "g3", "kind": "glob", "target": "removed.py", "expect": False}, repo_root=root)
        assert g_asp["label"] == "aspirational", "missing glob that was not expected = aspirational"

        # invalid type doesn't crash, becomes bug if it was expected
        inv = run_probe({"name": "bad", "kind": "xyz", "target": "z", "expect": True})
        assert inv["real"] is False and inv["label"] == "bug", "invalid type that was expected = bug"

        # aggregation + render
        probes = [
            {"name": "g1", "kind": "glob", "target": "present.txt", "expect": True},
            {"name": "g2", "kind": "glob", "target": "absent.txt", "expect": True},
        ]
        res = drift_check(None, probes, repo_root=root)
        assert res["total"] == 2
        assert res["summary"]["by-design"] == 1 and res["summary"]["bug"] == 1
        assert res["drift"] is True
        md = render_markdown(res)
        assert "Drift check" in md and "| Label |" in md

        # no probes: render warns, doesn't crash
        empty = drift_check(None, [], repo_root=root)
        assert empty["total"] == 0 and empty["drift"] is False
        assert "No probe" in render_markdown(empty)

    print("self-test OK")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
