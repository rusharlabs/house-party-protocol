"""WorkGraph: rejects a cycle (direct, indirect and self-dependency) and
produces topological waves that are stable and deterministic across runs.
"""
from __future__ import annotations

import pytest

from hpp.workgraph import WorkGraphError, compile_workgraph


def _spec(*items):
    return {"work": list(items)}


def _item(item_id, depends_on=None, tier="economy"):
    return {"id": item_id, "depends_on": depends_on or [], "acceptance": [f"{item_id} done"], "tier": tier}


def test_waves_respect_dependency_in_topological_order():
    spec = _spec(
        _item("spec"),
        _item("build", depends_on=["spec"], tier="balanced"),
        _item("docs", depends_on=["spec"]),
        _item("verify", depends_on=["build", "docs"], tier="frontier"),
    )
    compiled = compile_workgraph(spec)
    assert compiled["waves"] == [
        {"index": 1, "work": ["spec"]},
        {"index": 2, "work": ["build", "docs"]},
        {"index": 3, "work": ["verify"]},
    ]
    assert compiled["tier_counts"] == {"economy": 2, "balanced": 1, "frontier": 1}
    assert {edge["from"] for edge in compiled["edges"]} <= {"spec", "build", "docs"}


def test_order_within_the_same_wave_is_alphabetical_and_deterministic_across_runs():
    spec = _spec(
        _item("z"),
        _item("a"),
        _item("m", depends_on=["z", "a"]),
    )
    first = compile_workgraph(spec)
    second = compile_workgraph(spec)
    assert first == second
    assert first["waves"][0] == {"index": 1, "work": ["a", "z"]}
    assert first["waves"][1] == {"index": 2, "work": ["m"]}


def test_direct_cycle_between_two_items_is_rejected():
    spec = _spec(
        _item("a", depends_on=["b"]),
        _item("b", depends_on=["a"]),
    )
    with pytest.raises(WorkGraphError, match="dependency cycle"):
        compile_workgraph(spec)


def test_indirect_cycle_of_three_items_is_rejected():
    spec = _spec(
        _item("a", depends_on=["c"]),
        _item("b", depends_on=["a"]),
        _item("c", depends_on=["b"]),
    )
    with pytest.raises(WorkGraphError, match="dependency cycle"):
        compile_workgraph(spec)


def test_self_dependency_is_a_cycle_of_size_one():
    spec = _spec(_item("a", depends_on=["a"]))
    with pytest.raises(WorkGraphError, match="dependency cycle"):
        compile_workgraph(spec)


def test_dependency_on_a_nonexistent_item_is_rejected():
    spec = _spec(_item("a", depends_on=["fantasma"]))
    with pytest.raises(WorkGraphError, match="unknown dependency"):
        compile_workgraph(spec)


def test_duplicate_id_is_rejected():
    spec = _spec(_item("a"), {"id": "a", "acceptance": ["outro"], "tier": "economy"})
    with pytest.raises(WorkGraphError, match="duplicate work id"):
        compile_workgraph(spec)


def test_item_with_no_acceptance_criterion_is_rejected():
    spec = _spec({"id": "a", "acceptance": [], "tier": "economy"})
    with pytest.raises(WorkGraphError):
        compile_workgraph(spec)


def test_item_with_invalid_tier_is_rejected():
    spec = _spec({"id": "a", "acceptance": ["x"], "tier": "premium"})
    with pytest.raises(WorkGraphError, match="invalid tier"):
        compile_workgraph(spec)


def test_empty_work_list_is_rejected():
    with pytest.raises(WorkGraphError):
        compile_workgraph({"work": []})


def test_CONTROLE_spec_with_no_cycle_compiles_normally():
    """Control: proves that the detector only fails when there is a real
    cycle -- a legitimate linear chain passes."""
    spec = _spec(_item("a"), _item("b", depends_on=["a"]), _item("c", depends_on=["b"]))
    compiled = compile_workgraph(spec)
    assert compiled["waves"] == [
        {"index": 1, "work": ["a"]},
        {"index": 2, "work": ["b"]},
        {"index": 3, "work": ["c"]},
    ]


def test_CONTROLE_shared_dependency_is_not_mistaken_for_a_cycle():
    """Control: two items depending on the SAME item, without depending on
    each other, is not a cycle -- they must fall into the same wave."""
    spec = _spec(_item("base"), _item("left", depends_on=["base"]), _item("right", depends_on=["base"]))
    compiled = compile_workgraph(spec)
    assert compiled["waves"][1]["work"] == ["left", "right"]
