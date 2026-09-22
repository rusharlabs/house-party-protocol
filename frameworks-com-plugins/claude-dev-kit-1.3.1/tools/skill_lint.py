#!/usr/bin/env python3
"""
skill_lint — automatic enforcement of the SKILL-CONTRACT (see docs/SKILL-CONTRACT.md of this kit).
Vendorized copy — every kit of this marketplace is self-contained (C5 of the contract itself).

Implements the checks L1a-L6, mapped 1:1 to the 6 clauses C1-C6. Runs against a single SKILL.md
or a folder of skills (--all). Fixes nothing — it only points (read-only), the same principle as
the cross-model CHECKER of the loop-maker-checker rule.

Usage:
    python tools/skill_lint.py <skill.md or skill-dir>
    python tools/skill_lint.py --all <skills-dir> [--json out.json] [--run-proofs]
    python tools/skill_lint.py --self-test

Exit: 0 PASS (zero FAIL) · 1 WARNs only · 2 >=1 FAIL.
C5 adjustment: ${CLAUDE_PLUGIN_ROOT}/... is a VALID reference. FAIL only on a raw relative path
(operator-kit/scripts/..., operator-kit/_lib/..., a loose _lib/...) without that anchor.

Schema tokens — English is CANONICAL, Portuguese is ACCEPTED LEGACY (since 2026-09-21):
    ## When NOT to Activate     (legacy: ## Quando NÃO Ativar)
    ## Contract                 (legacy: ## Contrato)
    ## Proof                    (legacy: ## Prova)
    > **Priority:**             (legacy: > **Prioridade:**)
    **INPUT:** / **OUTPUT:** / **EXIT CODES** / **STATE IT TOUCHES:**
                                (legacy: **ENTRADA:** / **SAÍDA:** / **EXIT CODES** / **ESTADO QUE TOCA:**)
    exit-0 row word `always`    (legacy: `sempre`)
    <!-- executed: DATE · exit=N -->   (legacy: <!-- executado: DATE · exit=N -->)
Every check accepts EITHER form on its own, so a file that mixes forms lints exactly like a
pure one — the contract is structural (the section/field exists with the right content); the
language of the token is not a clause, and a WARN here would turn a cosmetic state into an
exit-1 gate for the whole `--all` run. Finding ids (rule_id) are unchanged: they are the
checker's output contract; only the messages moved to English.

stdlib only. v1.1.0 — 2026-09-21 (English canonical schema · Windows proof runner fix)
v1.0.0 — 2026-07-10 (claude-dev-kit · vendorized from kit-forge)
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# (canonical, *legacy) per header field; rule ids stay as they were in v1.0.0.
_HEADER_FIELDS = (
    ("L1b.auto-trigger", ("Auto-Trigger",)),
    ("L1b.keywords", ("Keywords",)),
    ("L1b.prioridade", ("Priority", "Prioridade")),
    ("L1b.tools", ("Tools",)),
)
_SECTION_WHEN_NOT = ("When NOT to Activate", "Quando NÃO Ativar")
_SECTION_CONTRACT = ("Contract", "Contrato")
_SECTION_PROOF = ("Proof", "Prova")
# (rule id, canonical needle, legacy needle) — matched case-insensitively inside the Contract section.
_CONTRACT_NEEDLES = (
    ("L2b.entrada", "INPUT", "ENTRADA"),
    ("L2c.saida", "OUTPUT", "SAÍDA"),
    ("L2d.exit_codes", "EXIT CODES", None),
    ("L2e.estado", "STATE IT TOUCHES", "ESTADO QUE TOCA"),
)
_EXEC_MARKER_RE = re.compile(r"<!--\s*(?:executed|executado):\s*(\d{4}-\d{2}-\d{2})[^>]*exit=(-?\d+)[^>]*-->")
_ALWAYS_ZERO_ROW_RE = re.compile(r"\|\s*`?0`?\s*\|[^|\n]*\b(?:always|sempre)\b", re.IGNORECASE)
_WIKILINK_RE = re.compile(r"\[\[[^\]]+\]\]")
_PY_LAUNCHER_RE = re.compile(r"(?<![\w.\-])py\s+[\w./\\\-]+\.py\b")
_SCHEDULEWAKEUP_RE = re.compile(r"ScheduleWakeup")
_SCHEDULEWAKEUP_QUALIFIER_RE = re.compile(r"optional|opcional|fallback|exclusiv", re.IGNORECASE)
_BROKEN_PATH_RE = re.compile(r"operator-kit/(scripts|_lib)/[\w./\-]*|(?<![\w/\-])_lib/[\w.\-]+\.py\b")
_FENCE_RE = re.compile(r"```")
_PLUGIN_ROOT_TOKEN = "${CLAUDE_PLUGIN_ROOT}"


def _finding(rule_id: str, severity: str, message: str) -> dict:
    return {"rule_id": rule_id, "severity": severity, "message": message}


def _section(text: str, headers: tuple | str) -> str | None:
    """Extract the body of a '## header' section (any of the accepted spellings) up to the next
    '## ' or the end of the file."""
    if isinstance(headers, str):
        headers = (headers,)
    alternation = "|".join(re.escape(h) for h in headers)
    pattern = re.compile(rf"^##\s+(?:{alternation})\s*$", re.MULTILINE)
    m = pattern.search(text)
    if not m:
        return None
    start = m.end()
    nxt = re.search(r"^##\s+", text[start:], re.MULTILINE)
    return text[start : start + nxt.start()] if nxt else text[start:]


def lint_text(text: str, skill_path: str = "<inline>") -> list:
    findings = []

    # C1 · HEADER
    front_m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not front_m:
        findings.append(_finding("L1a.frontmatter", "fail", "frontmatter --- name/description --- missing"))
    else:
        fm = front_m.group(1)
        if "name:" not in fm:
            findings.append(_finding("L1a.name", "fail", "frontmatter without 'name:'"))
        if "description:" not in fm:
            findings.append(_finding("L1a.description", "fail", "frontmatter without 'description:'"))

    header_zone = text[:3000]
    for rule_id, names in _HEADER_FIELDS:
        alternation = "|".join(re.escape(n) for n in names)
        if not re.search(rf">\s*\*\*(?:{alternation}):\*\*", header_zone):
            findings.append(_finding(rule_id, "fail", f"header without line '> **{names[0]}:**'" + (f" (legacy '{names[1]}')" if len(names) > 1 else "")))

    kw_m = re.search(r">\s*\*\*Keywords:\*\*\s*(.+)", header_zone)
    if kw_m:
        keywords = [k for k in re.split(r",", kw_m.group(1)) if k.strip()]
        if len(keywords) < 4:
            findings.append(_finding("L1c.keywords_min4", "fail", f"Keywords has {len(keywords)} < 4"))

    when_not = _section(text, _SECTION_WHEN_NOT)
    if when_not is None:
        findings.append(_finding("L1d.quando_nao_ativar", "fail", f"section '## {_SECTION_WHEN_NOT[0]}' (legacy '## {_SECTION_WHEN_NOT[1]}') missing"))
    else:
        bullets = [ln for ln in when_not.splitlines() if re.match(r"^\s*[-*]\s+\S", ln)]
        if len(bullets) < 2:
            findings.append(_finding("L1d.quando_nao_ativar_min2", "fail", f"'{_SECTION_WHEN_NOT[0]}' has {len(bullets)} bullet(s) < 2"))

    if _WIKILINK_RE.search(text):
        findings.append(_finding("L1e.wikilink", "fail", "wikilink [[...]] present (staging contamination)"))

    # C2 · I/O CONTRACT
    contract = _section(text, _SECTION_CONTRACT)
    if contract is None:
        findings.append(_finding("L2a.contrato_ausente", "fail", f"section '## {_SECTION_CONTRACT[0]}' (legacy '## {_SECTION_CONTRACT[1]}') missing"))
    else:
        upper = contract.upper()
        for rule_id, canonical, legacy in _CONTRACT_NEEDLES:
            if canonical not in upper and not (legacy and legacy in upper):
                findings.append(_finding(rule_id, "fail", f"Contract without '{canonical}'" + (f" (legacy '{legacy}')" if legacy else "")))

    # C3 · >=3 EXECUTED EXAMPLES
    markers = _EXEC_MARKER_RE.findall(text)
    if len(markers) < 3:
        findings.append(_finding("L3a.exemplos_min3", "fail", f"{len(markers)} executed example(s) < 3"))
    # single-exit-code contract (e.g. connectors "exit 0 always"): the EXIT CODES table of the
    # Contract documents EXPLICITLY that only exit 0 exists — demanding a failure example would
    # force a fake failure against the honest design of the mechanism itself.
    always_zero_contract = bool(_ALWAYS_ZERO_ROW_RE.search(contract or ""))
    if markers and not any(int(exit_code) != 0 for _, exit_code in markers) and not always_zero_contract:
        findings.append(_finding("L3b.exemplo_falha", "fail", "no FAILURE example (exit != 0)"))
    today = datetime.date.today()
    for date_str, _ in markers:
        try:
            d = datetime.date.fromisoformat(date_str)
            if (today - d).days > 90:
                findings.append(_finding("L3c.exemplo_expirado", "warn", f"example from {date_str} is older than 90 days"))
        except ValueError:
            findings.append(_finding("L3c.data_invalida", "warn", f"invalid example date: {date_str}"))

    # C4 · PROOF
    proof = _section(text, _SECTION_PROOF)
    if proof is None:
        findings.append(_finding("L4a.prova_ausente", "fail", f"section '## {_SECTION_PROOF[0]}' (legacy '## {_SECTION_PROOF[1]}') missing"))
    elif not _FENCE_RE.search(proof):
        findings.append(_finding("L4b.prova_sem_comando", "fail", f"section '{_SECTION_PROOF[0]}' without a code block with a command"))

    # C5 · PORTABILITY
    if _PY_LAUNCHER_RE.search(text):
        findings.append(_finding("L5a.py_launcher", "fail", "launcher 'py <script>.py' is Windows-only (forbidden)"))
    schedulewakeup_matches = list(_SCHEDULEWAKEUP_RE.finditer(text))
    if schedulewakeup_matches:
        unqualified = []
        for m in schedulewakeup_matches:
            window = text[max(0, m.start() - 400) : m.end() + 400]
            if not _SCHEDULEWAKEUP_QUALIFIER_RE.search(window):
                unqualified.append(m.start())
        if unqualified:
            findings.append(_finding("L5b.schedulewakeup", "fail", "ScheduleWakeup cited as a dependency without 'optional/fallback/exclusive' nearby (it is exclusive to the /loop main-loop)"))
    for m in _BROKEN_PATH_RE.finditer(text):
        window_start = max(0, m.start() - 25)
        preceding = text[window_start : m.start()]
        if _PLUGIN_ROOT_TOKEN not in preceding:
            findings.append(_finding("L5c.path_relativo_cru", "fail", f"reference without anchor: {m.group(0)!r}"))

    # C6 · EXECUTABLE BODY (heuristic: fences outside Contract/Proof)
    total_fences = len(_FENCE_RE.findall(text)) // 2
    if total_fences < 2:
        findings.append(_finding("L6a.corpo_sem_comando", "warn", f"only {total_fences} code block(s) in the body — may be prose without a literal command"))

    return findings


def lint_file(path: Path) -> dict:
    skill_md = path / "SKILL.md" if path.is_dir() else path
    if not skill_md.exists():
        return {"skill": str(path), "status": "error", "findings": [_finding("L0.missing", "fail", f"SKILL.md not found at {path}")]}
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    findings = lint_text(text, str(skill_md))
    fails = [f for f in findings if f["severity"] == "fail"]
    status = "fail" if fails else ("warn" if findings else "pass")
    return {"skill": str(skill_md), "status": status, "findings": findings}


def strip_trailing_comment(cmd: str) -> str:
    """Drop a trailing `# ...` shell comment, honouring quotes and backslash escapes.

    # Why: `--run-proofs` runs the proof line through the platform shell, and cmd.exe has no
    # `#` comments — a trailing `# -> self-test OK · exit 0` made the `>` a redirect and left a
    # 0-byte file named `self-test` inside the skill directory. A `#` inside quotes
    # (python -c "print('#')") is data, not a comment.
    """
    quote: str | None = None
    i = 0
    while i < len(cmd):
        ch = cmd[i]
        if quote:
            if ch == "\\" and quote == '"':
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch == "\\":
            i += 2
            continue
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "#" and (i == 0 or cmd[i - 1].isspace()):
            return cmd[:i].rstrip()
        i += 1
    return cmd


def expand_plugin_root(cmd: str, module_root: Path) -> str:
    """Replace `${CLAUDE_PLUGIN_ROOT}` with the skill's module root, the way a POSIX shell would
    see it: not inside single quotes; bare inside double quotes; wrapped in double quotes when
    unquoted, so a root containing spaces stays one argument on both cmd.exe and bash.

    # Why: cmd.exe does not expand `${VAR}`, so every proof anchored on `${CLAUDE_PLUGIN_ROOT}`
    # (the anchor C5 REQUIRES) exited 2 with "No such file or directory" on Windows while
    # passing on macOS/Linux.
    """
    root = module_root.resolve().as_posix()
    out: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(cmd):
        if cmd.startswith(_PLUGIN_ROOT_TOKEN, i) and quote != "'":
            out.append(root if quote == '"' else f'"{root}"')
            i += len(_PLUGIN_ROOT_TOKEN)
            continue
        ch = cmd[i]
        if quote:
            if ch == "\\" and quote == '"':
                out.append(cmd[i : i + 2])
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch == "\\":
            out.append(cmd[i : i + 2])
            i += 2
            continue
        elif ch in ("'", '"'):
            quote = ch
        out.append(ch)
        i += 1
    return "".join(out)


def module_root_of(skill_dir: Path) -> Path:
    """`<module>/skills/<skill>/` -> `<module>`; any other layout -> the skill dir itself."""
    return skill_dir.parent.parent if skill_dir.parent.name == "skills" else skill_dir


def run_proof(path: Path, timeout: int = 30) -> dict:
    skill_md = path / "SKILL.md" if path.is_dir() else path
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    proof = _section(text, _SECTION_PROOF)
    if proof is None:
        return {"ran": False, "reason": "no Proof section"}
    m = re.search(r"```(?:bash|sh|console)?\n(.*?)```", proof, re.DOTALL)
    if not m:
        return {"ran": False, "reason": "no code block in the Proof section"}
    cmd = m.group(1).strip().splitlines()[0]
    module_root = module_root_of(skill_md.parent)
    executed = expand_plugin_root(strip_trailing_comment(cmd), module_root)
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(module_root.resolve()))
    try:
        proc = subprocess.run(executed, shell=True, cwd=str(skill_md.parent), capture_output=True, text=True, timeout=timeout, env=env)
        return {"ran": True, "cmd": cmd, "executed": executed, "exit_code": proc.returncode, "tail": (proc.stdout + proc.stderr)[-300:]}
    except subprocess.TimeoutExpired:
        return {"ran": True, "cmd": cmd, "executed": executed, "exit_code": 124, "tail": f"timeout {timeout}s"}
    except Exception as e:  # noqa: BLE001
        return {"ran": True, "cmd": cmd, "executed": executed, "exit_code": 1, "tail": str(e)}


_COMPLIANT_FIXTURE = """---
name: fixture-compliant
description: Fixture skill 100% conformant to the SKILL-CONTRACT, used by the skill_lint self-test.
---

> **Auto-Trigger:** when the skill_lint self-test runs.
> **Keywords:** "fixture", "compliant", "self-test", "skill-lint"
> **Priority:** LOW
> **Tools:** Read

## When NOT to Activate
- Outside the skill_lint self-test.
- If the neighbouring skill `fixture-violator` already covers the case.

## Contract
**INPUT:** none.
**OUTPUT:** fixed string "ok".

**EXIT CODES:**
| Exit | Meaning |
|---|---|
| 0 | ok |
| 1 | never happens |
| 2 | never happens |

**STATE IT TOUCHES:**
| File | Reads/Writes | Purpose |
|---|---|---|
| (none) | - | pure fixture |

## Executed examples
```console
$ python -c "print('ok')"
ok
```
<!-- executed: 2026-07-10 · exit=0 -->

```console
$ python -c "import sys; sys.exit(1)"
```
<!-- executed: 2026-07-10 · exit=1 -->

```console
$ python -c "print('ok again')"
ok again
```
<!-- executed: 2026-07-10 · exit=0 -->

## Proof
```bash
python -c "print('ok')"   # -> self-test OK · exit 0
```
"""

# The same fixture spelled with every legacy (Portuguese) token — the control that proves the
# lint keeps accepting skills written before 2026-09-21. Built by substitution so the two
# fixtures cannot drift structurally.
_LEGACY_TOKEN_MAP = (
    ("## When NOT to Activate", "## Quando NÃO Ativar"),
    ("## Contract", "## Contrato"),
    ("## Proof", "## Prova"),
    ("> **Priority:** LOW", "> **Prioridade:** BAIXA"),
    ("**INPUT:**", "**ENTRADA:**"),
    ("**OUTPUT:**", "**SAÍDA:**"),
    ("**STATE IT TOUCHES:**", "**ESTADO QUE TOCA:**"),
    ("<!-- executed:", "<!-- executado:"),
)


def legacy_fixture() -> str:
    text = _COMPLIANT_FIXTURE
    for canonical, legacy in _LEGACY_TOKEN_MAP:
        text = text.replace(canonical, legacy)
    return text


_VIOLATOR_FIXTURE = """# fixture-violator

A skill without frontmatter, without header, without contract, without examples, without proof,
using [[some-wikilink]] and `py script.py` as launcher, depending on
ScheduleWakeup and referencing operator-kit/scripts/thing.py without any anchor.
"""


def _self_test() -> int:
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="skill_lint_selftest_"))
    try:
        compliant_dir = tmp / "fixture-compliant"
        compliant_dir.mkdir()
        (compliant_dir / "SKILL.md").write_text(_COMPLIANT_FIXTURE, encoding="utf-8")

        legacy_dir = tmp / "fixture-legacy"
        legacy_dir.mkdir()
        legacy_text = legacy_fixture()
        assert legacy_text != _COMPLIANT_FIXTURE and "## Contrato" in legacy_text
        (legacy_dir / "SKILL.md").write_text(legacy_text, encoding="utf-8")

        violator_dir = tmp / "fixture-violator"
        violator_dir.mkdir()
        (violator_dir / "SKILL.md").write_text(_VIOLATOR_FIXTURE, encoding="utf-8")

        report_ok = lint_file(compliant_dir)
        assert report_ok["status"] == "pass", f"compliant fixture (English tokens) should PASS: {report_ok['findings']}"

        report_legacy = lint_file(legacy_dir)
        assert report_legacy["status"] == "pass", f"legacy fixture (Portuguese tokens) should PASS: {report_legacy['findings']}"

        report_bad = lint_file(violator_dir)
        assert report_bad["status"] == "fail", f"violator fixture should FAIL: {report_bad}"
        fail_ids = {f["rule_id"] for f in report_bad["findings"] if f["severity"] == "fail"}
        for expected in ("L1a.frontmatter", "L5a.py_launcher", "L5b.schedulewakeup", "L5c.path_relativo_cru", "L1e.wikilink"):
            assert expected in fail_ids, f"expected {expected} in the violator findings: {sorted(fail_ids)}"

        anchored = compliant_dir.parent / "fixture-anchored"
        anchored.mkdir()
        anchored_text = _COMPLIANT_FIXTURE.replace(
            "## Proof", "Valid reference: ${CLAUDE_PLUGIN_ROOT}/operator-kit/scripts/x.py\n\n## Proof"
        )
        (anchored / "SKILL.md").write_text(anchored_text, encoding="utf-8")
        report_anchored = lint_file(anchored)
        anchored_fail_ids = {f["rule_id"] for f in report_anchored["findings"] if f["severity"] == "fail"}
        assert "L5c.path_relativo_cru" not in anchored_fail_ids, f"path with \\${{CLAUDE_PLUGIN_ROOT}} should be accepted: {report_anchored['findings']}"

        proof = run_proof(compliant_dir)
        assert proof["ran"] and proof["exit_code"] == 0, f"proof should run and exit 0: {proof}"
        assert not (compliant_dir / "self-test").exists(), "the trailing '# -> self-test OK' comment must not become a redirect"
        assert strip_trailing_comment("python -c \"print('#')\" # note") == "python -c \"print('#')\"", "a # inside quotes is data"
        assert expand_plugin_root("python ${CLAUDE_PLUGIN_ROOT}/x.py", Path("/a b")).startswith('python "'), "unquoted root gets quoted"

        print("self-test OK — fixture compliant(EN)=PASS, legacy(PT)=PASS, violator=FAIL (5 rules hit), ${CLAUDE_PLUGIN_ROOT} accepted, run-proof exit 0 and no stray file")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="skill_lint.py")
    p.add_argument("target", nargs="?")
    p.add_argument("--all", dest="all_dir", default=None)
    p.add_argument("--json", dest="json_out", default=None)
    p.add_argument("--run-proofs", action="store_true")
    p.add_argument("--self-test", action="store_true")
    return p


def main(argv) -> int:
    args = build_parser().parse_args(argv)

    if args.self_test:
        return _self_test()

    if args.all_dir:
        base = Path(args.all_dir)
        if not base.is_dir():
            print(f"skill_lint: folder does not exist: {base}", file=sys.stderr)
            return 3
        reports = []
        for skill_dir in sorted(p for p in base.iterdir() if p.is_dir()):
            r = lint_file(skill_dir)
            if args.run_proofs and r["status"] != "error":
                r["proof"] = run_proof(skill_dir)
            reports.append(r)
    elif args.target:
        reports = [lint_file(Path(args.target))]
        if args.run_proofs:
            reports[0]["proof"] = run_proof(Path(args.target))
    else:
        print("usage: skill_lint.py <skill.md|dir> OR --all <skills-dir> [--run-proofs] [--json out.json]", file=sys.stderr)
        return 3

    fail_count = sum(1 for r in reports if r["status"] == "fail")
    warn_count = sum(1 for r in reports if r["status"] == "warn")
    summary = {"total": len(reports), "fail": fail_count, "warn": warn_count, "pass": len(reports) - fail_count - warn_count, "reports": reports}

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in reports:
        marker = {"pass": "PASS", "warn": "WARN", "fail": "FAIL", "error": "ERROR"}[r["status"]]
        print(f"[{marker}] {r['skill']}")
        for f in r["findings"]:
            print(f"    {f['severity'].upper():<4} {f['rule_id']:<28} {f['message']}")
        # Why: proofs used to run and land ONLY in --json; a proof exiting 2 on every Windows
        # machine went unseen for months. Informational — it does not
        # change the status, the summary line nor the exit code (--run-proofs semantics kept).
        proof = r.get("proof")
        if proof is not None:
            if proof.get("ran"):
                print(f"    PROOF exit={proof['exit_code']:<3} {proof['cmd']}")
            else:
                print(f"    PROOF not run: {proof.get('reason')}")
    print(f"\nskill_lint: {summary['pass']} pass · {summary['warn']} warn · {summary['fail']} fail (of {summary['total']})")

    if fail_count:
        return 2
    if warn_count:
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
