"""Repository consumers distinguish measured imports from absent or stale inputs."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess

import pytest

from hpp._repository import snapshot
from hpp.attest import AttestationError, create_attestation, verify_attestation
from hpp.maps import build_lane_map
from hpp.territories import (TerritoryError, measure_blast_radius, normalise_territory,
                             propose_lanes, territory_coupling)
from hpp.workgraph import WorkGraphError, compile_workgraph


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout.strip()


def commit(repo: Path, *paths: str) -> str:
    git(repo, "add", "--", *paths)
    message = repo.parent / "fixture-message.txt"
    message.write_text("Record fixture changes\n", encoding="utf-8")
    git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-F", str(message))
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "HPP Test")
    git(root, "config", "user.email", "hpp@example.invalid")
    paths = ["cart/cart.py", "pricing/price.py", "checkout/pay.py", "SPEC.md"]
    for path in paths:
        destination = root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("# committed input\n", encoding="utf-8")
    commit(root, *paths)
    return root


def documents(repo, edges=None):
    snap = snapshot(repo)
    inventory = {"schema": "hpp.inventory/v1", "commit": snap.commit, "files": list(snap.files),
                 "sections": {"hotspots": {"status": "measured", "top": [["pricing/price.py", 3]]}}}
    graph = {"schema": "hpp.codegraph/v1", "commit": snap.commit,
             "instrument": {"status": "measured"},
             "nodes": [{"id": "module:" + p, "kind": "module", "path": p} for p in snap.files],
             "edges": [{"from": "module:" + a, "to": "module:" + b, "relation": "imports"}
                       for a, b in (edges if edges is not None else [("cart/cart.py", "pricing/price.py")])]}
    return inventory, graph


def lanes():
    return [{"id": "cart", "territory": ["cart"]}, {"id": "pricing", "territory": ["pricing"]}]


def work_spec():
    return {"work": [{"id": name, "tier": "balanced", "acceptance": ["bounded change works"],
                      "territory": [name]} for name in ("cart", "pricing")]}


def test_lane_proposal_is_deterministic_read_only_and_carries_cut_cost(repo):
    inventory, graph = documents(repo)
    before = git(repo, "status", "--porcelain", "--untracked-files=all")
    first = propose_lanes(repo, inventory, graph, max_lanes=4)
    assert first == propose_lanes(repo, inventory, graph, max_lanes=4)
    assert first["schema"] == "hpp.lane-proposal/v1"
    assert first["relations"] == "measured" and first["cut_cost"] == 1
    assert first["inputs"] == {"inventory_commit": inventory["commit"], "codegraph_commit": graph["commit"]}
    assert first["approval"] == "required before applying territories"
    assert git(repo, "status", "--porcelain", "--untracked-files=all") == before
    assert not (repo / ".hpp").exists()


def test_greedy_merge_preserves_the_strongest_relationship(repo):
    inventory, graph = documents(repo)
    proposal = propose_lanes(repo, inventory, graph, max_lanes=3)
    assert len(proposal["lanes"]) == 3 and proposal["cut_cost"] == 0
    assert any(lane["territory"] == ["cart", "pricing"] for lane in proposal["lanes"])


def test_shared_hub_and_hotspot_expose_parallel_coordination_risk(repo):
    inventory, graph = documents(repo, [("cart/cart.py", "pricing/price.py"),
                                         ("checkout/pay.py", "pricing/price.py")])
    proposal = propose_lanes(repo, inventory, graph)
    assert proposal["shared"] == ["pricing"]
    assert all("pricing" not in lane["territory"] for lane in proposal["lanes"])
    assert proposal["cut_cost"] == 2
    assert proposal["red_zones"][0]["path"] == "pricing/price.py"
    assert len(proposal["red_zones"][0]["groups"]) == 3


@pytest.mark.parametrize("mode", ["absent", "stale", "failed"])
def test_fallback_does_not_invent_relationships(repo, mode):
    inventory, graph = documents(repo)
    if mode == "absent":
        graph = None
    elif mode == "stale":
        old = graph["commit"]
        (repo / "pricing/price.py").write_text("# next revision\n", encoding="utf-8")
        commit(repo, "pricing/price.py")
        inventory, _ = documents(repo)
        assert inventory["commit"] != old
    else:
        graph["instrument"]["status"] = "instrument-failure"
    proposal = propose_lanes(repo, inventory, graph)
    assert proposal["relations"] == "not-measured"
    assert proposal["cut"] == [] and proposal["shared"] == [] and proposal["red_zones"] == []


def test_dirty_inventory_is_not_accepted_as_a_current_partition(repo):
    inventory, graph = documents(repo)
    (repo / "cart/cart.py").write_text("# unsaved tracked changes\n", encoding="utf-8")
    with pytest.raises(TerritoryError, match="fresh inventory"):
        propose_lanes(repo, inventory, graph)


def test_inventory_paths_must_belong_to_the_head_universe(repo):
    inventory, graph = documents(repo)
    inventory["files"].append("untracked.py")
    with pytest.raises(TerritoryError, match="universe"):
        propose_lanes(repo, inventory, graph)


def test_empty_measured_repository_universe_can_have_no_lanes(repo):
    inventory, _ = documents(repo)
    inventory["files"] = []
    assert propose_lanes(repo, inventory)["lanes"] == []


def test_square_bracket_route_directories_are_literal_territories():
    assert normalise_territory(["app/[slug]"]) == ["app/[slug]"]


@pytest.mark.parametrize("value", [[], ["../private"], ["/private"], ["C:/private"], ["a\\b"],
                                    ["a//b"], ["a/./b"], ["a/**"], ["a\nb"], [123]])
def test_territory_rejects_unsafe_or_ambiguous_paths(value):
    with pytest.raises(TerritoryError):
        normalise_territory(value)


@pytest.mark.parametrize("options", [{"max_lanes": 0}, {"max_lanes": True}, {"max_lanes": 129},
                                      {"depth": 0}, {"depth": 1.5}, {"depth": True}])
def test_lane_partition_parameters_are_bounded(repo, options):
    inventory, _ = documents(repo)
    with pytest.raises(TerritoryError):
        propose_lanes(repo, inventory, **options)


def test_coupling_is_directed_imports_not_calls_or_path_overlap(repo):
    _, graph = documents(repo)
    graph["edges"].append({"from": "module:pricing/price.py", "to": "module:cart/cart.py", "relation": "calls"})
    result = territory_coupling(repo, lanes(), graph)
    assert result["warnings"] == [{"from": "cart", "to": "pricing", "edges": 1,
                                    "reason": "territories are linked by imports"}]
    result = build_lane_map(lanes(), codegraph=graph, target=repo)
    assert result["collisions"] == []
    assert result["territory_coupling"]["warnings"][0]["from"] == "cart"


def test_lane_map_ignores_dead_and_nonexclusive_lanes_for_coupling(repo):
    _, graph = documents(repo)
    for update in ({"status": "dead"}, {"exclusive": False}):
        source = lanes()
        source[0].update(update)
        assert build_lane_map(source, codegraph=graph, target=repo)["territory_coupling"]["warnings"] == []


def test_workgraph_warns_only_inside_the_same_wave(repo):
    _, graph = documents(repo)
    spec = work_spec()
    result = compile_workgraph(spec, codegraph=graph, target=repo)
    assert result["work"][0]["territory"] == ["cart"]
    assert result["territory_coupling"][0]["warnings"][0]["to"] == "pricing"
    spec["work"][0]["depends_on"] = ["pricing"]
    separated = compile_workgraph(spec, codegraph=graph, target=repo)
    assert all(not wave["warnings"] for wave in separated["territory_coupling"])


def test_workgraph_no_graph_preserves_legacy_output(repo):
    spec = work_spec()
    for item in spec["work"]:
        del item["territory"]
    result = compile_workgraph(spec)
    assert "territory_coupling" not in result
    assert all("territory" not in item for item in result["work"])
    assert "territory_coupling" not in build_lane_map(lanes())


def test_workgraph_rejects_bad_territory(repo):
    spec = work_spec()
    spec["work"][0]["territory"] = ["../private"]
    with pytest.raises(WorkGraphError, match="relative"):
        compile_workgraph(spec)


def test_consumers_refuse_stale_graph_instead_of_silent_zero_coupling(repo):
    _, graph = documents(repo)
    (repo / "pricing/price.py").write_text("# dirty\n", encoding="utf-8")
    result = territory_coupling(repo, lanes(), graph)
    assert result["status"] == "not-measured" and result["freshness"]["status"] == "stale"
    assert result["warnings"] == []
    assert measure_blast_radius(repo, graph["commit"], graph)["status"] == "not-measured"


def test_graph_target_is_required_for_freshness(repo):
    _, graph = documents(repo)
    result = compile_workgraph(work_spec(), codegraph=graph)
    assert result["territory_coupling"][0]["status"] == "not-measured"


@pytest.mark.parametrize("mutation", ["duplicate", "outside", "dangling"])
def test_consumer_rejects_invalid_resolved_graph_inputs(repo, mutation):
    _, graph = documents(repo)
    if mutation == "duplicate":
        graph["nodes"].append(copy.deepcopy(graph["nodes"][0]))
    elif mutation == "outside":
        graph["nodes"][0]["path"] = "outside.py"
    else:
        graph["edges"][0]["to"] = "missing"
    with pytest.raises(TerritoryError):
        territory_coupling(repo, lanes(), graph)


def test_blast_radius_traces_transitive_reverse_imports_not_forward_dependencies(repo):
    base = git(repo, "rev-parse", "HEAD")
    (repo / "pricing/price.py").write_text("# changed price\n", encoding="utf-8")
    commit(repo, "pricing/price.py")
    _, graph = documents(repo, [("cart/cart.py", "pricing/price.py"), ("checkout/pay.py", "cart/cart.py"),
                               ("pricing/price.py", "cart/cart.py")])
    radius = measure_blast_radius(repo, base, graph)
    assert radius["changed"] == ["pricing/price.py"]
    assert radius["dependents"] == ["cart/cart.py", "checkout/pay.py"]
    assert radius["graph_commit"] == graph["commit"]
    assert radius["scope"] == "resolved imports only"
    assert measure_blast_radius(repo, "--invalid-ref", graph)["status"] == "not-measured"


def test_attestation_carries_impact_before_signing_without_changing_existing_bindings(repo):
    base = git(repo, "rev-parse", "HEAD")
    (repo / "pricing/price.py").write_text("# changed price\n", encoding="utf-8")
    commit(repo, "pricing/price.py")
    _, graph = documents(repo)
    output = repo / "proof.json"
    record = create_attestation(repo, repo / "SPEC.md", output, "maker", "checker", "review-1", "approved",
                                codegraph=graph, base_commit=base)
    assert record["base_commit"] == graph["commit"]
    assert record["blast_radius"]["dependents"] == ["cart/cart.py"]
    assert json.loads(output.read_text(encoding="utf-8"))["blast_radius"] == record["blast_radius"]
    assert verify_attestation(output, repo)["status"] == "valid"


def test_attestation_base_requires_explicit_graph_and_does_not_write(repo):
    output = repo / "proof.json"
    with pytest.raises(AttestationError, match="requires a code graph"):
        create_attestation(repo, repo / "SPEC.md", output, "maker", "checker", "review-1", "approved",
                           base_commit=git(repo, "rev-parse", "HEAD"))
    assert not output.exists()
