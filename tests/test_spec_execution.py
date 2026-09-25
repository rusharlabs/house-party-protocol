"""A criterion a test names is not a criterion a test ran.

`spec_coverage` answers "does some test cite this criterion?". A skipped test still cites it, a
test that was never collected still cites it, and a failing test still cites it: the citation
reads as coverage in all three cases. `spec_execution` joins the citations with a JUnit XML
report and keeps five buckets apart: `executed` (a citing test ran and passed), `failed`,
`cited_not_run` (skipped, absent from the report, or cited outside a test), `orphans` and
`unknown`.

Fixtures carry their markers inside string literals, never in a docstring of this module, so the
suite's own coverage check (`test_spec_coverage.py`) reads only the citations that are real.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from hpp import cli
from hpp.workgraph import (
    WorkGraphError,
    compile_workgraph,
    cited_tests,
    read_junit,
    spec_coverage,
    spec_execution,
)

PRODUCT_ROOT = Path(__file__).resolve().parent.parent

SPEC = {"work": [{"id": "pricing", "tier": "economy", "acceptance": [
    {"id": "member", "text": "members pay less"},
    {"id": "bulk", "text": "large orders pay less"},
]}]}

TEST_SOURCE = '''"""module doc"""
import pytest


def test_member():
    """[spec: pricing/member]"""


@pytest.mark.skip(reason="waiting for the bulk rule")
def test_bulk():
    """[spec: pricing/bulk]"""
'''


def _junit(*cases: str) -> str:
    body = "".join(cases)
    return (f'<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest" '
            f'tests="{len(cases)}">{body}</testsuite></testsuites>')


def _case(classname: str, name: str, child: str = "") -> str:
    return f'<testcase classname="{classname}" name="{name}" time="0.001">{child}</testcase>'


def _report(source: str, path: str, junit: str) -> dict:
    return spec_execution(compile_workgraph(SPEC), cited_tests(source, path), read_junit(junit))


def _ids(bucket: list[dict]) -> list[str]:
    return [entry["id"] for entry in bucket]


# --------------------------------------------------------------------------- reading the citations


def test_citations_are_read_per_test_and_keep_the_class():
    source = (
        '"""[spec: pricing/member]"""\n'
        'class TestPrices:\n'
        '    """[spec: pricing/bulk]"""\n'
        '    def test_bulk(self):\n'
        '        """[spec: pricing/bulk] [spec: pricing/member]"""\n'
        'def helper():\n'
        '    return "[spec: pricing/never]"\n'
    )
    assert cited_tests(source, "tests/test_prices.py") == [
        {"test": "tests/test_prices.py", "kind": "module", "cites": ["pricing/member"]},
        {"test": "tests/test_prices.py::TestPrices", "kind": "class", "cites": ["pricing/bulk"]},
        {"test": "tests/test_prices.py::TestPrices::test_bulk", "kind": "function",
         "cites": ["pricing/bulk", "pricing/member"]},
    ]


def test_a_source_that_is_not_python_is_refused():
    with pytest.raises(WorkGraphError, match="not valid Python"):
        cited_tests("def (:\n", "tests/test_broken.py")


# --------------------------------------------------------------------------- reading the report


def test_the_report_reads_every_outcome():
    cases = read_junit(_junit(
        _case("tests.test_x", "test_ok"),
        _case("tests.test_x", "test_bad", '<failure message="boom"/>'),
        _case("tests.test_x", "test_broken", '<error message="fixture"/>'),
        _case("tests.test_x", "test_later", '<skipped message="later"/>'),
    ))
    assert [(case["name"], case["outcome"]) for case in cases] == [
        ("test_ok", "passed"), ("test_bad", "failed"), ("test_broken", "error"), ("test_later", "skipped")]


def test_a_single_testsuite_root_is_read_too():
    cases = read_junit('<testsuite name="x"><testcase classname="m" name="test_a"/></testsuite>')
    assert cases == [{"classname": "m", "name": "test_a", "outcome": "passed"}]


def test_a_report_with_declarations_is_refused():
    """[spec: spec-execution/junit-with-declarations-refused]

    An entity declaration is how an XML file expands to gigabytes on read; the report is
    evidence from a test runner and never needs one.
    """
    bomb = '<?xml version="1.0"?><!DOCTYPE t [<!ENTITY a "aaaa">]><testsuites>&a;</testsuites>'
    with pytest.raises(WorkGraphError, match="DOCTYPE or ENTITY"):
        read_junit(bomb)
    with pytest.raises(WorkGraphError, match="DOCTYPE or ENTITY"):
        read_junit(bomb.encode("utf-8"))
    # the same declaration in UTF-16 would slip past a UTF-8 probe while the parser honours it
    with pytest.raises(WorkGraphError, match="must be UTF-8"):
        read_junit(bomb.replace('"1.0"', '"1.0" encoding="utf-16"').encode("utf-16"))


@pytest.mark.parametrize("text, message", [
    ("<testsuites><testsuite>", "not valid XML"),
    ("<results><case/></results>", "not a JUnit report"),
    ('<testsuite><testcase classname="m"/></testsuite>', "has no name"),
])
def test_a_report_that_is_not_junit_is_refused(text, message):
    with pytest.raises(WorkGraphError, match=message):
        read_junit(text)


# --------------------------------------------------------------------------- joining the two


def test_a_skipped_test_leaves_its_criterion_cited_but_not_run():
    """[spec: spec-execution/skipped-is-cited-not-run]"""
    report = _report(TEST_SOURCE, "tests/test_prices.py", _junit(
        _case("tests.test_prices", "test_member"),
        _case("tests.test_prices", "test_bulk", '<skipped message="waiting"/>'),
    ))
    assert report["schema"] == "hpp.spec-execution/v1"
    assert _ids(report["executed"]) == ["pricing/member"]
    assert report["cited_not_run"] == [{"id": "pricing/bulk", "tests": [
        {"test": "tests/test_prices.py::test_bulk", "outcome": "skipped"}]}]
    assert report["complete"] is False


def test_a_test_missing_from_the_report_leaves_its_criterion_not_run():
    """[spec: spec-execution/absent-from-junit-is-cited-not-run]

    A test that was deselected, or never collected, cites its criterion and proves nothing.
    """
    report = _report(TEST_SOURCE, "tests/test_prices.py", _junit(_case("tests.test_prices", "test_member")))
    assert report["cited_not_run"] == [{"id": "pricing/bulk", "tests": [
        {"test": "tests/test_prices.py::test_bulk", "outcome": "not-in-junit"}]}]
    assert (report["junit_testcases"], report["matched_testcases"]) == (1, 1)


def test_a_failing_test_does_not_execute_its_criterion():
    """[spec: spec-execution/failed-is-not-executed]

    When two tests cite one criterion and one of them fails, the criterion is failed: a pass
    elsewhere does not cancel a run that contradicts it.
    """
    source = TEST_SOURCE + '\n\ndef test_member_again():\n    """[spec: pricing/member]"""\n'
    report = _report(source, "tests/test_prices.py", _junit(
        _case("tests.test_prices", "test_member"),
        _case("tests.test_prices", "test_member_again", '<error message="teardown"/>'),
        _case("tests.test_prices", "test_bulk"),
    ))
    assert _ids(report["failed"]) == ["pricing/member"]
    assert _ids(report["executed"]) == ["pricing/bulk"]
    assert report["complete"] is False


def test_a_citation_outside_a_test_never_runs():
    """[spec: spec-execution/citation-outside-a-test-never-runs]

    A module or class docstring counts as a citation for `spec_coverage`, but no test runs it.
    """
    source = '"""[spec: pricing/member] [spec: pricing/bulk]"""\n\ndef test_member():\n    pass\n'
    report = _report(source, "tests/test_prices.py", _junit(_case("tests.test_prices", "test_member")))
    assert report["executed"] == []
    assert {entry["id"]: entry["tests"][0]["outcome"] for entry in report["cited_not_run"]} == {
        "pricing/bulk": "not-a-test", "pricing/member": "not-a-test"}


def test_parametrized_cases_count_for_their_function():
    report = _report(TEST_SOURCE.replace("@pytest.mark.skip(reason=\"waiting for the bulk rule\")\n", ""),
                     "tests/test_prices.py", _junit(
        _case("tests.test_prices", "test_member[gold]"),
        _case("tests.test_prices", "test_member[silver]"),
        _case("tests.test_prices", "test_bulk"),
    ))
    assert _ids(report["executed"]) == ["pricing/bulk", "pricing/member"]
    assert report["complete"] is True
    assert report["matched_testcases"] == 3


def test_orphans_and_unknown_markers_stay_apart():
    source = 'def test_member():\n    """[spec: pricing/member] [spec: pricing/rael]"""\n'
    report = _report(source, "tests/test_prices.py", _junit(_case("tests.test_prices", "test_member")))
    assert report["orphans"] == ["pricing/bulk"]
    assert report["unknown"] == [{"id": "pricing/rael", "sources": ["tests/test_prices.py::test_member"]}]


@pytest.mark.parametrize("path, classname", [
    ("tests/test_prices.py", "tests.test_prices"),
    ("test_prices.py", "tests.test_prices"),              # the runner's rootdir sits above the path given
    ("repo/tests/test_prices.py", "tests.test_prices"),   # the path given is longer than the module
    ("tests\\test_prices.py", "tests.test_prices"),       # a Windows path
])
def test_a_case_matches_by_module_suffix_and_name(path, classname):
    """[spec: spec-execution/junit-matches-by-module-and-name]"""
    report = _report(TEST_SOURCE, path, _junit(_case(classname, "test_member"), _case(classname, "test_bulk")))
    assert _ids(report["executed"]) == ["pricing/bulk", "pricing/member"]


def test_a_method_matches_through_its_class():
    source = 'class TestPrices:\n    def test_member(self):\n        """[spec: pricing/member]"""\n'
    matched = _report(source, "tests/test_prices.py", _junit(_case("tests.test_prices.TestPrices", "test_member")))
    assert _ids(matched["executed"]) == ["pricing/member"]
    unmatched = _report(source, "tests/test_prices.py", _junit(_case("tests.test_prices", "test_member")))
    assert matched["executed"] and not unmatched["executed"]


# --------------------------------------------------------------------------- the command


def _workspace(tmp_path: Path, source: str = TEST_SOURCE) -> tuple[Path, Path]:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_prices.py").write_text(source, encoding="utf-8")
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(SPEC), encoding="utf-8")
    return spec, tmp_path / "tests"


def test_without_a_report_the_command_answers_the_citation_question(tmp_path, capsys):
    spec, tests = _workspace(tmp_path)
    assert cli.main(["work", "coverage", str(spec), "--tests", str(tests)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["schema"] == "hpp.spec-coverage/v1"
    assert report["complete"] is True
    assert report["sources"] == 1


def test_with_a_report_the_command_answers_the_execution_question(tmp_path, capsys):
    spec, tests = _workspace(tmp_path)
    junit = tmp_path / "junit.xml"
    junit.write_text(_junit(_case("tests.test_prices", "test_member"),
                            _case("tests.test_prices", "test_bulk", "<skipped/>")), encoding="utf-8")
    assert cli.main(["work", "coverage", str(spec), "--tests", str(tests), "--junit", str(junit)]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["schema"] == "hpp.spec-execution/v1"
    assert _ids(report["cited_not_run"]) == ["pricing/bulk"]
    assert report["junit"] == [str(junit)]


def test_the_command_refuses_what_it_cannot_measure(tmp_path):
    spec, tests = _workspace(tmp_path)
    bomb = tmp_path / "bomb.xml"
    bomb.write_text('<!DOCTYPE t [<!ENTITY a "a">]><testsuites/>', encoding="utf-8")
    empty = tmp_path / "empty"
    empty.mkdir()
    notes = tmp_path / "notes.md"
    notes.write_text("[spec: pricing/member]", encoding="utf-8")
    assert cli.main(["work", "coverage", str(spec), "--tests", str(tests), "--junit", str(bomb)]) == 2
    assert cli.main(["work", "coverage", str(spec), "--tests", str(empty)]) == 2, "an empty universe is not coverage"
    assert cli.main(["work", "coverage", str(spec), "--tests", str(notes)]) == 2, "only Python sources are read"
    assert cli.main(["work", "coverage", str(spec), "--tests", str(tmp_path / "missing")]) == 2
    assert cli.main(["work", "coverage", str(spec), "--tests", str(tests), "--junit", str(tmp_path / "no.xml")]) == 2


def test_the_real_runner_report_is_read_as_the_runner_wrote_it(tmp_path, capsys):
    """The report here is written by pytest itself, not by hand: the matching rule is proved
    against the format it has to read, not against a fixture shaped after the rule."""
    spec, tests = _workspace(tmp_path)
    junit = tmp_path / "junit.xml"
    run = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider",
                          f"--junitxml={junit}"], cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stdout + run.stderr
    assert cli.main(["work", "coverage", str(spec), "--tests", str(tests), "--junit", str(junit)]) == 1
    report = json.loads(capsys.readouterr().out)
    assert _ids(report["executed"]) == ["pricing/member"]
    assert report["cited_not_run"][0]["tests"][0]["outcome"] == "skipped"
    assert report["matched_testcases"] == 2


# --------------------------------------------------------------------------- the shipped example

EXAMPLE = "examples/cited-and-run"


def test_the_documented_example_measures_what_its_readme_says(tmp_path, capsys, monkeypatch):
    root = tmp_path / "product"
    (root / EXAMPLE).mkdir(parents=True)
    for name in ("workgraph.json", "check_prices.py"):
        (root / EXAMPLE / name).write_bytes((PRODUCT_ROOT / EXAMPLE / name).read_bytes())
    monkeypatch.chdir(root)
    spec, source = f"{EXAMPLE}/workgraph.json", f"{EXAMPLE}/check_prices.py"
    assert cli.main(["work", "coverage", spec, "--tests", source]) == 0
    assert json.loads(capsys.readouterr().out)["complete"] is True
    run = subprocess.run([sys.executable, "-m", "pytest", source, "-q", "-p", "no:cacheprovider",
                          "--junitxml=out/cited-and-run.xml"], cwd=root, capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stdout + run.stderr
    assert cli.main(["work", "coverage", spec, "--tests", source, "--junit", "out/cited-and-run.xml"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert _ids(report["executed"]) == ["pricing/member-discount", "pricing/rounding"]
    assert report["cited_not_run"] == [{"id": "pricing/bulk-discount", "tests": [
        {"test": f"{EXAMPLE}/check_prices.py::test_bulk_discount", "outcome": "skipped"}]}]


# --------------------------------------------------------------------------- CONTROLS


def test_CONTROLE_the_citation_question_alone_calls_the_skipped_criterion_covered():
    """The defect this feature exists for, measured: without the report the skipped criterion
    reads as covered, and with the report the same inputs are not complete. If both answered
    the same, the report would add nothing."""
    compiled = compile_workgraph(SPEC)
    cited = spec_coverage(compiled, {"tests/test_prices.py": TEST_SOURCE})
    assert cited["complete"] is True
    executed = _report(TEST_SOURCE, "tests/test_prices.py", _junit(
        _case("tests.test_prices", "test_member"), _case("tests.test_prices", "test_bulk", "<skipped/>")))
    assert executed["complete"] is False


def test_CONTROLE_the_same_inputs_with_the_test_run_are_complete():
    """The negative above must turn positive when the only change is that the test ran."""
    report = _report(TEST_SOURCE, "tests/test_prices.py", _junit(
        _case("tests.test_prices", "test_member"), _case("tests.test_prices", "test_bulk")))
    assert report["complete"] is True
    assert report["cited_not_run"] == report["failed"] == report["orphans"] == report["unknown"] == []


def test_CONTROLE_a_same_named_test_in_another_module_does_not_match():
    """The matcher must tell modules apart, or any `test_member` anywhere would execute the criterion."""
    report = _report(TEST_SOURCE, "tests/test_prices.py", _junit(
        _case("tests.test_orders", "test_member"), _case("tests.test_orders", "test_bulk")))
    assert report["executed"] == []
    assert report["matched_testcases"] == 0
    assert report["junit_testcases"] == 2


def test_CONTROLE_an_empty_report_executes_nothing():
    """Zero test cases is a report with no sample, never a pass."""
    report = _report(TEST_SOURCE, "tests/test_prices.py", "<testsuites/>")
    assert report["junit_testcases"] == 0
    assert report["executed"] == [] and report["complete"] is False


# --------------------------------------------------------------------------- adversarial review, round 1
# Each test reproduces a defect the reviewer found in the first version of `work coverage`.


def test_SHADOWED_TEST_COUNTED_EXECUTED_a_citing_test_redefined_later_never_ran():
    source = ('import pytest\n\n\ndef test_member():\n    """[spec: pricing/member]"""\n    pytest.skip()\n\n\n'
              'def test_member():\n    assert True\n\n\ndef test_bulk():\n    """[spec: pricing/bulk]"""\n')
    report = _report(source, "tests/test_prices.py", _junit(
        _case("tests.test_prices", "test_member"), _case("tests.test_prices", "test_bulk")))
    assert report["cited_not_run"] == [{"id": "pricing/member", "tests": [
        {"test": "tests/test_prices.py::test_member", "outcome": "shadowed"}]}]
    assert _ids(report["executed"]) == ["pricing/bulk"]


def test_SUFFIX_MATCH_AMBIGUOUS_one_citing_test_matching_two_modules_is_not_executed():
    source = 'def test_create():\n    """[spec: pricing/member]"""\n'
    report = _report(source, "test_api.py", _junit(
        _case("tests.unit.test_api", "test_create", "<skipped/>"),
        _case("tests.integration.test_api", "test_create")))
    assert report["cited_not_run"][0]["tests"] == [{"test": "test_api.py::test_create", "outcome": "ambiguous"}]
    assert report["executed"] == []


def test_CONTROLE_the_full_path_disambiguates_the_same_report():
    source = 'def test_create():\n    """[spec: pricing/member]"""\n'
    report = _report(source, "tests/unit/test_api.py", _junit(
        _case("tests.unit.test_api", "test_create", "<skipped/>"),
        _case("tests.integration.test_api", "test_create")))
    assert report["cited_not_run"][0]["tests"][0]["outcome"] == "skipped"


def test_DOTTED_DIR_NEVER_MATCHES_a_directory_with_a_dot_in_its_name_still_matches():
    source = 'def test_member():\n    """[spec: pricing/member]"""\n'
    report = _report(source, "lane-kit-1.5.0/tests/test_prices.py",
                     _junit(_case("lane-kit-1.5.0.tests.test_prices", "test_member")))
    assert _ids(report["executed"]) == ["pricing/member"]
    other = _report(source, "lane-kit-1.5.0/tests/test_prices.py",
                    _junit(_case("kit-1.5.0.tests.test_prices", "test_member")))
    assert other["executed"] == [], "a dotted suffix matches at a boundary, never inside a name"


def test_JUNIT_UNKNOWN_ENCODING_EXIT3_an_unknown_encoding_is_a_refusal():
    with pytest.raises(WorkGraphError):
        read_junit(b'<?xml version="1.0" encoding="x-nope"?><testsuite/>')


def test_JUNIT_NON_UTF8_ACCEPTED_a_latin1_report_is_refused():
    latin = '<?xml version="1.0" encoding="ISO-8859-1"?><testsuite><testcase classname="m" name="t\xe9"/></testsuite>'
    with pytest.raises(WorkGraphError, match="UTF-8"):
        read_junit(latin.encode("latin-1"))
    with pytest.raises(WorkGraphError, match="UTF-8"):
        read_junit(b'<testsuite><testcase classname="m" name="t\xe9"/></testsuite>')


def test_STALE_JUNIT_COUNTS_AS_RUN_a_source_edited_after_the_report_is_not_executed(tmp_path, capsys):
    spec, tests = _workspace(tmp_path, TEST_SOURCE.replace('@pytest.mark.skip(reason="waiting for the bulk rule")\n', ""))
    junit = tmp_path / "junit.xml"
    junit.write_text(_junit(_case("tests.test_prices", "test_member"), _case("tests.test_prices", "test_bulk")),
                     encoding="utf-8")
    assert cli.main(["work", "coverage", str(spec), "--tests", str(tests), "--junit", str(junit)]) == 0
    before = json.loads(capsys.readouterr().out)
    assert before["reports"][0]["sha256"] and before["stale_sources"] == []
    source = tests / "test_prices.py"
    later = junit.stat().st_mtime + 60
    os.utime(source, (later, later))
    assert cli.main(["work", "coverage", str(spec), "--tests", str(tests), "--junit", str(junit)]) == 1
    after = json.loads(capsys.readouterr().out)
    assert after["stale_sources"] == [source.as_posix()]
    assert after["complete"] is False
