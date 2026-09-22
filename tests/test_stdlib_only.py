"""The harness imports nothing outside the Python standard library.

`pyproject.toml` declares `dependencies = []` and the README promises "no third-party
packages"; the release workflow installs the wheel with `pip install --no-index`, which is
where a stray `import yaml` would surface for the first time. Measured before this file
existed: `hpp/` imported 18 distinct top-level modules, all standard library or `hpp` itself,
and nothing enforced it. This test reads every import in every `.py` under `hpp/` with `ast`
(so an import inside a function or a `try:` counts too) and compares each top-level name with
`sys.stdlib_module_names`. The test suite itself may add exactly one third-party name: pytest.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = PRODUCT_ROOT / "hpp"
TESTS = PRODUCT_ROOT / "tests"
# Why (CI run 35678986775, 2026-09-22): `sys.stdlib_module_names` is the running interpreter's list, and
# on the 3.10 floor it has no `tomllib` (stdlib since 3.11). Two tests import it behind a guard, which
# is correct; this gate must not read a guarded stdlib import as a third-party dependency on 3.10.
STDLIB = frozenset(sys.stdlib_module_names) | frozenset({"tomllib"})
OWN = frozenset({"hpp"})
TEST_ONLY = frozenset({"pytest"})


def top_level_imports(root: Path) -> dict[str, list[str]]:
    """Top-level module name -> files (relative, posix) that import it, relative imports excluded."""
    found: dict[str, set[str]] = {}
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = path.relative_to(root).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    found.setdefault(alias.name.split(".")[0], set()).add(rel)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.setdefault(node.module.split(".")[0], set()).add(rel)
    return {name: sorted(files) for name, files in sorted(found.items())}


def third_party(imports: dict[str, list[str]], allowed: frozenset[str]) -> dict[str, list[str]]:
    return {name: files for name, files in imports.items() if name not in STDLIB and name not in allowed}


# --------------------------------------------------------------------------- the gate itself

def test_package_imports_only_the_standard_library():
    imports = top_level_imports(PACKAGE)
    assert len(imports) >= 10, f"only {len(imports)} imports seen under hpp/ — the gate would be vacuous"
    offenders = third_party(imports, OWN)
    assert offenders == {}, f"third-party imports in hpp/: {offenders}"


def test_test_suite_adds_only_pytest():
    offenders = third_party(top_level_imports(TESTS), OWN | TEST_ONLY)
    assert offenders == {}, f"third-party imports in tests/: {offenders}"


def test_pyproject_declares_no_dependencies():
    text = (PRODUCT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    try:
        import tomllib  # 3.11+
    except ModuleNotFoundError:  # 3.10: the floor in requires-python
        match = re.search(r"^dependencies\s*=\s*\[(.*?)\]", text, re.M | re.S)
        assert match is not None, "pyproject.toml has no `dependencies` key"
        assert match.group(1).strip() == "", match.group(0)
        return
    project = tomllib.loads(text)["project"]
    assert project["dependencies"] == [], project["dependencies"]
    assert "optional-dependencies" not in project, project.get("optional-dependencies")


# --------------------------------------------------------------------------- GATE 1e: it discriminates

def test_collector_reports_a_planted_third_party_import(tmp_path: Path):
    (tmp_path / "top.py").write_text("import json\nimport requests\n", encoding="utf-8")
    (tmp_path / "nested.py").write_text(
        "def load():\n    try:\n        import yaml\n    except ImportError:\n        yaml = None\n    return yaml\n",
        encoding="utf-8",
    )
    (tmp_path / "from_form.py").write_text("from rich.console import Console\n", encoding="utf-8")
    offenders = third_party(top_level_imports(tmp_path), OWN)
    assert offenders == {
        "requests": ["top.py"],
        "rich": ["from_form.py"],
        "yaml": ["nested.py"],
    }, offenders


def test_collector_is_silent_on_stdlib_and_relative_imports(tmp_path: Path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "a.py").write_text(
        "from __future__ import annotations\nimport os.path\nfrom pathlib import Path\n"
        "from . import b\nfrom .b import helper\nfrom hpp.manifest import find_manifest\n",
        encoding="utf-8",
    )
    (pkg / "b.py").write_text("def helper():\n    import subprocess\n    return subprocess\n", encoding="utf-8")
    imports = top_level_imports(tmp_path)
    assert set(imports) == {"__future__", "os", "pathlib", "hpp", "subprocess"}, imports
    assert third_party(imports, OWN) == {}
