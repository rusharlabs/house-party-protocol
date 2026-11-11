"""Measurement readers reject linked parent paths before reading document content."""
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from hpp import journey


def directory_link(link, target):
    if os.name == "nt":
        result = subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(link), str(target)],
                                capture_output=True, check=False)
        assert result.returncode == 0, "could not create the test junction"
        assert link.lstat().st_file_attributes & 0x400
    else:
        link.symlink_to(target, target_is_directory=True)
        assert link.is_symlink()


def test_document_rejects_linked_parent_with_regular_positive_control(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "input.json").write_text('{"control":true}', encoding="utf-8")
    assert journey.read_document(real / "input.json") == {"control": True}
    linked = tmp_path / "linked"
    directory_link(linked, real)
    with pytest.raises(ValueError, match="link or reparse"):
        journey.read_document(linked / "input.json")


def test_cache_rejects_linked_parent_without_hiding_normal_cache(tmp_path, monkeypatch):
    commit = "a" * 40
    monkeypatch.setattr(journey, "snapshot", lambda target: SimpleNamespace(root=Path(target), commit=commit))
    document = {"schema": "hpp.codegraph/v1", "commit": commit}
    ordinary = tmp_path / "ordinary"
    normal_cache = ordinary / ".hpp" / "codegraph"
    normal_cache.mkdir(parents=True)
    (normal_cache / (commit + ".json")).write_text(json.dumps(document), encoding="utf-8")
    assert journey.cached_document(ordinary, "codegraph") == document
    alternate = tmp_path / "alternate"
    alternate.mkdir()
    directory_link(alternate / ".hpp", ordinary / ".hpp")
    with pytest.raises(ValueError, match="link or reparse"):
        journey.cached_document(alternate, "codegraph")
