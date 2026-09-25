"""Review lenses report in one fixed shape, so a finding can be counted, compared and seated.

A lens is a read-only reviewer that looks at a change for ONE kind of defect. Whatever the lens,
it answers with an `hpp.findings/v1` document, and `hpp findings check` holds the shape:

- every finding names a stable `code`, a `severity`, a `file` and a `line`, the `claim` and the
  `evidence` it rests on — the same finding in two rounds reads the same way;
- a key the contract does not define rejects the WHOLE document: a reviewer that improvises the
  form is improvising the judgement too;
- an empty review is not a pass unless it says what it inspected: "found nothing" without the
  universe is indistinguishable from "looked at nothing";
- the verdict is derived from the findings, never declared by the reviewer.
"""
from __future__ import annotations

import copy
import json

import pytest

from hpp import cli
from hpp.findings import LENSES, FindingsError, check

SUBJECT = "a" * 64


def _finding(**overrides):
    finding = {"code": "UNTESTED_BRANCH", "severity": "medium", "file": "billing/invoice.py", "line": 42,
               "claim": "the new refund branch has no test that fails when it breaks",
               "evidence": ["grep -n refund tests/ -> no match"]}
    finding.update(overrides)
    return finding


def _document(*findings, **overrides):
    document = {"schema": "hpp.findings/v1", "lens": "verification-gap", "subject_sha256": SUBJECT,
                "inspected": ["billing/invoice.py", "tests/test_invoice.py"], "findings": list(findings)}
    document.update(overrides)
    return document


def test_the_four_shipped_lenses_are_named():
    assert LENSES == ("verification-gap", "partial-set", "deletion", "stale-evidence")


def test_a_finding_document_is_checked_and_its_verdict_derived():
    report = check(_document(_finding(), _finding(code="MISSING_NEGATIVE_CASE", severity="low", line=50)))
    assert report["verdict"] == "warn"
    assert report["counts"] == {"high": 0, "medium": 1, "low": 1}
    assert [item["code"] for item in report["findings"]] == ["UNTESTED_BRANCH", "MISSING_NEGATIVE_CASE"]


def test_a_high_finding_fails_the_review():
    assert check(_document(_finding(severity="high")))["verdict"] == "fail"


def test_CONTROLE_an_empty_review_that_names_what_it_inspected_passes():
    report = check(_document())
    assert (report["verdict"], report["counts"]) == ("pass", {"high": 0, "medium": 0, "low": 0})


def test_an_empty_review_that_inspected_nothing_is_refused():
    with pytest.raises(FindingsError, match="inspected"):
        check(_document(inspected=[]))


@pytest.mark.parametrize("change, fragment", [
    ({"verdict": "pass"}, "does not define"),
    ({"schema": "hpp.findings/v0"}, "schema"),
    ({"lens": "Verification Gap"}, "lens"),
    ({"subject_sha256": "abc"}, "subject_sha256"),
    ({"findings": "none"}, "findings"),
])
def test_the_document_contract_refuses_each_malformed_document(change, fragment):
    with pytest.raises(FindingsError, match=fragment):
        check(_document(_finding(), **change))


@pytest.mark.parametrize("change, fragment", [
    ({"confidence": 0.9}, "does not define"),
    ({"code": "untested branch"}, "code"),
    ({"severity": "critical"}, "severity"),
    ({"file": ""}, "file"),
    ({"line": 0}, "line"),
    ({"line": True}, "line"),
    ({"claim": " "}, "claim"),
    ({"evidence": []}, "evidence"),
    ({"evidence": ["ok", ""]}, "evidence"),
    ({"fix": 3}, "fix"),
])
def test_the_finding_contract_refuses_each_malformed_finding(change, fragment):
    with pytest.raises(FindingsError, match=fragment):
        check(_document(_finding(**change)))


def test_a_finding_about_a_whole_file_has_no_line():
    report = check(_document(_finding(code="FILE_DELETED_WITH_READERS", line=None, fix="keep the file or move its readers")))
    assert report["findings"][0]["line"] is None
    assert report["findings"][0]["fix"] == "keep the file or move its readers"


def test_the_same_finding_twice_is_refused():
    with pytest.raises(FindingsError, match="twice"):
        check(_document(_finding(), _finding(claim="said again in other words")))


def test_a_custom_lens_is_allowed_by_its_slug():
    assert check(_document(lens="migration-order"))["lens"] == "migration-order"


def test_cli_findings_check_follows_the_exit_contract(tmp_path, capsys):
    def write(name, value):
        path = tmp_path / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return str(path)

    assert cli.main(["findings", "check", write("clean.json", _document())]) == 0
    assert cli.main(["findings", "check", write("found.json", _document(_finding()))]) == 1
    bad = copy.deepcopy(_document(_finding()))
    bad["findings"][0]["confidence"] = 1
    assert cli.main(["findings", "check", write("bad.json", bad)]) == 2
    capsys.readouterr()
    assert cli.main(["findings", "check", str(tmp_path / "clean.json"), str(tmp_path / "found.json")]) == 1
    reports = json.loads(capsys.readouterr().out)
    assert [item["verdict"] for item in reports["reports"]] == ["pass", "warn"]


def test_CONTROLE_the_checker_is_not_refusing_everything():
    """Every refusal above is paired with this: the same shape, well-formed, is accepted."""
    for lens in LENSES:
        assert check(_document(_finding(), lens=lens))["verdict"] == "warn"


def test_the_documented_example_answers_what_its_readme_says(capsys):
    """The two shipped reviews: one passes with its universe stated, one finds a caller left behind,
    and both name the change they reviewed by the sha256 of `change.diff`."""
    import hashlib
    from pathlib import Path

    example = Path(__file__).resolve().parent.parent / "examples" / "review-lenses"
    subject = hashlib.sha256((example / "change.diff").read_bytes()).hexdigest()
    clean = str(example / "deletion-clean.json")
    found = str(example / "partial-set.json")
    assert cli.main(["findings", "check", clean]) == 0
    capsys.readouterr()
    assert cli.main(["findings", "check", clean, found]) == 1
    reports = json.loads(capsys.readouterr().out)["reports"]
    assert [(item["lens"], item["verdict"]) for item in reports] == [("deletion", "pass"), ("partial-set", "warn")]
    assert reports[1]["findings"][0]["code"] == "CALLER_NOT_UPDATED"
    assert {item["subject_sha256"] for item in reports} == {subject}


# --------------------------------------------------------------------------- adversarial review, round 1


def test_FINDING_DUP_PATH_NOT_NORMALISED_the_same_file_written_two_ways_is_one_finding():
    for other in ("./billing/invoice.py", "billing\\invoice.py", " billing/invoice.py"):
        with pytest.raises(FindingsError, match="twice"):
            check(_document(_finding(), _finding(file=other, claim="again")))


def test_FINDINGS_SUBJECT_UNBOUND_a_review_of_another_change_is_refused(tmp_path, capsys):
    import hashlib
    change = tmp_path / "change.diff"
    change.write_bytes(b"--- a/x\n+++ b/x\n")
    subject = hashlib.sha256(change.read_bytes()).hexdigest()
    bound = tmp_path / "bound.json"
    bound.write_text(json.dumps(_document(subject_sha256=subject)), encoding="utf-8")
    other = tmp_path / "other.json"
    other.write_text(json.dumps(_document()), encoding="utf-8")
    assert check(_document(subject_sha256=subject), subject=change.read_bytes())["verdict"] == "pass"
    with pytest.raises(FindingsError, match="another change"):
        check(_document(), subject=change.read_bytes())
    assert cli.main(["findings", "check", str(bound), "--subject", str(change)]) == 0
    assert cli.main(["findings", "check", str(other), "--subject", str(change)]) == 2
