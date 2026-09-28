#!/usr/bin/env python3
"""codex_marketplace.py -- renders the Codex CLI plugin channel of the product, from data.

Codex CLI installs plugins from a marketplace it reads at `<root>/.agents/plugins/marketplace.json`
and, per plugin, from a manifest at `<plugin>/.codex-plugin/plugin.json`. Measured with the installed
CLI (0.153.4) in an isolated CODEX_HOME: that marketplace file is preferred over the legacy-compatible
`.claude-plugin/marketplace.json` when both exist, and a root `marketplace.json` alone is refused.
The forms follow the Codex plugin documentation ("Package your plugin"): the marketplace carries
`name`, `interface.displayName` and `plugins[]` entries with `name`, a `source` object
(`{"source": "local", "path": "./<dir>"}`), a `policy` (`installation`, `authentication`) and a
`category`; the plugin manifest carries `name`, `version`, `description`, `author`, `homepage`,
`repository`, `license`, `keywords`, `skills` (the skills directory) and an `interface` block.

What is rendered, and from where:

    <staging>/<kit>/.codex-plugin/plugin.json    from the kit's .claude-plugin/plugin.json (name,
                                                 version, author, keywords), the skills it carries
                                                 (the descriptions) and the marketplace (site,
                                                 repository)
    <product>/.agents/plugins/marketplace.json   from staging/marketplace.json + the product manifest

Only a kit that qualifies gets a manifest and an entry: supported on Codex (`hosts.codex` of its
module in the product manifest is not `unsupported`) and carrying skills (`skills` among its
components). The channel registers skills and nothing else, and every rendered text says so:

* `hooks` is always the EMPTY inline hooks object `{"hooks": {}}`. Absent, it would not mean "no
  hooks": with no `hooks` key the Codex plugin loader falls back to `hooks/hooks.json` in the plugin
  root (its documentation: "By default, Codex looks for hooks/hooks.json inside the plugin root. If a
  manifest defines hooks, Codex uses those manifest entries instead"), and an empty LIST is dropped
  as if absent. Measured with the installed CLI (0.153.4, `hooks/list` of its app-server): without
  the key the four modules that carry `hooks/hooks.json` registered 16 hooks; with the empty object,
  none. On Codex the hooks stay explicit commands (`kit_doctor.py install --host codex`).
* `description` names the skills the plugin registers and what of the module it does not register
  (commands, agents, hooks, rules), from the files the kit carries -- never the Claude description,
  which announces what only the Claude plugin installs.

The rendered files are committed beside their Claude twins; `--check` refuses drift and the emission
runs `--write` first, so a version bump can never leave the two channels disagreeing.

Usage:
    python codex_marketplace.py --write [--staging DIR] [--manifest FILE]
    python codex_marketplace.py --check [--staging DIR] [--manifest FILE] [--product DIR]
    python codex_marketplace.py --emit PRODUCT [--staging DIR] [--manifest FILE]
    python codex_marketplace.py --self-test

Exit: 0 ok - 1 drift (--check) - 2 usage or unreadable input. Stdlib only; deterministic bytes (LF).
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
DEFAULT_STAGING = HERE.parents[2]
DEFAULT_MANIFEST = HERE.parents[3] / "scripts" / "kits" / "product-root" / "hpp.manifest.json"
CODEX_MARKETPLACE_REL = Path(".agents") / "plugins" / "marketplace.json"
CODEX_PLUGIN_REL = Path(".codex-plugin") / "plugin.json"
CLAUDE_PLUGIN_REL = Path(".claude-plugin") / "plugin.json"
SKILLS_DIR = "./skills/"
CATEGORY = "Developer Tools"
POLICY = {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}
# The empty inline hooks object: the one `hooks` value that makes Codex register no plugin hook.
NO_HOOKS: dict = {"hooks": {}}
# What a kit may carry that the Codex plugin does not register: (label, path inside the kit).
NOT_REGISTERED = (("commands", "commands"), ("agents", "agents"), ("hooks", "hooks/hooks.json"), ("rules", "rules"))
_SHORT = 200


def _load(path: Path) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"codex_marketplace: not found: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"codex_marketplace: not JSON: {path}: {exc.msg}")
    if not isinstance(document, dict):
        raise SystemExit(f"codex_marketplace: root must be an object: {path}")
    return document


def _dump(document: dict) -> bytes:
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def eligible(manifest: dict) -> dict[str, dict]:
    """The modules that join the Codex plugin channel: supported on Codex and carrying skills."""
    return {module["id"]: module for module in manifest["modules"]
            if module["hosts"].get("codex") != "unsupported" and "skills" in module.get("components", [])}


def display_name(marketplace: dict) -> str:
    return marketplace.get("displayName") or marketplace["name"].replace("-", " ").title()


def first_sentence(text: str) -> str:
    """The short description Codex shows in its browser: the first sentence, capped by length."""
    sentence = text.split(". ", 1)[0].strip()
    if not sentence.endswith("."):
        sentence += "."
    if len(sentence) > _SHORT:
        sentence = sentence[:_SHORT].rsplit(" ", 1)[0].rstrip(",;:") + "..."
    return sentence


def skill_names(kit_dir: Path) -> list[str]:
    """The skills Codex registers from `skills/`: each `SKILL.md`'s frontmatter `name`, else its folder."""
    names = []
    for skill in (kit_dir / "skills").glob("*/SKILL.md"):
        text = skill.read_text(encoding="utf-8")
        front = text.split("---", 2)[1] if text.startswith("---") else ""
        found = [line.split(":", 1)[1].strip().strip("\"'") for line in front.splitlines() if line.startswith("name:")]
        names.append(found[0] if found and found[0] else skill.parent.name)
    return sorted(names)


def _series(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def codex_description(display: str, kit_dir: Path) -> str:
    """What the Codex plugin installs, from the files the kit carries: its skills, named, and what of
    the module it does not register."""
    skills = skill_names(kit_dir)
    text = (f"{display} on Codex: {len(skills)} skill{'' if len(skills) == 1 else 's'} ({', '.join(skills)}). "
            "This plugin registers skills only")
    others = [label for label, rel in NOT_REGISTERED if (kit_dir / rel).exists()]
    if others:
        text += f"; it does not register the module's {_series(others)}"
    return text + "."


def render_plugin(kit: str, claude: dict, entry: dict, marketplace: dict, kit_dir: Path) -> dict:
    display = claude.get("displayName") or entry.get("displayName") or kit
    description = codex_description(display, kit_dir)
    source_author = claude.get("author") or marketplace.get("owner") or {}
    # Why: the publisher's url is a publication credit the IP/PII ruleset allows ONLY in the files
    # it names (`.claude-plugin/plugin.json`, marketplace, LICENSE...); a render that copied
    # `author.url` here made the assembler's lint block the whole kit. The Codex manifest carries
    # the author's name; the site is `homepage`, and the url credit stays where it lives.
    author = {"name": source_author["name"]} if isinstance(source_author, dict) and source_author.get("name") else {}
    document = {
        "name": kit,
        "version": claude["version"],
        "description": description,
        "author": author,
        "homepage": marketplace.get("site"),
        "repository": marketplace.get("repository"),
        "license": claude.get("license", "MIT"),
        "keywords": list(claude.get("keywords") or entry.get("keywords") or []),
        "skills": SKILLS_DIR,
        "hooks": dict(NO_HOOKS),
        "interface": {
            "displayName": display,
            "shortDescription": first_sentence(description),
            "longDescription": f"{description} On Claude Code the same module installs whole, from the same repository.",
            "developerName": author.get("name") if isinstance(author, dict) else None,
            "category": CATEGORY,
        },
    }
    document["interface"] = {key: value for key, value in document["interface"].items() if value}
    return {key: value for key, value in document.items() if value not in (None, {}, [])}


def render_marketplace(marketplace: dict, manifest: dict) -> dict:
    chosen = eligible(manifest)
    plugins = [
        {"name": entry["name"], "source": {"source": "local", "path": entry["source"]},
         "policy": dict(POLICY), "category": CATEGORY}
        for entry in marketplace["plugins"] if entry["name"] in chosen
    ]
    return {"name": marketplace["name"], "interface": {"displayName": display_name(marketplace)}, "plugins": plugins}


def expected_plugins(staging: Path, manifest: dict, marketplace: dict) -> dict[Path, bytes]:
    chosen = eligible(manifest)
    expected: dict[Path, bytes] = {}
    for entry in marketplace["plugins"]:
        kit = entry["name"]
        if kit not in chosen:
            continue
        claude = _load(staging / kit / CLAUDE_PLUGIN_REL)
        expected[staging / kit / CODEX_PLUGIN_REL] = _dump(render_plugin(kit, claude, entry, marketplace, staging / kit))
    return expected


def check(staging: Path, manifest: dict, product: Path | None = None) -> list[str]:
    marketplace = _load(staging / "marketplace.json")
    problems: list[str] = []
    for path, data in expected_plugins(staging, manifest, marketplace).items():
        rel = path.relative_to(staging).as_posix()
        if not path.is_file():
            problems.append(f"{rel}: missing (run --write)")
        elif path.read_bytes() != data:
            problems.append(f"{rel}: differs from its render (run --write)")
    chosen = eligible(manifest)
    for entry in marketplace["plugins"]:
        kit = entry["name"]
        if kit not in chosen and (staging / kit / CODEX_PLUGIN_REL).exists():
            problems.append(f"{kit}: does not qualify for the Codex channel and carries {CODEX_PLUGIN_REL.as_posix()}")
        if kit in chosen and not (staging / kit / "skills").is_dir():
            problems.append(f"{kit}: the manifest promises skills and {kit}/skills is not a directory")
    if product is not None:
        target = product / CODEX_MARKETPLACE_REL
        data = _dump(render_marketplace(marketplace, manifest))
        if not target.is_file():
            problems.append(f"{CODEX_MARKETPLACE_REL.as_posix()}: missing in the product (run --emit)")
        elif target.read_bytes() != data:
            problems.append(f"{CODEX_MARKETPLACE_REL.as_posix()}: differs from the render (run --emit)")
    return problems


def write(staging: Path, manifest: dict) -> list[Path]:
    marketplace = _load(staging / "marketplace.json")
    changed: list[Path] = []
    for path, data in expected_plugins(staging, manifest, marketplace).items():
        if path.is_file() and path.read_bytes() == data:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        changed.append(path)
    return changed


def emit(product: Path, staging: Path, manifest: dict) -> Path:
    marketplace = _load(staging / "marketplace.json")
    target = product / CODEX_MARKETPLACE_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_dump(render_marketplace(marketplace, manifest)))
    return target


def _self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="codex-marketplace-") as scratch:
        root = Path(scratch)
        staging = root / "staging"
        for kit, skills in (("alpha-kit", True), ("beta-kit", False), ("gamma-kit", True)):
            (staging / kit / ".claude-plugin").mkdir(parents=True)
            claude = {"name": kit, "displayName": kit.title(), "version": "1.2.3", "description": f"{kit} does one thing. Then another.",
                      "author": {"name": "Team", "url": "https://example.invalid"}, "keywords": ["a"], "hooks": "./hooks/hooks.json"}
            (staging / kit / ".claude-plugin" / "plugin.json").write_text(json.dumps(claude), encoding="utf-8")
            if skills:
                (staging / kit / "skills" / "one").mkdir(parents=True)
                (staging / kit / "skills" / "one" / "SKILL.md").write_text("---\nname: first-skill\n---\n", encoding="utf-8")
                (staging / kit / "skills" / "two").mkdir()
                (staging / kit / "skills" / "two" / "SKILL.md").write_text("# no frontmatter\n", encoding="utf-8")
        (staging / "alpha-kit" / "commands").mkdir()
        (staging / "alpha-kit" / "hooks").mkdir()
        (staging / "alpha-kit" / "hooks" / "hooks.json").write_text("{}", encoding="utf-8")
        marketplace = {"name": "test-market", "site": "https://example.invalid/site", "repository": "https://example.invalid/repo",
                       "owner": {"name": "Team"},
                       "plugins": [{"name": kit, "version": "1.2.3", "source": f"./mods/{kit}-1.2.3", "description": f"{kit} long"}
                                   for kit in ("alpha-kit", "beta-kit", "gamma-kit")]}
        (staging / "marketplace.json").write_text(json.dumps(marketplace), encoding="utf-8")
        manifest = {"modules": [
            {"id": "alpha-kit", "version": "1.2.3", "path": "mods/alpha-kit-1.2.3", "hosts": {"claude-code": "native", "codex": "explicit-command"}, "components": ["skills", "hooks"]},
            {"id": "beta-kit", "version": "1.2.3", "path": "mods/beta-kit-1.2.3", "hosts": {"claude-code": "native", "codex": "explicit-command"}, "components": ["scripts"]},
            {"id": "gamma-kit", "version": "1.2.3", "path": "mods/gamma-kit-1.2.3", "hosts": {"claude-code": "native", "codex": "unsupported"}, "components": ["skills"]},
        ]}
        assert sorted(eligible(manifest)) == ["alpha-kit"], "eligibility: skills AND supported on Codex"
        assert check(staging, manifest) == ["alpha-kit/.codex-plugin/plugin.json: missing (run --write)"]
        written = write(staging, manifest)
        assert [p.name for p in written] == ["plugin.json"] and written[0].parent.parent.name == "alpha-kit"
        assert write(staging, manifest) == [], "write is idempotent"
        assert check(staging, manifest) == []
        rendered = json.loads((staging / "alpha-kit" / CODEX_PLUGIN_REL).read_text(encoding="utf-8"))
        assert rendered["skills"] == SKILLS_DIR and rendered["hooks"] == {"hooks": {}}, \
            "skills only: an absent `hooks` makes Codex load hooks/hooks.json, an empty inline object does not"
        assert rendered["description"] == ("Alpha-Kit on Codex: 2 skills (first-skill, two). This plugin registers "
                                           "skills only; it does not register the module's commands and hooks."), rendered
        assert rendered["interface"]["shortDescription"] == "Alpha-Kit on Codex: 2 skills (first-skill, two)."
        assert rendered["interface"]["longDescription"].startswith(rendered["description"] + " On Claude Code")
        assert "does one thing" not in json.dumps(rendered), "the Claude description is not what Codex installs"
        assert rendered["homepage"] == "https://example.invalid/site"
        assert rendered["author"] == {"name": "Team"}, "the author's url is a credit that lives elsewhere"
        assert (staging / "alpha-kit" / CODEX_PLUGIN_REL).read_bytes().count(b"\r") == 0
        drifted = dict(rendered, version="0.0.1")
        (staging / "alpha-kit" / CODEX_PLUGIN_REL).write_text(json.dumps(drifted), encoding="utf-8")
        problems = check(staging, manifest)
        assert len(problems) == 1 and problems[0].startswith("alpha-kit/"), problems
        write(staging, manifest)
        (staging / "beta-kit" / ".codex-plugin").mkdir()
        (staging / "beta-kit" / CODEX_PLUGIN_REL).write_text("{}", encoding="utf-8")
        assert any(p.startswith("beta-kit:") for p in check(staging, manifest)), "a stale manifest on a kit that does not qualify"
        (staging / "beta-kit" / CODEX_PLUGIN_REL).unlink()
        product = root / "product"
        target = emit(product, staging, manifest)
        document = json.loads(target.read_text(encoding="utf-8"))
        assert document["name"] == "test-market" and document["interface"] == {"displayName": "Test Market"}
        assert [p["name"] for p in document["plugins"]] == ["alpha-kit"]
        assert document["plugins"][0]["source"] == {"source": "local", "path": "./mods/alpha-kit-1.2.3"}
        assert document["plugins"][0]["policy"] == POLICY
        assert check(staging, manifest, product) == []
        assert first_sentence("x" * 300) .endswith("...")
    print("codex_marketplace self-test OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--staging", type=Path, default=DEFAULT_STAGING)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--product", type=Path, help="with --check: also compare the product's Codex marketplace")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write", action="store_true", help="render every qualifying kit's .codex-plugin/plugin.json into staging")
    action.add_argument("--check", action="store_true", help="exit 1 if a rendered file is missing or differs")
    action.add_argument("--emit", type=Path, metavar="PRODUCT", help="write PRODUCT/.agents/plugins/marketplace.json")
    action.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    manifest = _load(args.manifest)
    staging = args.staging.resolve()
    if args.write:
        changed = write(staging, manifest)
        print(f"codex_marketplace: {len(changed)} file(s) written" + "".join(f"\n  {p.relative_to(staging).as_posix()}" for p in changed))
        return 0
    if args.emit is not None:
        target = emit(args.emit.resolve(), staging, manifest)
        listed = len(json.loads(target.read_text(encoding="utf-8"))["plugins"])
        print(f"codex_marketplace: {target} written ({listed} plugin(s))")
        return 0
    problems = check(staging, manifest, args.product.resolve() if args.product else None)
    if problems:
        print("codex_marketplace: drift" + "".join(f"\n  {p}" for p in problems))
        return 1
    print("codex_marketplace: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
