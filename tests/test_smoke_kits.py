"""Integrity check of the distributed modules, via CHECKSUMS.txt.

The SOURCE tree contains neither the physical module directories nor
marketplace.json -- they only exist in the EMITTED COPY, assembled by another
stage of the pipeline. Running from inside the emitted copy (the case of
whoever installed it, and CI's case over the published content), the root is
the directory right above `tests/`; running from source, there is nothing to
check and the test SKIPS, explicitly.

# Why: the path was absolute and carried the username of ONE machine. A test
# like that never runs anywhere but there, and the personal path travels
# inside the published package. The root is DERIVED from the file's position;
# HPP_EMITTED_COPY allows pointing at another tree without editing code.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

_DERIVED_ROOT = Path(__file__).resolve().parents[1]
EMITTED_COPY = Path(os.environ.get("HPP_EMITTED_COPY") or _DERIVED_ROOT)
MARKETPLACE = EMITTED_COPY / "marketplace.json"


def _skip_reason() -> str | None:
    if not EMITTED_COPY.is_dir():
        return f"emitted copy missing at {EMITTED_COPY} (expected in CI and in fresh clones)"
    if not MARKETPLACE.is_file():
        return f"{MARKETPLACE} does not exist -- nothing to discover modules from"
    return None


def _declared_modules() -> list[tuple[str, Path]]:
    marketplace = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    modules = []
    for plugin in marketplace.get("plugins", []):
        source = str(plugin.get("source", "")).removeprefix("./")
        name = plugin.get("name")
        if source and name:
            modules.append((name, EMITTED_COPY / source))
    return modules


def _checksum_failures(module_dir: Path, checksums_file: Path) -> list[str]:
    failures: list[str] = []
    lines = [line for line in checksums_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    for line in lines:
        expected_hash, separator, relative_path = line.partition("  ")
        if not separator:
            failures.append(f"line without the expected 'hash  path' separator: {line!r}")
            continue
        target = module_dir / relative_path
        if not target.is_file():
            failures.append(f"listed in CHECKSUMS.txt and missing on disk: {relative_path}")
            continue
        actual_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            failures.append(f"hash mismatch: {relative_path} (expected {expected_hash[:12]}..., actual {actual_hash[:12]}...)")
    return failures


def test_marketplace_declares_at_least_one_module():
    reason = _skip_reason()
    if reason:
        pytest.skip(reason)
    assert _declared_modules(), "marketplace.json declared no module at all"


def test_checksums_of_every_distributed_module_check_out():
    reason = _skip_reason()
    if reason:
        pytest.skip(reason)
    modules = _declared_modules()
    assert modules, "marketplace.json declared no module at all"

    all_failures: list[str] = []
    modules_with_checksums = 0
    for name, module_dir in modules:
        checksums_file = module_dir / "CHECKSUMS.txt"
        if not checksums_file.is_file():
            continue
        modules_with_checksums += 1
        failures = _checksum_failures(module_dir, checksums_file)
        all_failures.extend(f"{name}: {item}" for item in failures)

    # A zero denominator is as suspicious as a failure: if NO module publishes
    # CHECKSUMS.txt, this check would pass empty and look ok without checking anything.
    assert modules_with_checksums > 0, (
        "none of the modules declared in marketplace.json publishes CHECKSUMS.txt "
        "-- the denominator of this check would be zero"
    )
    assert not all_failures, "\n".join(all_failures)


def test_CONTROLE_tampered_hash_detection_works(tmp_path):
    """
    Control, independent of the emitted copy (always runs): proves that
    `_checksum_failures` -- the SAME logic used above -- actually FAILS on a
    real hash divergence, and not just confirms the happy path.
    """
    module_dir = tmp_path / "modulo-fake"
    module_dir.mkdir()
    (module_dir / "file.txt").write_text("real content", encoding="utf-8")
    checksums_file = module_dir / "CHECKSUMS.txt"
    checksums_file.write_text("0" * 64 + "  file.txt\n", encoding="utf-8")

    failures = _checksum_failures(module_dir, checksums_file)

    assert failures
    assert "hash mismatch" in failures[0]


def test_CONTROLE_a_listed_and_missing_file_is_detected(tmp_path):
    module_dir = tmp_path / "modulo-fake-2"
    module_dir.mkdir()
    checksums_file = module_dir / "CHECKSUMS.txt"
    checksums_file.write_text("a" * 64 + "  does-not-exist.txt\n", encoding="utf-8")

    failures = _checksum_failures(module_dir, checksums_file)

    assert failures
    assert "missing on disk" in failures[0]


def test_CONTROLE_correct_checksums_do_not_produce_a_false_positive(tmp_path):
    """Symmetric control: a genuinely correct CHECKSUMS.txt does not fail."""
    module_dir = tmp_path / "modulo-ok"
    module_dir.mkdir()
    target = module_dir / "file.txt"
    target.write_text("conteudo estavel", encoding="utf-8")
    real_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    (module_dir / "CHECKSUMS.txt").write_text(f"{real_hash}  file.txt\n", encoding="utf-8")

    failures = _checksum_failures(module_dir, module_dir / "CHECKSUMS.txt")

    assert failures == []
