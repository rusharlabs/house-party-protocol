"""Deterministic project inventory from HEAD blobs and bounded Git history.

Runner hints and CI commands are candidates, never commands executed by this module.
No file writes, models, optional parsers or working-tree source imports are involved.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import PurePosixPath
import re

from hpp._repository import RepositoryError, Snapshot, _decode, _git, _path, _secret_path, read_text, snapshot
from hpp.context import _SECRET_PATTERN


_MANIFESTS = {
    "pyproject.toml": "python", "setup.py": "python", "setup.cfg": "python",
    "requirements.txt": "python", "Pipfile": "python", "package.json": "javascript",
    "go.mod": "go", "Cargo.toml": "rust", "pom.xml": "java", "build.gradle": "java",
    "build.gradle.kts": "java", "Gemfile": "ruby", "composer.json": "php", "mix.exs": "elixir",
    "pubspec.yaml": "dart", "Package.swift": "swift", "CMakeLists.txt": "cmake",
}
_CREDENTIAL = re.compile(r"https?://[^\s/]+@|\b(?:gh[pousr]_[A-Za-z0-9_]{8,}|github_pat_[A-Za-z0-9_]+|"
                         r"xox[baprs]-[A-Za-z0-9-]+|AKIA[A-Z0-9]{16}|AIza[A-Za-z0-9_-]{20,})")


def _command(value: str) -> tuple[str, bool]:
    withheld = bool(_SECRET_PATTERN.search(value) or _CREDENTIAL.search(value))
    return ("[withheld: credential-like command]" if withheld else value, withheld)


def _ci_file(path: str) -> bool:
    return ((path.startswith(".github/workflows/") and path.endswith((".yml", ".yaml")))
            or path in {".gitlab-ci.yml", "azure-pipelines.yml", "azure-pipelines.yaml",
                        "bitbucket-pipelines.yml", "Jenkinsfile", ".circleci/config.yml"})


def _ci_candidates(path: str, text: str) -> list[dict]:
    rows = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^(\s*)(?:-\s*)?(?:run|script):\s*(.*)$", line)
        if not match:
            continue
        command = match.group(2).strip()
        if command.startswith(("|", ">")) or not command:
            indent = len(match.group(1))
            block = []
            for continuation in lines[index + 1:]:
                if continuation.strip() and len(continuation) - len(continuation.lstrip()) <= indent:
                    break
                block.append(continuation.strip())
            command = "\n".join(block).strip()
        if not command:
            continue
        safe, withheld = _command(command)
        rows.append({"file": path, "line": index + 1, "command": safe, "withheld": withheld,
                     "status": "candidate", "executed": False})
    return rows


def _test_path(path: str) -> bool:
    p = PurePosixPath(path)
    return (any(part.lower() in {"test", "tests", "__tests__", "spec", "specs"} for part in p.parts[:-1])
            or p.name.startswith("test_") or p.name.endswith(("_test.py", "_test.go", ".test.js", ".spec.js", ".test.ts", ".spec.ts")))


def _hooks(value: object) -> int:
    if not isinstance(value, list):
        return 0
    return sum(len(item["hooks"]) if isinstance(item, dict) and isinstance(item.get("hooks"), list) else 1 for item in value)


def _history(snap: Snapshot, limit: int, files: set[str]) -> tuple[int, int, list[list]]:
    # Lowercase placeholders preserve committed identities instead of applying a
    # possibly dirty working-tree .mailmap. Identities never enter the report.
    identities = _git(snap.root, "log", "--no-show-signature", "--no-use-mailmap",
                      "--format=%an%x00%ae%x00", "-z", snap.commit).split(b"\0\0")
    authors = {hashlib.sha256(identity.strip()).digest() for identity in identities if identity.strip()}
    history = _git(snap.root, "log", "--no-show-signature", "--no-ext-diff", "--no-textconv", "--no-renames",
                   "-n", str(limit), "--format=%x1e%H%x00", "--name-only", "-z", snap.commit, "--")
    counts: Counter = Counter()
    commits = 0
    for record in history.split(b"\x1e"):
        if not record:
            continue
        commits += 1
        paths = set()
        for raw in record.split(b"\0")[1:]:
            if raw.strip(b"\n"):
                path = _path(_decode(raw.strip(b"\n")))
                if path in files:
                    paths.add(path)
        counts.update(paths)
    return len(authors), commits, [[p, n] for p, n in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def build_inventory(target, history_limit: int = 200) -> dict:
    """Measure a committed tree; invalid input/instrument failure raises RepositoryError."""
    if isinstance(history_limit, bool) or not isinstance(history_limit, int) or not 1 <= history_limit <= 10000:
        raise RepositoryError("history_limit must be an integer from 1 to 10000")
    snap = snapshot(target)
    excluded = []
    for path, mode in sorted(snap.modes.items()):
        reason = "symlink" if mode == "120000" else "gitlink" if mode == "160000" else None
        if reason is None and _secret_path(path):
            reason = "secret-file content and downstream analysis excluded"
        if reason is not None:
            excluded.append({"path": path, "reason": reason})
    files = [p for p in snap.files if not _secret_path(p)]
    manifests = [{"path": p, "ecosystem": _MANIFESTS[PurePosixPath(p).name]} for p in files if PurePosixPath(p).name in _MANIFESTS]
    test_files = [p for p in files if _test_path(p)]
    ci_files = [p for p in files if _ci_file(p)]
    docs = [p for p in files if p.startswith("docs/") or PurePosixPath(p).name.upper().startswith(("README", "CHANGELOG", "CONTRIBUTING", "ARCHITECTURE"))]
    instructions = [p for p in files if PurePosixPath(p).name in {"AGENTS.md", "AGENTS.override.md", "CLAUDE.md", "GEMINI.md"}
                    or p.startswith((".agents/", ".cursor/rules/")) or p == ".github/copilot-instructions.md"]
    settings = [p for p in files if (p.startswith(".claude/settings") and p.endswith(".json")) or p in {".codex/config.toml", ".codex/hooks.json", ".mcp.json"}]
    hints = []
    ci_commands = []
    events: Counter = Counter()
    unmeasured = []
    inspect = sorted(set(ci_files + [m["path"] for m in manifests]
                         + [p for p in files if PurePosixPath(p).name in {"pytest.ini", "tox.ini"}]
                         + [p for p in settings if p.endswith(".json") and p != ".mcp.json"]))
    for path in inspect:
        try:
            text = read_text(snap, path)
        except RepositoryError:
            unmeasured.append({"path": path, "reason": "not readable as bounded UTF-8 snapshot text"})
            continue
        if path in ci_files:
            ci_commands.extend(_ci_candidates(path, text))
        name = PurePosixPath(path).name
        if name == "pyproject.toml" and re.search(r"\[tool\.pytest(?:\.|\])", text):
            hints.append({"source": path, "runner": "pytest", "method": "configuration section name"})
        if name in {"setup.cfg", "pytest.ini", "tox.ini"} and re.search(r"\[(?:tool:)?pytest\]", text):
            hints.append({"source": path, "runner": "pytest", "method": "configuration section name"})
        if name == "package.json":
            try:
                config = json.loads(text)
                command = config.get("scripts", {}).get("test") if isinstance(config, dict) and isinstance(config.get("scripts", {}), dict) else None
                if isinstance(command, str):
                    safe, withheld = _command(command)
                    hints.append({"source": path, "runner": "npm test", "command": safe, "withheld": withheld, "executed": False})
            except ValueError:
                unmeasured.append({"path": path, "reason": "invalid JSON; runner hints not measured"})
        if path in settings and path.endswith(".json"):
            try:
                config = json.loads(text)
                hooks = config.get("hooks", {}) if isinstance(config, dict) else {}
                if isinstance(hooks, dict):
                    for event, entries in hooks.items():
                        # Event names are labels, never hook commands or environment values.
                        if isinstance(event, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,79}", event):
                            events[event] += _hooks(entries)
            except ValueError:
                unmeasured.append({"path": path, "reason": "invalid JSON; hooks not measured"})
    authors, commits, hotspots = _history(snap, history_limit, set(files))
    counts = Counter(PurePosixPath(p).suffix.lower() or "[none]" for p in files)
    codeowners = [p for p in files if p in {"CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"}]
    def status(items):
        return "measured" if items else "absent"
    return {
        "schema": "hpp.inventory/v1", "commit": snap.commit, "dirty_tracked": len(snap.dirty_paths),
        "files": files,
        "universe": {"rule": "regular Git HEAD blobs, paths normalized POSIX/NFC", "files": len(files),
                     "tracked_files": len(snap.modes), "excluded": excluded,
                     "outside": "untracked and ignored files; working-tree contents; symlinks; gitlinks; secret-file contents"},
        "sections": {
            "stack": {"status": status(manifests), "items": manifests, "method": "manifest filenames, not dependency resolution"},
            "languages": {"status": status(files), "unit": "regular files by extension, not parsed languages", "by_extension": dict(sorted(counts.items()))},
            "tests": {"status": status(test_files or hints), "unit": "files under conventional test paths, not test cases", "files": test_files, "count": len(test_files), "runner_hints": hints},
            "ci": {"status": status(ci_files), "files": ci_files, "run": ci_commands,
                   "method": "run/script lines and indented blocks; candidates only, YAML expressions not evaluated"},
            "docs": {"status": status(docs), "files": docs, "count": len(docs)},
            "agent_config": {"status": status(instructions or settings), "instructions": instructions, "settings": settings, "hooks_by_event": dict(sorted(events.items()))},
            "ownership": {"status": "measured", "codeowners": codeowners, "authors_count": authors, "method": "unique author name/email pairs counted, identities omitted"},
            "hotspots": {"status": "measured", "window": f"last {history_limit} commits", "commits_measured": commits,
                         "unit": "commits touching current inventory files; default Git merge diff semantics", "top": hotspots},
            "relations": {"status": "not-measured", "reason": "inventory does not infer code relations", "command": "hpp codegraph build"},
        },
        "not_measured": [{"what": "test outcome and coverage", "why": "requires explicit evidence execution"},
                         {"what": "runtime/deploy topology, semantic documentation freshness and real ownership", "why": "not established by tracked filenames or commit authors"},
                         {"what": "secret-file values, untracked and ignored files", "why": "excluded by design"}],
        "unreadable_inputs": unmeasured,
        "reproduce": "hpp inventory --target ." + (f" --history-limit {history_limit}" if history_limit != 200 else ""),
    }
