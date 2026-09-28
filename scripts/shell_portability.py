#!/usr/bin/env python3
"""Shell portability lint: every shipped `.sh` must run on a stock Mac (bash 3.2, BSD tools).

macOS ships bash 3.2 as `/bin/bash` and BSD `sed`, `grep`, `date`, `stat`, `readlink`, and no
`timeout` or bare `python`. A module script that uses a bash 4 feature or a GNU-only flag works on
Linux and on Git Bash and breaks on the Mac of the first user who runs it. This lint catches the
static half before release; CI runs the same scripts under `/bin/bash` on a macOS runner for the
dynamic half (`scripts/module_checks.py`).

    python scripts/shell_portability.py [path ...]   # files or directories; default: the
                                                     # modules listed in marketplace.json
    python scripts/shell_portability.py --json

A finding can be waived on its own line with `# portable: <reason>`; a waiver without a reason
does not count. Exit: 0 clean (or nothing to scan, said out loud) - 1 findings - 3 error.

Standard library only. Read-only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (id, pattern, why it breaks, portable form). Patterns run on code only: comments and heredoc
# bodies are removed first, so a rule named in prose or in an embedded Python program is not a hit.
RULES: tuple[tuple[str, str, str, str], ...] = (
    ("assoc-or-nameref", r"\b(?:declare|local|typeset)\s+-[a-zA-Z]*[An]\b",
     "associative arrays and namerefs need bash 4", "indexed arrays or plain variables"),
    ("mapfile", r"\b(?:mapfile|readarray)\b",
     "mapfile/readarray need bash 4", "a `while IFS= read -r` loop"),
    ("case-modification", r"\$\{[#!]?[A-Za-z_][A-Za-z0-9_]*(?:\[[^]]*\])?(?:,,?|\^\^?)\}",
     "${var,,} and ${var^^} need bash 4", "`tr '[:upper:]' '[:lower:]'`"),
    ("parameter-transform", r"\$\{[A-Za-z_][A-Za-z0-9_]*@[QEPAaUuLK]\}",
     "${var@Q} needs bash 4.4", "printf '%q'"),
    ("pipe-stderr", r"\|&",
     "`|&` needs bash 4", "`2>&1 |`"),
    ("append-both", r"&>>",
     "`&>>` needs bash 4", "`>>file 2>&1`"),
    ("coproc", r"\bcoproc\b",
     "coproc needs bash 4", "a named pipe or a temp file"),
    ("bash4-shopt", r"\bshopt\s+-s\s+(?:globstar|lastpipe|autocd|dirspell|checkjobs)\b",
     "this shopt needs bash 4", "find(1) or an explicit loop"),
    ("wait-n", r"\bwait\s+-n\b",
     "`wait -n` needs bash 4.3", "wait on each pid"),
    ("test-v", r"(?:\[\[|\[|\btest)\s+-v\s",
     "`-v var` needs bash 4.2", "`[ -n \"${var+x}\" ]`"),
    ("negative-index", r"\$\{[A-Za-z_][A-Za-z0-9_]*\[-[0-9]+\]\}",
     "negative array indexes need bash 4.3", "${arr[${#arr[@]}-1]}"),
    ("epoch-vars", r"\bEPOCH(?:SECONDS|REALTIME)\b",
     "EPOCHSECONDS/EPOCHREALTIME need bash 5", "`date +%s`"),
    ("brace-step", r"\{[0-9]+\.\.[0-9]+\.\.[0-9]+\}",
     "a step in brace expansion needs bash 4", "a counted while loop"),
    ("sed-inplace", r"\bsed\b[^|;&\n]*?\s-[a-zA-Z]*i(?:\s|$)",
     "`sed -i` takes a suffix argument on BSD and none on GNU", "`sed -i.bak ...` then remove the .bak, or a temp file"),
    ("sed-r", r"\bsed\b[^|;&\n]*?\s-[a-zA-Z]*r\b",
     "`sed -r` is GNU-only", "`sed -E`"),
    ("grep-P", r"\bgrep\b[^|;&\n]*?\s-[a-zA-Z]*P",
     "`grep -P` does not exist in BSD grep", "`grep -E`"),
    ("date-gnu", r"\bdate\b[^|;&\n]*?\s(?:-d\b|--date\b|--iso|-I\b)",
     "`date -d`/`--iso` are GNU-only", "`date +%s` arithmetic, or python"),
    ("stat-gnu", r"\bstat\b[^|;&\n]*?\s(?:-c\b|--format\b|--printf\b)",
     "`stat -c` is GNU-only (BSD uses -f)", "`wc -c <file` or python"),
    ("readlink-f", r"\breadlink\s+-[a-zA-Z]*f\b(?![^\n]*\|\|)",
     "`readlink -f` is missing on older macOS", "add `|| fallback` on the same line"),
    ("find-printf", r"\bfind\b[^|;&\n]*?\s-printf\b",
     "`find -printf` is GNU-only", "`find ... -exec` or python"),
    ("head-negative", r"\bhead\s+-[nc]\s*-[0-9]",
     "negative counts in head are GNU-only", "sed or awk"),
    ("timeout", r"(?:^|[\s;&|(])timeout\s+-?[0-9]",
     "`timeout` is not installed on macOS", "a background job and kill, or python's subprocess timeout"),
    ("gnu-checksum", r"\b(?:sha(?:1|224|256|384|512)sum|md5sum)\b",
     "sha256sum/md5sum are not on every Mac", "`shasum -a 256`, or python hashlib"),
    ("gnu-flags", r"\b(?:base64\s+-w|du\s+-[a-zA-Z]*b\b|wc\s+-L\b|ln\s+-[a-zA-Z]*r\b"
                  r"|mktemp\s+(?:-[a-zA-Z]+\s+)*(?:-p\b|--tmpdir)"
                  r"|xargs\s+(?:-[a-zA-Z]+\s+)*--no-run-if-empty|sort\s+(?:-[a-zA-Z]+\s+)*--version-sort)",
     "a GNU-only flag", "the POSIX form"),
    ("gnu-tools", r"(?:^|[\s;&|(])(?:tac|nproc|numfmt|shuf)(?:\s|$)",
     "a GNU-only tool", "awk, sed or python"),
)
_COMPILED = tuple((rid, re.compile(rx), why, fix) for rid, rx, why, fix in RULES)

# A bare interpreter in command position. The resolver itself (hooks/pyrun.sh, or a script that
# defines `python()`) is how a script is allowed to say `python`.
_BARE_PY = re.compile(r"""(?<![\w./$"'-])(?:python3?|py)(?=\s)""")
# `command -v python3` asks whether it exists; it runs nothing
_PROBE = re.compile(r"\b(?:command\s+-[vV]|which|type|hash)\s+\S+")
_PY_FUNCTION = re.compile(r"^\s*python\s*\(\)\s*\{", re.M)
_WAIVER = re.compile(r"#\s*portable:\s*(\S.*)$")
_HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    rule: str
    why: str
    fix: str
    text: str


_CODE = ("code", "cmd", "paren", "tick")


def _expansion_end(raw: str, i: int) -> int:
    """Index just past the `${...}` that starts at raw[i] (nested braces counted)."""
    depth = 0
    j = i + 1
    while j < len(raw):
        if raw[j] == "{":
            depth += 1
        elif raw[j] == "}":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return len(raw)


def _code_lines(text: str) -> list[tuple[int, str, str]]:
    """(line number, code without comments and literal text, raw line), heredoc bodies dropped.

    A context stack is carried across lines, so a multi-line `python -c "..."` body is text and
    not shell, while everything bash expands inside double quotes -- `$(...)`, `${...}`, `$name`,
    backticks -- is kept as code: `"$(date -d x)"` and `"${v,,}"` are the common forms."""
    out: list[tuple[int, str, str]] = []
    heredoc_end: str | None = None
    stack: list[str] = ["code"]
    for number, raw in enumerate(text.splitlines(), 1):
        if heredoc_end is not None:
            if raw.strip() == heredoc_end:
                heredoc_end = None
            continue
        if number == 1 and raw.startswith("#!"):
            continue
        code: list[str] = []
        comment_at = len(raw)
        i = 0
        while i < len(raw):
            ch, nxt, top = raw[i], raw[i + 1: i + 2], stack[-1]
            if top == "sq":
                if ch == "'":
                    stack.pop()
                i += 1
            elif top == "dq":
                if ch == "\\":
                    i += 2
                elif ch == '"':
                    stack.pop()
                    i += 1
                elif ch == "$" and nxt == "(":
                    stack.append("cmd")
                    code.append("$(")
                    i += 2
                elif ch == "$" and nxt == "{":
                    end = _expansion_end(raw, i + 1)
                    code.append(raw[i:end])
                    i = end
                elif ch == "$" and (nxt.isalnum() or nxt == "_"):
                    j = i + 1
                    while j < len(raw) and (raw[j].isalnum() or raw[j] == "_"):
                        j += 1
                    code.append(raw[i:j])
                    i = j
                elif ch == "`":
                    stack.append("tick")
                    i += 1
                else:
                    i += 1
            else:
                if ch == "\\":
                    code.append(raw[i:i + 2])
                    i += 2
                elif ch == "'":
                    stack.append("sq")
                    i += 1
                elif ch == '"':
                    stack.append("dq")
                    i += 1
                elif ch == "`":
                    if top == "tick":
                        stack.pop()
                    else:
                        stack.append("tick")
                    code.append(" ")
                    i += 1
                elif ch == "#" and (i == 0 or raw[i - 1].isspace() or raw[i - 1] in ";&|("):
                    comment_at = i
                    break
                elif ch == "$" and nxt == "(":
                    stack.append("cmd")
                    code.append("$(")
                    i += 2
                elif ch == "(" and top in ("cmd", "paren"):
                    stack.append("paren")
                    code.append(ch)
                    i += 1
                elif ch == ")" and top in ("cmd", "paren"):
                    stack.pop()
                    code.append(ch)
                    i += 1
                else:
                    code.append(ch)
                    i += 1
        line_code = "".join(code)
        # the delimiter is quoted (`<<'PY'`), so it is looked for on the line itself, minus comments
        match = _HEREDOC.search(raw[:comment_at])
        if match and stack[-1] in _CODE:
            heredoc_end = match.group(2)
        out.append((number, line_code, raw))
    return out


def lint_text(text: str, name: str = "<text>") -> list[Finding]:
    findings: list[Finding] = []
    lines = _code_lines(text)
    for number, code, raw in lines:
        waiver = _WAIVER.search(raw)
        if waiver and waiver.group(1).strip():
            continue
        for rid, rx, why, fix in _COMPILED:
            if rx.search(code):
                findings.append(Finding(name, number, rid, why, fix, raw.strip()))
    if not _PY_FUNCTION.search(text) and Path(name).name != "pyrun.sh":
        for number, code, raw in lines:
            waiver = _WAIVER.search(raw)
            if waiver and waiver.group(1).strip():
                continue
            if _BARE_PY.search(_PROBE.sub(" ", code)):
                findings.append(Finding(
                    name, number, "bare-python",
                    "a stock Mac has `python3` and no `python`; Windows may have only the Store stub",
                    "resolve the interpreter first (the order of hooks/pyrun.sh) and call it"
                    " through a variable or a `python()` function",
                    raw.strip()))
    return findings


def discover(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix == ".sh":
            files.append(path)
        elif path.is_dir():
            files.extend(p for p in sorted(path.rglob("*.sh")) if ".git" not in p.parts)
    return files


class MissingModules(ValueError):
    """`marketplace.json` declares modules this copy does not carry: an incomplete distribution."""


def module_dirs(root: Path) -> list[Path]:
    """The shipped modules, as `marketplace.json` declares them (the emitted copy only).

    No `marketplace.json` is the source tree: an empty list, which callers say out loud. A declared
    module whose directory is missing raises instead of being dropped -- dropped, the checkers ran
    on the modules that were left and passed, and with every module missing they passed on nothing.
    """
    marketplace = root / "marketplace.json"
    if not marketplace.is_file():
        return []
    data = json.loads(marketplace.read_text(encoding="utf-8"))
    plugins = data.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        raise MissingModules(f"{marketplace} declares no module")
    dirs, missing = [], []
    for plugin in plugins:
        source = str(plugin.get("source", "")).removeprefix("./") if isinstance(plugin, dict) else ""
        if source and (root / source).is_dir():
            dirs.append(root / source)
        else:
            name = plugin.get("name", "?") if isinstance(plugin, dict) else "?"
            missing.append(f"{name} ({source or 'no source'})")
    if missing:
        raise MissingModules(f"marketplace.json declares module(s) this copy does not carry: {', '.join(missing)}")
    return dirs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        targets = args.paths or module_dirs(ROOT)
    except MissingModules as exc:
        print(f"shell_portability: {exc}", file=sys.stderr)
        return 3
    if not targets:
        print("shell_portability: no marketplace.json here (source tree) and no path given: nothing to scan")
        return 0
    files = discover(targets)
    findings = [f for path in files for f in lint_text(path.read_text(encoding="utf-8"), str(path))]
    if args.json:
        print(json.dumps({"files": len(files), "findings": [asdict(f) for f in findings]}, indent=2))
    else:
        for f in findings:
            print(f"{f.file}:{f.line}: [{f.rule}] {f.why} -> {f.fix}\n    {f.text}")
        print(f"shell_portability: {len(files)} file(s), {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
