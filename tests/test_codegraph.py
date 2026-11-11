"""Code graph safety, conservative relationships and declared instrument controls."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from hpp import codegraph
from hpp._process import run_bounded
from hpp._repository import RepositoryError, artifact_status, snapshot, write_artifact


def git(root, *args, data=None):
    return subprocess.run(["git", "-c", "core.hooksPath=", "-c", "commit.gpgSign=false",
                           "-C", str(root), *args], input=data, capture_output=True, check=True).stdout.decode().strip()


def commit(root, files):
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    git(root, "add", "--", *files)
    message = root.parent / "commit-message.txt"
    message.write_text("Test graph fixture\n", encoding="utf-8")
    git(root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-F", str(message))
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init")
    commit(root, {"src/shop/__init__.py": "", "src/shop/pricing.py": "def price_of():\n    return 1\n",
                  "src/shop/cart.py": "from .pricing import price_of\ndef total():\n    return price_of()\n"})
    return root


def pairs(graph, relation):
    paths = {node["id"]: node["path"] for node in graph["nodes"]}
    return {(paths[edge["from"]], paths[edge["to"]]) for edge in graph["edges"] if edge["relation"] == relation}


def declared(repo):
    return {"schema": codegraph.SCHEMA, "commit": git(repo, "rev-parse", "HEAD"),
            "producer": {"kind": "declared", "version": "1.0"},
            "nodes": [{"id": "a", "kind": "module", "path": "src/shop/cart.py"},
                      {"id": "b", "kind": "module", "path": "src/shop/pricing.py"}],
            "edges": [{"from": "a", "to": "b", "relation": "imports"}]}


def test_python_ast_imports_definitions_calls_are_commit_bound_and_inert(repo):
    commit(repo, {"danger.py": "raise RuntimeError('must never run')\n",
                  "setup.py": "from pathlib import Path\nPath('executed').touch()\n"})
    graph = codegraph.build_codegraph(repo)
    assert graph["schema"] == codegraph.SCHEMA
    assert graph["instrument"]["status"] == "measured"
    assert ("src/shop/cart.py", "src/shop/pricing.py") in pairs(graph, "imports")
    assert ("src/shop/cart.py", "src/shop/pricing.py") in pairs(graph, "calls")
    assert any(n["kind"] == "function" and n["line"] == 2 for n in graph["nodes"])
    assert graph["freshness"]["status"] == "fresh"
    assert not (repo / "executed").exists()
    assert not (repo / ".hpp").exists()
    assert str(repo) not in json.dumps(graph)
    assert graph == codegraph.build_codegraph(repo)


def test_dirty_worktree_is_not_executed_or_indexed_and_reports_stale(repo):
    (repo / "src/shop/cart.py").write_text("not valid Python!", encoding="utf-8")
    graph = codegraph.build_codegraph(repo)
    assert graph["freshness"]["status"] == "stale"
    assert graph["freshness"]["dirty_tracked"] == 1
    assert any(n["kind"] == "function" and n["path"].endswith("cart.py") for n in graph["nodes"])


def test_dynamic_external_and_shadowed_calls_remain_unresolved(repo):
    commit(repo, {"dynamic.py": "import absent\nimport importlib\ndef local(): pass\ndef test(local):\n    local()\n    importlib.import_module('not_executed')\n    getattr(absent, 'method')()\n"})
    graph = codegraph.build_codegraph(repo)
    assert any(e["relation"] == "calls" and e["target"] == "local" for e in graph["unresolved"])
    assert any(e["target"] == "<withheld>" for e in graph["unresolved"])
    assert any(e["target"] == "absent" for e in graph["unresolved"])
    assert ("dynamic.py", "dynamic.py") not in pairs(graph, "calls")


def test_local_import_bindings_do_not_leak_to_other_functions(repo):
    commit(repo, {"scopes.py": "def first():\n    from shop.pricing import price_of\n    price_of()\ndef second():\n    price_of()\n"})
    graph = codegraph.build_codegraph(repo)
    nodes = {n["id"]: n for n in graph["nodes"]}
    calls = [nodes[e["from"]]["line"] for e in graph["edges"] if e["relation"] == "calls" and nodes[e["from"]]["path"] == "scopes.py"]
    assert calls == [1]
    assert any(e["target"] == "price_of" and "second" in e["from"] for e in graph["unresolved"])


def test_root_assignment_does_not_create_false_static_call(repo):
    commit(repo, {"assigned.py": "def f(): pass\nf = object()\nf()\n"})
    graph = codegraph.build_codegraph(repo)
    assert ("assigned.py", "assigned.py") not in pairs(graph, "calls")


def test_class_scope_is_not_a_function_lexical_scope(repo):
    commit(repo, {"class_scope.py": "def f(): pass\nclass C:\n    def f(self): pass\n    def g(self): f()\n"})
    graph = codegraph.build_codegraph(repo)
    calls = [e for e in graph["edges"] if e["relation"] == "calls" and "class_scope.py:C.g" in e["from"]]
    assert len(calls) == 1
    assert calls[0]["to"] == "symbol:class_scope.py:f"


def test_ambiguous_aliases_and_invalid_relative_imports_are_unresolved(repo):
    commit(repo, {"ambiguous.py": "from shop.pricing import price_of as f\nfrom elsewhere import f\nf()\n",
                  "src/shop/invalid.py": "from ...shop.pricing import price_of\nprice_of()\n"})
    graph = codegraph.build_codegraph(repo)
    assert not any(a in {"ambiguous.py", "src/shop/invalid.py"} for a, b in pairs(graph, "calls"))


def test_branch_aliases_and_optional_imports_do_not_claim_a_callee(repo):
    commit(repo, {"a.py": "def run(): pass\n", "b.py": "def run(): pass\n",
                  "branches.py": "if True:\n    import a as chosen\nelse:\n    import b as chosen\nchosen.run()\n",
                  "optional.py": "if False:\n    import a as chosen\nchosen.run()\n"})
    graph = codegraph.build_codegraph(repo)
    assert not any(source in {"branches.py", "optional.py"} for source, _ in pairs(graph, "calls"))
    assert {e["from"] for e in graph["unresolved"] if e["target"] == "chosen.run"} == {"module:branches.py", "module:optional.py"}


def test_nested_lexical_import_shadows_module_alias(repo):
    commit(repo, {"a.py": "def run(): pass\n", "b.py": "def run(): pass\n",
                  "nested.py": "import a as chosen\ndef outer():\n    import b as chosen\n    def inner():\n        chosen.run()\n    inner()\n"})
    graph = codegraph.build_codegraph(repo)
    assert ("nested.py", "b.py") in pairs(graph, "calls")
    assert ("nested.py", "a.py") not in pairs(graph, "calls")


def test_from_package_submodule_adds_the_submodule_import_edge(repo):
    commit(repo, {"src/shop/another.py": "from . import pricing\npricing.price_of()\n"})
    graph = codegraph.build_codegraph(repo)
    assert ("src/shop/another.py", "src/shop/pricing.py") in pairs(graph, "imports")
    assert ("src/shop/another.py", "src/shop/pricing.py") in pairs(graph, "calls")


def test_duplicate_python_module_roots_and_redefinitions_keep_unique_ids(repo):
    commit(repo, {"shop/pricing.py": "def price_of(): pass\ndef price_of(): pass\n"})
    graph = codegraph.build_codegraph(repo)
    identities = [n["id"] for n in graph["nodes"]]
    assert len(identities) == len(set(identities))
    assert ("src/shop/cart.py", "src/shop/pricing.py") not in pairs(graph, "calls")


def test_javascript_typescript_are_explicitly_imports_only(repo):
    commit(repo, {"web/a.ts": "import {b} from './b';\nb();\n", "web/b.ts": "export function b() {}\n",
                  "web/package.js": "import thing from 'external-package';\n", "foreign.go": "package foreign\n"})
    graph = codegraph.build_codegraph(repo)
    assert ("web/a.ts", "web/b.ts") in pairs(graph, "imports")
    assert graph["coverage"]["typescript"] == "imports-only (lexical)"
    assert not any(n["kind"] == "function" and n["path"].endswith(".ts") for n in graph["nodes"])
    assert any(e["target"] == "external-package" for e in graph["unresolved"])
    assert any(e["reason"] == "unsupported language" and e["count"] >= 1 for e in graph["excluded"])


def test_invalid_python_and_excluded_content_are_counted_without_values(repo):
    commit(repo, {"broken.py": "def broken(:", ".env": "API_KEY=do-not-publish-this-value\n",
                  "secrets/hidden.py": "def hidden(): pass\n", "oversize.py": "#" * (2 * 1024 * 1024 + 1)})
    graph = codegraph.build_codegraph(repo)
    rendered = json.dumps(graph)
    assert "do-not-publish-this-value" not in rendered
    assert not any(n["path"] in {"broken.py", "secrets/hidden.py", "oversize.py"} for n in graph["nodes"])
    assert any(e["reason"] == "Python parse failure" for e in graph["excluded"])
    assert any(e["reason"] == "unreadable or excluded file" for e in graph["excluded"])


def test_declared_normalizes_paths_counts_exclusions_and_unknown_edges(repo):
    document = declared(repo)
    document["nodes"].extend([{"id": "out", "kind": "module", "path": "../outside.py"},
                              {"id": "abs", "kind": "module", "path": "/absolute/hidden.py"}])
    document["edges"].extend([{"from": "a", "to": "unknown", "relation": "calls"},
                              {"from": "out", "to": "a", "relation": "imports"}])
    graph = codegraph.import_codegraph(repo, document)
    assert len(graph["nodes"]) == 2
    assert graph["measured"]["excluded_nodes"] == 2
    assert graph["measured"]["covered_files"] == 2
    assert graph["measured"]["unresolved_edges"] == 2
    assert {edge["reason"] for edge in graph["unresolved"]} == {"unknown node", "unknown source node"}
    assert "absolute/hidden" not in json.dumps(graph)


@pytest.mark.parametrize("mutation", ["duplicate", "unknown-kind", "bad-line", "unsafe-id", "failed-instrument"])
def test_declared_rejects_malformed_contract(repo, mutation):
    document = declared(repo)
    if mutation == "duplicate":
        document["nodes"].append(dict(document["nodes"][0]))
    elif mutation == "unknown-kind":
        document["nodes"][0]["kind"] = "arbitrary"
    elif mutation == "bad-line":
        document["nodes"][0]["line"] = True
    elif mutation == "unsafe-id":
        document["nodes"][0]["id"] = "secret=never-print-this"
    else:
        document["instrument"] = {"status": "instrument-failure"}
    with pytest.raises(codegraph.CodegraphError):
        codegraph.import_codegraph(repo, document)


def test_import_rejects_secret_files_and_symlinks_without_following_them(repo):
    commit(repo, {"secrets/private.py": "def private(): pass\n"})
    oid = git(repo, "hash-object", "-w", "--stdin", data=b"src/shop/cart.py")
    git(repo, "update-index", "--add", "--cacheinfo", f"120000,{oid},link.py")
    message = repo.parent / "commit-message.txt"
    git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-F", str(message))
    document = declared(repo)
    document["nodes"].extend([{"id": "secret", "kind": "module", "path": "secrets/private.py"},
                              {"id": "link", "kind": "module", "path": "link.py"}])
    graph = codegraph.import_codegraph(repo, document)
    assert len(graph["nodes"]) == 2
    assert graph["measured"]["excluded_nodes"] == 2


def test_import_unicode_nfc_and_comparison_do_not_depend_on_node_ids(repo):
    commit(repo, {"café.py": "pass\n"})
    document = declared(repo)
    document["nodes"].append({"id": "unicode", "kind": "module", "path": "café.py"})
    graph = codegraph.import_codegraph(repo, document)
    assert any(n["path"] == "café.py" for n in graph["nodes"])
    compared = codegraph.compare_codegraphs(repo, document)
    assert compared["status"] == "measured"
    assert compared["shared"] == [{"from": "src/shop/cart.py", "to": "src/shop/pricing.py"}]
    assert not compared["missing_from_declared"]
    commit(repo, {"later.py": "pass\n"})
    old = codegraph.compare_codegraphs(repo, document)
    assert old["status"] == "not-measured"
    assert old["freshness"]["commits_behind"] == 1
    assert not old["shared"]


def test_head_change_during_normalization_cannot_publish_fresh_universe(repo, monkeypatch):
    old_snapshot = snapshot(repo)
    commit(repo, {"new.py": "pass\n"})
    document = declared(repo)
    document["nodes"].append({"id": "new", "kind": "module", "path": "new.py"})
    monkeypatch.setattr(codegraph, "snapshot", lambda _target: old_snapshot)
    graph = codegraph.import_codegraph(repo, document)
    assert graph["commit"] == document["commit"]
    assert graph["universe_commit"] == old_snapshot.commit
    assert not any(n["path"] == "new.py" for n in graph["nodes"])
    assert graph["freshness"]["status"] == "stale"
    assert graph["freshness"]["commits_behind"] == 0
    assert graph["freshness"]["reason"] == "graph universe differs from artifact commit"
    assert artifact_status(repo, graph)["status"] == "stale"
    with pytest.raises(RepositoryError, match="universe"):
        write_artifact(repo, "codegraph", graph)
    assert not (repo / ".hpp").exists()


def test_reimport_cannot_replace_explicit_mismatched_universe_provenance(repo, monkeypatch):
    old_snapshot = snapshot(repo)
    commit(repo, {"new.py": "pass\n"})
    document = declared(repo)
    document["nodes"] = [{"id": "new", "kind": "module", "path": "new.py"}]
    with monkeypatch.context() as patch:
        patch.setattr(codegraph, "snapshot", lambda _target: old_snapshot)
        raced = codegraph.import_codegraph(repo, document)
    assert raced["freshness"]["status"] == "stale"
    assert raced["universe_commit"] == old_snapshot.commit
    assert not raced["nodes"]
    with pytest.raises(codegraph.CodegraphError, match="universe provenance"):
        codegraph.import_codegraph(repo, json.loads(json.dumps(raced)))
    assert artifact_status(repo, raced)["status"] == "stale"
    with pytest.raises(RepositoryError, match="universe"):
        write_artifact(repo, "codegraph", raced)
    assert not (repo / ".hpp").exists()


def test_legitimate_old_provenance_and_legacy_missing_provenance_remain_stale(repo):
    old_graph = codegraph.build_codegraph(repo)
    legacy = declared(repo)
    commit(repo, {"new.py": "pass\n"})
    for document in (old_graph, legacy):
        imported = codegraph.import_codegraph(repo, document)
        assert imported["freshness"]["status"] == "stale"
        assert imported["freshness"]["commits_behind"] == 1


@pytest.mark.parametrize("identity", [None, "invalid", 3, "0" * 40])
def test_import_rejects_invalid_or_incompatible_explicit_universe(repo, identity):
    document = declared(repo)
    document["universe_commit"] = identity
    with pytest.raises(codegraph.CodegraphError, match="universe provenance"):
        codegraph.import_codegraph(repo, document)


@pytest.mark.parametrize("identity", [None, "invalid", 3])
def test_artifact_status_rejects_malformed_optional_universe(repo, identity):
    graph = declared(repo)
    graph["universe_commit"] = identity
    assert artifact_status(repo, graph)["status"] == "invalid"
    with pytest.raises(RepositoryError, match="universe"):
        write_artifact(repo, "codegraph", graph)


def test_declared_command_stdin_valid_output_and_redacted_arguments(repo):
    script = "import json,sys; q=json.load(sys.stdin); print(json.dumps({'schema':'hpp.codegraph/v1','commit':q['commit'],'nodes':[],'edges':[]}))"
    graph = codegraph.build_codegraph(repo, [sys.executable, "-c", script])
    assert graph["instrument"]["status"] == "measured"
    assert graph["producer"]["argv"][1:] == ["<argument>", "<argument>"]
    assert graph["measured"]["covered_files"] == 0
    assert str(repo) not in json.dumps(graph)


@pytest.mark.parametrize("script,reason", [
    ("import sys; print('secret=not-to-copy',file=sys.stderr); sys.exit(7)", "nonzero exit"),
    ("print('not JSON')", "invalid indexer JSON or graph contract"),
    ("import time; time.sleep(30)", "timeout"),
    ("import sys; sys.stdout.write('a'*3000000)", "output-limit"),
])
def test_declared_command_failure_is_not_measured_empty(repo, script, reason):
    graph = codegraph.build_codegraph(repo, [sys.executable, "-c", script], timeout=0.3 if reason == "timeout" else 10)
    assert graph["instrument"]["status"] == "instrument-failure"
    assert graph["freshness"]["status"] == "invalid"
    assert graph["instrument"]["reason"] == reason
    assert not graph["nodes"]
    assert "not-to-copy" not in json.dumps(graph)
    assert script not in json.dumps(graph)


@pytest.mark.parametrize("command", ['echo hello', '"shell text"', [], ["x", 1], ["x\x00y"]])
def test_command_requires_explicit_bounded_argv(repo, command):
    with pytest.raises(codegraph.CodegraphError):
        codegraph.build_codegraph(repo, command)


def test_could_not_start_is_instrument_failure(repo):
    graph = codegraph.build_codegraph(repo, [str(repo / "missing-executable")])
    assert graph["instrument"]["reason"] == "could-not-start"


def test_output_limit_bounds_combined_stdout_stderr_and_preserves_defaults(tmp_path):
    script = "import os; [(os.write(1,b'x'*65536),os.write(2,b'y'*65536)) for _ in range(100)]"
    started = time.monotonic()
    state, code, out, err = run_bounded([sys.executable, "-c", script], timeout=10, max_output_bytes=8192)
    assert state == "output-limit" and code is None
    assert len(out) + len(err) <= 8192
    assert time.monotonic() - started < 15
    assert run_bounded([sys.executable, "-c", "print('small')"], timeout=10)[:3] == ("exited", 0, b"small" + os.linesep.encode())


@pytest.mark.parametrize("_attempt", range(3))
def test_output_limit_stops_a_live_descendant_before_side_effect(tmp_path, _attempt):
    marker = tmp_path / "descendant-marker"
    child = f"import time,pathlib; time.sleep(3); pathlib.Path({str(marker)!r}).touch()"
    parent = f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(.2); sys.stdout.write('x'*200000); sys.stdout.flush(); time.sleep(30)"
    state, _, out, err = run_bounded([sys.executable, "-c", parent], timeout=10, max_output_bytes=1024)
    assert state == "output-limit"
    assert len(out) + len(err) <= 1024
    time.sleep(3.2)
    assert not marker.exists()


def test_output_limit_reaps_children_under_development_warnings():
    product = str(Path(codegraph.__file__).resolve().parent.parent)
    script = (f"import sys,gc; sys.path.insert(0,{product!r}); from hpp._process import run_bounded; "
              "state,code,out,err=run_bounded([sys.executable,'-c',\"import sys,time; sys.stdout.write('x'*200000); sys.stdout.flush(); time.sleep(30)\"],"
              "timeout=10,max_output_bytes=1024); assert state=='output-limit'; gc.collect()")
    result = subprocess.run([sys.executable, "-X", "dev", "-W", "error", "-c", script],
                            capture_output=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert b"ResourceWarning" not in result.stderr


@pytest.mark.parametrize("maximum", [-1, True, 1.5])
def test_output_budget_invalid_types_are_refused_before_start(maximum):
    with pytest.raises(ValueError):
        run_bounded(["must-not-start"], timeout=1, max_output_bytes=maximum)
