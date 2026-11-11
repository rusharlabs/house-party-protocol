"""Committed-byte provenance, freshness and repository-execution refusal controls."""
import os
from pathlib import Path
import subprocess
import unicodedata

import pytest

from hpp._repository import (RepositoryError, artifact_status, changed_paths_since, read_blob,
                             read_text, snapshot, write_artifact)


def git(root, *args, env=None):
    result = subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", str(root), *args],
                            env=env, capture_output=True, check=True)
    return result.stdout.decode("utf-8").strip()


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "Test Author")
    git(root, "config", "user.email", "author@example.invalid")
    (root / "app.py").write_text("committed = True\n", encoding="utf-8")
    git(root, "add", "app.py")
    git(root, "commit", "-qm", "fixture")
    return root


def test_head_bytes_and_tracked_dirty_are_separate_from_untracked(repo):
    baseline = snapshot(repo)
    assert read_text(baseline, "app.py") == "committed = True\n"
    (repo / "app.py").write_text("changed\n", encoding="utf-8")
    (repo / "untracked.py").write_text("not in universe", encoding="utf-8")
    snap = snapshot(repo)
    assert snap.commit == baseline.commit
    assert snap.files == ("app.py",)
    assert snap.dirty_paths == ("app.py",)
    assert read_text(snap, "app.py") == "committed = True\n"
    assert artifact_status(repo, {"schema": "hpp.inventory/v1", "commit": snap.commit})["status"] == "stale"


def test_staged_new_file_is_dirty_but_not_a_head_blob(repo):
    (repo / "new.py").write_text("new", encoding="utf-8")
    git(repo, "add", "new.py")
    snap = snapshot(repo)
    assert "new.py" in snap.dirty_paths and "new.py" not in snap.files
    with pytest.raises(RepositoryError):
        read_blob(snap, "new.py")


def test_fresh_stale_absent_invalid_and_explicit_non_overwrite_cache(repo):
    snap = snapshot(repo)
    doc = {"schema": "hpp.inventory/v1", "commit": snap.commit, "files": list(snap.files)}
    assert artifact_status(repo, None)["status"] == "absent"
    assert artifact_status(repo, Path("missing.json"))["status"] == "absent"
    assert artifact_status(repo, {"schema": "oops", "commit": snap.commit})["status"] == "invalid"
    assert artifact_status(repo, {"schema": "hpp.inventory/v1", "commit": "0" * 40})["status"] == "invalid"
    assert artifact_status(repo, doc)["status"] == "fresh"
    before = git(repo, "ls-files", "--stage")
    path = write_artifact(repo, "inventory", doc)
    assert path == repo / ".hpp/inventory" / (snap.commit + ".json")
    assert artifact_status(repo, path)["status"] == "fresh"
    assert write_artifact(repo, "inventory", doc) == path
    with pytest.raises(RepositoryError, match="different content"):
        write_artifact(repo, "inventory", {**doc, "files": []})
    assert git(repo, "ls-files", "--stage") == before
    (repo / "app.py").write_text("next\n", encoding="utf-8")
    git(repo, "add", "app.py")
    git(repo, "commit", "-qm", "next")
    state = artifact_status(repo, doc)
    assert state["status"] == "stale" and state["commits_behind"] == 1
    assert state["changed_files"] == 1 and state["changed_paths"] == ["app.py"]
    assert changed_paths_since(snapshot(repo), snap.commit) == ("app.py",)


def test_non_git_unborn_invalid_paths_and_limits_have_sanitized_errors(tmp_path, repo):
    empty = tmp_path / "private-user-path"
    empty.mkdir()
    for target in (empty, empty / "not-there"):
        with pytest.raises(RepositoryError) as error:
            snapshot(target)
        assert str(tmp_path) not in str(error.value)
    git(empty, "init", "-q")
    with pytest.raises(RepositoryError):
        snapshot(empty)
    snap = snapshot(repo)
    for path in ("../app.py", "/app.py", "app\\file", "C:/app.py"):
        with pytest.raises(RepositoryError):
            read_blob(snap, path)
    with pytest.raises(RepositoryError, match="read limit"):
        read_blob(snap, "app.py", max_bytes=1)


def test_secret_files_are_metadata_only_and_never_requested_from_git(repo, monkeypatch):
    (repo / ".env").write_text("PASSWORD=never-copy-this-value\n", encoding="utf-8")
    git(repo, "add", ".env")
    git(repo, "commit", "-qm", "secret presence fixture")
    snap = snapshot(repo)
    assert ".env" in snap.files
    import hpp._repository as module
    monkeypatch.setattr(module, "_git", lambda *args, **kwargs: pytest.fail("secret content requested from Git"))
    with pytest.raises(RepositoryError, match="secret-file"):
        read_blob(snap, ".env")


def test_nfc_paths_are_stable_even_if_git_stores_decomposed_name(repo):
    raw = "caf\u0065\u0301.py"
    (repo / raw).write_text("nfc = True\n", encoding="utf-8")
    git(repo, "add", "--", raw)
    git(repo, "commit", "-qm", "unicode")
    snap = snapshot(repo)
    normalized = unicodedata.normalize("NFC", raw)
    assert normalized in snap.files
    assert read_text(snap, normalized) == "nfc = True\n"


def test_symlink_and_gitlink_blobs_are_never_followed(repo):
    blob = git(repo, "rev-parse", "HEAD:app.py")
    git(repo, "update-index", "--add", "--cacheinfo", "120000," + blob + ",link.py")
    git(repo, "update-index", "--add", "--cacheinfo", "160000," + git(repo, "rev-parse", "HEAD") + ",vendor")
    git(repo, "commit", "-qm", "link metadata")
    snap = snapshot(repo)
    assert snap.modes["link.py"] == "120000" and snap.modes["vendor"] == "160000"
    assert "link.py" not in snap.files and "vendor" not in snap.files
    for name in ("link.py", "vendor"):
        with pytest.raises(RepositoryError):
            read_blob(snap, name)


def test_symlink_cache_parent_is_refused(repo, tmp_path):
    destination = tmp_path / "elsewhere"
    destination.mkdir()
    try:
        (repo / ".hpp").symlink_to(destination, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        subprocess.run(["cmd", "/c", "mklink", "/J", str(repo / ".hpp"), str(destination)],
                       check=True, capture_output=True)
    snap = snapshot(repo)
    with pytest.raises(RepositoryError, match="reparse|symlink"):
        write_artifact(repo, "inventory", {"schema": "hpp.inventory/v1", "commit": snap.commit})
    assert not list(destination.iterdir())


def test_fsmonitor_filters_diff_textconv_and_gpg_are_not_executed(repo):
    (repo / ".gitattributes").write_text("*.py filter=trap diff=trap\n", encoding="utf-8")
    git(repo, "add", ".gitattributes")
    git(repo, "commit", "-qm", "attributes")
    marker = repo / "trap-was-executed"
    command = f'echo executed > "{marker.as_posix()}"'
    for key in ("core.fsmonitor", "filter.trap.clean", "filter.trap.process", "diff.trap.command", "diff.trap.textconv", "gpg.program"):
        git(repo, "config", key, command)
    git(repo, "config", "log.showSignature", "true")
    (repo / "app.py").write_text("dirty to trigger content comparison\n", encoding="utf-8")
    snap = snapshot(repo)
    read_text(snap, "app.py")
    changed_paths_since(snap, snap.commit)
    assert snap.dirty_paths == ("app.py",)
    assert not marker.exists()


def test_dirty_artifact_cannot_poison_the_immutable_commit_cache(repo):
    snap = snapshot(repo)
    (repo / "app.py").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(RepositoryError, match="clean tracked snapshot"):
        write_artifact(repo, "inventory", {"schema": "hpp.inventory/v1", "commit": snap.commit})
    assert not (repo / ".hpp").exists()


def test_instrument_failure_document_is_not_fresh(repo):
    snap = snapshot(repo)
    assert artifact_status(repo, {"schema": "hpp.codegraph/v1", "commit": snap.commit,
                                  "status": "instrument-failure"})["status"] == "invalid"


def test_line_endings_follow_effective_git_configuration(repo):
    # Git's own clean control must agree; byte-for-byte worktree comparison is wrong.
    git(repo, "config", "core.autocrlf", "true")
    (repo / "app.py").write_bytes(b"committed = True\r\n")
    assert git(repo, "status", "--porcelain") == ""
    assert snapshot(repo).dirty_paths == ()


def test_nfc_collisions_are_input_failures_instead_of_silent_deduplication(repo):
    blob = git(repo, "rev-parse", "HEAD:app.py")
    for name in ("caf\u0065\u0301.py", "caf\u00e9.py"):
        git(repo, "update-index", "--add", "--cacheinfo", "100644," + blob + "," + name)
    git(repo, "commit", "-qm", "colliding paths")
    with pytest.raises(RepositoryError, match="collide"):
        snapshot(repo)


def test_secret_named_output_is_refused_without_reading_its_values(repo):
    snap = snapshot(repo)
    with pytest.raises(RepositoryError, match="secret-file path"):
        write_artifact(repo, "inventory", {"schema": "hpp.inventory/v1", "commit": snap.commit}, out=".env")
    assert not (repo / ".env").exists()


def test_invalid_artifact_json_and_large_input_are_bounded(repo):
    path = repo / "bad.json"
    path.write_bytes(b"not-json-private-value")
    assert artifact_status(repo, path)["status"] == "invalid"
    path.write_bytes(b" " * (4 * 1024 * 1024 + 1))
    assert artifact_status(repo, path)["status"] == "invalid"
