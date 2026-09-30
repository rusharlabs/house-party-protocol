"""The coding standard is enforced, not described: a ruff rule set in pyproject.toml, run by CI.

Before this file existed the product had no `[tool.ruff]` table, so `ruff check` applied the default
rules of whichever ruff version a contributor happened to run, and no CI job ran a linter at all.
Measured with ruff 0.16.9 against the rule set below: 10 findings in `hpp/`, `tests/` and `scripts/`
(3 unused imports, 3 unused variables, 2 ambiguous names, 2 assigned lambdas), all fixed by hand.

These tests pin the three pieces that make the standard real, so none of them can go away quietly:
the rule set in `pyproject.toml`, the CI job that runs it, and the hash-pinned ruff that job installs.
"""
from __future__ import annotations

import re
from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = PRODUCT_ROOT / "pyproject.toml"
CI = PRODUCT_ROOT / ".github" / "workflows" / "ci.yml"
LINT_PIN = PRODUCT_ROOT / ".github" / "requirements" / "lint.txt"
RULES = ["E4", "E7", "E9", "F"]
COMMAND = "ruff check hpp tests scripts"


def ruff_settings(text: str) -> dict[str, object]:
    """`target-version` and `select` from the `[tool.ruff]` tables, or {} when there are none."""
    try:
        import tomllib  # 3.11+
    except ModuleNotFoundError:  # 3.10: the floor in requires-python
        return ruff_settings_by_regex(text)
    ruff = tomllib.loads(text).get("tool", {}).get("ruff", {})
    found = {"target-version": ruff.get("target-version"), "select": ruff.get("lint", {}).get("select")}
    return {key: value for key, value in found.items() if value is not None}


def ruff_settings_by_regex(text: str) -> dict[str, object]:
    """The same reading without tomllib, for 3.10; the CONTROLE tests hold it to the tomllib one."""
    found: dict[str, object] = {}
    table = re.search(r"(?ms)^\[tool\.ruff\]\n(.*?)(?=^\[(?!tool\.ruff)|\Z)", text)
    if table:
        target = re.search(r'(?m)^target-version\s*=\s*"([^"]+)"', table.group(1))
        select = re.search(r"(?m)^select\s*=\s*\[([^\]]*)\]", table.group(1))
        if target:
            found["target-version"] = target.group(1)
        if select:
            found["select"] = re.findall(r'"([^"]+)"', select.group(1))
    return found


def job(workflow: str, name: str) -> str:
    """The body of one top-level job, from its header to the next job header ("" when absent)."""
    match = re.search(rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [\w-]+:\n|\Z)", workflow)
    return match.group(1) if match else ""


def test_pyproject_carries_the_ruff_rule_set():
    settings = ruff_settings(PYPROJECT.read_text(encoding="utf-8"))
    assert settings.get("select") == RULES, f"[tool.ruff.lint] select is {settings.get('select')!r}, expected {RULES}"


def test_ruff_targets_the_python_floor_the_package_promises():
    text = PYPROJECT.read_text(encoding="utf-8")
    floor = re.search(r'(?m)^requires-python\s*=\s*">=3\.(\d+)"', text)
    assert floor, "pyproject.toml has no requires-python floor"
    assert ruff_settings(text).get("target-version") == f"py3{floor.group(1)}"


def test_ci_has_a_lint_job_that_installs_the_pinned_ruff_and_runs_it():
    lint = job(CI.read_text(encoding="utf-8"), "lint")
    assert lint, "ci.yml has no `lint` job"
    install = lint.find("--require-hashes -r .github/requirements/lint.txt")
    run = lint.find(COMMAND)
    assert install != -1, "the lint job does not install ruff from the hash-pinned requirements file"
    assert run != -1 and install < run, f"the lint job must run `{COMMAND}` after installing ruff"
    assert "persist-credentials: false" in lint


def test_the_ruff_pin_is_hash_checked_and_names_no_local_path():
    text = LINT_PIN.read_text(encoding="utf-8")
    assert re.search(r"(?m)^ruff==\d+\.\d+\.\d+ ", text), text[:200]
    assert text.count("--hash=sha256:") >= 10, "one hash per published ruff wheel"
    assert "# via" not in text and ":/" not in text and ":\\" not in text, "no local path in a published pin"


# --------------------------------------------------------------------------- the readers discriminate

def test_CONTROLE_the_readers_see_nothing_when_the_table_and_the_job_are_gone():
    without_table = '[project]\nname = "x"\nrequires-python = ">=3.10"\n\n[tool.setuptools]\npackages = ["x"]\n'
    assert ruff_settings(without_table) == {}
    assert ruff_settings_by_regex(without_table) == {}
    workflow = "jobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: ruff check hpp tests scripts\n"
    assert job(workflow, "lint") == ""
    assert COMMAND in job(workflow, "test"), "the job reader must still find a job that exists"


def test_CONTROLE_both_settings_readers_read_a_planted_table_and_the_real_one_alike():
    planted = (
        '[project]\nname = "x"\n\n[tool.ruff]\n# comment\ntarget-version = "py311"\n\n'
        '[tool.ruff.lint]\nselect = ["F"]\n\n[tool.other]\nselect = ["X"]\n'
    )
    assert ruff_settings(planted) == {"target-version": "py311", "select": ["F"]}
    assert ruff_settings_by_regex(planted) == {"target-version": "py311", "select": ["F"]}
    real = PYPROJECT.read_text(encoding="utf-8")
    assert ruff_settings_by_regex(real) == ruff_settings(real)
