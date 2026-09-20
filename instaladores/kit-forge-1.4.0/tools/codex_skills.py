#!/usr/bin/env python3
"""Instala um kit HPP no formato descoberto pelo Codex CLI.

O runtime completo fica em ``.agents/hpp/<kit>`` e cada skill vira uma cópia
namespaced em ``.agents/skills/hpp-<kit>-<skill>``. O gerador não ativa hooks:
hooks do Claude Code não têm equivalência automática no Codex.

Exit: 0 ok/no-op · 1 warn · 2 conflito/bloqueio · 3 erro.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path


_TEXT_SUFFIXES = {".md", ".txt", ".yaml", ".yml", ".json", ".jsonc", ".toml", ".py", ".sh"}
_IGNORED_NAMES = {"__pycache__", ".pytest_cache", "ip-ruleset.yaml", "operator-profile.yaml", "HANDOVER.md"}


def _ignored(path: Path) -> bool:
    return any(part in _IGNORED_NAMES or part.startswith("_superseded") for part in path.parts)


def _kit_name(kit_dir: Path) -> str:
    plugin = kit_dir / ".claude-plugin" / "plugin.json"
    if plugin.is_file():
        try:
            name = json.loads(plugin.read_text(encoding="utf-8")).get("name")
            if isinstance(name, str) and name:
                return name
        except (OSError, json.JSONDecodeError):
            pass
    return re.sub(r"-\d+\.\d+\.\d+$", "", kit_dir.name)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")


def _files(root: Path) -> dict[str, bytes]:
    if not root.is_dir():
        return {}
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and not _ignored(path.relative_to(root)):
            result[path.relative_to(root).as_posix()] = path.read_bytes()
    return result


def _digest(files: dict[str, bytes]) -> str:
    h = hashlib.sha256()
    for rel, data in sorted(files.items()):
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(data)
        h.update(b"\0")
    return h.hexdigest()


def _generated_skill_files(skill_dir: Path, kit_name: str, runtime_rel: str) -> dict[str, bytes]:
    result = _files(skill_dir)
    skill_md = result.get("SKILL.md")
    if skill_md is None:
        raise ValueError(f"SKILL.md ausente em {skill_dir}")

    generated_name = f"hpp-{_slug(kit_name)}-{_slug(skill_dir.name)}"
    for rel, data in list(result.items()):
        suffix = Path(rel).suffix.lower()
        if suffix not in _TEXT_SUFFIXES:
            continue
        text = data.decode("utf-8", errors="strict")
        text = text.replace("${CLAUDE_PLUGIN_ROOT}", runtime_rel)
        if rel == "SKILL.md":
            text, count = re.subn(
                r"(?m)^name:[^\r\n]*(?=\r?$)",
                f"name: {generated_name}",
                text,
                count=1,
            )
            if count != 1:
                raise ValueError(f"frontmatter sem name em {skill_dir / 'SKILL.md'}")
            frontmatter = re.match(r"\A---\r?\n.*?^---\r?\n", text, flags=re.MULTILINE | re.DOTALL)
            if frontmatter is None:
                raise ValueError(f"frontmatter inválido em {skill_dir / 'SKILL.md'}")
            newline = "\r\n" if "\r\n" in frontmatter.group(0) else "\n"
            note = (
                "\n> **Codex CLI:** execute os comandos a partir da raiz do repositório. "
                f"O runtime deste kit está em `{runtime_rel}`. Hooks do Claude Code não são ativados.\n"
            ).replace("\n", newline)
            text = text[: frontmatter.end()] + note + text[frontmatter.end() :]
        result[rel] = text.encode("utf-8")
    return result


def _write_files(root: Path, files: dict[str, bytes]) -> None:
    for rel, data in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def build_plan(kit_dir: Path, target: Path, apply: bool) -> tuple[dict, int]:
    kit_dir = kit_dir.resolve()
    target = target.resolve()
    if not kit_dir.is_dir() or not target.is_dir():
        return {"status": "error", "detail": "kit ou target não é diretório"}, 3

    kit_name = _kit_name(kit_dir)
    runtime_rel = f".agents/hpp/{kit_name}"
    runtime = target / runtime_rel
    skill_root = kit_dir / "skills"
    source_runtime = _files(kit_dir)
    actions: list[dict] = []
    conflicts: list[str] = []

    if runtime.exists():
        if _digest(_files(runtime)) == _digest(source_runtime):
            actions.append({"action": "skip-same", "target": runtime_rel})
        else:
            conflicts.append(runtime_rel)
    else:
        actions.append({"action": "copy-runtime" if apply else "would-copy-runtime", "target": runtime_rel})

    generated: list[tuple[Path, dict[str, bytes], str]] = []
    if skill_root.is_dir():
        for skill_dir in sorted(p for p in skill_root.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()):
            dest_name = f"hpp-{_slug(kit_name)}-{_slug(skill_dir.name)}"
            dest_rel = f".agents/skills/{dest_name}"
            dest = target / dest_rel
            files = _generated_skill_files(skill_dir, kit_name, runtime_rel)
            generated.append((dest, files, dest_rel))
            if dest.exists():
                if _digest(_files(dest)) == _digest(files):
                    actions.append({"action": "skip-same", "target": dest_rel})
                else:
                    conflicts.append(dest_rel)
            else:
                actions.append({"action": "copy-skill" if apply else "would-copy-skill", "target": dest_rel})

    if conflicts:
        return {
            "status": "block",
            "kit": kit_name,
            "runtime": runtime_rel,
            "skills": len(generated),
            "actions": actions,
            "conflicts": conflicts,
        }, 2

    if apply:
        if not runtime.exists():
            _write_files(runtime, source_runtime)
        for dest, files, _ in generated:
            if not dest.exists():
                _write_files(dest, files)

    return {
        "status": "ok",
        "mode": "apply" if apply else "plan",
        "kit": kit_name,
        "runtime": runtime_rel,
        "skills": len(generated),
        "actions": actions,
        "conflicts": [],
    }, 0


def _self_test() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="codex_skills_selftest_"))
    try:
        kit = tmp / "demo-kit"
        target = tmp / "repo"
        (kit / ".claude-plugin").mkdir(parents=True)
        (kit / ".claude-plugin" / "plugin.json").write_text('{"name":"demo-kit"}\n', encoding="utf-8")
        skill = kit / "skills" / "demo"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nname: demo\ndescription: fixture\n---\n\n"
            "Rode `python ${CLAUDE_PLUGIN_ROOT}/scripts/demo.py --self-test`.\n",
            encoding="utf-8",
        )
        (kit / "scripts").mkdir()
        (kit / "scripts" / "demo.py").write_text("print('ok')\n", encoding="utf-8")
        target.mkdir()

        plan, rc_plan = build_plan(kit, target, apply=False)
        assert rc_plan == 0 and plan["skills"] == 1
        assert not (target / ".agents").exists(), "modo plano escreveu no target"

        report, rc = build_plan(kit, target, apply=True)
        assert rc == 0 and report["status"] == "ok"
        generated = target / ".agents" / "skills" / "hpp-demo-kit-demo" / "SKILL.md"
        text = generated.read_text(encoding="utf-8")
        assert "name: hpp-demo-kit-demo" in text
        assert "${CLAUDE_PLUGIN_ROOT}" not in text
        assert ".agents/hpp/demo-kit/scripts/demo.py" in text
        assert (target / ".agents" / "hpp" / "demo-kit" / "scripts" / "demo.py").is_file()

        rerun, rc_rerun = build_plan(kit, target, apply=True)
        assert rc_rerun == 0 and all(a["action"] == "skip-same" for a in rerun["actions"])
        print("self-test OK — plano não escreve; runtime e skill namespaced copiados; rerun idempotente")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--kit")
    parser.add_argument("--target")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    if not args.kit or not args.target:
        parser.error("--kit e --target são obrigatórios")
    report, rc = build_plan(Path(args.kit), Path(args.target), args.apply)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
