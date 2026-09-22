#!/usr/bin/env python3
"""
ip_pii_linter -- pre-packaging gate against secret/client/infra/PII/brand/third-party-code.

Scans a folder that is a candidate to become a distributable kit and fails (exit 2) if it finds
any finding with BLOCK severity. It is the unbreakable gate that kit_assembler.py runs BEFORE
emitting a kit -- there is no --skip-lint flag.

Usage:
    python ip_pii_linter.py <target_folder>
        [--ruleset ip-ruleset.yaml]      # default: ip-ruleset.yaml next to this script,
                                         # fallback ip-ruleset.example.yaml
        [--json <out.json>]              # machine report (contract: schemas/lint-report.schema.json)
        [--baseline <b.json>]            # ratchet: only fails on findings NEW vs baseline
        [--strict]                       # promotes every WARN -> BLOCK
        [--category secret,client,infra,pii,identity,derived,hygiene]
        [--self-test]                    # runs against embedded fixtures; exit 0 if detection is exact

Exit: 0 clean (zero BLOCK, zero WARN or all WARNs in baseline) | 1 WARNs present |
      2 >=1 BLOCK (folder CANNOT become a kit) | 3 execution error.

stdlib + PyYAML. Cross-platform (pathlib). Mirrors the --self-test pattern of scripts/loop/done_gate.py.

v1.0.0 -- 2026-07-10 (PHASE 1 | kit-forge)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml  # PyYAML
except ImportError:  # explicit degrade -- without YAML there is no way to read a real ruleset (exit 3)
    yaml = None  # type: ignore[assignment]

_ROOT = Path(__file__).resolve().parent
_CATEGORIES = {"secret", "client", "infra", "pii", "identity", "derived", "hygiene"}

SECRET_PATTERNS = [
    ("secret.anthropic", re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}")),
    ("secret.openai", re.compile(r"sk-proj-[A-Za-z0-9_\-]{10,}")),
    ("secret.github", re.compile(r"ghp_[A-Za-z0-9]{20,}")),
    ("secret.slack", re.compile(r"xox[bap]-[A-Za-z0-9\-]{10,}")),
    ("secret.google", re.compile(r"AIza[A-Za-z0-9_\-]{20,}")),
    ("secret.supabase", re.compile(r"sbp_[A-Za-z0-9]{20,}")),
    ("secret.jwt", re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
    ("secret.pem", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("secret.generic_kv", re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*[\"'][A-Za-z0-9_\-]{16,}[\"']")),
]

CNPJ_RE = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
CPF_RE = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}")

_SELFTEST_RULESET = {
    "version": 1,
    "banned_terms": {
        "clients": ["acme-client-x"],
        "infra": ["127.0.0.1:9999"],
        "identity": ["internalbrandx"],
    },
    "derived": {
        "filenames": ["license.js"],
        "content": ["thirdpartyforkxyz", "genericeccref"],
        "reference_only_ok": ["genericeccref"],
        "attribution_required_if_missing": ["MIT-ATTRIBUTION-TAG"],
    },
    "pii": {
        "personal_emails": ["personal@example.com"],
    },
    "allow": [],
}


def _cnpj_valid(digits: str) -> bool:
    if len(digits) != 14 or len(set(digits)) == 1:
        return False

    def calc(nums: str, weights: list) -> str:
        s = sum(int(n) * w for n, w in zip(nums, weights))
        r = s % 11
        return "0" if r < 2 else str(11 - r)

    d13 = calc(digits[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    d14 = calc(digits[:12] + d13, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return digits[12] == d13 and digits[13] == d14


def _cpf_valid(digits: str) -> bool:
    if len(digits) != 11 or len(set(digits)) == 1:
        return False

    def calc(nums: str, start: int) -> str:
        s = sum(int(n) * (start - i) for i, n in enumerate(nums))
        r = (s * 10) % 11
        return "0" if r == 10 else str(r)

    d10 = calc(digits[:9], 10)
    d11 = calc(digits[:9] + d10, 11)
    return digits[9] == d10 and digits[10] == d11


def redact(s: str) -> str:
    if len(s) <= 8:
        return "*" * len(s)
    return f"{s[:4]}...{s[-4:]}"


def _finding(file: str, line: int, category: str, severity: str, rule_id: str, raw_match: str) -> dict:
    return {
        "file": file,
        "line": line,
        "category": category,
        "severity": severity,
        "rule_id": rule_id,
        "match_redacted": redact(str(raw_match)),
    }


def _safe_read(path: Path):
    try:
        raw = path.read_bytes()
    except Exception:
        return None
    if b"\x00" in raw[:8000]:
        return None  # binary -- only filename checks apply
    try:
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return None


def _has_attribution(text: str, attribution_terms: list) -> bool:
    return any(term in text for term in attribution_terms)


def load_ruleset(path: Path) -> dict:
    if yaml is None:
        raise RuntimeError("PyYAML missing — install pyyaml to read the ruleset")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise RuntimeError("ruleset is not a valid YAML mapping")
    return data


_DIRS_FORA_DO_UNIVERSO = {".git"}


def iter_target_files(target: Path):
    # Why: `.git/` stays out of the universe. Config, logs and refs carry the committer's e-mail --
    # metadata that GitHub does not serve as content -- and commit identity is a decision for whoever
    # publishes, not a lint finding. The universe is declared here, not via a flag, so the number is
    # reproducible.
    for p in sorted(target.rglob("*")):
        if p.is_file() and not (_DIRS_FORA_DO_UNIVERSO & set(p.relative_to(target).parts[:-1])):
            yield p


def _is_allowed(allow_entries: list, rel_path: str, category: str, raw_match: str) -> bool:
    """Auditable allowlist (SKILL-CONTRACT): each exception has path+category+pattern+owner+reason.
    Without this, genuine self-test fixture findings (e.g.: test 'sk-ant-...') would block
    the emission of any kit that self-tests -- which is EVERY kit in this marketplace."""
    for entry in allow_entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("categoria") != category:
            continue
        path_pat = entry.get("path", "")
        if path_pat and path_pat not in rel_path:
            continue
        match_pat = entry.get("pattern", "")
        if match_pat and not re.search(match_pat, raw_match):
            continue
        return True
    return False


def _term_matcher(term: str):
    """Compiles a banned term into a matcher with a word boundary.

    # Why: the matcher used to be `term in line.lower()` -- raw substring. A short term matched
    # INSIDE a legitimate word ("ray" in "array", "web" in "cobweb"), and a gate that fails a
    # legitimate word gets turned off before it is ever right for a single day. The examples are
    # synthetic on purpose: this file travels inside the kit, and the document that teaches the
    # rule cannot be the violation of it.
    #
    # The boundary is by the SHAPE of the term, not by length:
    #   starts AND ends alphanumeric -> lookaround [0-9a-z]. "ray" does not match "array", but
    #     it still matches "ray-core" and "ray_core", because "-" and "_" are not [0-9a-z]. The
    #     middle can have a dot, space or colon -- re.escape handles them; the boundary only looks at the ends.
    #   punctuation on either end -> raw substring. There the lookaround would look at the
    #     wrong character: in a term starting with ":", the neighbor to the left is a digit from its own address.
    #
    # Declared cost: a term does not match its own concatenation without a separator ("web" does
    # not match "webv1") -- a rare false negative against frequent false positives.
    #
    # Lookaround instead of \b on purpose: written through a path that escapes, the sequence turns
    # into the 0x08 byte (backspace) and the regex stops matching everything, including true positives.
    """
    tl = term.lower()
    if tl and tl[0].isalnum() and tl[-1].isalnum():
        return re.compile("(?<![0-9a-z])" + re.escape(tl) + "(?![0-9a-z])")
    return None  # None = usar substring cru


def _term_hit(matcher, term_lower: str, line_lower: str) -> bool:
    if matcher is not None:
        return matcher.search(line_lower) is not None
    return term_lower in line_lower


def _is_encoded_blob(line: str) -> bool:
    """A line with no space and very long = base64/hex/minified, not prose.

    # Why: a banned term matched inside an encoded blob is noise by construction -- the byte
    # matched, the MEANING does not exist. Does not apply to SECRET, which keeps being searched on every line.
    """
    # Why: a bare URL or path over 200 characters has no space and would be treated as a
    # blob -- a link with a proper name would slip through. An encoded blob is only base64/hex/
    # minified alphabet; URL and path stay OUT.
    t = line.strip()
    if len(t) <= 200 or " " in t:
        return False
    if "://" in t or t.startswith(("/", "./", "~")) or "\\" in t:
        return False
    if re.search(r"/[a-z]{3,}/", t):   # Why: a word-segment between slashes is a relative path, not base64.
        return False
    return re.fullmatch(r"[A-Za-z0-9+/=_-]+", t) is not None


def scan(target: Path, ruleset: dict, categories: set | None = None) -> list:
    cats = categories or _CATEGORIES
    banned = ruleset.get("banned_terms", {}) or {}
    clients = [t.lower() for t in banned.get("clients", []) if t]
    infra = [t.lower() for t in banned.get("infra", []) if t]
    identity = [t.lower() for t in banned.get("identity", []) if t]
    clients_m = [(t, _term_matcher(t)) for t in clients]
    infra_m = [(t, _term_matcher(t)) for t in infra]
    identity_m = [(t, _term_matcher(t)) for t in identity]

    derived = ruleset.get("derived", {}) or {}
    derived_filenames = {f.lower() for f in derived.get("filenames", []) if f}
    derived_content = [t for t in derived.get("content", []) if t]
    reference_only_ok = {t.lower() for t in derived.get("reference_only_ok", []) if t}
    attribution_terms = derived.get("attribution_required_if_missing", []) or []

    pii_conf = ruleset.get("pii", {}) or {}
    personal_emails = [e.lower() for e in pii_conf.get("personal_emails", []) if e]

    allow_entries = ruleset.get("allow", []) or []
    findings = []

    def add(rel: str, lineno: int, category: str, severity: str, rule_id: str, raw_match) -> None:
        if _is_allowed(allow_entries, rel, category, str(raw_match)):
            return
        findings.append(_finding(rel, lineno, category, severity, rule_id, raw_match))

    for f in iter_target_files(target):
        rel = f.relative_to(target).as_posix()
        name_lower = f.name.lower()

        if "hygiene" in cats:
            if name_lower.endswith(".bak"):
                add(rel, 0, "hygiene", "warn", "hygiene.bak", f.name)
            if name_lower.endswith(".pyc"):
                add(rel, 0, "hygiene", "warn", "hygiene.pyc", f.name)
            if "__pycache__" in f.parts:
                add(rel, 0, "hygiene", "warn", "hygiene.pycache", f.name)
            if name_lower == ".env" or name_lower.startswith(".env."):
                content = _safe_read(f)
                if content is not None and content.strip():
                    add(rel, 0, "hygiene", "block", "hygiene.env_nonempty", f.name)
                elif content is not None:
                    add(rel, 0, "hygiene", "warn", "hygiene.env_present_empty", f.name)
            if name_lower == "registry.json":
                content = _safe_read(f)
                if content:
                    try:
                        data = json.loads(content)
                        if data not in ({}, [], None, {"faturas": []}):
                            add(rel, 0, "hygiene", "warn", "hygiene.registry_nonempty", f.name)
                    except Exception:  # noqa: BLE001 -- malformed JSON is not what this check measures
                        pass

        if "derived" in cats and name_lower in derived_filenames:
            add(rel, 0, "derived", "block", "derived.filename", f.name)

        text = _safe_read(f)
        if text is None:
            continue

        if "derived" in cats:
            for term in derived_content:
                tl = term.lower()
                if tl in text.lower():
                    line_no = next((i for i, ln in enumerate(text.splitlines(), 1) if tl in ln.lower()), 0)
                    if tl in reference_only_ok:
                        if not _has_attribution(text, attribution_terms):
                            add(rel, line_no, "derived", "block", "derived.attribution_missing", term)
                    else:
                        add(rel, line_no, "derived", "block", "derived.content", term)

        for lineno, line in enumerate(text.splitlines(), start=1):
            low = line.lower()

            if "secret" in cats:
                for rule_id, pattern in SECRET_PATTERNS:
                    for m in pattern.finditer(line):
                        add(rel, lineno, "secret", "block", rule_id, m.group(0))

            if "client" in cats and not _is_encoded_blob(line):
                for term, m in clients_m:
                    if _term_hit(m, term, low):
                        add(rel, lineno, "client", "block", "client.banned_term", term)

            if "infra" in cats and not _is_encoded_blob(line):
                for term, m in infra_m:
                    if _term_hit(m, term, low):
                        add(rel, lineno, "infra", "block", "infra.banned_term", term)

            if "identity" in cats and not _is_encoded_blob(line):
                for term, m in identity_m:
                    if _term_hit(m, term, low):
                        add(rel, lineno, "identity", "warn", "identity.banned_term", term)

            if "pii" in cats:
                for m in CNPJ_RE.finditer(line):
                    digits = re.sub(r"\D", "", m.group(0))
                    sev = "block" if _cnpj_valid(digits) else "warn"
                    add(rel, lineno, "pii", sev, "pii.cnpj", m.group(0))
                for m in CPF_RE.finditer(line):
                    digits = re.sub(r"\D", "", m.group(0))
                    sev = "block" if _cpf_valid(digits) else "warn"
                    add(rel, lineno, "pii", sev, "pii.cpf", m.group(0))
                for email in personal_emails:
                    if email in low:
                        add(rel, lineno, "pii", "block", "pii.personal_email", email)

    return findings


def _finding_key(f: dict):
    return (f["file"], f["line"], f["category"], f["rule_id"])


def apply_baseline(findings: list, baseline_findings: list) -> list:
    baseline_keys = {_finding_key(f) for f in baseline_findings}
    return [f for f in findings if _finding_key(f) not in baseline_keys]


def compute_status(findings: list, strict: bool):
    block = [f for f in findings if f["severity"] == "block" or (strict and f["severity"] == "warn")]
    if block:
        return "block", 2
    warn = [f for f in findings if f["severity"] == "warn"]
    if warn:
        return "warn", 1
    return "ok", 0


def _print_human(report: dict) -> None:
    findings = report["findings"]
    if not findings:
        print("ip_pii_linter: clean — 0 findings")
        return
    print(f"{'file:line':<50} | {'category':<9} | {'rule_id':<28} | match")
    print("-" * 110)
    for f in findings:
        loc = f"{f['file']}:{f['line']}"
        print(f"{loc:<50} | {f['category']:<9} | {f['rule_id']:<28} | {f['match_redacted']}")
    c = report["counts"]
    print(f"\nip_pii_linter: status={report['status']} block={c['block']} warn={c['warn']} total={c['total']}")


def _self_test() -> int:
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="ip_pii_linter_selftest_"))
    try:
        (tmp / "secret.txt").write_text('token = "sk-ant-1234567890abcdef1234"\n', encoding="utf-8")
        (tmp / "client.txt").write_text("Client: acme-client-x signed the contract\n", encoding="utf-8")
        (tmp / "infra.txt").write_text("endpoint 127.0.0.1:9999\n", encoding="utf-8")
        (tmp / "identity.txt").write_text("Product InternalBrandX\n", encoding="utf-8")
        (tmp / "pii_valid_cnpj.txt").write_text("CNPJ: 11.222.333/0001-81\n", encoding="utf-8")
        (tmp / "pii_invalid_cnpj.txt").write_text("CNPJ: 11.222.333/0001-80\n", encoding="utf-8")
        (tmp / "pii_valid_cpf.txt").write_text("CPF: 111.444.777-35\n", encoding="utf-8")
        (tmp / "personal_email.txt").write_text("contact: personal@example.com\n", encoding="utf-8")

        derived_dir = tmp / "derived_filename"
        derived_dir.mkdir()
        (derived_dir / "license.js").write_text("// third party license\n", encoding="utf-8")
        (tmp / "derived_hardblock.txt").write_text("uses thirdpartyforkxyz internally\n", encoding="utf-8")
        (tmp / "derived_ecc_noattrib.txt").write_text("based on genericeccref pattern\n", encoding="utf-8")
        (tmp / "derived_ecc_attrib.txt").write_text(
            "based on genericeccref pattern\n# MIT-ATTRIBUTION-TAG\n", encoding="utf-8"
        )

        hygiene_dir = tmp / "hygiene"
        hygiene_dir.mkdir()
        (hygiene_dir / "old.bak").write_text("stale\n", encoding="utf-8")
        pycache = hygiene_dir / "__pycache__"
        pycache.mkdir()
        (pycache / "x.pyc").write_bytes(b"\x00\x01binary")
        (hygiene_dir / ".env").write_text("SOME_FLAG=abc\n", encoding="utf-8")
        emptyenv_dir = hygiene_dir / "emptyenv"
        emptyenv_dir.mkdir()
        (emptyenv_dir / ".env").write_text("", encoding="utf-8")

        (tmp / "clean.txt").write_text("nothing suspicious here\n", encoding="utf-8")

        findings = scan(tmp, _SELFTEST_RULESET)
        by_rule: dict = {}
        for f in findings:
            by_rule.setdefault(f["rule_id"], []).append(f)

        assert any(r.startswith("secret.") for r in by_rule), f"secret not detected: {sorted(by_rule)}"
        assert "client.banned_term" in by_rule, "client not detected"
        assert "infra.banned_term" in by_rule, "infra not detected"
        assert "identity.banned_term" in by_rule, "identity not detected"
        assert all(f["severity"] == "warn" for f in by_rule["identity.banned_term"]), "identity should be warn by default"
        assert "derived.filename" in by_rule, "derived filename not detected"
        assert "derived.content" in by_rule, "derived content hard-block not detected"
        assert "derived.attribution_missing" in by_rule, "derived ECC without attribution should block"
        ecc_attrib_findings = [f for f in findings if f["file"] == "derived_ecc_attrib.txt"]
        assert not ecc_attrib_findings, f"ECC with attribution should not produce a finding: {ecc_attrib_findings}"
        assert "pii.personal_email" in by_rule, "pii personal_email not detected"

        cnpj_findings = [f for f in findings if f["rule_id"] == "pii.cnpj"]
        valid_cnpj = [f for f in cnpj_findings if f["file"] == "pii_valid_cnpj.txt"]
        invalid_cnpj = [f for f in cnpj_findings if f["file"] == "pii_invalid_cnpj.txt"]
        assert valid_cnpj and valid_cnpj[0]["severity"] == "block", "valid CNPJ should be block"
        assert invalid_cnpj and invalid_cnpj[0]["severity"] == "warn", "CNPJ with invalid checksum should be warn"

        cpf_findings = [f for f in findings if f["rule_id"] == "pii.cpf"]
        assert cpf_findings and cpf_findings[0]["severity"] == "block", "valid CPF should be block"

        assert "hygiene.bak" in by_rule, "hygiene .bak not detected"
        assert "hygiene.pycache" in by_rule, "hygiene __pycache__ not detected"
        assert "hygiene.env_nonempty" in by_rule, "hygiene .env with content should block"
        assert "hygiene.env_present_empty" in by_rule, "hygiene empty .env should be warn"

        status, exit_code = compute_status(findings, strict=False)
        assert status == "block" and exit_code == 2, f"expected status block, got {status}"

        strict_status, strict_exit = compute_status(findings, strict=True)
        assert strict_status == "block" and strict_exit == 2

        only_secret = scan(tmp, _SELFTEST_RULESET, categories={"secret"})
        assert only_secret and all(f["category"] == "secret" for f in only_secret), "--category filter leaked another category"

        baseline_findings = [f for f in findings if f["rule_id"] == "hygiene.bak"]
        ratcheted = apply_baseline(findings, baseline_findings)
        assert not any(f["rule_id"] == "hygiene.bak" for f in ratcheted), "baseline did not filter a known finding"
        assert len(ratcheted) == len(findings) - len(baseline_findings)

        print(f"self-test OK — {len(findings)} findings across {len(by_rule)} distinct rules")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ip_pii_linter.py")
    p.add_argument("target", nargs="?", help="folder to scan")
    p.add_argument("--ruleset", default=None)
    p.add_argument("--json", dest="json_out", default=None, help="path to write the JSON report to")
    p.add_argument("--baseline", default=None)
    p.add_argument("--strict", action="store_true")
    p.add_argument("--category", default=None)
    p.add_argument("--self-test", action="store_true")
    return p


def main(argv) -> int:
    args = build_parser().parse_args(argv)

    if args.self_test:
        return _self_test()

    if not args.target:
        print("usage: ip_pii_linter.py <target_folder> [--ruleset ...] [--json out.json] [--baseline b.json] [--strict] [--category ...]", file=sys.stderr)
        return 3

    target = Path(args.target)
    if not target.is_dir():
        print(f"ip_pii_linter: folder does not exist: {target}", file=sys.stderr)
        return 3

    if args.ruleset:
        ruleset_path = Path(args.ruleset)
    else:
        ruleset_path = _ROOT / "ip-ruleset.yaml"
        if not ruleset_path.exists():
            ruleset_path = _ROOT / "ip-ruleset.example.yaml"

    if not ruleset_path.exists():
        print(f"ip_pii_linter: ruleset not found: {ruleset_path}", file=sys.stderr)
        return 3

    try:
        ruleset = load_ruleset(ruleset_path)
    except Exception as e:  # noqa: BLE001 -- any parsing error becomes exit 3, not a crash
        print(f"ip_pii_linter: invalid ruleset ({ruleset_path}): {e}", file=sys.stderr)
        return 3

    categories = None
    if args.category:
        categories = {c.strip().lower() for c in args.category.split(",") if c.strip()}
        unknown = categories - _CATEGORIES
        if unknown:
            print(f"ip_pii_linter: unknown category/categories: {sorted(unknown)}", file=sys.stderr)
            return 3

    findings = scan(target, ruleset, categories)

    if args.baseline:
        try:
            baseline_data = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
            findings = apply_baseline(findings, baseline_data.get("findings", []))
        except Exception as e:  # noqa: BLE001
            print(f"ip_pii_linter: invalid baseline ({args.baseline}): {e}", file=sys.stderr)
            return 3

    status, exit_code = compute_status(findings, args.strict)
    counts = {
        "block": sum(1 for f in findings if f["severity"] == "block" or (args.strict and f["severity"] == "warn")),
        "warn": 0 if args.strict else sum(1 for f in findings if f["severity"] == "warn"),
        "total": len(findings),
    }
    report = {"status": status, "counts": counts, "findings": findings}

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"ip_pii_linter: report written to {args.json_out} (status={status})")
    else:
        _print_human(report)

    return exit_code


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
