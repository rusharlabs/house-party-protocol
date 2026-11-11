"""A wave references a bounded local proposal; it never treats it as configuration."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import errno
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.fixture
def dashboard():
    product = Path(__file__).resolve().parents[1]
    modules = sorted(product.glob("multi-session/lane-kit-*/scripts/lane_dashboard.py"))
    if not modules:
        source = product.parents[2] / "staging/lane-kit/scripts/lane_dashboard.py"
        if not source.is_file():
            pytest.skip("requires the emitted lane-kit or a source checkout")
        modules = [source]
    assert len(modules) == 1
    spec = importlib.util.spec_from_file_location("hpp_lane_proposal_dashboard", modules[0])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_proposal_reference_binds_exact_bytes_and_commit(dashboard, tmp_path):
    source = tmp_path / "proposal.json"
    raw = json.dumps({"schema": "hpp.lane-proposal/v1", "commit": "a" * 40, "lanes": []}).encode()
    source.write_bytes(raw)
    assert dashboard._proposal_reference(tmp_path, "proposal.json") == {
        "path": "proposal.json", "commit": "a" * 40, "sha256": hashlib.sha256(raw).hexdigest()}
    assert dashboard._proposal_reference(tmp_path, None) is None
    args = dashboard.build_cli_parser().parse_args(["wave", "start", "--spec", "ONE", "--mode", "solo",
                                                 "--agent", "claude", "--lane-proposal", "proposal.json"])
    assert args.lane_proposal == "proposal.json"


@pytest.mark.parametrize("value", ["../outside.json", "/absolute.json", "", 12])
def test_proposal_reference_refuses_unbounded_paths(dashboard, tmp_path, value):
    with pytest.raises(ValueError):
        dashboard._proposal_reference(tmp_path, value)


def test_proposal_reference_refuses_bad_schema_and_overflow(dashboard, tmp_path):
    source = tmp_path / "proposal.json"
    source.write_text('{"schema":"hpp.lanes/v0"}', encoding="utf-8")
    with pytest.raises(ValueError, match="schema|hpp.lane-proposal"):
        dashboard._proposal_reference(tmp_path, "proposal.json")
    source.write_bytes(b" " * (1024 * 1024 + 1))
    with pytest.raises(ValueError, match="exceeds"):
        dashboard._proposal_reference(tmp_path, "proposal.json")


def test_proposal_reference_refuses_internal_junction_or_symlink(dashboard, tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "proposal.json").write_text(json.dumps({"schema": "hpp.lane-proposal/v1", "commit": "a" * 40}), encoding="utf-8")
    assert dashboard._proposal_reference(tmp_path, "real/proposal.json")["commit"] == "a" * 40
    link = tmp_path / "linked"
    if os.name == "nt":
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(real)], capture_output=True)
        assert result.returncode == 0, "Windows must create the junction fixture: " + repr(result.stderr)
        assert getattr(link.lstat(), "st_file_attributes", 0) & 0x400
        assert not getattr(link.stat(), "st_file_attributes", 0) & 0x400
        assert not link.is_symlink(), "the control must exercise a junction, not the existing symlink guard"
    else:
        try:
            link.symlink_to(real, target_is_directory=True)
        except OSError as error:
            if error.errno in {errno.ENOSYS, errno.EOPNOTSUPP, errno.EPERM}:
                pytest.skip("this filesystem does not permit creating the symlink fixture")
            raise
        assert link.is_symlink()
    # The target stays within the project, so rejection must come from the link guard.
    assert link.resolve() == real.resolve()
    with pytest.raises(ValueError, match="links|reparse"):
        dashboard._proposal_reference(tmp_path, "linked/proposal.json")
