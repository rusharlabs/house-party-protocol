"""The project journey uses real committed inputs and never silently writes a cache."""
from __future__ import annotations

import json
import hashlib
import subprocess

import pytest

from hpp.atlas import render_atlas
from hpp.cli import main
from hpp.journey import project_journey, read_document


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True).stdout.decode().strip()


@pytest.fixture
def project(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "Example")
    git(tmp_path, "config", "user.email", "example@example.invalid")
    (tmp_path / "app.py").write_text("def total():\n    return 1\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text(".hpp/\n", encoding="utf-8")
    git(tmp_path, "add", "app.py", ".gitignore")
    message = tmp_path / "commit.txt"
    message.write_text("Initial fixture\n", encoding="utf-8")
    git(tmp_path, "commit", "-q", "-F", str(message))
    message.unlink()
    return tmp_path


def test_cli_inventory_and_graph_default_no_writes(project, capsys):
    before = set(project.rglob("*"))
    assert main(["inventory", "--target", str(project)]) == 0
    inventory = json.loads(capsys.readouterr().out)
    assert inventory["schema"] == "hpp.inventory/v1"
    assert inventory["commit"] == git(project, "rev-parse", "HEAD")
    assert main(["codegraph", "build", "--target", str(project)]) == 0
    graph = json.loads(capsys.readouterr().out)
    assert graph["instrument"]["status"] == "measured"
    assert set(project.rglob("*")) == before
    assert not (project / ".hpp").exists()


def test_explicit_cache_advances_journey_then_dirty_marks_stale(project, capsys):
    assert project_journey(project)["next_command"] == "hpp init --target ."
    (project / ".hpp").mkdir()
    (project / ".hpp/profile.json").write_text('{"schema":"hpp.init/v1"}', encoding="utf-8")
    assert project_journey(project)["next_command"] == "hpp inventory --target . --out"
    assert main(["inventory", "--target", str(project), "--out"]) == 0
    capsys.readouterr()
    assert project_journey(project)["next_command"] == "hpp codegraph build --target . --out"
    assert main(["codegraph", "build", "--target", str(project), "--out"]) == 0
    capsys.readouterr()
    assert project_journey(project)["next_command"] == "hpp lanes propose --target ."
    (project / "app.py").write_text("changed = True\n", encoding="utf-8")
    status = project_journey(project)
    assert status["inventory"]["status"] == "stale"
    assert status["codegraph"]["status"] == "stale"
    assert status["next_command"] == "hpp inventory --target . --out"


def test_lanes_default_is_only_a_proposal(project, capsys):
    assert main(["lanes", "propose", "--target", str(project)]) == 0
    proposal = json.loads(capsys.readouterr().out)
    assert proposal["schema"] == "hpp.lane-proposal/v1"
    assert not (project / ".hpp").exists()
    assert not (project / ".claude").exists()


def test_wrong_kind_cannot_complete_an_inventory_stage(project):
    fake = {"schema": "hpp.codegraph/v1", "commit": git(project, "rev-parse", "HEAD")}
    report = project_journey(project, inventory=fake)
    assert report["inventory"]["status"] == "invalid"


def test_project_atlas_includes_coverage_and_stale_marker(project, capsys):
    assert main(["codegraph", "build", "--target", str(project), "--out"]) == 0
    capsys.readouterr()
    page = render_atlas(project)
    assert 'id="project"' in page
    assert 'id="project-code"' in page
    assert "fresh" in page
    assert "symbols" in page or "coverage" in page
    for args in (["inventory", "--inspect"], ["codegraph", "show"]):
        assert main([*args, "--target", str(project)]) == 0
        value = json.loads(capsys.readouterr().out)
        canonical = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        assert hashlib.sha256(canonical.encode("ascii")).hexdigest() in page
    (project / "app.py").write_text("changed = True\n", encoding="utf-8")
    assert "stale" in render_atlas(project)


def test_invalid_and_oversized_measurement_is_not_accepted(tmp_path):
    source = tmp_path / "input.json"
    source.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="object"):
        read_document(source)
    source.write_bytes(b" " * (4 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="exceeds"):
        read_document(source)


def test_external_failure_cannot_be_cached(project, capsys):
    assert main(["codegraph", "build", "--target", str(project), "--indexer-command",
                 '["nonexistent-indexer-example"]', "--out"]) == 2
    assert "failure" in capsys.readouterr().err
    assert not (project / ".hpp").exists()


def test_measurement_symlink_is_refused(tmp_path):
    real = tmp_path / "real.json"
    real.write_text("{}", encoding="utf-8")
    link = tmp_path / "linked.json"
    try:
        link.symlink_to(real)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(ValueError, match="link"):
        read_document(link)
