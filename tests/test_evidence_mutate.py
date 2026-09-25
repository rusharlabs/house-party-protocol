"""Sensitivity of a criterion: it must pass on the clean tree and fail on every mutant.

A green criterion proves only that nothing it checks is broken. `hpp evidence mutate` asks the
other half: would it notice if something WERE broken? It runs the criterion on a copy of the
workspace, first clean (it must pass, or the measurement has no control), then once per mutant
(it must fail). A mutant the criterion lets through is a named blind spot, never a percentage
without a denominator. The user's tree is never modified.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from hpp import cli
from hpp.evidence import EvidenceError, generate_mutants, run_mutation

CODE = "def is_adult(age):\n    # the limit is >= 18, not > 18\n    return age >= 18\n\nLABEL = 'a >= b'\n"
STRONG = "from calc import is_adult\nassert is_adult(18)\nassert not is_adult(17)\n"
WEAK = "from calc import is_adult\nassert is_adult(30)\n"


def _workspace(tmp_path: Path, check: str = STRONG) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "calc.py").write_text(CODE, encoding="utf-8")
    (root / "check.py").write_text(check, encoding="utf-8")
    return root


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts
                       and ".hpp" not in p.parts):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


GE_TO_GT = [{"id": "ge-to-gt", "file": "calc.py", "find": "age >= 18", "replace": "age > 18"}]
CRITERION = [sys.executable, "check.py"]


def test_CONTROLE_a_criterion_that_checks_the_boundary_kills_the_mutant(tmp_path):
    root = _workspace(tmp_path)
    report = run_mutation("boundary", CRITERION, GE_TO_GT, root=root, timeout=60)
    assert report["clean"]["verdict"] == "passed"
    assert [item["outcome"] for item in report["mutants"]] == ["killed"]
    assert report["verdict"] == "sensitive"
    assert report["metrics"] == {"total": 1, "killed": 1, "survived": 0, "not_applied": 0, "errors": 0,
                                 "score": 1.0}


def test_a_criterion_that_misses_the_boundary_names_the_surviving_mutant(tmp_path):
    root = _workspace(tmp_path, WEAK)
    report = run_mutation("boundary", CRITERION, GE_TO_GT, root=root, timeout=60)
    assert report["verdict"] == "blind-spots"
    survivor = report["mutants"][0]
    assert (survivor["outcome"], survivor["file"], survivor["line"]) == ("survived", "calc.py", 3)
    assert report["metrics"]["score"] == 0.0


def test_a_criterion_that_fails_on_the_clean_tree_is_no_control_and_runs_no_mutant(tmp_path):
    root = _workspace(tmp_path, "raise SystemExit(1)\n")
    report = run_mutation("boundary", CRITERION, GE_TO_GT, root=root, timeout=60)
    assert report["verdict"] == "no-control"
    assert report["mutants"] == [] and report["metrics"]["score"] is None, "no control means no score, never 0%"


def test_a_mutant_whose_text_is_absent_is_not_applied_never_killed(tmp_path):
    root = _workspace(tmp_path)
    absent = [{"id": "ghost", "file": "calc.py", "find": "age == 21", "replace": "age != 21"}]
    report = run_mutation("boundary", CRITERION, absent, root=root, timeout=60)
    assert report["mutants"][0]["outcome"] == "not-applied"
    assert report["metrics"]["killed"] == 0 and report["metrics"]["score"] is None
    assert report["verdict"] == "no-mutants"


def test_the_users_tree_is_never_modified(tmp_path):
    root = _workspace(tmp_path, WEAK)
    before = _tree_hash(root)
    run_mutation("boundary", CRITERION, GE_TO_GT + generate_mutants(root, ["calc.py"]), root=root, timeout=60)
    assert _tree_hash(root) == before


def test_generated_mutants_touch_operators_never_strings_or_comments(tmp_path):
    root = _workspace(tmp_path)
    mutants = generate_mutants(root, ["calc.py"])
    assert [(item["line"], item["find"], item["replace"]) for item in mutants] == [(3, ">=", ">")], \
        "the '>=' in the comment (line 2) and in the string (line 5) are not code"


def test_CONTROLE_generation_finds_every_operator_it_knows(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "m.py").write_text("x = a == b and c != d or e <= f\ny = True if g < h else False\n", encoding="utf-8")
    found = {(item["find"], item["replace"]) for item in generate_mutants(root, ["m.py"])}
    assert {("==", "!="), ("!=", "=="), ("and", "or"), ("or", "and"), ("<=", "<"), ("<", "<="),
            ("True", "False"), ("False", "True")} <= found


def test_a_generated_mutant_is_applied_at_its_own_position(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "m.py").write_text("def f(a, b):\n    return a == 1 and b == 2\n", encoding="utf-8")
    (root / "check.py").write_text("from m import f\nassert f(1, 2)\nassert not f(1, 3)\n", encoding="utf-8")
    report = run_mutation("pos", CRITERION, generate_mutants(root, ["m.py"]), root=root, timeout=60)
    outcomes = {(item["find"], item["column"]): item["outcome"] for item in report["mutants"]}
    # `a == 1` flipped: f(1, 2) fails -> killed. `b == 2` flipped: f(1, 2) fails -> killed.
    assert outcomes[("==", 13)] == "killed" and outcomes[("==", 24)] == "killed"


@pytest.mark.parametrize("mutants, fragment", [
    ([{"id": "x", "file": "../outside.py", "find": "a", "replace": "b"}], "inside the workspace"),
    ([{"id": "x", "file": "calc.py", "find": "age", "replace": "age"}], "changes nothing"),
    ([{"id": "x", "file": "calc.py", "find": "", "replace": "b"}], "non-empty"),
    ([{"id": "x", "file": "calc.py", "find": "a", "replace": "b"}] * 2, "unique"),
    ([], "at least one mutant"),
])
def test_malformed_mutants_are_refused_before_anything_runs(tmp_path, mutants, fragment):
    with pytest.raises(EvidenceError, match=fragment):
        run_mutation("boundary", CRITERION, mutants, root=_workspace(tmp_path), timeout=60)


def test_a_secret_like_command_is_refused(tmp_path):
    with pytest.raises(EvidenceError, match="secret"):
        run_mutation("boundary", [sys.executable, "check.py", "--token", "abc123"], GE_TO_GT,
                     root=_workspace(tmp_path), timeout=60)


def test_the_record_is_written_and_self_hashed(tmp_path):
    root = _workspace(tmp_path)
    report = run_mutation("boundary", CRITERION, GE_TO_GT, root=root, timeout=60)
    written = json.loads((root / report["record_path"]).read_text(encoding="utf-8"))
    body = {key: value for key, value in written.items() if key != "record_sha256"}
    assert written["schema"] == "hpp.mutation/v1"
    assert written["record_sha256"] == hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def test_cli_evidence_mutate_follows_the_exit_contract(tmp_path, monkeypatch, capsys):
    mutants = tmp_path / "mutants.json"
    mutants.write_text(json.dumps({"schema": "hpp.mutants/v1", "mutants": GE_TO_GT}), encoding="utf-8")
    strong = _workspace(tmp_path)
    monkeypatch.chdir(strong)
    assert cli.main(["evidence", "mutate", "--id", "b", "--mutants", str(mutants), "--", *CRITERION]) == 0
    assert cli.main(["evidence", "mutate", "--id", "g", "--generate", "calc.py", "--", *CRITERION]) == 0
    weak = tmp_path / "weak"
    weak.mkdir()
    (weak / "calc.py").write_text(CODE, encoding="utf-8")
    (weak / "check.py").write_text(WEAK, encoding="utf-8")
    monkeypatch.chdir(weak)
    assert cli.main(["evidence", "mutate", "--id", "b", "--mutants", str(mutants), "--", *CRITERION]) == 1
    (weak / "check.py").write_text("raise SystemExit(3)\n", encoding="utf-8")
    assert cli.main(["evidence", "mutate", "--id", "b", "--mutants", str(mutants), "--", *CRITERION]) == 2
    assert cli.main(["evidence", "mutate", "--id", "b", "--", *CRITERION]) == 2, "no mutant source is refused"


# --------------------------------------------------------------------------- the shipped example

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
SENSITIVITY = "examples/criterion-sensitivity"


@pytest.mark.parametrize("check, verdict, survivors", [
    ("check_strong.py", "sensitive", 0),
    ("check_weak.py", "blind-spots", 3),
])
def test_the_documented_example_measures_what_its_readme_says(tmp_path, check, verdict, survivors):
    root = tmp_path / "product"
    (root / SENSITIVITY).mkdir(parents=True)
    for name in ("discount.py", "check_strong.py", "check_weak.py", "mutants.json"):
        (root / SENSITIVITY / name).write_bytes((PRODUCT_ROOT / SENSITIVITY / name).read_bytes())
    mutants = generate_mutants(root, [f"{SENSITIVITY}/discount.py"])
    declared = json.loads((root / SENSITIVITY / "mutants.json").read_text(encoding="utf-8"))["mutants"]
    report = run_mutation("example", [sys.executable, f"{SENSITIVITY}/{check}"], mutants, root=root, timeout=60)
    assert (report["verdict"], len(report["survivors"])) == (verdict, survivors)
    both = run_mutation("declared", [sys.executable, f"{SENSITIVITY}/{check}"], declared, root=root, timeout=60)
    assert both["mutants"][0]["outcome"] == ("killed" if check == "check_strong.py" else "survived")


# --------------------------------------------------------------------------- cross-model review, round 2
# Each test reproduces a defect the checker found in the first version of `mutate`.

def _can_symlink(tmp_path: Path) -> bool:
    try:
        (tmp_path / "probe-link").symlink_to(tmp_path)
        return True
    except (OSError, NotImplementedError):
        return False


def test_MUTANT_WRITES_THROUGH_SYMLINK_a_mutant_reached_through_a_symlink_is_refused(tmp_path):
    if not _can_symlink(tmp_path):
        pytest.skip("this account cannot create symlinks (Windows without developer mode); CI on Linux runs it")
    root = _workspace(tmp_path)
    (root / "real").mkdir()
    (root / "real" / "calc.py").write_text(CODE, encoding="utf-8")
    (root / "link").symlink_to(root / "real", target_is_directory=True)
    mutant = [{"id": "via-link", "file": "link/calc.py", "find": "age >= 18", "replace": "age > 18"}]
    with pytest.raises(EvidenceError, match="symlink"):
        run_mutation("boundary", CRITERION, mutant, root=root, timeout=60)
    with pytest.raises(EvidenceError, match="symlink"):
        generate_mutants(root, ["link/calc.py"])


def test_FALSE_KILL_NON_IDEMPOTENT_CRITERION_every_run_gets_a_fresh_copy(tmp_path):
    """A criterion that creates a directory fails on a SECOND run in the same copy. With one copy
    shared by all runs it 'killed' every mutant and a weak criterion came out `sensitive`."""
    root = _workspace(tmp_path, "import os\nos.mkdir('out')\n" + WEAK)
    report = run_mutation("boundary", CRITERION, GE_TO_GT, root=root, timeout=60)
    assert (report["verdict"], report["mutants"][0]["outcome"]) == ("blind-spots", "survived")


@pytest.mark.parametrize("name", [".hpp/x.py", "node_modules/pkg/x.py", ".venv/lib/x.py"])
def test_IGNORED_DIR_TARGET_a_mutant_in_a_directory_the_copy_leaves_out_is_refused(tmp_path, name):
    root = _workspace(tmp_path)
    (root / name).parent.mkdir(parents=True)
    (root / name).write_text("x = 1 == 1\n", encoding="utf-8")
    with pytest.raises(EvidenceError, match="left out of the copy"):
        run_mutation("boundary", CRITERION, [{"id": "i", "file": name, "find": "==", "replace": "!="}],
                     root=root, timeout=60)


def test_NON_UTF8_SOURCE_a_file_that_is_not_utf8_is_refused_before_anything_runs(tmp_path):
    root = _workspace(tmp_path)
    (root / "legacy.py").write_bytes(b"# -*- coding: latin-1 -*-\nNAME = '\xe9'\nOK = 1 == 1\n")
    with pytest.raises(EvidenceError, match="UTF-8"):
        generate_mutants(root, ["legacy.py"])
    with pytest.raises(EvidenceError, match="UTF-8"):
        run_mutation("b", CRITERION, [{"id": "l", "file": "legacy.py", "find": "==", "replace": "!="}],
                     root=root, timeout=60)


def test_OFFSET_SPLITLINES_MISMATCH_a_generated_mutant_after_a_unicode_separator_is_applied(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "m.py").write_text('S = "a b"\ndef f(a, b):\n    return a == b\n', encoding="utf-8")
    (root / "check.py").write_text("from m import f\nassert f(1, 1)\nassert not f(1, 2)\n", encoding="utf-8")
    report = run_mutation("sep", CRITERION, generate_mutants(root, ["m.py"]), root=root, timeout=60)
    assert [item["outcome"] for item in report["mutants"]] == ["killed"]


def test_COPY_FAILURE_a_workspace_that_cannot_be_copied_is_refused_not_an_internal_error(tmp_path, monkeypatch):
    import shutil

    def broken(*args, **kwargs):
        raise shutil.Error([("src/socket", "dst/socket", "[Errno 6] No such device or address")])

    monkeypatch.setattr(shutil, "copytree", broken)
    with pytest.raises(EvidenceError, match="could not be copied"):
        run_mutation("b", CRITERION, GE_TO_GT, root=_workspace(tmp_path), timeout=60)


# --------------------------------------------------------------------------- cross-model review, round 3

def test_CR_ONLY_NEWLINE_MISMATCH_generated_mutants_apply_in_a_cr_only_file(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "m.py").write_bytes(b"x = 1\ry = x == 1\r")
    (root / "check.py").write_text("from m import y\nassert y\n", encoding="utf-8")
    report = run_mutation("cr", CRITERION, generate_mutants(root, ["m.py"]), root=root, timeout=60)
    assert [item["outcome"] for item in report["mutants"]] == ["killed"]


def test_SCRATCH_INSIDE_WORKSPACE_a_temporary_directory_inside_the_workspace_is_refused(tmp_path, monkeypatch):
    import tempfile

    root = _workspace(tmp_path)
    (root / "tmp").mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(root / "tmp"))
    with pytest.raises(EvidenceError, match="inside the workspace"):
        run_mutation("b", CRITERION, GE_TO_GT, root=root, timeout=60)


def test_COPY_COST_UNBOUNDED_a_mutant_that_does_not_apply_costs_no_copy(tmp_path, monkeypatch):
    import hpp.evidence as evidence

    copies = []
    real = evidence._fresh_copy

    def counting(*args, **kwargs):
        copies.append(args[2])
        return real(*args, **kwargs)

    monkeypatch.setattr(evidence, "_fresh_copy", counting)
    absent = [{"id": "ghost", "file": "calc.py", "find": "age == 21", "replace": "age != 21"}]
    report = run_mutation("b", CRITERION, absent + GE_TO_GT, root=_workspace(tmp_path), timeout=60)
    assert [item["outcome"] for item in report["mutants"]] == ["not-applied", "killed"]
    assert len(copies) == 2, "one copy for the clean run, one for the mutant that applies"


# --------------------------------------------------------------------------- cross-model review, round 4

def test_BOM_SOURCE_a_generated_mutant_request_on_a_bom_file_names_the_bom(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "m.py").write_bytes(b"\xef\xbb\xbfy = 1 == 1\n")
    with pytest.raises(EvidenceError, match="byte-order mark"):
        generate_mutants(root, ["m.py"])


def test_CONTROLE_a_declared_mutant_still_applies_to_a_bom_file(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "m.py").write_bytes(b"\xef\xbb\xbfy = 1 == 1\n")
    (root / "check.py").write_text("from m import y\nassert y\n", encoding="utf-8")
    report = run_mutation("bom", CRITERION, [{"id": "eq", "file": "m.py", "find": "==", "replace": "!="}],
                          root=root, timeout=60)
    assert [item["outcome"] for item in report["mutants"]] == ["killed"]
