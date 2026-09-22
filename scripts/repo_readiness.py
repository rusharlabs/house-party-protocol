#!/usr/bin/env python3
"""Repository readiness: the dated table a maintainer reads before opening or releasing.

Every row is a check that ran now, against the checkout this script lives in, with the
command or file that proves it. Nothing here is new doctrine: the rows reuse the gates the
test suite already enforces (personal paths, stdlib-only) and add the ones that are about the
repository rather than the code — community files, workflow pins, version sources, language
pairs, the README module table against `marketplace.json` when it is beside the manifest.

    python scripts/repo_readiness.py          # table; exit 1 if any row FAILS
    python scripts/repo_readiness.py --json   # the same rows as JSON

Standard library only. Read-only: it writes nothing and calls no network.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

from test_no_personal_paths import scan as scan_personal_paths  # noqa: E402  (reused gate)
from test_stdlib_only import OWN, third_party, top_level_imports  # noqa: E402  (reused gate)

COMMUNITY_FILES = (
    "README.md", "README.pt-BR.md", "LICENSE", "NOTICE", "CITATION.cff",
    "CONTRIBUTING.md", "CONTRIBUTING.pt-BR.md", "CODE_OF_CONDUCT.md", "CODE_OF_CONDUCT.pt-BR.md",
    "SECURITY.md", "SECURITY.pt-BR.md", "CHANGELOG.md", "CHANGELOG.pt-BR.md",
    ".github/CODEOWNERS", ".github/dependabot.yml", ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/ISSUE_TEMPLATE/config.yml", ".github/ISSUE_TEMPLATE/problem.yml",
    ".github/ISSUE_TEMPLATE/feedback.yml", ".github/ISSUE_TEMPLATE/idea.yml", ".github/labels.json",
    ".github/workflows/ci.yml", ".github/workflows/release.yml",
)
PT = ".pt-BR.md"
_USES = re.compile(r"^\s*-?\s*uses:\s*([\w.-]+/[\w.-]+)@(\S+)(\s+#\s*(v\S+))?\s*$")
_SHA = re.compile(r"^[0-9a-f]{40}$")


def row(name: str, ok: bool | None, detail: str) -> dict:
    return {"check": name, "status": "ok" if ok else "skip" if ok is None else "FAIL", "detail": detail}


# ----------------------------------------------------------------------------- checks

def community_files() -> dict:
    missing = [name for name in COMMUNITY_FILES if not (ROOT / name).is_file()]
    return row("community files", not missing,
               f"{len(COMMUNITY_FILES) - len(missing)}/{len(COMMUNITY_FILES)} present" + (f"; missing: {missing}" if missing else ""))


def workflows() -> dict:
    """No YAML parser in the standard library: this reads the shape a workflow must have."""
    problems, files = [], sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    for path in files:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        if not any(line.startswith("on:") for line in lines):
            problems.append(f"{path.name}: no top-level `on:`")
        if not any(line.startswith("jobs:") for line in lines):
            problems.append(f"{path.name}: no top-level `jobs:`")
        if not any(line.startswith("permissions:") for line in lines):
            problems.append(f"{path.name}: no top-level `permissions:`")
        if any("\t" in line for line in lines):
            problems.append(f"{path.name}: tab character (YAML forbids tabs in indentation)")
        for number, line in enumerate(lines, 1):
            match = _USES.match(line)
            if not match:
                continue
            action, ref, _, label = match.groups()
            if not _SHA.match(ref):
                problems.append(f"{path.name}:{number}: {action}@{ref} is not a 40-hex commit SHA")
            elif not label:
                problems.append(f"{path.name}:{number}: {action} pinned without a `# vX.Y.Z` label")
            if action == "actions/checkout":
                window = "\n".join(lines[number:number + 3])
                if "persist-credentials: false" not in window:
                    problems.append(f"{path.name}:{number}: checkout without `persist-credentials: false`")
    return row("workflows: shape, SHA pins, persist-credentials", not problems and bool(files),
               f"{len(files)} workflow(s), " + ("; ".join(problems) if problems else "all `uses:` pinned by SHA with a version label"))


def _version_sources() -> dict[str, str]:
    sources = {}
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    sources["pyproject.toml"] = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M).group(1)
    init = (ROOT / "hpp" / "__init__.py").read_text(encoding="utf-8")
    sources["hpp/__init__.py"] = re.search(r'^__version__\s*=\s*"([^"]+)"', init, re.M).group(1)
    manifest = json.loads((ROOT / "hpp.manifest.json").read_text(encoding="utf-8"))
    sources["hpp.manifest.json"] = str(manifest.get("product_version"))
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    sources["CITATION.cff"] = re.search(r'^version:\s*"([^"]+)"', citation, re.M).group(1)
    for name in ("CHANGELOG.md", "CHANGELOG.pt-BR.md"):
        match = re.search(r"^## \[(\d+\.\d+\.\d+)\]", (ROOT / name).read_text(encoding="utf-8"), re.M)
        sources[f"{name} (latest section)"] = match.group(1) if match else "?"
    return sources


def version_sources() -> dict:
    sources = _version_sources()
    distinct = sorted(set(sources.values()))
    return row("version sources agree", len(distinct) == 1,
               f"{distinct[0]} in {len(sources)} sources" if len(distinct) == 1 else f"disagree: {sources}")


def readme_tag() -> dict:
    """The quick-start `pip install git+...@vX.Y.Z` must name the version the package carries."""
    version = _version_sources()["pyproject.toml"]
    findings = []
    for name in ("README.md", "README.pt-BR.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        tags = re.findall(r"pip install git\+https://github\.com/[\w.-]+/house-party-protocol@v(\d+\.\d+\.\d+)", text)
        if not tags:
            findings.append(f"{name}: quick start not pinned to a tag")
        elif set(tags) != {version}:
            findings.append(f"{name}: pinned to {sorted(set(tags))}, package is {version}")
    return row("README quick-start tag == package version", not findings,
               f"@v{version} on both sides" if not findings else "; ".join(findings) + " (expected right after a release bump; the release workflow refuses a tag that disagrees)")


def personal_paths() -> dict:
    hits = scan_personal_paths(ROOT)
    return row("no personal paths", not hits, "0 hits" if not hits else f"{len(hits)} hit(s): {hits[:3]}")


def stdlib_only() -> dict:
    offenders = third_party(top_level_imports(ROOT / "hpp"), OWN)
    return row("hpp/ imports only the standard library", not offenders, "0 third-party imports" if not offenders else str(offenders))


def language_pairs() -> dict:
    bases, missing = [], []
    for path in sorted(ROOT.rglob("*.md")):
        parts = set(path.relative_to(ROOT).parts[:-1])
        if parts & {".github", "hpp", "tests", "assets", "__pycache__", "examples", "skills", "commands", "rules"}:
            continue
        if any(part.startswith(("frameworks-", "instaladores", "continuidade", "multi-sessao", "wizards", "_superseded")) for part in parts):
            continue  # emitted module directories carry their own pair gate in the forge
        if path.name.endswith(PT):
            sibling = path.with_name(path.name[: -len(PT)] + ".md")
        else:
            sibling = path.with_name(path.name[: -len(".md")] + PT)
        bases.append(path)
        if not sibling.is_file():
            missing.append(path.relative_to(ROOT).as_posix())
    return row("en / pt-BR pairs present (root + docs)", not missing,
               f"{len(bases)} files, every one has its pair" if not missing else f"without pair: {missing}")


def readme_modules_vs_marketplace() -> dict:
    marketplace = ROOT / "marketplace.json"
    if not marketplace.is_file():
        return row("README module table == marketplace.json", None,
                   "no marketplace.json beside the manifest (source tree); measured in the emitted repository")
    plugins = {p["name"]: p["version"] for p in json.loads(marketplace.read_text(encoding="utf-8"))["plugins"]}
    findings = []
    for name in ("README.md", "README.pt-BR.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        table = dict(re.findall(r"^\| `([a-z0-9-]+)` \| (\d+\.\d+\.\d+) \|", text, re.M))
        if table != plugins:
            findings.append(f"{name}: table {table} != marketplace {plugins}")
        if f"modules={len(plugins)}" not in text:
            findings.append(f"{name}: `modules={len(plugins)}` not quoted")
    return row("README module table == marketplace.json", not findings,
               f"{len(plugins)} modules, versions match on both sides" if not findings else "; ".join(findings))


CHECKS = (community_files, workflows, version_sources, readme_tag, personal_paths, stdlib_only,
          language_pairs, readme_modules_vs_marketplace)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="print the rows as JSON")
    args = parser.parse_args(argv)
    rows = [check() for check in CHECKS]
    failed = [r for r in rows if r["status"] == "FAIL"]
    report = {"date": date.today().isoformat(), "root": ROOT.name, "rows": rows,
              "verdict": "ready" if not failed else f"{len(failed)} check(s) failing"}
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        width = max(len(r["check"]) for r in rows)
        print(f"repo readiness · {report['date']} · {ROOT.name}")
        print("-" * (width + 60))
        for r in rows:
            print(f"{r['check']:<{width}}  {r['status']:<4}  {r['detail']}")
        print("-" * (width + 60))
        print(f"verdict: {report['verdict']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
