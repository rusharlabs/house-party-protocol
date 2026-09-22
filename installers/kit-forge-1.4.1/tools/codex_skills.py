#!/usr/bin/env python3
"""Installs an HPP kit in the format discovered by the Codex CLI.

The full runtime lives in ``.agents/hpp/<kit>`` and each skill becomes a namespaced
copy at ``.agents/skills/hpp-<kit>-<skill>``. The generator does not activate hooks:
Claude Code hooks have no automatic equivalent in Codex.

Symlinks and junctions inside the kit are NOT followed: they go into ``links_ignored`` in the
report (exit 1). A kit name that is not a plain path segment, and two skills that collapse
into the same slug, are an error (exit 3), with nothing written.

Exit: 0 ok/no-op - 1 warn (ignored links) - 2 conflict/block - 3 error.
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
# Why: the kit name becomes a path segment under the target (`.agents/hpp/<kit>`); a slash, `..`,
# an empty name or one starting with a dot would take it out of the target or hide it.
_KIT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _ignored(path: Path) -> bool:
    return any(part in _IGNORED_NAMES or part.startswith("_superseded") for part in path.parts)


def _valid_kit_name(name: str) -> bool:
    return bool(_KIT_NAME.fullmatch(name)) and ".." not in name


def _kit_name(kit_dir: Path) -> str:
    """Kit name (plugin.json > directory name without version suffix), validated as a
    single path segment. Raises ValueError when the name would escape the target."""
    plugin = kit_dir / ".claude-plugin" / "plugin.json"
    name = None
    if plugin.is_file():
        try:
            candidate = json.loads(plugin.read_text(encoding="utf-8")).get("name")
            if isinstance(candidate, str) and candidate:
                name = candidate
        except (OSError, json.JSONDecodeError):
            pass
    if name is None:
        name = re.sub(r"-\d+\.\d+\.\d+$", "", kit_dir.name)
    if not _valid_kit_name(name):
        raise ValueError(f"invalid kit name for a path segment: {name!r} (use letters, digits, '.', '_' or '-')")
    return name


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")


def _is_link(path: Path) -> bool:
    # Why: is_file() follows symlink and junction; what gets copied has to be what is INSIDE the
    # kit's tree, never an `.env` or an outside directory reached through a link.
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction and is_junction())


def _walk(root: Path) -> tuple[list[Path], list[str]]:
    """Regular files under root WITHOUT following links. Returns (files, ignored links)."""
    files: list[Path] = []
    links: list[str] = []
    stack = [root]
    while stack:
        cur = stack.pop()
        for child in sorted(cur.iterdir()):
            if _is_link(child):
                links.append(child.relative_to(root).as_posix())
            elif child.is_dir():
                stack.append(child)
            elif child.is_file():
                files.append(child)
    return sorted(files), sorted(links)


def _files(root: Path) -> dict[str, bytes]:
    if not root.is_dir():
        return {}
    result = {}
    for path in _walk(root)[0]:
        if not _ignored(path.relative_to(root)):
            result[path.relative_to(root).as_posix()] = path.read_bytes()
    return result


def _links_ignored(root: Path) -> list[str]:
    return _walk(root)[1] if root.is_dir() else []


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
        raise ValueError(f"SKILL.md missing in {skill_dir}")

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
                raise ValueError(f"frontmatter without name in {skill_dir / 'SKILL.md'}")
            frontmatter = re.match(r"\A---\r?\n.*?^---\r?\n", text, flags=re.MULTILINE | re.DOTALL)
            if frontmatter is None:
                raise ValueError(f"invalid frontmatter in {skill_dir / 'SKILL.md'}")
            newline = "\r\n" if "\r\n" in frontmatter.group(0) else "\n"
            note = (
                "\n> **Codex CLI:** run the commands from the repository root. "
                f"This kit's runtime lives in `{runtime_rel}`. Claude Code hooks are not activated.\n"
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
        return {"status": "error", "detail": "kit or target is not a directory"}, 3

    try:
        kit_name = _kit_name(kit_dir)
    except ValueError as e:
        return {"status": "error", "detail": str(e)}, 3
    runtime_rel = f".agents/hpp/{kit_name}"
    runtime = target / runtime_rel
    skill_root = kit_dir / "skills"
    source_runtime = _files(kit_dir)
    links_ignored = _links_ignored(kit_dir)
    actions: list[dict] = []
    conflicts: list[str] = []
    slug_owner: dict[str, str] = {}

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
            if dest_name in slug_owner:
                # Why: two skill names that collapse into the same slug would make the second one
                # vanish in silence, with the plan saying both were copied.
                return {
                    "status": "error",
                    "detail": f"slug collision: skills {slug_owner[dest_name]!r} and {skill_dir.name!r} "
                              f"produce the same destination {dest_name}",
                }, 3
            slug_owner[dest_name] = skill_dir.name
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
            "links_ignored": links_ignored,
        }, 2

    if apply:
        if not runtime.exists():
            _write_files(runtime, source_runtime)
        for dest, files, _ in generated:
            if not dest.exists():
                _write_files(dest, files)

    return {
        "status": "warn" if links_ignored else "ok",
        "mode": "apply" if apply else "plan",
        "kit": kit_name,
        "runtime": runtime_rel,
        "skills": len(generated),
        "actions": actions,
        "conflicts": [],
        "links_ignored": links_ignored,
    }, (1 if links_ignored else 0)


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
            "Run `python ${CLAUDE_PLUGIN_ROOT}/scripts/demo.py --self-test`.\n",
            encoding="utf-8",
        )
        (kit / "scripts").mkdir()
        (kit / "scripts" / "demo.py").write_text("print('ok')\n", encoding="utf-8")
        target.mkdir()

        plan, rc_plan = build_plan(kit, target, apply=False)
        assert rc_plan == 0 and plan["skills"] == 1
        assert not (target / ".agents").exists(), "plan mode wrote to the target"

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
        assert rerun["links_ignored"] == []

        # name that would escape the target -> error 3, nothing written
        escape = tmp / "escape-kit"
        (escape / ".claude-plugin").mkdir(parents=True)
        (escape / ".claude-plugin" / "plugin.json").write_text('{"name":"../../outside"}\n', encoding="utf-8")
        rep_escape, rc_escape = build_plan(escape, target, apply=True)
        assert rc_escape == 3 and rep_escape["status"] == "error", rep_escape
        assert not (tmp / "outside").exists()

        # two skills that collapse into the same slug -> explicit error 3
        collision = tmp / "collision-kit"
        (collision / ".claude-plugin").mkdir(parents=True)
        (collision / ".claude-plugin" / "plugin.json").write_text('{"name":"collision"}\n', encoding="utf-8")
        for name in ("a_b", "a-b"):
            (collision / "skills" / name).mkdir(parents=True)
            (collision / "skills" / name / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
        rep_col, rc_col = build_plan(collision, target, apply=True)
        assert rc_col == 3 and "a_b" in rep_col["detail"] and "a-b" in rep_col["detail"], rep_col

        print("self-test OK — the plan writes nothing; runtime and namespaced skill copied; rerun idempotent; "
              "a traversing name and a slug collision are error 3")
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
        parser.error("--kit and --target are required")
    report, rc = build_plan(Path(args.kit), Path(args.target), args.apply)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
