"""Spec-driven work decomposition for reproducible agent operations.

The WorkGraph is intentionally data-only: it schedules declared work into
dependency waves, names every acceptance criterion so a test can cite it, and
answers a declared done gate over facts someone else measured. It never launches
an agent, a process or a git command.
"""
from __future__ import annotations

import re
from typing import Any


TIERS = ("economy", "balanced", "frontier")

# A criterion id reads `capability/scenario` and a test cites it as `[spec: capability/scenario]`.
_CITABLE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_SCENARIO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_NOT_SLUG = re.compile(r"[^a-z0-9]+")
SPEC_MARKER = re.compile(r"\[spec:\s*([A-Za-z0-9._/-]+)\s*\]")
_SCENARIO_MAX = 48


class WorkGraphError(ValueError):
    """A work specification cannot be compiled truthfully."""


def _criteria(work_id: str, raw: Any) -> list[dict[str, str]]:
    """Name every acceptance criterion, so a test can cite exactly one of them.

    Accepts a plain string (the scenario id is derived from the text) or
    `{"id": ..., "text": ...}` when the wording is expected to change but the
    citation must not.
    """
    if not isinstance(raw, list) or not raw:
        raise WorkGraphError(f"work {work_id} needs non-empty acceptance criteria")
    criteria: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in raw:
        if isinstance(entry, str):
            text, scenario = entry, ""
        elif isinstance(entry, dict) and isinstance(entry.get("text"), str):
            text = entry["text"]
            scenario = entry.get("id", "")
            if not isinstance(scenario, str):
                raise WorkGraphError(f"work {work_id} has a criterion id that is not a string")
        else:
            raise WorkGraphError(f"work {work_id} needs non-empty acceptance criteria")
        if not text.strip():
            raise WorkGraphError(f"work {work_id} needs non-empty acceptance criteria")
        scenario = scenario.strip() or _NOT_SLUG.sub("-", text.strip().lower())[:_SCENARIO_MAX].strip("-")
        if not _SCENARIO.fullmatch(scenario):
            raise WorkGraphError(f"work {work_id} has an uncitable criterion id: {scenario!r}")
        criterion_id = f"{work_id}/{scenario}"
        if not _CITABLE.fullmatch(criterion_id):
            raise WorkGraphError(f"work {work_id} produces an uncitable criterion id: {criterion_id!r}")
        # Why: two criteria whose text slugs to the same scenario would silently become one
        # citation, and the second criterion would look covered by the first one's test.
        if criterion_id in seen:
            raise WorkGraphError(f"duplicate acceptance criterion id: {criterion_id}")
        seen.add(criterion_id)
        criteria.append({"id": criterion_id, "work": work_id, "text": text.strip()})
    return criteria


def _gate(where: str, raw: Any) -> list[str]:
    """Resolve a declared done gate; an unknown or empty one is an error, never a pass."""
    if not isinstance(raw, list) or not all(isinstance(name, str) for name in raw):
        raise WorkGraphError(f"{where} needs a list of done gate predicate names")
    if not raw:
        raise WorkGraphError(f"{where} declares an empty done gate; an empty gate decides nothing")
    if len(set(raw)) != len(raw):
        raise WorkGraphError(f"{where} repeats a done gate predicate")
    for name in raw:
        if name not in _GATE_PREDICATES:
            raise WorkGraphError(f"unknown done gate predicate: {name}")
    return list(raw)


def _items(spec: dict[str, Any], default_gate: list[str]) -> dict[str, dict[str, Any]]:
    raw_work = spec.get("work")
    if not isinstance(raw_work, list) or not raw_work:
        raise WorkGraphError("work must be a non-empty list")
    work: dict[str, dict[str, Any]] = {}
    for item in raw_work:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"].strip():
            raise WorkGraphError("every work item needs a non-empty string id")
        work_id = item["id"]
        if work_id in work:
            raise WorkGraphError(f"duplicate work id: {work_id}")
        dependencies = item.get("depends_on", [])
        if not isinstance(dependencies, list) or not all(isinstance(value, str) for value in dependencies):
            raise WorkGraphError(f"work {work_id} needs a list of depends_on ids")
        if len(set(dependencies)) != len(dependencies):
            raise WorkGraphError(f"work {work_id} has duplicate dependency")
        criteria = _criteria(work_id, item.get("acceptance"))
        tier = item.get("tier")
        if tier not in TIERS:
            raise WorkGraphError(f"work {work_id} has invalid tier: {tier}")
        gate = _gate(f"work {work_id}", item["gate"]) if "gate" in item else list(default_gate)
        work[work_id] = {
            "id": work_id,
            "depends_on": sorted(dependencies),
            "acceptance": [criterion["text"] for criterion in criteria],
            "criteria": criteria,
            "tier": tier,
            "gate": gate,
        }
    for item in work.values():
        for dependency in item["depends_on"]:
            if dependency not in work:
                raise WorkGraphError(f"unknown dependency: {item['id']} -> {dependency}")
    return work


def _assert_acyclic(work: dict[str, dict[str, Any]]) -> None:
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(work_id: str) -> None:
        if work_id in visiting:
            start = visiting.index(work_id)
            cycle = " -> ".join([*visiting[start:], work_id])
            raise WorkGraphError(f"dependency cycle: {cycle}")
        if work_id in visited:
            return
        visiting.append(work_id)
        for dependency in work[work_id]["depends_on"]:
            visit(dependency)
        visiting.pop()
        visited.add(work_id)

    for work_id in sorted(work):
        visit(work_id)


def _waves(work: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    remaining = {work_id: set(item["depends_on"]) for work_id, item in work.items()}
    resolved: set[str] = set()
    result: list[dict[str, Any]] = []
    while remaining:
        ready = sorted(work_id for work_id, dependencies in remaining.items() if dependencies <= resolved)
        if not ready:  # Defensive: _assert_acyclic should have produced the detailed error.
            raise WorkGraphError("dependency cycle prevents scheduling")
        result.append({"index": len(result) + 1, "work": ready})
        resolved.update(ready)
        for work_id in ready:
            del remaining[work_id]
    return result


# ----------------------------------------------------------------- the done gate (R1)
#
# "Done" is a question with a git answer, and ONE evaluator answers it for every caller —
# a human running the check by hand and an automation closing a unit go through the same
# function, so the automation cannot reach a verdict the human would not have reached.
#
# This module never runs git. The caller measures and hands over a facts bundle:
#
#     {"index": "private",        # HOW the git facts were read (see below)
#      "dirty_paths": [...],      # paths still dirty in the worktree
#      "commits": 2,              # commits carrying this work
#      "review_ready": True,      # the review surface is open and ready
#      "evidence_ref": "run-17"}  # where the evidence of the run lives
#
# Why `index`: `git status --porcelain` consults the index's stat cache, so a repository
# whose index is shared between concurrent sessions answers about someone else's staging
# area. A clean/dirty reading taken that way is not evidence, so it is `undetermined`, not
# a pass. Read the facts under a private index -- `GIT_INDEX_FILE=<tmp>` plus
# `git read-tree HEAD` -- and declare `"index": "private"`.

_PASS, _FAIL, _UNDET = "pass", "fail", "undetermined"
_SHARED_INDEX = "git facts were not read under a private index, so they are not evidence"


def _private_index(facts: dict[str, Any]) -> bool:
    return facts.get("index") == "private"


def _p_clean_worktree(facts: dict[str, Any]) -> tuple[str, str]:
    if not _private_index(facts):
        return _UNDET, _SHARED_INDEX
    value = facts.get("dirty_paths")
    if value is None:
        return _UNDET, "fact dirty_paths was not measured"
    if not isinstance(value, list) or not all(isinstance(path, str) for path in value):
        raise WorkGraphError("fact dirty_paths must be a list of paths")
    return (_PASS, "worktree clean") if not value else (_FAIL, f"{len(value)} path(s) still dirty")


def _p_committed_changes(facts: dict[str, Any]) -> tuple[str, str]:
    if not _private_index(facts):
        return _UNDET, _SHARED_INDEX
    value = facts.get("commits")
    if value is None:
        return _UNDET, "fact commits was not measured"
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise WorkGraphError("fact commits must be a non-negative integer")
    return (_PASS, f"{value} commit(s) carry this work") if value else (_FAIL, "no commit carries this work")


def _p_review_ready(facts: dict[str, Any]) -> tuple[str, str]:
    value = facts.get("review_ready")
    if value is None:
        return _UNDET, "fact review_ready was not measured"
    if not isinstance(value, bool):
        raise WorkGraphError("fact review_ready must be a boolean")
    return (_PASS, "review surface ready") if value else (_FAIL, "review surface not ready")


def _p_evidence_ref_exists(facts: dict[str, Any]) -> tuple[str, str]:
    value = facts.get("evidence_ref")
    if value is None:
        return _UNDET, "fact evidence_ref was not measured"
    if not isinstance(value, str):
        raise WorkGraphError("fact evidence_ref must be a string")
    return (_PASS, f"evidence at {value.strip()}") if value.strip() else (_FAIL, "evidence_ref is empty")


_GATE_PREDICATES = {
    "clean_worktree": _p_clean_worktree,
    "committed_changes": _p_committed_changes,
    "review_ready": _p_review_ready,
    "evidence_ref_exists": _p_evidence_ref_exists,
}
DONE_GATE_PREDICATES = tuple(sorted(_GATE_PREDICATES))


def evaluate_done_gate(predicates: list[str], facts: dict[str, Any]) -> dict[str, Any]:
    """Answer a declared done gate. Only an all-`pass` gate is `pass`."""
    if not isinstance(predicates, list) or not all(isinstance(name, str) for name in predicates):
        raise WorkGraphError("done gate predicates must be a list of names")
    if not isinstance(facts, dict):
        raise WorkGraphError("done gate facts must be an object")
    if not predicates:
        return {"schema": "hpp.done-gate/v1", "verdict": _UNDET, "predicates": [],
                "reason": "empty gate: no predicate declared, so nothing was decided"}
    results = []
    for name in predicates:
        rule = _GATE_PREDICATES.get(name)
        if rule is None:
            raise WorkGraphError(f"unknown done gate predicate: {name}")
        verdict, reason = rule(facts)
        results.append({"predicate": name, "verdict": verdict, "reason": reason})
    said = {entry["verdict"] for entry in results}
    # Why: an unmeasured predicate is not a negative vote, it is an absent one — collapsing
    # the two would let a gate read "pass" on facts nobody ever produced.
    verdict = _FAIL if _FAIL in said else (_UNDET if _UNDET in said else _PASS)
    blocking = [entry["predicate"] for entry in results if entry["verdict"] != _PASS]
    reason = "every predicate passed" if verdict == _PASS else f"blocked by: {', '.join(blocking)}"
    return {"schema": "hpp.done-gate/v1", "verdict": verdict, "predicates": results, "reason": reason}


# ------------------------------------------------------- acceptance coverage (S2)


# Any `[spec: ...]` the loose regex accepts, so a MALFORMED citation is seen and not silently dropped.
_ANY_MARKER = re.compile(r"\[spec:\s*([^\]]*?)\s*\]")


def find_spec_markers(text: str) -> set[str]:
    """The criterion ids a source cites, written `[spec: capability/scenario]`.

    A malformed citation — `[spec: cap]` with no scenario, or `[spec: cap/first thing]` with a
    space — is returned as `malformed:<text>` instead of being dropped, and `spec_coverage` routes
    it to `unknown`. Otherwise a typo in the citation would read as "this test cites nothing" and
    the orphan check would never see the criterion it meant: a broken citation is a finding, not
    silence.
    """
    if not isinstance(text, str):
        raise WorkGraphError("spec markers can only be read from text")
    found: set[str] = set()
    for match in _ANY_MARKER.finditer(text):
        raw = match.group(1).strip()
        # A placeholder that DOCUMENTS the form (`<capability>/<scenario>`, `<id>`) and an empty
        # marker are not citations of anything — the file describing the syntax must not count as
        # using it (the same trap the coverage test itself hit on its first run).
        if not raw or "<" in raw or ">" in raw:
            continue
        found.add(raw if _CITABLE.fullmatch(raw) else f"malformed:{raw}")
    return found


def spec_coverage(compiled: dict[str, Any], sources: dict[str, str]) -> dict[str, Any]:
    """Link every acceptance criterion to the sources that name it.

    Three buckets, never two: `covered`, `orphans` (a criterion no source names) and
    `unknown` (a marker naming no declared criterion — a broken citation, which would
    otherwise read as coverage of something).
    """
    if not isinstance(compiled, dict) or not isinstance(compiled.get("criteria"), list):
        raise WorkGraphError("spec coverage needs a compiled workgraph")
    if not isinstance(sources, dict) or not all(
        isinstance(name, str) and isinstance(text, str) for name, text in sources.items()
    ):
        raise WorkGraphError("sources must be a mapping of name to text")
    declared = {criterion["id"] for criterion in compiled["criteria"]}
    cited: dict[str, list[str]] = {}
    for name in sorted(sources):
        for marker in sorted(find_spec_markers(sources[name])):
            cited.setdefault(marker, []).append(name)
    orphans = sorted(declared - set(cited))
    unknown = sorted(set(cited) - declared)
    return {
        "schema": "hpp.spec-coverage/v1",
        "criteria": len(declared),
        "covered": [{"id": key, "sources": cited[key]} for key in sorted(declared & set(cited))],
        "orphans": orphans,
        "unknown": [{"id": key, "sources": cited[key]} for key in unknown],
        "complete": not orphans and not unknown,
    }


def compile_workgraph(spec: dict[str, Any]) -> dict[str, Any]:
    """Validate a declarative work spec and return stable topological waves."""
    if not isinstance(spec, dict):
        raise WorkGraphError("workgraph spec must be an object")
    default_gate = _gate("spec done_gate", spec["done_gate"]) if "done_gate" in spec else []
    work = _items(spec, default_gate)
    _assert_acyclic(work)
    ordered_ids = [work_id for wave in _waves(work) for work_id in wave["work"]]
    edges = [
        {"from": dependency, "to": work_id, "relation": "depends-on"}
        for work_id in ordered_ids
        for dependency in work[work_id]["depends_on"]
    ]
    tier_counts = {tier: sum(item["tier"] == tier for item in work.values()) for tier in TIERS}
    return {
        "schema": "hpp.workgraph/v1",
        "work": [work[work_id] for work_id in ordered_ids],
        "criteria": sorted(
            (criterion for item in work.values() for criterion in item["criteria"]),
            key=lambda criterion: criterion["id"],
        ),
        "done_gate": list(default_gate),
        "edges": sorted(edges, key=lambda edge: (edge["from"], edge["to"])),
        "waves": _waves(work),
        "tier_counts": tier_counts,
    }
