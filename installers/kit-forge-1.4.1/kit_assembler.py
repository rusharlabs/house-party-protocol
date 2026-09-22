#!/usr/bin/env python3
"""
kit_assembler -- from manifest to distributable kit, with ip_pii_linter as an unbreakable GATE.

Reads a YAML manifest, resolves the file set (include - exclude), copies it to a
temporary staging area, applies deterministic sanitizations, generates LICENSE/SANITIZATION.md
(+ the SANITIZATION.pt-BR.md pair)/CHECKSUMS.txt, runs ip_pii_linter as a gate, and ONLY THEN
swaps atomically to the final destination (+ deterministic zip). There is no --skip-lint -- the
gate has no back door.

Usage:
    python kit_assembler.py --manifest <manifest.yaml>
        [--out <dir>]           # default: dist/ next to this script
        [--dry-run]             # prints the plan (IN/OUT/actions) and stops -- zero writes
        [--json <out.json>]     # machine report
        [--strict]              # passes --strict through to the linter
        [--self-test]

Exit: 0 emitted clean (or idempotent no-op) | 1 emitted with warnings | 2 lint BLOCK (nothing
      emitted) | 3 error (invalid manifest, divergent plugin.json, IO).

stdlib + PyYAML. v1.0.0 -- 2026-07-10 (PHASE 1 | kit-forge)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

try:
    import yaml  # PyYAML
except ImportError:
    yaml = None  # type: ignore[assignment]

_ROOT = Path(__file__).resolve().parent
_LINTER = _ROOT / "ip_pii_linter.py"
_ZIP_EPOCH = (2020, 1, 1, 0, 0, 0)  # fixed timestamp -> deterministic zip

# Why (English-first docs): human docs ship English-first with a pt-BR pair. The sanitization
# record is generated, so the pair is generated too — same numbers, same headings, pair link at
# the top — and the Portuguese-only SANITIZACAO.md is no longer emitted. The manifest switch keeps
# its historical name (`generate.sanitizacao_md`): it is a config key, not a file name.
_SANITIZATION_FILES = ("SANITIZATION.md", "SANITIZATION.pt-BR.md")
_SANITIZATION_PAIR_LINK = "[English](SANITIZATION.md) · [Português](SANITIZATION.pt-BR.md)"
_SANITIZATION_TEXT = {
    "SANITIZATION.md": {
        "applied_h": "## Sanitization applied",
        "exclude": "- {n} file exclusion pattern(s) (see the build's internal manifest — not distributed)",
        "replaces": "- {n} text replacement(s) applied",
        "lint_h": "## Lint result",
    },
    "SANITIZATION.pt-BR.md": {
        "applied_h": "## Sanitização aplicada",
        "exclude": "- {n} padrão(ões) de exclusão de arquivo (ver manifesto interno da build — não distribuído)",
        "replaces": "- {n} substituição(ões) de texto aplicada(s)",
        "lint_h": "## Resultado do lint",
    },
}

sys.path.insert(0, str(_ROOT / "hooks"))
try:
    from guard_origins import sweep as _go_sweep, verify as _go_verify
except ImportError:  # noqa: BLE001 -- safe fallback if guard_origins is not present
    _go_sweep = None  # type: ignore[assignment]
    _go_verify = None  # type: ignore[assignment]

_LICENSE_MIT = """MIT License

Copyright (c) {year} {author}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def _glob_to_regex(pattern: str):
    """Converts a glob (supports ** cross-slash, * and ?) into an anchored regex."""
    tokens = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if pattern[i : i + 2] == "**":
            tokens.append(".*")
            i += 2
            if i < len(pattern) and pattern[i] == "/":
                i += 1
        elif c == "*":
            tokens.append("[^/]*")
            i += 1
        elif c == "?":
            tokens.append("[^/]")
            i += 1
        elif c == ".":
            tokens.append(r"\.")
            i += 1
        else:
            tokens.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(tokens) + "$")


def resolve_fileset(source_root: Path, include: list, exclude: list) -> list:
    include_res = [_glob_to_regex(p) for p in include]
    exclude_res = [_glob_to_regex(p) for p in exclude]
    result = []
    for p in sorted(source_root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(source_root).as_posix()
        if any(r.match(rel) for r in include_res) and not any(r.match(rel) for r in exclude_res):
            result.append(rel)
    return sorted(result)


def load_manifest(path: Path) -> dict:
    if yaml is None:
        raise RuntimeError("PyYAML missing — install pyyaml to read the manifest")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise RuntimeError("manifest is not a valid YAML mapping")
    return data


def validate_manifest(manifest: dict) -> list:
    """Returns a list of errors (empty = valid)."""
    errors = []
    kit = manifest.get("kit")
    if not isinstance(kit, dict):
        return ["section 'kit' missing or invalid"]
    for field in ("name", "version", "license", "author", "source_root"):
        if not kit.get(field):
            errors.append(f"kit.{field} missing")
    version = kit.get("version", "")
    if version and not re.match(r"^\d+\.\d+\.\d+([-+].*)?$", str(version)):
        errors.append(f"kit.version '{version}' is not semver")
    if not manifest.get("include"):
        errors.append("'include' missing or empty")
    plugin_json = kit.get("_plugin_json_check")  # injected by the caller, if applicable
    if plugin_json:
        if plugin_json.get("version") and plugin_json["version"] != version:
            errors.append(f"plugin.json version ({plugin_json['version']}) diverges from the manifest ({version})")
        if plugin_json.get("license") and plugin_json["license"] != kit.get("license"):
            errors.append("plugin.json license diverges from the manifest")
    return errors


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def write_checksums(staging: Path, files: list) -> Path:
    lines = []
    for rel in sorted(files):
        digest = sha256_file(staging / rel)
        lines.append(f"{digest}  {rel}")
    out = staging / "CHECKSUMS.txt"
    _write_lf(out, "\n".join(lines) + "\n")
    return out


def write_zip(staging: Path, files: list, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in sorted(files) + ["LICENSE", *_SANITIZATION_FILES, "CHECKSUMS.txt"]:
            p = staging / rel
            if not p.exists():
                continue
            info = zipfile.ZipInfo(rel, date_time=_ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, p.read_bytes())


# --- THE PROOF OF THE ARTIFACT THAT TRAVELS ------------------------------------------
# Why: the assembler used to write the .zip and never open it again, and kit_doctor verifies
# the CHECKSUMS.txt inside the kit's DIRECTORY, not in the zip. A truncated zip, with an entry
# that escapes the extraction directory, or carrying .bak/.env/ip-ruleset.yaml would exit with
# 0. The directory is what got assembled; the zip is what travels. They are two artifacts, and
# both need a check.

# Why: the same list from the 10 manifests (exclude .bak) plus what must
# NEVER leave home. The real ip-ruleset.yaml carries client names and
# internal infra -- only the .example is publishable.
_ZIP_PROIBIDO = (
    "*.bak",
    "*.bak-*",
    # Why: the list knew `.bak` and `.orig` and not the naming this house actually uses for a
    # pre-edit snapshot — `x.py.pre52`, `x.py.pre-selfref`. One of those reached the emitted
    # tree, the zip AND the CHECKSUMS of a published module before anyone noticed, which is the
    # whole defect this gate exists to stop. Two precise patterns instead of `*.pre*`, which
    # would also match a name like `x.prettier.json`.
    "*.pre[0-9]*",
    "*.pre-*",
    "*.orig",
    "*.rej",
    "*.rebuild*.json",
    "*.build.json",
    "*.pyc",
    "*.pyo",
    "__pycache__",
    ".pytest_cache",
    ".env",
    ".env.*",
    "ip-ruleset.yaml",
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    "*.INVALIDO",
)


def _entrada_proibida(name: str) -> str | None:
    """Returns the pattern that fails the entry, or None. Matches the BASENAME and each
    directory component -- `a/__pycache__/b.txt` fails via the directory."""
    import fnmatch

    parts = name.split("/")
    base = parts[-1]
    # Why: the distribution .gitignore negates .env.example on purpose; the check has
    # to negate it too, or the gate fails the file it wants to exist.
    if base.endswith(".example"):
        return None
    # Why: fnmatch.fnmatch is case-insensitive only on Windows -- "X.BAK" would fail the zip here
    # and pass on macOS. The check for the artifact that travels cannot depend on the emitter's
    # OS: fnmatchcase over lowercase, always.
    for pattern in _ZIP_PROIBIDO:
        for part in parts:
            if fnmatch.fnmatchcase(part.lower(), pattern.lower()):
                return pattern
    return None


def verify_zip(zip_path: Path, source_dir: Path, expected: list) -> dict:
    """Reopens the emitted .zip and proves it is what it should be.

    Four independent proofs -- one alone is not enough, and each one catches a
    failure mode the others do not see:

      1. INTEGRITY  testzip() validates the CRC of each member (truncated zip)
      2. FIDELITY   sha256 of the member == sha256 of the file on disk
      3. STRUCTURE  no absolute path, no `..` traversal
      4. HYGIENE    no forbidden entry (.bak, .env, ip-ruleset.yaml)

    Plus COMPLETENESS: every file resolved by the manifest has to be there.

    Never raises -- returns {"ok", "entries", "errors"} for the caller to decide.
    """
    errors: list = []
    names: list = []

    if not zip_path.exists():
        return {"ok": False, "entries": 0, "errors": [f"zip does not exist: {zip_path}"]}

    try:
        with zipfile.ZipFile(zip_path) as zf:
            corrupted = zf.testzip()
            if corrupted is not None:
                errors.append(f"invalid CRC (corrupt zip) at: {corrupted}")

            names = zf.namelist()
            for name in names:
                # 3 - STRUCTURE. An entry that escapes the extraction directory
                # overwrites a file belonging to whoever installs it. This is not hygiene, it is security.
                if name.startswith("/") or (len(name) > 1 and name[1] == ":"):
                    errors.append(f"absolute path in zip: {name}")
                    continue
                if ".." in name.split("/"):
                    errors.append(f"directory traversal in zip: {name}")
                    continue
                if chr(92) in name:
                    # Why: chr(92) is the backslash. Written literally, the backslash-b sequence could turn
                    # into the 0x08 byte (backspace) and the gate would stop matching everything, including
                    # true positives. Written this way, it has no way of getting lost.
                    errors.append(f"Windows separator in zip: {name}")
                    continue

                # 4 - HYGIENE
                pattern = _entrada_proibida(name)
                if pattern is not None:
                    errors.append(f"forbidden entry in zip: {name} (matches {pattern})")

                # 2 - FIDELITY
                on_disk = source_dir / name
                if not on_disk.exists():
                    errors.append(f"zip entry with no counterpart on disk: {name}")
                    continue
                if hashlib.sha256(zf.read(name)).hexdigest() != sha256_file(on_disk):
                    errors.append(f"zip content diverges from disk: {name}")

            present = set(names)
            for rel in sorted(expected):
                if rel not in present:
                    errors.append(f"manifest file missing from zip: {rel}")
    except zipfile.BadZipFile as exc:
        return {"ok": False, "entries": 0, "errors": [f"unreadable zip: {exc}"]}

    return {"ok": not errors, "entries": len(names), "errors": errors}


# --- STRUCTURE-AWARE SANITIZATION (A12) ------------------------------
# Why: detection (ip_pii_linter) has a word boundary; the MUTATION was a raw
# `text.replace(find, repl)` -- the same defect, in the writing half. The first
# sanitize rule anyone writes is exactly to swap a name before
# publishing, which is the exact case where a raw substring destroys the neighboring word.
#
# Three things the raw `text.replace` did not have and now does:
#   declared MODE     word (default) | literal | regex -- raw substring became a CHOICE,
#                     not silent behavior
#   COUNT             how many hits per file. A rule that expected 2 and made 400 becomes
#                     visible in the report instead of turning into a mysterious diff
#   VACUITY           a rule with ZERO hits gets a warning: it was written for a reason and
#                     did nothing
_SANITIZE_MODOS = ("word", "literal", "regex")


def _compile_replace(find: str, mode: str):
    """Returns the compiled pattern, or None for a raw substring."""
    if mode == "regex":
        return re.compile(find)
    if mode == "literal":
        return None
    # "word" -- the DEFAULT, and the reason this function exists.
    # The boundary only looks at the ENDS: the middle can have a dot, space or
    # colon freely, because re.escape takes care of them. Same criterion as
    # ip_pii_linter, on purpose -- detection and mutation must not diverge.
    if find and find[0].isalnum() and find[-1].isalnum():
        return re.compile("(?<![0-9A-Za-z])" + re.escape(find) + "(?![0-9A-Za-z])")
    return None


def _read_preserving_linebreak(path: Path) -> str:
    # Why: read_text/write_text translate line breaks. In a checkout with CRLF files,
    # rewriting a whole file because of ONE substitution would silently convert the
    # entire file -- and `git diff --numstat` is blind to it.
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def _write_preserving_linebreak(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def _write_lf(path: Path, text: str) -> None:
    """A file GENERATED by the assembler always comes out in LF -- on any OS."""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _copy_normalizing_eol(src: Path, dst: Path) -> None:
    """Copies to staging normalizing text to LF; binary goes byte for byte.

    # Why: a kit emitted on Windows used to carry CRLF files (LICENSE/CHECKSUMS/SANITIZATION
    # generated by write_text, and sources that the local checkout keeps in CRLF). A repo with
    # `* text=auto eol=lf` normalizes everything to LF on the first clone, and CHECKSUMS.txt --
    # which holds the hash of the CRLF bytes -- ends up failing the kit it describes itself. And
    # the zip stops being deterministic across OSes. LF in the copy closes both things.
    """
    raw = src.read_bytes()
    if b"\x00" in raw[:8000] or src.suffix.lower() in _BINARY_EXTS:
        shutil.copy2(src, dst)
        return
    dst.write_bytes(raw.replace(b"\r\n", b"\n"))
    shutil.copystat(src, dst)


_BINARY_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".woff", ".woff2", ".ttf", ".pyc"}


def apply_replaces(staging: Path, rules: list) -> tuple[list, list, list]:
    """Applies the manifest's substitutions. Returns (applied, warnings, errors).

    Never raises: a manifest error becomes an item in `errors` and the caller decides.
    """
    applied: list = []
    warnings: list = []
    errors: list = []

    for i, rule in enumerate(rules):
        find = rule.get("find")
        repl = rule.get("replace")
        mode = rule.get("mode", "word")
        files = rule.get("files") or []

        if not find:
            errors.append(
                f"sanitize.replaces[{i}]: empty 'find' — an empty find inserts the "
                "replace BETWEEN EVERY CHARACTER of the file"
            )
            continue
        if repl is None:
            errors.append(f"sanitize.replaces[{i}]: 'replace' missing")
            continue
        if mode not in _SANITIZE_MODOS:
            errors.append(
                f"sanitize.replaces[{i}]: invalid mode '{mode}' "
                f"(use one of: {', '.join(_SANITIZE_MODOS)})"
            )
            continue
        if not files:
            errors.append(f"sanitize.replaces[{i}]: empty 'files' — the rule has no target")
            continue
        try:
            pattern = _compile_replace(find, mode)
        except re.error as exc:
            errors.append(f"sanitize.replaces[{i}]: invalid regex: {exc}")
            continue

        if mode == "word" and pattern is None:
            # Why: a find with a non-alphanumeric end ("-core", "/x/", "@org/") has no possible
            # boundary and falls back to a raw substring -- and the report still said mode "word".
            # The report says what HAPPENED.
            warnings.append(
                f"sanitize.replaces[{i}]: mode 'word' requested, but the 'find' starts or ends in a "
                "non-alphanumeric — no word boundary is possible; applied as 'literal' "
                "(substring). Declare mode: literal if that is what you want."
            )
        if mode != "regex" and find in repl:
            warnings.append(
                f"sanitize.replaces[{i}]: the 'replace' CONTAINS the 'find' — "
                "the rule stops being idempotent and the 2nd build re-substitutes"
            )

        total = 0
        for rel_file in files:
            target = staging / rel_file
            if not target.exists():
                warnings.append(f"sanitize.replaces[{i}]: file missing from staging: {rel_file}")
                continue
            text = _read_preserving_linebreak(target)
            if pattern is None:
                new_text = text.replace(find, repl)
                n = text.count(find)
            elif mode == "regex":
                # backreference allowed -- whoever asked for regex asked for this
                new_text, n = pattern.subn(repl, text)
            else:
                # substitution function: the text goes in VERBATIM, without re
                # interpreting any escape inside it
                new_text, n = pattern.subn(lambda _m: repl, text)
            if n:
                _write_preserving_linebreak(target, new_text)
                applied.append(
                    {"file": rel_file, "find": find, "replace": repl,
                     # Why: the report records the mode that was applied, not just the one requested.
                     "mode": ("literal (degraded from word)" if mode == "word" and pattern is None else mode),
                     "hits": n}
                )
                total += n

        if total == 0:
            warnings.append(
                f"sanitize.replaces[{i}]: ZERO occurrences in {len(files)} file(s) — "
                "VACUOUS rule, it was written for a reason and did nothing"
            )

    return applied, warnings, errors


def run_pipeline(manifest: dict, manifest_dir: Path, out_dir: Path, dry_run: bool, strict: bool, plugin_json: dict | None = None):
    """Runs the pipeline. Returns (exit_code, report_dict)."""
    manifest = dict(manifest)
    if plugin_json is None:
        # Why: the version check existed in validate_manifest and no call site fed it -- a kit
        # could ship declaring a version in plugin.json different from the manifest's. Without
        # loading the source plugin.json, the gate is vacuous.
        kit0 = manifest.get("kit") or {}
        if kit0.get("source_root"):
            cand = (manifest_dir / kit0["source_root"]).resolve() / ".claude-plugin" / "plugin.json"
            if cand.is_file():
                try:
                    plugin_json = json.loads(cand.read_text(encoding="utf-8"))
                except (OSError, ValueError) as e:
                    return 3, {"status": "error", "errors": [f"unreadable plugin.json at {cand}: {e}"]}
    if plugin_json is not None:
        manifest.setdefault("kit", {})["_plugin_json_check"] = plugin_json

    errors = validate_manifest(manifest)
    if errors:
        return 3, {"status": "error", "errors": errors}

    kit = manifest["kit"]
    name = kit["name"]
    version = kit["version"]
    source_root = (manifest_dir / kit["source_root"]).resolve()
    if not source_root.is_dir():
        return 3, {"status": "error", "errors": [f"source_root does not exist: {source_root}"]}

    include = manifest.get("include", [])
    exclude = manifest.get("exclude", []) or []
    files = resolve_fileset(source_root, include, exclude)

    plan = {
        "kit": name,
        "version": version,
        "source_root": str(source_root),
        "files_in": len(files),
        "files": files,
    }
    if dry_run:
        return 0, {"status": "dry-run", **plan}

    ts = str(int(time.time() * 1000))
    staging = out_dir / f".staging-{name}-{ts}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    try:
        origin_snapshot = _go_sweep(source_root, files) if _go_sweep else None

        for rel in files:
            dst = staging / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            _copy_normalizing_eol(source_root / rel, dst)

        if _go_verify and origin_snapshot is not None:
            drift = _go_verify(origin_snapshot, source_root, files)
            if drift:
                shutil.rmtree(staging, ignore_errors=True)
                return 3, {"status": "error", "errors": [
                    f"source changed during assembly (guard_origins): {drift}"
                ]}

        sanitize = manifest.get("sanitize", {}) or {}
        applied_replaces, sanitize_warnings, sanitize_errors = apply_replaces(
            staging, sanitize.get("replaces", []) or []
        )
        if sanitize_errors:
            shutil.rmtree(staging, ignore_errors=True)
            return 3, {"status": "error", "errors": sanitize_errors}

        generate = manifest.get("generate", {}) or {}
        if generate.get("license", True):
            _write_lf(staging / "LICENSE", _LICENSE_MIT.format(year=kit.get("year", 2026), author=kit["author"]))

        lint_conf = manifest.get("lint", {}) or {}
        ruleset_path = lint_conf.get("ruleset")
        lint_report_path = staging / ".lint-report.json"
        cmd = [sys.executable, str(_LINTER), str(staging), "--json", str(lint_report_path)]
        if ruleset_path:
            cmd += ["--ruleset", str((manifest_dir / ruleset_path).resolve())]
        if strict:
            cmd.append("--strict")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        lint_report = {}
        if lint_report_path.exists():
            lint_report = json.loads(lint_report_path.read_text(encoding="utf-8"))
            lint_report_path.unlink()

        fail_on = lint_conf.get("fail_on", "block")
        lint_status = lint_report.get("status", "error" if proc.returncode == 3 else "unknown")

        if proc.returncode == 2 or lint_status == "block":
            shutil.rmtree(staging, ignore_errors=True)
            return 2, {"status": "block", "lint": lint_report, "stderr": proc.stderr}
        if proc.returncode == 3:
            shutil.rmtree(staging, ignore_errors=True)
            return 3, {"status": "error", "errors": ["lint failed to run"], "stderr": proc.stderr}
        if lint_status == "warn" and fail_on == "warn":
            shutil.rmtree(staging, ignore_errors=True)
            return 2, {"status": "block", "lint": lint_report, "reason": "fail_on=warn"}

        if generate.get("sanitizacao_md", True):
            # NEVER echo the 'exclude' patterns literally here: an exclude exists
            # precisely to HIDE a sensitive name (e.g.: a script/file with a third
            # party's IP) -- printing the pattern back into the public artifact would negate the
            # exclusion itself (the name of what was hidden would leak into the report). Only the
            # COUNT is reported; the same goes for 'replaces' (the 'find' can contain the
            # sensitive text being replaced).
            for fname in _SANITIZATION_FILES:
                t = _SANITIZATION_TEXT[fname]
                lines = [_SANITIZATION_PAIR_LINK, "", f"# {fname}", "", f"Kit: {name} {version}", "",
                         t["applied_h"],
                         t["exclude"].format(n=len(exclude)),
                         t["replaces"].format(n=len(applied_replaces)),
                         "", t["lint_h"], f"- status: {lint_status}", f"- counts: {lint_report.get('counts', {})}"]
                _write_lf(staging / fname, "\n".join(lines) + "\n")

        emitted_files = files + (["LICENSE"] if generate.get("license", True) else [])
        if generate.get("sanitizacao_md", True):
            emitted_files = emitted_files + list(_SANITIZATION_FILES)
        if generate.get("checksums", True):
            write_checksums(staging, emitted_files)
            emitted_files = emitted_files + ["CHECKSUMS.txt"]

        if _go_verify and origin_snapshot is not None:
            drift_final = _go_verify(origin_snapshot, source_root, files)
            if drift_final:
                shutil.rmtree(staging, ignore_errors=True)
                return 3, {"status": "error", "errors": [
                    f"source changed during assembly, detected before the final swap (guard_origins): {drift_final}"
                ]}

        final_dir = out_dir / f"{name}-{version}"
        new_checksums = (staging / "CHECKSUMS.txt").read_text(encoding="utf-8") if generate.get("checksums", True) else None
        if final_dir.exists() and new_checksums is not None:
            old_checksums_path = final_dir / "CHECKSUMS.txt"
            if old_checksums_path.exists() and old_checksums_path.read_text(encoding="utf-8") == new_checksums:
                shutil.rmtree(staging, ignore_errors=True)
                return 0, {"status": "no-op", "kit": name, "version": version, "reason": "CHECKSUMS identical"}

        if final_dir.exists():
            shutil.rmtree(final_dir)
        staging.rename(final_dir)

        zip_path = None
        zip_check = None
        if generate.get("zip", True):
            zip_path = out_dir / f"{name}-{version}.zip"
            write_zip(final_dir, files, zip_path)

            # Why: writing is not proving. The zip is the artifact that travels, and needs to be
            # reopened after being written.
            zip_check = verify_zip(zip_path, final_dir, files)
            if not zip_check["ok"]:
                # Halted, not deleted: a zip that failed is EVIDENCE. But it
                # cannot keep the name of the good artifact, or someone will install it.
                invalid = zip_path.parent / (zip_path.name + ".INVALIDO")
                if invalid.exists():
                    invalid.unlink()
                zip_path.rename(invalid)
                return 2, {
                    "status": "zip-reprovado",
                    "kit": name,
                    "version": version,
                    "out": str(final_dir),
                    "zip": None,
                    "zip_parado_em": str(invalid),
                    "files": len(emitted_files),
                    "lint": lint_report,
                    "zip_errors": zip_check["errors"],
                }

        report = {
            "status": "emitted",
            "kit": name,
            "version": version,
            "out": str(final_dir),
            "zip": str(zip_path) if zip_path else None,
            "zip_entries": zip_check["entries"] if zip_check else None,
            "files": len(emitted_files),
            "lint": lint_report,
            # Why: the find/replace values stay OUT of the report for the same
            # reason they stay out of SANITIZATION.md -- the 'find' is usually
            # exactly the sensitive text being hidden.
            "sanitize": {
                "aplicadas": [
                    {"file": a["file"], "mode": a["mode"], "hits": a["hits"]}
                    for a in applied_replaces
                ],
                "avisos": sanitize_warnings,
            },
        }
        return (1 if lint_status == "warn" else 0), report
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _self_test() -> int:
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="kit_assembler_selftest_"))
    try:
        src = tmp / "src"
        src.mkdir()
        (src / "README.md").write_text("# Fixture Kit\nnothing suspicious\n", encoding="utf-8")
        (src / "scripts").mkdir()
        (src / "scripts" / "hello.py").write_text("print('hello')\n", encoding="utf-8")
        (src / "operator-profile.yaml").write_text("real: true\n", encoding="utf-8")

        ruleset = tmp / "ip-ruleset.example.yaml"
        ruleset.write_text("version: 1\nbanned_terms: {clients: [], infra: [], identity: []}\nderived: {filenames: [], content: []}\n", encoding="utf-8")

        manifest = {
            "kit": {"name": "fixture-kit", "version": "1.0.0", "license": "MIT", "author": "Test Author", "year": 2026, "source_root": "src"},
            "include": ["**"],
            "exclude": ["operator-profile.yaml"],
            "generate": {"license": True, "sanitizacao_md": True, "checksums": True, "zip": True},
            "lint": {"ruleset": "ip-ruleset.example.yaml", "fail_on": "block"},
        }

        out_dir = tmp / "dist"
        out_dir.mkdir()

        code, report = run_pipeline(manifest, tmp, out_dir, dry_run=True, strict=False)
        assert code == 0 and report["status"] == "dry-run", f"dry-run failed: {report}"
        assert "operator-profile.yaml" not in report["files"], "exclude did not work in the dry-run"
        assert "README.md" in report["files"] and "scripts/hello.py" in report["files"]

        code1, report1 = run_pipeline(manifest, tmp, out_dir, dry_run=False, strict=False)
        assert code1 == 0, f"1st emission should be exit 0: {report1}"
        final_dir = Path(report1["out"])
        assert (final_dir / "LICENSE").exists(), "LICENSE not generated"
        for fname in _SANITIZATION_FILES:
            assert (final_dir / fname).exists(), f"{fname} not generated"
        assert not (final_dir / "SANITIZACAO.md").exists(), "the old name is being emitted again"
        assert (final_dir / "CHECKSUMS.txt").exists(), "CHECKSUMS.txt not generated"
        assert not (final_dir / "operator-profile.yaml").exists(), "excluded file leaked into the kit"
        assert Path(report1["zip"]).exists(), "zip not generated"

        code2, report2 = run_pipeline(manifest, tmp, out_dir, dry_run=False, strict=False)
        assert code2 == 0 and report2["status"] == "no-op", f"2nd emission should be a no-op: {report2}"

        (src / "scripts" / "hello.py").write_text("print('hello v2')\n", encoding="utf-8")
        code3, report3 = run_pipeline(manifest, tmp, out_dir, dry_run=False, strict=False)
        assert code3 == 0 and report3["status"] == "emitted", f"a real change should re-emit: {report3}"

        (src / "scripts" / "leak.py").write_text('token = "sk-ant-FAKE1234567890abcd"\n', encoding="utf-8")
        code4, report4 = run_pipeline(manifest, tmp, out_dir, dry_run=False, strict=False)
        assert code4 == 2, f"sabotage should block: {report4}"
        assert not any(p.name.startswith(".staging-") for p in out_dir.iterdir()), "temporary staging leaked (was not cleaned up)"
        (src / "scripts" / "leak.py").unlink()

        bad_manifest = {"kit": {"name": "x"}, "include": []}
        code5, report5 = run_pipeline(bad_manifest, tmp, out_dir, dry_run=False, strict=False)
        assert code5 == 3, f"invalid manifest should exit 3: {report5}"

        # The test that FORCES A FAIL (gateguard section NASCIMENTO DE GATE): plugin.json in the
        # source with a version diverging from the manifest has to exit 3 WITHOUT anyone injecting plugin_json.
        (src / ".claude-plugin").mkdir()
        (src / ".claude-plugin" / "plugin.json").write_text('{"name": "fixture-kit", "version": "9.9.9"}\n', encoding="utf-8")
        code6, report6 = run_pipeline(manifest, tmp, out_dir, dry_run=True, strict=False)
        assert code6 == 3 and any("diverge" in e for e in report6.get("errors", [])), f"divergent plugin.json should exit 3: {report6}"
        (src / ".claude-plugin" / "plugin.json").write_text('{"name": "fixture-kit", "version": "1.0.0"}\n', encoding="utf-8")
        code7, report7 = run_pipeline(manifest, tmp, out_dir, dry_run=True, strict=False)
        assert code7 == 0 and report7["status"] == "dry-run", f"plugin.json equal to the manifest should pass: {report7}"

        print("self-test OK — dry-run, emission, no-op, re-emission, sabotage, invalid manifest and divergent plugin.json covered")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kit_assembler.py")
    p.add_argument("--manifest", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", dest="json_out", default=None)
    p.add_argument("--strict", action="store_true")
    p.add_argument("--self-test", action="store_true")
    return p


def main(argv) -> int:
    args = build_parser().parse_args(argv)

    if args.self_test:
        return _self_test()

    if not args.manifest:
        print("usage: kit_assembler.py --manifest <manifest.yaml> [--out dir] [--dry-run] [--json out.json] [--strict]", file=sys.stderr)
        return 3

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"kit_assembler: manifest not found: {manifest_path}", file=sys.stderr)
        return 3

    try:
        manifest = load_manifest(manifest_path)
    except Exception as e:  # noqa: BLE001
        print(f"kit_assembler: invalid manifest: {e}", file=sys.stderr)
        return 3

    out_dir = Path(args.out) if args.out else (_ROOT / "dist")
    out_dir.mkdir(parents=True, exist_ok=True)

    code, report = run_pipeline(manifest, manifest_path.parent, out_dir, args.dry_run, args.strict)

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))

    return code


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
