"""The pip-installed package must find its own manifest from any directory.

Measured before this file existed: `pip install <product>` produced a `site-packages/hpp/`
with no manifest, and from any directory outside the source tree `hpp doctor` and `hpp init`
exited 2 with "hpp.manifest.json not found". The tests below build a real wheel from a copy of
the source tree (so `build/` and `*.egg-info` never land in the checkout), unpack it into a
private "site-packages", and drive that layout from an empty directory through a subprocess.

The source checkout is never mistaken for the installed layout here: every subprocess asserts
that the `hpp` it imported lives inside the unpacked wheel.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from hpp.manifest import find_manifest

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
ROOT_MANIFEST = PRODUCT_ROOT / "hpp.manifest.json"
PACKAGED_MANIFEST = PRODUCT_ROOT / "hpp" / "hpp.manifest.json"
WHEEL_MEMBER = "hpp/hpp.manifest.json"
BUILD_INPUTS = ("pyproject.toml", "hpp.manifest.json")


def _build_wheel(source: Path, out: Path) -> Path:
    command = [sys.executable, "-m", "pip", "wheel", str(source), "--no-deps", "-w", str(out),
               "-q", "--disable-pip-version-check"]
    if importlib.util.find_spec("setuptools") is not None:
        # Why: an in-process backend builds offline in a third of the time; the isolated build
        # (which pip-installs the backend from the index) is the fallback for interpreters that
        # ship without setuptools, such as most 3.12+ virtual environments.
        command.append("--no-build-isolation")
    result = subprocess.run(command, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        pytest.fail(f"pip wheel failed (rc={result.returncode}):\n{result.stdout}\n{result.stderr}")
    wheels = sorted(out.glob("*.whl"))
    assert len(wheels) == 1, wheels
    return wheels[0]


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    # Why: pip builds in place and leaves build/ and *.egg-info next to pyproject.toml; building
    # from a copy keeps those out of the checkout and out of the publication gate.
    source = tmp_path_factory.mktemp("source")
    shutil.copytree(PRODUCT_ROOT / "hpp", source / "hpp", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in BUILD_INPUTS:
        shutil.copyfile(PRODUCT_ROOT / name, source / name)
    return _build_wheel(source, tmp_path_factory.mktemp("wheel"))


@pytest.fixture(scope="module")
def site(wheel: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The wheel unpacked the way pip lays it out: `<site>/hpp/...` with no repository around it."""
    target = tmp_path_factory.mktemp("site")
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(target)
    return target


def _run(site: Path, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(site), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run([sys.executable, *args], cwd=cwd, env=env, capture_output=True, text=True,
                          encoding="utf-8", timeout=300)


PROBE = ("import hpp, hpp.manifest as m, json, pathlib; "
         "print(json.dumps({'package': hpp.__file__, 'manifest': str(m.find_manifest(start=pathlib.Path('.')))}))")


def _probe(site: Path, cwd: Path) -> dict[str, str]:
    result = _run(site, cwd, "-c", PROBE)
    assert result.returncode == 0, result.stderr
    found = json.loads(result.stdout)
    assert Path(found["package"]).resolve().is_relative_to(site.resolve()), found
    return found


def test_wheel_ships_the_manifest_inside_the_package(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert WHEEL_MEMBER in names, sorted(name for name in names if name.startswith("hpp/"))
        assert archive.read(WHEEL_MEMBER) == ROOT_MANIFEST.read_bytes()


def test_find_manifest_resolves_inside_the_installed_package_from_an_empty_directory(site: Path, tmp_path: Path) -> None:
    empty = tmp_path / "elsewhere"
    empty.mkdir()
    found = _probe(site, empty)
    assert Path(found["manifest"]) == (site / WHEEL_MEMBER).resolve()


def test_doctor_runs_from_an_empty_directory_without_mistaking_site_packages_for_a_distribution(site: Path, tmp_path: Path) -> None:
    empty = tmp_path / "elsewhere"
    empty.mkdir()
    result = _run(site, empty, "-m", "hpp", "doctor", "--json")
    assert result.returncode == 0, result.stderr or result.stdout
    report = json.loads(result.stdout)
    assert report["status"] == "ok"
    assert Path(report["manifest"]).resolve() == (site / WHEEL_MEMBER).resolve()
    # Why: the wizard treats the manifest's parent as the distribution root. Inside site-packages
    # there is no marketplace.json, so the answer must stay "source-contract" — never a
    # distribution check against a directory that holds only Python modules.
    assert report["distribution"] == {"checked": False, "status": "source-contract"}


def test_init_plans_from_an_empty_directory_and_reports_the_unshipped_parts_as_not_verified(site: Path, tmp_path: Path) -> None:
    empty = tmp_path / "elsewhere"
    empty.mkdir()
    target = tmp_path / "project"
    target.mkdir()
    result = _run(site, empty, "-m", "hpp", "init", "--target", str(target), "--non-interactive",
                  "--no-animation", "--no-benchmark", "--json")
    assert result.stdout.lstrip().startswith("{"), result.stderr or result.stdout
    report = json.loads(result.stdout)
    assert report["exit_code"] == result.returncode
    assert "not found" not in json.dumps(report)
    items = {item["id"]: item for item in report["readiness"]["items"]}
    assert items["distribution"]["status"] == "not-verified"
    assert items["checksums"]["status"] == "not-verified"
    assert items["benchmark"]["status"] == "not-verified"
    assert report["readiness"]["verified"] > 0


def test_a_manifest_in_the_working_directory_still_wins_over_the_packaged_copy(site: Path, tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    local = project / "hpp.manifest.json"
    shutil.copyfile(ROOT_MANIFEST, local)
    found = _probe(site, project)
    assert Path(found["manifest"]) == local.resolve()
    # The same rule in-process: an explicit `start` above a manifest resolves to that manifest.
    assert find_manifest(start=project) == local.resolve()


def test_the_packaged_copy_is_byte_identical_to_the_root_manifest() -> None:
    """One source of truth: the root file is what the tests, the emitter and the distribution
    read; the copy under hpp/ exists only so the wheel carries it. Any drift is a release bug."""
    assert PACKAGED_MANIFEST.is_file(), "hpp/hpp.manifest.json is missing: the wheel would ship without a manifest"
    assert PACKAGED_MANIFEST.read_bytes() == ROOT_MANIFEST.read_bytes()
