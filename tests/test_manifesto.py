"""Structural validation of hpp.manifest.json and its coherence with pyproject/__init__.

No network, no `~/.claude`, no machine environment variable: everything reads the
hpp.manifest.json and pyproject.toml of this product-root itself, or builds a
synthetic manifest in tmp_path when the test needs an INVALID case to serve as
a control.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from hpp import __version__
from hpp.manifest import (
    ManifestError,
    find_manifest,
    load_manifest,
    validate_distribution,
    validate_manifest,
)

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PRODUCT_ROOT / "hpp.manifest.json"
PYPROJECT_PATH = PRODUCT_ROOT / "pyproject.toml"


def _pyproject_version() -> str:
    """Extracts `version = "X.Y.Z"` from inside `[project]`, with no external lib.

    `tomllib` only exists in the stdlib from Python 3.11 on; the CI matrix also
    covers 3.10. This is NOT a general TOML parser -- it is the minimal, explicit
    reading of the single field this test needs, so as not to bring in a
    dependency just because of two Python versions.
    """
    if sys.version_info >= (3, 11):
        import tomllib

        with PYPROJECT_PATH.open("rb") as handle:
            return tomllib.load(handle)["project"]["version"]
    in_project = False
    for line in PYPROJECT_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_project = stripped == "[project]"
            continue
        if in_project:
            match = re.match(r'version\s*=\s*"([^"]+)"', stripped)
            if match:
                return match.group(1)
    raise AssertionError("version not found under [project] in pyproject.toml")


def _manifest_dict() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_is_valid_json_with_an_object_root():
    data = _manifest_dict()
    assert isinstance(data, dict)


def test_the_three_version_sources_agree():
    """
    This test alone already catches a real class of regression: it only takes
    one session updating hpp/__init__.py without touching hpp.manifest.json (or
    pyproject.toml), or vice versa, for the CLI's `--version` and `doctor` to
    diverge silently.
    """
    manifest = _manifest_dict()
    assert manifest["product_version"] == __version__
    assert __version__ == _pyproject_version()


def test_every_declared_module_has_the_required_fields_and_is_unique():
    manifest = _manifest_dict()
    modules = manifest["modules"]
    assert modules, "manifest with no module at all"
    ids = [module["id"] for module in modules]
    assert len(ids) == len(set(ids)), "duplicate module in the manifest"
    for module in modules:
        for field in ("id", "version", "path", "capabilities", "hosts", "requires", "integrates_with"):
            assert field in module, f"{module.get('id')} without the field {field}"
        assert module["path"], f"{module['id']} with an empty path"
        assert not module["path"].startswith(("/", "..")), f"{module['id']} with an absolute/escaping path"


def test_bundle_reliable_coding_only_references_existing_modules_and_capabilities():
    manifest = _manifest_dict()
    known_modules = {m["id"] for m in manifest["modules"]}
    known_capabilities = {c for m in manifest["modules"] for c in m["capabilities"]}
    for name, bundle in manifest["bundles"].items():
        unknown_modules = set(bundle["modules"]) - known_modules
        unknown_capabilities = set(bundle["capabilities"]) - known_capabilities
        assert not unknown_modules, f"bundle {name} references a module that does not exist: {unknown_modules}"
        assert not unknown_capabilities, f"bundle {name} references a capability that does not exist: {unknown_capabilities}"


def test_manifest_exit_codes_are_0_ok_1_warn_2_block_3_error():
    manifest = _manifest_dict()
    assert manifest["exit_codes"] == {"ok": 0, "warn": 1, "block": 2, "error": 3}


def test_CONTROLE_manifest_with_no_modules_is_rejected():
    """Control: proves that the validator knows how to FAIL, not just approve the real one."""
    broken = _manifest_dict()
    del broken["modules"]
    with pytest.raises(ManifestError):
        validate_manifest(broken)


def test_CONTROLE_bundle_with_a_phantom_module_is_rejected():
    broken = _manifest_dict()
    broken["bundles"]["reliable-coding"]["modules"] = [
        *broken["bundles"]["reliable-coding"]["modules"],
        "module-that-does-not-exist",
    ]
    with pytest.raises(ManifestError):
        validate_manifest(broken)


def test_CONTROLE_dependency_cycle_between_modules_is_rejected():
    broken = _manifest_dict()
    first_id = broken["modules"][0]["id"]
    second_id = broken["modules"][1]["id"]
    broken["modules"][0]["requires"] = [second_id]
    broken["modules"][1]["requires"] = [first_id]
    with pytest.raises(ManifestError):
        validate_manifest(broken)


def test_the_real_manifest_passes_its_own_validator():
    # Sanity check symmetric to the three controls above: the real one needs to
    # keep validating -- otherwise the controls would be proving something empty.
    validate_manifest(_manifest_dict())


def test_validate_distribution_in_source_mode_does_not_require_a_physical_module_directory():
    """
    This product-root has neither marketplace.json nor the physical module
    directories -- they only exist in the emitted copy, assembled by another
    stage of the publication pipeline. `validate_distribution` recognizes this
    as the "source-contract": the manifest is the source of truth even without
    the physical module content next to it.
    """
    manifest, path = load_manifest()
    if (path.parent / "marketplace.json").is_file():
        # Why: the same suite runs on the SOURCE tree and on the EMITTED copy. In the emitted one the
        # marketplace and the module directories exist, so the contract to verify is the other one --
        # and it has its own test. Skipping here is honest; asserting "source-contract" on the emitted
        # copy would be false.
        pytest.skip("copia emitida (tem marketplace.json) — o contrato de distribuicao completo e coberto pelo teste seguinte")
    result = validate_distribution(manifest, path.parent)
    assert result == {"checked": False, "status": "source-contract"}


def test_find_manifest_falls_back_to_the_package_when_no_manifest_is_above_the_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    found = find_manifest()
    assert found.resolve() == MANIFEST_PATH.resolve()


def test_find_manifest_explicit_but_nonexistent_fails():
    with pytest.raises(ManifestError):
        find_manifest(explicit=str(Path("this") / "path" / "does-not-exist" / "hpp.manifest.json"))


def test_load_manifest_accepts_an_explicit_path_to_a_copy(tmp_path):
    custom = tmp_path / "hpp.manifest.json"
    custom.write_text(MANIFEST_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    data, path = load_manifest(str(custom))
    assert path == custom.resolve()
    assert data["product_version"] == __version__


def test_load_manifest_with_invalid_json_gives_a_readable_error(tmp_path):
    custom = tmp_path / "hpp.manifest.json"
    custom.write_text("{ nao e json valido", encoding="utf-8")
    with pytest.raises(ManifestError):
        load_manifest(str(custom))
