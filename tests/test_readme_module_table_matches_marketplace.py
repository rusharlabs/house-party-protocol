"""The README module table names the versions the marketplace distributes.

Measured 2026-09-27: both READMEs said `operator-kit` 1.6.2 and `lane-kit` 1.4.1 while
`marketplace.json` distributed 1.7.0 and 1.6.0; a reader who compared the table with the module
directories of the same clone saw two numbers for one module. `scripts/repo_readiness.py` already
has the comparison, but it looks for `marketplace.json` beside the manifest, which is where the
emitted repository has it; in the source tree the row skipped, so nothing failed. This file runs
the same check, against the marketplace it can find: beside the manifest, or the copy the source
tree keeps in `staging/`.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = (ROOT / "marketplace.json", ROOT.parents[2] / "staging" / "marketplace.json")


def _readiness():
    """`scripts/repo_readiness.py`, loaded from its file: `scripts/` is not a package, and the stdlib
    gate reads every name imported under tests/ as a dependency. The comparison lives there; this
    file only points it at a marketplace."""
    spec = importlib.util.spec_from_file_location("repo_readiness", ROOT / "scripts" / "repo_readiness.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


repo_readiness = _readiness()


def _marketplace() -> Path:
    for candidate in CANDIDATES:
        if candidate.is_file():
            return candidate
    pytest.skip("no marketplace.json beside the manifest and no staging/ copy above this tree")


def test_the_readme_module_table_matches_the_marketplace():
    row = repo_readiness.readme_modules_vs_marketplace(_marketplace())
    assert row["status"] == "ok", row["detail"]


def test_CONTROLE_the_row_measured_something_here():
    # Why: the readiness row answers `skip` when it finds no marketplace; a suite that let that
    # through would be green with the table unchecked.
    row = repo_readiness.readme_modules_vs_marketplace(_marketplace())
    assert row["status"] in {"ok", "FAIL"}, row


def test_CONTROLE_the_check_fails_on_a_table_that_disagrees(tmp_path: Path):
    marketplace = json.loads(_marketplace().read_text(encoding="utf-8"))
    first = marketplace["plugins"][0]
    first["version"] = "0.0.1"
    planted = tmp_path / "marketplace.json"
    planted.write_text(json.dumps(marketplace), encoding="utf-8")
    row = repo_readiness.readme_modules_vs_marketplace(planted)
    assert row["status"] == "FAIL"
    assert first["name"] in row["detail"] and "0.0.1" in row["detail"], row["detail"]
