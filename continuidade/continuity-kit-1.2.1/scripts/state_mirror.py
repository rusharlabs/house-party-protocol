#!/usr/bin/env python3
"""
state_mirror — espelha arquivos gitignored críticos p/ uma pasta TRACKED (durabilidade).

Generaliza um padrão de backup real (4 blocos hardcoded específicos de um repo — ex.:
notas/sessions/mission-control/handoffs). Este script lê `paths.mirror_globs`
de um profile YAML — cada entrada = {glob, dest_subdir, keep_latest} — e funciona em
qualquer projeto. DURABILIDADE (não perder o arquivo se o .gitignore apagar o original)
é um problema DIFERENTE de RETOMADA (o handoff-v1 do continuity-kit) — os dois se
complementam, não se substituem.

Uso:
    python state_mirror.py --profile operator-profile.yaml
    python state_mirror.py --profile operator-profile.yaml --dry-run
    python state_mirror.py --self-test

Config (paths.mirror_dir + paths.mirror_globs no profile):
    paths:
      mirror_dir: docs/_state-mirror
      mirror_globs:
        - { glob: ".claude/notes/*.md", dest_subdir: "notes" }
        - { glob: ".claude/sessions/SESSION-*.md", dest_subdir: "sessions", keep_latest: 10 }

Exit: 0 ok (mesmo com 0 globs configurados — vira no-op documentado) · 2 uso inválido.
stdlib + PyYAML (degrada p/ {} sem PyYAML — profile fica vazio, no-op).

v1.0.0 — 2026-07-10 (continuity-kit · Tier 2 · mirror generico de durabilidade)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

_PROJECT_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())


def load_profile(path: str | None) -> dict:
    if not path:
        return {}
    p = Path(path)
    if not p.is_absolute():
        p = _PROJECT_ROOT / p
    if not p.exists() or yaml is None:
        return {}
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _get(d: dict, dotted: str, default=None):
    cur = d
    for k in dotted.split("."):
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur


def mirror(profile: dict, root: Path, dry_run: bool = False) -> dict:
    mirror_dir_rel = _get(profile, "paths.mirror_dir", "docs/_state-mirror")
    mirror_dir = root / mirror_dir_rel
    globs = _get(profile, "paths.mirror_globs", []) or []

    copied = []
    for entry in globs:
        pattern = entry.get("glob")
        dest_subdir = entry.get("dest_subdir", "")
        keep_latest = entry.get("keep_latest")
        if not pattern:
            continue
        matches = sorted(root.glob(pattern), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
        matches = [m for m in matches if m.is_file()]
        if keep_latest:
            matches = matches[:keep_latest]
        for m in matches:
            dest = mirror_dir / dest_subdir / m.name
            copied.append(str(dest.relative_to(mirror_dir)))
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(m, dest)

    manifest = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z") or time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": str(root),
        "mirror_dir": str(mirror_dir),
        "files_mirrored": len(copied),
        "note": "Critical state backup for git-ignored files. Mirror IS tracked in git.",
    }
    if not dry_run:
        mirror_dir.mkdir(parents=True, exist_ok=True)
        (mirror_dir / "_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest["copied"] = copied
    return manifest


_STATE_INDEX_THRESHOLD = 65536  # 64KB — A.1 item 3: proativo, não reativo (o padrão de referência só reagiu aos 107KB)


def _section(text: str, title: str, limit: int = 1800) -> str:
    idx = text.find(f"## {title}")
    if idx == -1:
        return ""
    rest = text[idx:]
    nxt = rest.find("\n## ", 3)
    return (rest if nxt == -1 else rest[:nxt]).strip()[:limit]


def generate_state_index(state_path: Path, threshold_bytes: int = _STATE_INDEX_THRESHOLD) -> dict | None:
    """Se o STATE.md passar do teto, gera <state>.state-index.json com as seções vivas
    (Agora, PENDÊNCIAS ABERTAS) — proativo: gera ANTES de virar problema de boot lento."""
    if not state_path.exists():
        return None
    size = state_path.stat().st_size
    if size <= threshold_bytes:
        return None
    text = state_path.read_text(encoding="utf-8", errors="replace")
    index = {
        "source": str(state_path),
        "size_bytes": size,
        "threshold_bytes": threshold_bytes,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "agora": _section(text, "Agora"),
        "pendencias": _section(text, "PENDÊNCIAS ABERTAS"),
    }
    index_path = state_path.with_suffix(state_path.suffix + ".state-index.json")
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return index


def _self_test() -> int:
    import shutil as _sh
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="state_mirror_selftest_"))
    try:
        (tmp / ".claude" / "notes").mkdir(parents=True)
        (tmp / ".claude" / "notes" / "MEMORY.md").write_text("memoria", encoding="utf-8")
        (tmp / ".claude" / "sessions").mkdir(parents=True)
        for i in range(5):
            (tmp / ".claude" / "sessions" / f"SESSION-{i}.md").write_text(f"s{i}", encoding="utf-8")
            time.sleep(0.01)

        profile = {
            "paths": {
                "mirror_dir": "docs/_state-mirror",
                "mirror_globs": [
                    {"glob": ".claude/notes/*.md", "dest_subdir": "notes"},
                    {"glob": ".claude/sessions/SESSION-*.md", "dest_subdir": "sessions", "keep_latest": 3},
                ],
            }
        }

        report_dry = mirror(profile, tmp, dry_run=True)
        assert report_dry["files_mirrored"] == 4, f"dry-run deveria contar 1 notes + 3 sessions: {report_dry}"
        assert not (tmp / "docs" / "_state-mirror").exists(), "dry-run não deveria escrever nada"

        report = mirror(profile, tmp, dry_run=False)
        assert report["files_mirrored"] == 4
        mirror_dir = tmp / "docs" / "_state-mirror"
        assert (mirror_dir / "notes" / "MEMORY.md").exists()
        assert len(list((mirror_dir / "sessions").glob("SESSION-*.md"))) == 3, "keep_latest=3 deveria limitar"
        assert (mirror_dir / "_manifest.json").exists()

        empty_profile: dict = {}
        report_empty = mirror(empty_profile, tmp, dry_run=True)
        assert report_empty["files_mirrored"] == 0, "sem mirror_globs configurado = no-op, não erro"

        small_state = tmp / "00-STATE-small.md"
        small_state.write_text("## Agora\nfoco\n", encoding="utf-8")
        assert generate_state_index(small_state) is None, "abaixo do teto não deveria gerar índice"

        big_state = tmp / "00-STATE-big.md"
        big_state.write_text("## Agora\nfoco atual\n\n## PENDÊNCIAS ABERTAS\n- [ ] x\n\n" + ("padding " * 10000), encoding="utf-8")
        idx = generate_state_index(big_state, threshold_bytes=1000)
        assert idx is not None and idx["agora"] and idx["pendencias"], f"acima do teto deveria gerar índice: {idx}"
        assert big_state.with_suffix(".md.state-index.json").exists()

        print("self-test OK — dry-run conta certo sem escrever, keep_latest limita, manifest gerado, "
              "profile vazio = no-op, state-index só gera acima do teto (proativo)")
        return 0
    finally:
        _sh.rmtree(tmp, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="state_mirror.py")
    p.add_argument("--profile", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--state-file", default=None, help="gera state-index.json se o arquivo passar de 64KB (A.1 item 3)")
    p.add_argument("--self-test", action="store_true")
    return p


def main(argv) -> int:
    args = build_parser().parse_args(argv)
    if args.self_test:
        return _self_test()
    profile = load_profile(args.profile)
    report = mirror(profile, _PROJECT_ROOT, args.dry_run)
    if args.state_file and not args.dry_run:
        idx = generate_state_index(_PROJECT_ROOT / args.state_file)
        report["state_index_generated"] = idx is not None
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
