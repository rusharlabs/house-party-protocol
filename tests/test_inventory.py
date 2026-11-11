"""Inventory counts evidence without running commands or copying private values."""
import json
import os
import subprocess

import pytest

from hpp._repository import RepositoryError, snapshot
from hpp.inventory import build_inventory


def git(root, *args, env=None):
    return subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", str(root), *args], env=env,
                          check=True, capture_output=True).stdout.decode().strip()


@pytest.fixture
def project(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "Private Author Alpha")
    git(tmp_path, "config", "user.email", "private-author@example.invalid")
    fixture_credential = "".join(("gh", "p_", "PrivateCredentialValue", "123456"))
    files = {
        "pyproject.toml": '[tool.pytest.ini_options]\ntestpaths=["tests"]\n',
        "nested/package.json": json.dumps({"scripts": {"test": "vitest run"}}),
        "tests/test_app.py": "raise Exception('MUST NOT RUN')\n",
        "app.py": "raise Exception('MUST NOT IMPORT')\n",
        "docs/guide.md": "# Guide\n", "README.md": "# App\n",
        "AGENTS.md": "instructions", ".github/CODEOWNERS": "* @private-person\n",
        ".claude/settings.json": json.dumps({"hooks": {"PreToolUse": [{"hooks": [{"command": "never-run-hook"}, {"command": "another-hook"}]}]}, "env": {"TOKEN": "never-copy-env-value"}}),
        ".env": "PASSWORD=never-read-env-value\n",
        ".github/workflows/ci.yml": f"jobs:\n  test:\n    steps:\n      - run: python -m pytest -q\n      - run: |\n          echo {fixture_credential}\n          pytest\n",
    }
    for path, content in files.items():
        dest = tmp_path / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
    git(tmp_path, "add", "--", *files)
    git(tmp_path, "commit", "-qm", "private commit message must not enter inventory")
    return tmp_path


def test_inventory_uses_head_and_declares_universe_and_privacy(project):
    first = build_inventory(project)
    assert first == build_inventory(project)
    assert first["schema"] == "hpp.inventory/v1"
    assert first["universe"]["tracked_files"] == 11
    assert len(first["files"]) == first["universe"]["files"] == 10
    assert ".env" not in first["files"]
    assert first["sections"]["tests"]["count"] == 1
    assert first["sections"]["agent_config"]["hooks_by_event"] == {"PreToolUse": 2}
    assert first["sections"]["ownership"]["authors_count"] == 1
    assert len(first["sections"]["ci"]["run"]) == 2
    assert first["sections"]["ci"]["run"][1]["withheld"] is True
    serialized = json.dumps(first)
    for forbidden in ("never-read-env-value", "never-copy-env-value", "PrivateCredentialValue", "Private Author", "private-author@", "private-person", "private commit message", "never-run-hook", str(project)):
        assert forbidden not in serialized
    (project / "pyproject.toml").write_text("broken local edits", encoding="utf-8")
    (project / "untracked.js").write_text("not measured", encoding="utf-8")
    changed = build_inventory(project)
    assert changed["sections"] == first["sections"]
    assert changed["files"] == first["files"] and changed["dirty_tracked"] == 1
    assert not (project / ".hpp").exists()


def test_hotspot_window_counts_commits_not_lines_and_authors_only_count(project):
    (project / "app.py").write_text("second\n" * 50, encoding="utf-8")
    git(project, "add", "app.py")
    env = {**os.environ, "GIT_AUTHOR_NAME": "Private Author Beta", "GIT_AUTHOR_EMAIL": "other-private@example.invalid"}
    git(project, "commit", "-qm", "second confidential message", env=env)
    result = build_inventory(project, history_limit=1)
    assert result["sections"]["ownership"]["authors_count"] == 2
    assert result["sections"]["hotspots"]["commits_measured"] == 1
    assert result["sections"]["hotspots"]["top"] == [["app.py", 1]]
    assert "Beta" not in json.dumps(result) and "confidential" not in json.dumps(result)
    assert build_inventory(project)["sections"]["hotspots"]["top"][0] == ["app.py", 2]


@pytest.mark.parametrize("limit", [0, -1, True, "200", 10001])
def test_invalid_window_is_an_input_failure(project, limit):
    with pytest.raises(RepositoryError):
        build_inventory(project, limit)


def test_inventory_never_reads_env_blob(project, monkeypatch):
    import hpp.inventory as module
    original = module.read_text
    def controlled(snap, path, *args):
        assert path != ".env"
        return original(snap, path, *args)
    monkeypatch.setattr(module, "read_text", controlled)
    assert build_inventory(project)["universe"]["excluded"][0]["path"] == ".env"


def test_absent_means_measured_zero_for_a_minimal_repository(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "Author")
    git(tmp_path, "config", "user.email", "author@example.invalid")
    (tmp_path / "a.txt").write_text("data", encoding="utf-8")
    git(tmp_path, "add", "a.txt")
    git(tmp_path, "commit", "-qm", "one")
    inventory = build_inventory(tmp_path)
    for section in ("stack", "tests", "ci", "docs", "agent_config"):
        assert inventory["sections"][section]["status"] == "absent"
    assert inventory["sections"]["relations"]["status"] == "not-measured"
    assert inventory["commit"] == snapshot(tmp_path).commit


def test_author_counts_do_not_use_a_dirty_mailmap(project):
    baseline = build_inventory(project)
    (project / ".mailmap").write_text("Changed <different@example.invalid> Private Author Alpha <private-author@example.invalid>\n", encoding="utf-8")
    assert build_inventory(project)["sections"]["ownership"] == baseline["sections"]["ownership"]
