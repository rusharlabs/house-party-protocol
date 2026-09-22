#!/usr/bin/env python3
"""
wizard -- new-project scaffold in 6 steps (generic setup-wizard method,
REWRITTEN FROM SCRATCH -- not one line of third-party code. See "WHAT NOT TO DO" in
the kickoff: the METHOD is extracted -- check environment, configure, validate, generate +
summary -- not the code of any specific installer).

The 6 steps:
  1. check_python()      -- does the environment have Python >= 3.9?
  2. check_git()          -- does the environment have git? (the target project is always a repo)
  3. check_deps()         -- is PyYAML available? (the wizard's only real dependency)
  4. configure()          -- project name + R0-R4 ladder + which templates to instantiate
                            (--demo = sensible defaults; --answers = ready-made answers;
                            neither = intentional NotImplementedError -- use
                            --interview first to get the question schema)
  5. validate()           -- is the resulting profile well-formed? (required fields)
  6. generate_and_summary() -- writes operator-profile.yaml + chosen templates + summary
                            (NEVER overwrites a customized file -- --force ignores the protection)

Usage:
    python wizard.py --interview                        # prints the question schema (JSON), exits 0
    python wizard.py --demo --out <dir>                  # non-interactive scaffold with defaults
    python wizard.py --answers respostas.json --out <dir>  # scaffold from ready-made answers
    python wizard.py --demo --out <dir> --force          # overwrites customization on purpose
    python wizard.py --self-test

No mode blocks on stdin -- the real operator of this ecosystem is often an
agent acting on behalf of the human; --interview/--answers is the "Confirm" (the agent reads the schema,
asks the human in the conversation, re-invokes with --answers), never a terminal input().

Exit: 0 ok (including re-run = no-op or skip-customized) - 2 environment missing a prerequisite
(python/git/PyYAML missing) or invalid usage (neither --demo, nor --answers, nor --interview).
stdlib + PyYAML. v1.1.0 -- 2026-07-11 (agent-framework-wizard - fixes the NotImplementedError
of interactive mode + unconditional overwrite -- see INSTALL-CONTRACT.md)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

_HERE = Path(__file__).resolve().parent
_TEMPLATES_DIR = _HERE / "templates"

_ESCADA_DEFAULT = [
    {"nivel": "R0", "nome": "Declared", "certifica": "the maker's word"},
    {"nivel": "R1", "nome": "Self-verified", "certifica": "--self-test/pytest exit 0"},
    {"nivel": "R2", "nome": "Gate", "certifica": "done_gate.py exit 0"},
    {"nivel": "R3", "nome": "Reviewed", "certifica": "goal_review.py + cross-model checker"},
    {"nivel": "R4", "nome": "Accepted", "certifica": "human gate / production"},
]

_DEFAULT_TEMPLATES = ["00-READ-FIRST", "00-STATE", "00-VISION", "00-PROCESSES"]

_DOCS_SUBDIR = ("docs", "plans", "execution")
# Why: the generated names and the directory that holds them were renamed to English. A repo
# scaffolded with the old spelling must keep working with zero action, so both the template
# names and the output directory are DUAL-READ for one version — the English form wins, the
# legacy one is accepted with a deprecation notice on stderr and the same exit code.
_LEGACY_DOCS_SUBDIR = ("docs", "plans", "execucao")
_LEGACY_TEMPLATE_NAMES = {"00-LEIA-PRIMEIRO": "00-READ-FIRST"}


def _resolve_template_names(names: list) -> list:
    out = []
    for name in names:
        english = _LEGACY_TEMPLATE_NAMES.get(name)
        if english:
            print(f"[wizard] deprecated template name '{name}'; use '{english}' — the old one is "
                  "accepted for one version only.", file=sys.stderr)
            name = english
        out.append(name)
    return out


def _docs_dir(out_dir: Path) -> Path:
    """The English directory, unless this repo already holds only the legacy one."""
    english = out_dir.joinpath(*_DOCS_SUBDIR)
    legacy = out_dir.joinpath(*_LEGACY_DOCS_SUBDIR)
    if legacy.is_dir() and not english.is_dir():
        print(f"[wizard] deprecated: wrote into '{'/'.join(_LEGACY_DOCS_SUBDIR)}'; rename that "
              "directory to 'execution' — the old spelling is accepted for one version only.",
              file=sys.stderr)
        return legacy
    return english


def _available_templates() -> list:
    return sorted(p.name[: -len(".template.md")] for p in _TEMPLATES_DIR.glob("*.template.md"))


def questions() -> list:
    """The wizard's question schema -- the SAME format consumed by kit_doctor.py's
    stage_configure (see INSTALL-CONTRACT.md 'Question schema'): id/prompt/type/
    options/default. Used by --interview (prints this schema) and --answers (resolves
    against it). 'answering questions' has ONE format only in this marketplace."""
    return [
        {
            "id": "project_name",
            "prompt": "What is the project/agent name? (it goes into the generated files; e.g. my-agent)",
            "type": "string", "default": "agente-teste",
        },
        {
            "id": "templates",
            "prompt": "Which base documents should be generated? You may pick more than one "
                      "(default: all 4 — 00-READ-FIRST, 00-STATE, 00-VISION, 00-PROCESSES)",
            "type": "choice", "options": _available_templates(), "default": list(_DEFAULT_TEMPLATES),
        },
    ]


def step(n: int, total: int, title: str) -> None:
    print(f"[{n}/{total}] {title}")


def check_python() -> tuple:
    ok = sys.version_info >= (3, 9)
    return ok, f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def check_git() -> tuple:
    try:
        r = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=10)
        return r.returncode == 0, (r.stdout or r.stderr).strip()
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def check_deps() -> tuple:
    return yaml is not None, "PyYAML available" if yaml is not None else "PyYAML MISSING — install it with 'pip install pyyaml'"


def configure(demo: bool, project_name: str | None, templates: list | None, answers: dict | None = None) -> dict:
    if demo:
        return {
            "project_name": project_name or "agente-teste",
            "escada": _ESCADA_DEFAULT,
            "templates": _resolve_template_names(templates or list(_DEFAULT_TEMPLATES)),
        }
    if answers is not None:
        # --answers: same schema as questions() -- a missing field falls back to the question's default.
        defaults = {q["id"]: q["default"] for q in questions()}
        return {
            "project_name": answers.get("project_name") or project_name or defaults["project_name"],
            "escada": _ESCADA_DEFAULT,
            "templates": _resolve_template_names(answers.get("templates") or templates or list(defaults["templates"])),
        }
    # Neither --demo nor --answers: with no real stdin there is no way to resolve. Use --interview
    # first (it prints the question schema) and re-invoke with --answers <file>.
    raise NotImplementedError("interactive mode requires --demo or --answers <file> (see --interview for the schema)")


def validate(config: dict) -> list:
    errors = []
    if not config.get("project_name"):
        errors.append("project_name missing")
    escada = config.get("escada", [])
    if len(escada) != 5 or {e["nivel"] for e in escada} != {"R0", "R1", "R2", "R3", "R4"}:
        errors.append("the ladder must have exactly the levels R0-R4")
    if not config.get("templates"):
        errors.append("no template selected")
    for t in config.get("templates", []):
        if not (_TEMPLATES_DIR / f"{t}.template.md").exists():
            errors.append(f"unknown template: {t}")
    return errors


def _sha256_dir(out_dir: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(out_dir.rglob("*")):
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


def _write_if_safe(dest: Path, content: str, force: bool, rel: str, written: list, skipped: list) -> None:
    """Never overwrites a customization by default (same spirit as stage_profile in
    kit_doctor.py): if the target already exists with content DIFFERENT from what would be
    generated now, it marks skip-customized instead of clobbering. --force ignores this protection."""
    if dest.exists() and not force:
        existing = dest.read_text(encoding="utf-8")
        if existing != content:
            skipped.append(rel)
            return
    dest.write_text(content, encoding="utf-8")
    written.append(rel)


def generate_and_summary(config: dict, out_dir: Path, force: bool = False) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    before_hash = _sha256_dir(out_dir) if out_dir.exists() else None

    profile = {
        "project_name": config["project_name"],
        "verificacao": {"escada": config["escada"]},
    }
    if yaml is not None:
        profile_content = yaml.safe_dump(profile, allow_unicode=True, sort_keys=False)
    else:
        profile_content = json.dumps(profile, ensure_ascii=False, indent=2)

    written: list = []
    skipped: list = []
    _write_if_safe(out_dir / "operator-profile.yaml", profile_content, force, "operator-profile.yaml", written, skipped)

    docs_dir = _docs_dir(out_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)
    for t in config["templates"]:
        src = _TEMPLATES_DIR / f"{t}.template.md"
        text = src.read_text(encoding="utf-8").replace("{{project_name}}", config["project_name"])
        dest = docs_dir / f"{t}.md"
        _write_if_safe(dest, text, force, str(dest.relative_to(out_dir)), written, skipped)

    after_hash = _sha256_dir(out_dir)
    no_op = before_hash == after_hash

    summary = {
        "project_name": config["project_name"],
        "out_dir": str(out_dir),
        "files_written": written,
        "files_skipped_customized": skipped,
        "no_op": no_op,
    }
    return summary


# Why: `templates` keeps the kit configurable for external consumers; the local flow uses the default.
def run_wizard(
    demo: bool, out_dir: Path, project_name: str | None = None, templates: list | None = None,
    answers: dict | None = None, force: bool = False,
) -> tuple:
    """Returns (exit_code, summary_or_errors)."""
    ok_py, msg_py = check_python()
    step(1, 6, f"check_python — {msg_py}")
    if not ok_py:
        return 2, {"error": f"Python >= 3.9 required: {msg_py}"}

    ok_git, msg_git = check_git()
    step(2, 6, f"check_git — {msg_git}")
    if not ok_git:
        return 2, {"error": f"git missing: {msg_git}"}

    ok_deps, msg_deps = check_deps()
    step(3, 6, f"check_deps — {msg_deps}")
    if not ok_deps:
        return 2, {"error": msg_deps}

    step(4, 6, "configure")
    config = configure(demo, project_name, templates, answers=answers)

    step(5, 6, "validate")
    errors = validate(config)
    if errors:
        return 2, {"errors": errors}

    step(6, 6, "generate_and_summary")
    summary = generate_and_summary(config, out_dir, force=force)
    return 0, summary


def _self_test() -> int:
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="wizard_selftest_"))
    try:
        out_dir = tmp / "agente-teste"
        code1, r1 = run_wizard(demo=True, out_dir=out_dir)
        assert code1 == 0, f"the 1st run should pass: {r1}"
        assert (out_dir / "operator-profile.yaml").exists()
        assert (out_dir.joinpath(*_DOCS_SUBDIR, "00-STATE.md")).exists()
        assert not r1["no_op"], "the 1st run should NOT be a no-op (new file)"

        code2, r2 = run_wizard(demo=True, out_dir=out_dir)
        assert code2 == 0 and r2["no_op"], f"the 2nd run should be a no-op (identical content): {r2}"

        bad_config = {"project_name": "", "escada": [], "templates": []}
        errs = validate(bad_config)
        assert len(errs) >= 2, f"an empty config should accumulate errors: {errs}"

        content = (out_dir.joinpath(*_DOCS_SUBDIR, "00-READ-FIRST.md")).read_text(encoding="utf-8")
        assert "agente-teste" in content and "{{project_name}}" not in content, "placeholder not substituted"

        # --- Bug A: --interview (schema) + --answers (non-interactive, no NotImplementedError) ---
        qs = questions()
        assert len(qs) >= 2 and {"id", "prompt", "type", "default"} <= set(qs[0].keys())
        try:
            configure(demo=False, project_name=None, templates=None, answers=None)
            raise AssertionError("configure without demo/answers should raise NotImplementedError")
        except NotImplementedError:
            pass

        answers_out = tmp / "agente-via-answers"
        code_a, r_a = run_wizard(demo=False, out_dir=answers_out, answers={"project_name": "via-answers"})
        assert code_a == 0 and r_a["project_name"] == "via-answers", f"--answers should configure without stdin: {r_a}"
        assert (answers_out / "operator-profile.yaml").exists()

        # --- Bug B: skip-exists -- a manual edit survives a re-run (never clobber without --force) ---
        edited_file = out_dir.joinpath(*_DOCS_SUBDIR, "00-STATE.md")
        edited_file.write_text("USER CUSTOMIZATION — DO NOT OVERWRITE\n", encoding="utf-8")
        code3, r3 = run_wizard(demo=True, out_dir=out_dir)
        assert code3 == 0
        assert any(s.endswith("00-STATE.md") for s in r3["files_skipped_customized"]), \
            f"the edit should be preserved (skip): {r3}"
        assert edited_file.read_text(encoding="utf-8") == "USER CUSTOMIZATION — DO NOT OVERWRITE\n", \
            "generate_and_summary overwrote a customization without --force"

        # --force ignores the protection on purpose
        code4, r4 = run_wizard(demo=True, out_dir=out_dir, force=True)
        assert code4 == 0 and any(w.endswith("00-STATE.md") for w in r4["files_written"]), f"--force should overwrite: {r4}"
        assert "agente-teste" in edited_file.read_text(encoding="utf-8"), "--force should have regenerated the file"

        # --- dual read: the legacy template name and the legacy output directory still work ---
        legacy_out = tmp / "legacy-repo"
        legacy_out.joinpath(*_LEGACY_DOCS_SUBDIR).mkdir(parents=True)
        code5, r5 = run_wizard(demo=False, out_dir=legacy_out,
                               answers={"project_name": "legacy", "templates": ["00-LEIA-PRIMEIRO"]})
        assert code5 == 0, f"the legacy template name must still be accepted: {r5}"
        assert (legacy_out.joinpath(*_LEGACY_DOCS_SUBDIR, "00-READ-FIRST.md")).exists(), \
            f"it should have written the English file inside the existing legacy directory: {r5}"
        assert not (legacy_out.joinpath(*_DOCS_SUBDIR)).exists(), \
            "it must not split the generated docs across two directories"

        print("self-test OK — the 6 steps run, 1st run generates, 2nd run = no-op, placeholders substituted, validate catches "
              "an empty config, --interview/--answers without NotImplementedError, skip-exists preserves the edit, --force overwrites, "
              "dual read of the legacy template name and of the legacy output directory")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wizard.py")
    p.add_argument("--demo", action="store_true")
    p.add_argument("--out", default=None)
    p.add_argument("--project-name", default=None)
    p.add_argument("--interview", action="store_true", help="print the question schema (JSON) and exit — generates nothing")
    p.add_argument("--answers", dest="answers_path", default=None, help="JSON/YAML file with answers to --interview")
    p.add_argument("--force", action="store_true", help="overwrite a customized file (default: never overwrite)")
    p.add_argument("--self-test", action="store_true")
    return p


def _load_answers(path: str) -> dict:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix in (".yaml", ".yml") and yaml is not None:
        return yaml.safe_load(text) or {}
    return json.loads(text) if text.strip() else {}


def main(argv) -> int:
    args = build_parser().parse_args(argv)
    if args.self_test:
        return _self_test()
    if args.interview:
        print(json.dumps({"questions": questions()}, ensure_ascii=False, indent=2))
        return 0
    if not args.out or not (args.demo or args.answers_path):
        print("usage: wizard.py --demo --out <dir> | wizard.py --answers <file> --out <dir> | wizard.py --interview", file=sys.stderr)
        return 2
    answers = _load_answers(args.answers_path) if args.answers_path else None
    code, result = run_wizard(
        demo=args.demo, out_dir=Path(args.out), project_name=args.project_name,
        answers=answers, force=args.force,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
