"""Every acceptance criterion carries a stable id, and a test has to name it.

The product's own thesis is "what counts as proof". A WorkGraph whose `acceptance`
entries are anonymous strings cannot state which test proves which criterion, so the
first consumer of the coverage check is this suite: the spec below describes the two
capabilities this wave delivers, and `test_the_suite_covers_its_own_spec` fails the
moment a criterion here has no test naming it with a spec marker of the form
`[spec: <capability>/<scenario>]`, or a marker names a criterion that does not exist.

A citation is read from a DOCSTRING, never from arbitrary source text: a fixture that
carries a marker as test data is describing the form, not claiming coverage, and a
regex over the raw file counts the two the same way.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from hpp.workgraph import WorkGraphError, compile_workgraph, find_spec_markers, spec_coverage

TESTS_DIR = Path(__file__).resolve().parent

# The acceptance spec of this wave. Each criterion below must be named by a test in
# TESTS_DIR; adding one here without a `[spec:]` marker turns the suite red.
WAVE_SPEC = {
    "work": [
        {
            "id": "spec-coverage",
            "tier": "economy",
            "acceptance": [
                {"id": "criterion-has-stable-id", "text": "every acceptance criterion is compiled with a stable capability/scenario id"},
                {"id": "orphan-criterion-fails", "text": "a criterion that no source names is reported as an orphan"},
                {"id": "marker-without-criterion-is-unknown", "text": "a marker naming no declared criterion is reported as unknown, never as coverage"},
            ],
        },
        {
            "id": "done-gate",
            "tier": "balanced",
            "depends_on": ["spec-coverage"],
            "acceptance": [
                {"id": "unknown-predicate-rejected-at-compile", "text": "a gate that names a predicate the evaluator does not implement fails to compile"},
                {"id": "missing-fact-is-undetermined", "text": "a predicate whose fact was not measured is undetermined, never a pass"},
                {"id": "shared-index-is-not-evidence", "text": "a git fact measured through a shared index is undetermined, never a pass"},
                {"id": "empty-gate-decides-nothing", "text": "a gate with no predicate is undetermined, never a pass"},
            ],
        },
    ],
}


_DOC_HOLDERS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def docstrings(source: str) -> str:
    """Only what a module/class/function documents — not every string in the file."""
    found = []
    for node in ast.walk(ast.parse(source)):
        # isinstance FIRST: ast.get_docstring raises TypeError on any other node.
        if isinstance(node, _DOC_HOLDERS):
            text = ast.get_docstring(node, clean=False)
            if text:
                found.append(text)
    return "\n".join(found)


def _sources() -> dict[str, str]:
    return {path.name: docstrings(path.read_text(encoding="utf-8")) for path in sorted(TESTS_DIR.glob("*.py"))}


# ------------------------------------------------------------------------- the capability


def test_every_criterion_is_compiled_with_a_stable_id():
    """[spec: spec-coverage/criterion-has-stable-id]"""
    compiled = compile_workgraph(WAVE_SPEC)
    ids = [criterion["id"] for criterion in compiled["criteria"]]
    assert "spec-coverage/criterion-has-stable-id" in ids
    assert len(ids) == len(set(ids)) == 7
    # An id derived from the text is stable across compilations and readable.
    derived = compile_workgraph({"work": [{"id": "build", "tier": "economy", "acceptance": ["The artifact exists"]}]})
    assert derived["criteria"] == [{"id": "build/the-artifact-exists", "work": "build", "text": "The artifact exists"}]
    assert derived["work"][0]["acceptance"] == ["The artifact exists"]  # the plain list stays, for existing readers


def test_a_criterion_no_source_names_is_an_orphan():
    """[spec: spec-coverage/orphan-criterion-fails]"""
    compiled = compile_workgraph({"work": [{"id": "build", "tier": "economy", "acceptance": [
        {"id": "covered", "text": "a"}, {"id": "forgotten", "text": "b"}]}]})
    report = spec_coverage(compiled, {"test_x.py": "def t(): '[spec: build/covered]'"})
    assert report["orphans"] == ["build/forgotten"]
    assert [entry["id"] for entry in report["covered"]] == ["build/covered"]
    assert report["complete"] is False


def test_a_marker_that_names_nothing_is_unknown_and_not_coverage():
    """[spec: spec-coverage/marker-without-criterion-is-unknown]"""
    compiled = compile_workgraph({"work": [{"id": "build", "tier": "economy", "acceptance": [{"id": "real", "text": "a"}]}]})
    report = spec_coverage(compiled, {"test_typo.py": "'[spec: build/rael]'"})
    assert report["unknown"] == [{"id": "build/rael", "sources": ["test_typo.py"]}]
    assert report["orphans"] == ["build/real"]
    assert report["complete"] is False


# ------------------------------------------------------------------------- the wiring


def test_the_suite_covers_its_own_spec():
    """The harness is the first consumer: zero orphan criteria, zero broken citations.

    Universe: every `*.py` in this directory. A criterion is covered when some file here
    carries `[spec: <id>]`.
    """
    report = spec_coverage(compile_workgraph(WAVE_SPEC), _sources())
    assert report["orphans"] == [], f"criteria with no named test: {report['orphans']}"
    assert report["unknown"] == [], f"markers naming no declared criterion: {report['unknown']}"
    assert report["complete"] is True
    assert report["criteria"] == 7


# ------------------------------------------------------------------------- CONTROLS


def test_CONTROLE_the_coverage_check_can_fail():
    """A planted orphan must be SEEN; otherwise the green run above means nothing."""
    planted = {"work": [{"id": "build", "tier": "economy", "acceptance": [
        {"id": "planted-orphan", "text": "nothing names this"}]}]}
    report = spec_coverage(compile_workgraph(planted), _sources())
    assert report["orphans"] == ["build/planted-orphan"]
    assert report["complete"] is False


def test_CONTROLE_the_marker_reader_discriminates():
    """The reader must find a real marker and must not invent one out of prose."""
    assert find_spec_markers("prose [spec: a/b] more [spec:c/d]") == {"a/b", "c/d"}
    assert find_spec_markers("the word spec: appears but no bracket; [spec] alone; [spec: ]") == set()
    # A half id must not vanish (neither covered nor unknown): a typo in a citation would read
    # as "cites nothing" and the orphan check would never see the criterion it meant. It is
    # surfaced as `malformed:<text>` and routed to `unknown`.
    assert find_spec_markers("half an id [spec: nocapability]") == {"malformed:nocapability"}
    assert find_spec_markers("a space [spec: cap/first thing]") == {"malformed:cap/first thing"}
    # ...while the PLACEHOLDER that documents the form is not a citation of anything
    assert find_spec_markers("write it as [spec: <capability>/<scenario>]") == set()


def test_CONTROLE_a_marker_in_test_data_is_not_a_citation():
    """The fixture that DESCRIBES the form must not be counted as USING it."""
    module = 'def f():\n    """doc [spec: real/one]"""\n    data = "[spec: fake/two]"\n    return data\n'
    assert find_spec_markers(module) == {"real/one", "fake/two"}   # the raw file cannot tell them apart
    assert find_spec_markers(docstrings(module)) == {"real/one"}   # the tokenizer can


def test_a_colliding_derived_id_fails_loudly_instead_of_merging_criteria():
    """Two criteria whose text slugs to the same scenario must not silently become one."""
    with pytest.raises(WorkGraphError, match="duplicate acceptance criterion id"):
        compile_workgraph({"work": [{"id": "build", "tier": "economy", "acceptance": ["Ship it!", "ship it"]}]})
