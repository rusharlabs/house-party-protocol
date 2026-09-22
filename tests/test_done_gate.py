""""Done" is a question with a git answer, asked through ONE shared evaluator.

The gate is declared in the spec (`done_gate` / per-unit `gate`), resolved at compile
time and answered by `evaluate_done_gate`. Automation cannot slip past it, because the
three ways a gate dies in silence are all closed here: an unknown predicate fails the
COMPILE, an unmeasured fact is `undetermined` (never a pass), and an empty gate is
`undetermined` (never a pass). A git fact read through a shared index is not evidence,
so it is `undetermined` too.

Adapted from phodal/routa (MIT) — concept only, no code reused.
"""
from __future__ import annotations

import pytest

from hpp.workgraph import DONE_GATE_PREDICATES, WorkGraphError, compile_workgraph, evaluate_done_gate

CLEAN = {"index": "private", "dirty_paths": [], "commits": 2, "review_ready": True, "evidence_ref": "run-17"}
FULL_GATE = ["clean_worktree", "committed_changes", "review_ready", "evidence_ref_exists"]


def _unit(gate=None, **extra):
    item = {"id": "build", "tier": "balanced", "acceptance": ["artifact exists"], **extra}
    if gate is not None:
        item["gate"] = gate
    return {"work": [item]}


# ------------------------------------------------------------------------- the capability


def test_a_declared_gate_is_resolved_onto_every_work_unit():
    compiled = compile_workgraph({"done_gate": ["clean_worktree"], "work": [
        {"id": "spec", "tier": "economy", "acceptance": ["scope"]},
        {"id": "build", "tier": "balanced", "acceptance": ["artifact"], "depends_on": ["spec"],
         "gate": FULL_GATE},
    ]})
    by_id = {item["id"]: item for item in compiled["work"]}
    assert by_id["spec"]["gate"] == ["clean_worktree"]          # inherits the spec default
    assert by_id["build"]["gate"] == FULL_GATE                   # the unit overrides it
    assert compiled["done_gate"] == ["clean_worktree"]


def test_a_gate_whose_facts_are_all_measured_and_green_passes():
    verdict = evaluate_done_gate(FULL_GATE, CLEAN)
    assert verdict["verdict"] == "pass"
    assert [entry["verdict"] for entry in verdict["predicates"]] == ["pass"] * 4


def test_a_dirty_worktree_fails_the_gate_and_names_the_paths():
    verdict = evaluate_done_gate(["clean_worktree"], {**CLEAN, "dirty_paths": ["a.py", "b.py"]})
    assert verdict["verdict"] == "fail"
    assert "2" in verdict["predicates"][0]["reason"]


def test_an_unknown_predicate_is_rejected_at_compile_time():
    """[spec: done-gate/unknown-predicate-rejected-at-compile]"""
    with pytest.raises(WorkGraphError, match="unknown done gate predicate: requireBlessing"):
        compile_workgraph(_unit(["clean_worktree", "requireBlessing"]))
    with pytest.raises(WorkGraphError, match="unknown done gate predicate"):
        evaluate_done_gate(["requireBlessing"], CLEAN)


def test_a_fact_that_was_not_measured_is_undetermined_not_a_pass():
    """[spec: done-gate/missing-fact-is-undetermined]"""
    facts = {key: value for key, value in CLEAN.items() if key != "review_ready"}
    verdict = evaluate_done_gate(FULL_GATE, facts)
    assert verdict["verdict"] == "undetermined"
    assert [entry["verdict"] for entry in verdict["predicates"]] == ["pass", "pass", "undetermined", "pass"]
    assert "not measured" in verdict["predicates"][2]["reason"]


def test_a_git_fact_read_through_a_shared_index_is_not_evidence():
    """[spec: done-gate/shared-index-is-not-evidence]"""
    for index in ("shared", None):
        facts = {**CLEAN}
        if index is None:
            facts.pop("index")
        else:
            facts["index"] = index
        verdict = evaluate_done_gate(["clean_worktree", "committed_changes"], facts)
        assert verdict["verdict"] == "undetermined", index
        assert all("index" in entry["reason"] for entry in verdict["predicates"]), index
    # CONTROLE: the non-git predicates of the same bundle still answer, so the rule is
    # scoped to the facts git produces and not a blanket refusal.
    assert evaluate_done_gate(["review_ready"], {"review_ready": True})["verdict"] == "pass"


def test_a_gate_with_no_predicate_decides_nothing():
    """[spec: done-gate/empty-gate-decides-nothing]"""
    verdict = evaluate_done_gate([], CLEAN)
    assert verdict["verdict"] == "undetermined"
    assert "empty gate" in verdict["reason"]
    # Declaring an empty gate in the spec is louder still: it fails the compile.
    with pytest.raises(WorkGraphError, match="empty done gate"):
        compile_workgraph(_unit([]))
    with pytest.raises(WorkGraphError, match="empty done gate"):
        compile_workgraph({"done_gate": [], "work": [{"id": "a", "tier": "economy", "acceptance": ["x"]}]})


def test_an_undeclared_gate_leaves_the_unit_ungated_and_that_is_visible():
    compiled = compile_workgraph(_unit())
    assert compiled["work"][0]["gate"] == []
    assert compiled["done_gate"] == []


# ------------------------------------------------------------------------- CONTROLS


def test_CONTROLE_the_evaluator_can_return_each_of_the_three_verdicts():
    """A gate that could only ever say one thing would be vacuous."""
    said = {
        evaluate_done_gate(["review_ready"], {"review_ready": True})["verdict"],
        evaluate_done_gate(["review_ready"], {"review_ready": False})["verdict"],
        evaluate_done_gate(["review_ready"], {})["verdict"],
    }
    assert said == {"pass", "fail", "undetermined"}


def test_CONTROLE_every_declared_predicate_is_reachable_and_typed():
    """No predicate name is advertised that the evaluator cannot answer."""
    assert set(DONE_GATE_PREDICATES) == set(FULL_GATE)
    for name in DONE_GATE_PREDICATES:
        assert evaluate_done_gate([name], CLEAN)["verdict"] == "pass", name
        assert evaluate_done_gate([name], {})["verdict"] == "undetermined", name


def test_a_malformed_fact_is_an_error_not_a_silent_pass():
    with pytest.raises(WorkGraphError, match="dirty_paths"):
        evaluate_done_gate(["clean_worktree"], {"index": "private", "dirty_paths": "a.py"})
    with pytest.raises(WorkGraphError, match="commits"):
        evaluate_done_gate(["committed_changes"], {"index": "private", "commits": -1})
    with pytest.raises(WorkGraphError, match="done gate facts"):
        evaluate_done_gate(["clean_worktree"], ["not", "a", "mapping"])
