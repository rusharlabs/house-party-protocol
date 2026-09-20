#!/usr/bin/env python3
"""
skill_lint — enforcement automático do SKILL-CONTRACT (ver docs/SKILL-CONTRACT.md deste kit).
Cópia vendorizada — cada kit deste marketplace é self-contained (C5 do próprio contrato).

Implementa os checks L1a-L6, mapeados 1:1 às 6 cláusulas C1-C6. Roda contra um SKILL.md
único ou uma pasta de skills (--all). Não corrige nada — só aponta (read-only), o mesmo
princípio do CHECKER cross-model do loop-maker-checker.

Uso:
    python tools/skill_lint.py <skill.md ou skill-dir>
    python tools/skill_lint.py --all <dir-de-skills> [--json out.json] [--run-proofs]
    python tools/skill_lint.py --self-test

Exit: 0 PASS (zero FAIL) · 1 só WARNs · 2 >=1 FAIL.
Ajuste C5: ${CLAUDE_PLUGIN_ROOT}/... é referência VÁLIDA. FAIL só em path relativo cru
(operator-kit/scripts/..., operator-kit/_lib/..., _lib/... solto) sem essa âncora.

stdlib only. v1.0.0 — 2026-07-10 (claude-dev-kit · vendorizado do kit-forge)
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

_HEADER_FIELDS = ["Auto-Trigger", "Keywords", "Prioridade", "Tools"]
_EXEC_MARKER_RE = re.compile(r"<!--\s*executado:\s*(\d{4}-\d{2}-\d{2})[^>]*exit=(-?\d+)[^>]*-->")
_WIKILINK_RE = re.compile(r"\[\[[^\]]+\]\]")
_PY_LAUNCHER_RE = re.compile(r"(?<![\w.\-])py\s+[\w./\\\-]+\.py\b")
_SCHEDULEWAKEUP_RE = re.compile(r"ScheduleWakeup")
_SCHEDULEWAKEUP_QUALIFIER_RE = re.compile(r"opcional|fallback|exclusiv", re.IGNORECASE)
_BROKEN_PATH_RE = re.compile(r"operator-kit/(scripts|_lib)/[\w./\-]*|(?<![\w/\-])_lib/[\w.\-]+\.py\b")
_FENCE_RE = re.compile(r"```")


def _finding(rule_id: str, severity: str, message: str) -> dict:
    return {"rule_id": rule_id, "severity": severity, "message": message}


def _section(text: str, header: str) -> str | None:
    """Extrai o conteúdo de uma seção '## header' até o próximo '## ' ou fim do arquivo."""
    pattern = re.compile(rf"^##\s+{re.escape(header)}\s*$", re.MULTILINE)
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
        findings.append(_finding("L1a.frontmatter", "fail", "frontmatter --- name/description --- ausente"))
    else:
        fm = front_m.group(1)
        if "name:" not in fm:
            findings.append(_finding("L1a.name", "fail", "frontmatter sem 'name:'"))
        if "description:" not in fm:
            findings.append(_finding("L1a.description", "fail", "frontmatter sem 'description:'"))

    header_zone = text[:3000]
    for field in _HEADER_FIELDS:
        if not re.search(rf">\s*\*\*{re.escape(field)}:\*\*", header_zone):
            findings.append(_finding(f"L1b.{field.lower()}", "fail", f"header sem linha '> **{field}:**'"))

    kw_m = re.search(r">\s*\*\*Keywords:\*\*\s*(.+)", header_zone)
    if kw_m:
        keywords = [k for k in re.split(r",", kw_m.group(1)) if k.strip()]
        if len(keywords) < 4:
            findings.append(_finding("L1c.keywords_min4", "fail", f"Keywords tem {len(keywords)} < 4"))

    quando_nao = _section(text, "Quando NÃO Ativar")
    if quando_nao is None:
        findings.append(_finding("L1d.quando_nao_ativar", "fail", "seção '## Quando NÃO Ativar' ausente"))
    else:
        bullets = [ln for ln in quando_nao.splitlines() if re.match(r"^\s*[-*]\s+\S", ln)]
        if len(bullets) < 2:
            findings.append(_finding("L1d.quando_nao_ativar_min2", "fail", f"'Quando NÃO Ativar' tem {len(bullets)} bullet(s) < 2"))

    if _WIKILINK_RE.search(text):
        findings.append(_finding("L1e.wikilink", "fail", "wikilink [[...]] presente (contaminação de staging)"))

    # C2 · CONTRATO DE I/O
    contrato = _section(text, "Contrato")
    if contrato is None:
        findings.append(_finding("L2a.contrato_ausente", "fail", "seção '## Contrato' ausente"))
    else:
        for needle, rule in (("ENTRADA", "L2b.entrada"), ("SAÍDA", "L2c.saida"), ("EXIT CODES", "L2d.exit_codes"), ("ESTADO QUE TOCA", "L2e.estado")):
            if needle not in contrato.upper():
                findings.append(_finding(rule, "fail", f"Contrato sem '{needle}'"))

    # C3 · >=3 EXEMPLOS EXECUTADOS
    markers = _EXEC_MARKER_RE.findall(text)
    if len(markers) < 3:
        findings.append(_finding("L3a.exemplos_min3", "fail", f"{len(markers)} exemplo(s) executado(s) < 3"))
    # single-exit-code-contract (ex.: connectors "exit 0 sempre"): a tabela EXIT CODES do
    # Contrato documenta EXPLICITAMENTE que só existe exit 0 — cobrar exemplo de falha
    # forçaria uma fake failure contra o próprio design honesto do mecanismo.
    always_zero_contract = bool(re.search(r"\|\s*0\s*\|[^|\n]*sempre", contrato or "", re.IGNORECASE))
    if markers and not any(int(exit_code) != 0 for _, exit_code in markers) and not always_zero_contract:
        findings.append(_finding("L3b.exemplo_falha", "fail", "nenhum exemplo de FALHA (exit != 0)"))
    today = datetime.date.today()
    for date_str, _ in markers:
        try:
            d = datetime.date.fromisoformat(date_str)
            if (today - d).days > 90:
                findings.append(_finding("L3c.exemplo_expirado", "warn", f"exemplo de {date_str} tem mais de 90 dias"))
        except ValueError:
            findings.append(_finding("L3c.data_invalida", "warn", f"data de exemplo inválida: {date_str}"))

    # C4 · PROVA
    prova = _section(text, "Prova")
    if prova is None:
        findings.append(_finding("L4a.prova_ausente", "fail", "seção '## Prova' ausente"))
    elif not _FENCE_RE.search(prova):
        findings.append(_finding("L4b.prova_sem_comando", "fail", "seção 'Prova' sem bloco de código com comando"))

    # C5 · PORTABILIDADE
    if _PY_LAUNCHER_RE.search(text):
        findings.append(_finding("L5a.py_launcher", "fail", "launcher 'py <script>.py' é Windows-only (proibido)"))
    schedulewakeup_matches = list(_SCHEDULEWAKEUP_RE.finditer(text))
    if schedulewakeup_matches:
        unqualified = []
        for m in schedulewakeup_matches:
            window = text[max(0, m.start() - 400) : m.end() + 400]
            if not _SCHEDULEWAKEUP_QUALIFIER_RE.search(window):
                unqualified.append(m.start())
        if unqualified:
            findings.append(_finding("L5b.schedulewakeup", "fail", "ScheduleWakeup citado como dependência sem qualificar 'opcional/fallback/exclusiva' por perto (exclusiva do main-loop /loop)"))
    for m in _BROKEN_PATH_RE.finditer(text):
        window_start = max(0, m.start() - 25)
        preceding = text[window_start : m.start()]
        if "${CLAUDE_PLUGIN_ROOT}" not in preceding:
            findings.append(_finding("L5c.path_relativo_cru", "fail", f"referência sem âncora: {m.group(0)!r}"))

    # C6 · CORPO EXECUTÁVEL (heurística: fences fora de Contrato/Prova)
    total_fences = len(_FENCE_RE.findall(text)) // 2
    if total_fences < 2:
        findings.append(_finding("L6a.corpo_sem_comando", "warn", f"apenas {total_fences} bloco(s) de código no corpo — pode ser prosa sem comando literal"))

    return findings


def lint_file(path: Path) -> dict:
    skill_md = path / "SKILL.md" if path.is_dir() else path
    if not skill_md.exists():
        return {"skill": str(path), "status": "error", "findings": [_finding("L0.missing", "fail", f"SKILL.md não encontrado em {path}")]}
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    findings = lint_text(text, str(skill_md))
    fails = [f for f in findings if f["severity"] == "fail"]
    status = "fail" if fails else ("warn" if findings else "pass")
    return {"skill": str(skill_md), "status": status, "findings": findings}


def run_proof(path: Path, timeout: int = 30) -> dict:
    skill_md = path / "SKILL.md" if path.is_dir() else path
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    prova = _section(text, "Prova")
    if prova is None:
        return {"ran": False, "reason": "sem seção Prova"}
    m = re.search(r"```(?:bash|sh|console)?\n(.*?)```", prova, re.DOTALL)
    if not m:
        return {"ran": False, "reason": "sem bloco de código na Prova"}
    cmd = m.group(1).strip().splitlines()[0]
    try:
        proc = subprocess.run(cmd, shell=True, cwd=str(skill_md.parent), capture_output=True, text=True, timeout=timeout)
        return {"ran": True, "cmd": cmd, "exit_code": proc.returncode, "tail": (proc.stdout + proc.stderr)[-300:]}
    except subprocess.TimeoutExpired:
        return {"ran": True, "cmd": cmd, "exit_code": 124, "tail": f"timeout {timeout}s"}
    except Exception as e:  # noqa: BLE001
        return {"ran": True, "cmd": cmd, "exit_code": 1, "tail": str(e)}


_COMPLIANT_FIXTURE = """---
name: fixture-compliant
description: Skill de fixture 100% conforme ao SKILL-CONTRACT, usada pelo self-test do skill_lint.
---

> **Auto-Trigger:** ao rodar o self-test do skill_lint.
> **Keywords:** "fixture", "compliant", "self-test", "skill-lint"
> **Prioridade:** BAIXA
> **Tools:** Read

## Quando NÃO Ativar
- Fora do self-test do skill_lint.
- Se a skill vizinha `fixture-violator` já cobre o caso.

## Contrato
ENTRADA: nenhuma.
SAÍDA: string fixa "ok".

EXIT CODES:
| Exit | Significado |
|---|---|
| 0 | ok |
| 1 | nunca ocorre |
| 2 | nunca ocorre |

ESTADO QUE TOCA:
| Arquivo | Lê/Escreve | Propósito |
|---|---|---|
| (nenhum) | - | fixture pura |

## Exemplos executados
```console
$ python -c "print('ok')"
ok
```
<!-- executado: 2026-07-10 · exit=0 -->

```console
$ python -c "import sys; sys.exit(1)"
```
<!-- executado: 2026-07-10 · exit=1 -->

```console
$ python -c "print('ok de novo')"
ok de novo
```
<!-- executado: 2026-07-10 · exit=0 -->

## Prova
```bash
python -c "print('ok')"
```
"""

_VIOLATOR_FIXTURE = """# fixture-violator

Uma skill sem frontmatter, sem header, sem contrato, sem exemplos, sem prova,
usando [[algum-wikilink]] e `py script.py` como launcher, dependendo de
ScheduleWakeup e referenciando operator-kit/scripts/coisa.py sem âncora nenhuma.
"""


def _self_test() -> int:
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="skill_lint_selftest_"))
    try:
        compliant_dir = tmp / "fixture-compliant"
        compliant_dir.mkdir()
        (compliant_dir / "SKILL.md").write_text(_COMPLIANT_FIXTURE, encoding="utf-8")

        violator_dir = tmp / "fixture-violator"
        violator_dir.mkdir()
        (violator_dir / "SKILL.md").write_text(_VIOLATOR_FIXTURE, encoding="utf-8")

        report_ok = lint_file(compliant_dir)
        assert report_ok["status"] == "pass", f"fixture compliant deveria PASS: {report_ok['findings']}"

        report_bad = lint_file(violator_dir)
        assert report_bad["status"] == "fail", f"fixture violator deveria FAIL: {report_bad}"
        fail_ids = {f["rule_id"] for f in report_bad["findings"] if f["severity"] == "fail"}
        for expected in ("L1a.frontmatter", "L5a.py_launcher", "L5b.schedulewakeup", "L5c.path_relativo_cru", "L1e.wikilink"):
            assert expected in fail_ids, f"esperava {expected} nos findings do violator: {sorted(fail_ids)}"

        anchored = compliant_dir.parent / "fixture-anchored"
        anchored.mkdir()
        anchored_text = _COMPLIANT_FIXTURE.replace(
            "## Prova", "Referência válida: ${CLAUDE_PLUGIN_ROOT}/operator-kit/scripts/x.py\n\n## Prova"
        )
        (anchored / "SKILL.md").write_text(anchored_text, encoding="utf-8")
        report_anchored = lint_file(anchored)
        anchored_fail_ids = {f["rule_id"] for f in report_anchored["findings"] if f["severity"] == "fail"}
        assert "L5c.path_relativo_cru" not in anchored_fail_ids, f"path com \\${{CLAUDE_PLUGIN_ROOT}} deveria ser aceito: {report_anchored['findings']}"

        proof = run_proof(compliant_dir)
        assert proof["ran"] and proof["exit_code"] == 0, f"prova deveria rodar e sair 0: {proof}"

        print("self-test OK — fixture compliant=PASS, violator=FAIL (5 regras batidas), ${CLAUDE_PLUGIN_ROOT} aceito, run-proof exit 0")
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
            print(f"skill_lint: pasta não existe: {base}", file=sys.stderr)
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
        print("uso: skill_lint.py <skill.md|dir> OU --all <dir-de-skills> [--run-proofs] [--json out.json]", file=sys.stderr)
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
    print(f"\nskill_lint: {summary['pass']} pass · {summary['warn']} warn · {summary['fail']} fail (de {summary['total']})")

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
