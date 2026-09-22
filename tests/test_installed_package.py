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

import hashlib
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
ROOT_EXAMPLES = PRODUCT_ROOT / "examples" / "reliable-coding"
PACKAGED_EXAMPLES = PRODUCT_ROOT / "hpp" / "examples" / "reliable-coding"
# Why: pyproject.toml names README.md as `readme` and LICENSE as a license file; the backend
# refuses to build when a declared file is missing, so both travel with the copy.
BUILD_INPUTS = ("pyproject.toml", "hpp.manifest.json", "README.md", "LICENSE")
# Why: the floor `[build-system] requires` declares — the SPDX `license` string needs it, and an
# older in-process backend would fail the build instead of falling back to the isolated one.
MIN_SETUPTOOLS = (77,)


def _local_setuptools_meets_floor() -> bool:
    if importlib.util.find_spec("setuptools") is None:
        return False
    try:
        from importlib.metadata import version
        installed = tuple(int(part) for part in version("setuptools").split(".")[: len(MIN_SETUPTOOLS)])
    except (ImportError, ValueError):
        return False
    return installed >= MIN_SETUPTOOLS


def _build_wheel(source: Path, out: Path) -> Path:
    command = [sys.executable, "-m", "pip", "wheel", str(source), "--no-deps", "-w", str(out),
               "-q", "--disable-pip-version-check"]
    if _local_setuptools_meets_floor():
        # Why: an in-process backend builds offline in a third of the time; the isolated build
        # (which pip-installs the backend from the index) is the fallback for interpreters that
        # ship without setuptools, such as most 3.12+ virtual environments, or with one older
        # than the floor.
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


def _run(site: Path, cwd: Path, *args: str, env: dict[str, str] | None = None,
         encoding: str = "utf-8") -> subprocess.CompletedProcess[str]:
    merged = {**os.environ, "PYTHONPATH": str(site), "PYTHONDONTWRITEBYTECODE": "1", **(env or {})}
    return subprocess.run([sys.executable, *args], cwd=cwd, env=merged, capture_output=True, text=True,
                          encoding=encoding, timeout=300)


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


# --------------------------------------------------------------------------- examples in the wheel
# Measured before these tests existed (2026-09-21, clean venv, `pip install <product-root>`, run
# from an empty directory): `hpp benchmark -k 3` and `hpp --self-test` exited 3 with
# `internal error: FileNotFoundError: .../site-packages/examples/reliable-coding/...`, because the
# wheel carried no examples/ and the CLI resolved the suite one level above the package.


def test_wheel_ships_every_example_file_inside_the_package(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        for source in sorted(path for path in ROOT_EXAMPLES.iterdir() if path.is_file()):
            member = f"hpp/examples/reliable-coding/{source.name}"
            assert member in names, sorted(name for name in names if name.startswith("hpp/examples"))
            assert archive.read(member) == source.read_bytes(), member


def test_the_packaged_examples_are_byte_identical_to_the_root_examples() -> None:
    """One source of truth: examples/reliable-coding is what the README, the emitter and the
    checkout use; the copy under hpp/ exists only so the wheel carries it. Any drift is a release bug."""
    assert PACKAGED_EXAMPLES.is_dir(), "hpp/examples/reliable-coding is missing: the wheel would ship without a suite"
    root_files = sorted(path.name for path in ROOT_EXAMPLES.iterdir() if path.is_file())
    packaged_files = sorted(path.name for path in PACKAGED_EXAMPLES.iterdir() if path.is_file())
    assert packaged_files == root_files
    for name in root_files:
        assert (PACKAGED_EXAMPLES / name).read_bytes() == (ROOT_EXAMPLES / name).read_bytes(), name


def test_benchmark_runs_from_an_empty_directory_with_the_installed_wheel(site: Path, tmp_path: Path) -> None:
    empty = tmp_path / "elsewhere"
    empty.mkdir()
    result = _run(site, empty, "-m", "hpp", "benchmark", "-k", "3", "--json")
    assert result.returncode == 0, result.stderr or result.stdout
    report = json.loads(result.stdout)
    assert report["gate"]["passed"] is True
    assert report["k"] == 3
    # Why: the suite hash must be the one the checkout ships, or the wheel ran something else.
    expected = hashlib.sha256((ROOT_EXAMPLES / "benchmark-suite.json").read_bytes()).hexdigest()
    assert report["suite"]["sha256"] == expected


def test_self_test_runs_from_an_empty_directory_with_the_installed_wheel(site: Path, tmp_path: Path) -> None:
    empty = tmp_path / "elsewhere"
    empty.mkdir()
    result = _run(site, empty, "-m", "hpp", "--self-test")
    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stdout.strip() == "hpp self-test OK"


def test_init_from_the_installed_wheel_verifies_the_benchmark(site: Path, tmp_path: Path) -> None:
    """The wizard resolves the suite from the manifest's directory; with the examples inside the
    package, the pip channel measures the benchmark instead of reporting the suite as unshipped."""
    empty = tmp_path / "elsewhere"
    empty.mkdir()
    target = tmp_path / "project"
    target.mkdir()
    result = _run(site, empty, "-m", "hpp", "init", "--target", str(target), "--non-interactive",
                  "--no-animation", "--json")
    report = json.loads(result.stdout)
    items = {item["id"]: item for item in report["readiness"]["items"]}
    assert items["benchmark"]["status"] == "verified", items["benchmark"]
    assert (report["readiness"]["verified"], report["readiness"]["not_verified"]) == (7, 4), report["readiness"]


def test_CONTROLE_a_missing_suite_is_a_refused_input_not_an_internal_error(site: Path, tmp_path: Path) -> None:
    """Strip the packaged examples from a copy of the site: the CLI must say what is missing in
    one line with exit 2 — never an exception name with exit 3."""
    crippled = tmp_path / "site-without-examples"
    shutil.copytree(site, crippled)
    shutil.rmtree(crippled / "hpp" / "examples")
    empty = tmp_path / "elsewhere"
    empty.mkdir()
    for args in (("benchmark", "-k", "1"), ("--self-test",)):
        result = _run(crippled, empty, "-m", "hpp", *args)
        assert result.returncode == 2, (args, result.returncode, result.stderr)
        assert result.stdout == "", (args, result.stdout)
        lines = result.stderr.strip().splitlines()
        assert len(lines) == 1, lines
        assert lines[0].startswith("hpp: benchmark suite not found: "), lines[0]
        assert "internal error" not in lines[0] and "FileNotFoundError" not in lines[0]


def test_eval_run_on_a_missing_suite_path_exits_2_with_one_line(site: Path, tmp_path: Path) -> None:
    empty = tmp_path / "elsewhere"
    empty.mkdir()
    result = _run(site, empty, "-m", "hpp", "eval", "run", "does-not-exist.json")
    assert result.returncode == 2, (result.returncode, result.stderr)
    assert result.stderr.strip().splitlines() == ["hpp: suite not found: does-not-exist.json"]


# ------------------------------------------------------------------- one-line reports on cp1252
# Measured before this test existed (2026-09-21): `hpp.exe doctor` with a cp1252 stdout wrote the
# middle dot as the single byte 0xB7; read as UTF-8 by a terminal or a capturing agent it showed
# as `�`. The wizard already picks ASCII glyphs from the stream encoding; the doctor line now goes
# through the same console.


def test_doctor_degrades_to_ascii_on_a_cp1252_stream(site: Path, tmp_path: Path) -> None:
    empty = tmp_path / "elsewhere"
    empty.mkdir()
    result = _run(site, empty, "-m", "hpp", "doctor", env={"PYTHONIOENCODING": "cp1252"}, encoding="cp1252")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ("HPP doctor: ok - modules=10 - hosts=claude-code, codex "
                                     "- hooks=18 (permission gates=9 - llm egress=0)"), result.stdout
    assert result.stdout.isascii(), result.stdout


def test_CONTROLE_doctor_keeps_the_middle_dot_on_a_utf8_stream(site: Path, tmp_path: Path) -> None:
    empty = tmp_path / "elsewhere"
    empty.mkdir()
    result = _run(site, empty, "-m", "hpp", "doctor", env={"PYTHONIOENCODING": "utf-8"})
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ("HPP doctor: ok · modules=10 · hosts=claude-code, codex "
                                     "· hooks=18 (permission gates=9 · llm egress=0)"), result.stdout
