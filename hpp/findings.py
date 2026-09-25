"""Review lenses: one read-only reviewer per kind of defect, all answering in one fixed shape.

A lens looks at a change for ONE kind of defect and reports an `hpp.findings/v1` document. The
harness ships four lenses as read-only agents in the operator module; this module holds the shape
they answer in, so a finding can be counted, compared across rounds and later seated in a review
panel. It never reads the change itself and never calls a model.

- `verification-gap`  behaviour the change adds or alters that no test would notice breaking;
- `partial-set`       a change applied to some members of a set and not the others;
- `deletion`          something removed while something still depends on it;
- `stale-evidence`    proof cited for the change that predates the change, or was never re-run.

Rules the shape enforces, each a way a review goes wrong in practice:

- A key the contract does not define rejects the whole document. A reviewer that improvises the
  form is improvising the judgement, and its well-formed fields are no more trustworthy.
- `inspected` is required and non-empty. "Found nothing" without the universe searched cannot be
  told apart from "looked at nothing".
- The verdict is derived from the findings (`fail` on any high, `warn` on any other, `pass` on
  none); a reviewer cannot declare it.
- The same finding (code, file, line) twice is refused: rephrasing a finding is not a second one.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Optional

SCHEMA = "hpp.findings/v1"
LENSES = ("verification-gap", "partial-set", "deletion", "stale-evidence")
SEVERITIES = ("high", "medium", "low")
_DOCUMENT_KEYS = {"schema", "lens", "subject_sha256", "inspected", "findings"}
_FINDING_KEYS = {"code", "severity", "file", "line", "claim", "evidence", "fix"}
_LENS = re.compile(r"[a-z][a-z0-9-]{0,62}\Z")
_CODE = re.compile(r"[A-Z][A-Z0-9_]{1,63}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class FindingsError(ValueError):
    """A findings document does not satisfy the contract."""


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FindingsError(f"{label} must be non-empty text")
    return value


def _texts(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
        raise FindingsError(f"{label} must be a non-empty list of non-empty strings")
    return list(value)


def _finding(raw: Any, index: int) -> dict[str, Any]:
    where = f"finding {index}"
    if not isinstance(raw, dict):
        raise FindingsError(f"{where} must be an object")
    extra = sorted(set(raw) - _FINDING_KEYS)
    if extra:
        raise FindingsError(f"{where} carries keys the contract does not define: {extra}; the whole document is refused")
    code = raw.get("code")
    if not isinstance(code, str) or not _CODE.fullmatch(code):
        raise FindingsError(f"{where}: code must be a stable UPPER_SNAKE identifier, got {code!r}")
    if raw.get("severity") not in SEVERITIES:
        raise FindingsError(f"{where}: severity must be one of {', '.join(SEVERITIES)}")
    line = raw.get("line")
    if line is not None and (isinstance(line, bool) or not isinstance(line, int) or line < 1):
        raise FindingsError(f"{where}: line must be a line number from 1, or null for the whole file")
    finding = {"code": code, "severity": raw["severity"], "file": _text(raw.get("file"), f"{where}: file"),
               "line": line, "claim": _text(raw.get("claim"), f"{where}: claim"),
               "evidence": _texts(raw.get("evidence"), f"{where}: evidence")}
    if "fix" in raw:
        finding["fix"] = _text(raw["fix"], f"{where}: fix")
    return finding


def _file_key(path: str) -> str:
    """One spelling per file, so `checkout.py`, `./checkout.py` and a backslash-separated path compare equal."""
    key = path.strip().replace("\\", "/")
    while key.startswith("./"):
        key = key[2:]
    return key


def check(document: Any, subject: Optional[bytes] = None) -> dict[str, Any]:
    """The normalised document with its derived verdict and counts, or FindingsError.

    With `subject` (the bytes of the change reviewed), the document must name that change by its
    sha256: a review of another change is refused, not read as a review of this one.
    """
    if not isinstance(document, dict):
        raise FindingsError("a findings document must be an object")
    extra = sorted(set(document) - _DOCUMENT_KEYS)
    if extra:
        raise FindingsError(f"the document carries keys the contract does not define: {extra}")
    if document.get("schema") != SCHEMA:
        raise FindingsError(f"schema must be {SCHEMA}")
    lens = document.get("lens")
    if not isinstance(lens, str) or not _LENS.fullmatch(lens):
        raise FindingsError(f"lens must be a lowercase slug such as {LENSES[0]!r}, got {lens!r}")
    named = document.get("subject_sha256")
    if not isinstance(named, str) or not _HEX64.fullmatch(named):
        raise FindingsError("subject_sha256 must be the 64-character sha256 of the change reviewed")
    if subject is not None and hashlib.sha256(subject).hexdigest() != named:
        raise FindingsError("subject_sha256 names another change than the one given; this review is not of it")
    inspected = _texts(document.get("inspected"), "inspected (what the lens looked at)")
    raw = document.get("findings")
    if not isinstance(raw, list):
        raise FindingsError("findings must be a list (empty when nothing was found)")
    findings = [_finding(item, index) for index, item in enumerate(raw)]
    seen: set[tuple[str, str, Any]] = set()
    for item in findings:
        key = (item["code"], _file_key(item["file"]), item["line"])
        if key in seen:
            raise FindingsError(f"the same finding {item['code']} at {item['file']}:{item['line']} is reported twice")
        seen.add(key)
    counts = {severity: sum(item["severity"] == severity for item in findings) for severity in SEVERITIES}
    verdict = "fail" if counts["high"] else "warn" if findings else "pass"
    return {"schema": SCHEMA, "lens": lens, "subject_sha256": named, "inspected": inspected,
            "findings": findings, "counts": counts, "verdict": verdict}


def exit_for(reports: list[dict[str, Any]]) -> int:
    """0 when every review passed; 1 when any lens found something."""
    return 0 if all(report["verdict"] == "pass" for report in reports) else 1
