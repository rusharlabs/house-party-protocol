"""Append-only event log, status projection, and resume that never re-runs a
step already completed.

Every test passes `tmp_path` explicitly to `event_path`/`append_event` --
none depends on the real cwd nor on execution order between them.
"""
from __future__ import annotations

import json

import pytest

from hpp.manifest import load_manifest
from hpp.state import StateError, append_event, event_path, project, read_events


@pytest.fixture()
def manifest():
    data, _ = load_manifest()
    return data


def test_event_path_derives_from_the_given_workspace_not_the_cwd(tmp_path):
    assert event_path(tmp_path) == tmp_path.resolve() / ".hpp" / "events.jsonl"


def test_missing_log_projects_the_initial_state_declared_by_the_manifest(manifest, tmp_path):
    path = event_path(tmp_path)
    assert not path.exists()
    status = project(read_events(path), manifest)
    assert status["state"] == manifest["loop"]["initial"]
    assert status["event_count"] == 0
    assert status["history"] == []
    assert status["next_step"]


def test_full_sequence_advances_to_the_last_state_of_the_loop(manifest, tmp_path):
    path = event_path(tmp_path)
    ordered_events = [transition["event"] for transition in manifest["loop"]["transitions"]]
    result = None
    for event_type in ordered_events:
        result = append_event(path, event_type, manifest)
    assert result["state"] == manifest["loop"]["transitions"][-1]["to"]
    assert result["event_count"] == len(ordered_events)
    assert result["evidence_count"] >= 1


def test_event_log_is_append_only_old_records_are_never_rewritten(manifest, tmp_path):
    path = event_path(tmp_path)
    append_event(path, "work_started", manifest)
    append_event(path, "evidence_recorded", manifest)
    lines_after_two = path.read_text(encoding="utf-8").splitlines()
    assert len(lines_after_two) == 2
    first_record = json.loads(lines_after_two[0])
    second_record = json.loads(lines_after_two[1])
    assert first_record == {"seq": 1, "id": "event:1", "type": "work_started", "data": {}}
    assert second_record["seq"] == 2 and second_record["id"] == "event:2"

    append_event(path, "check_passed", manifest)
    lines_after_three = path.read_text(encoding="utf-8").splitlines()
    assert len(lines_after_three) == 3
    # the first two lines remain byte-for-byte identical: real append-only
    assert lines_after_three[0] == lines_after_two[0]
    assert lines_after_three[1] == lines_after_two[1]


def test_transition_that_skips_loop_steps_is_rejected_and_nothing_is_written(manifest, tmp_path):
    path = event_path(tmp_path)
    with pytest.raises(StateError):
        append_event(path, "human_approved", manifest)  # from the initial state straight to the end
    assert not path.exists()


def test_resume_does_not_re_run_an_event_already_applied(manifest, tmp_path):
    """
    'resume' derives the next step from the event log, never from an external
    task list -- so reapplying an event that already moved the loop forward is
    not a valid transition from the current state, and the log stays intact.
    """
    path = event_path(tmp_path)
    append_event(path, "work_started", manifest)
    status_before = project(read_events(path), manifest)

    with pytest.raises(StateError):
        append_event(path, "work_started", manifest)  # 'active' does not accept 'work_started' again

    status_after = project(read_events(path), manifest)
    assert status_after == status_before


def test_verified_requires_evidence_even_under_a_custom_loop_with_a_shortcut():
    """
    Under the real manifest's transitions, this path is unreachable (the only
    way to reach 'approved' goes through 'evidenced', which requires
    'evidence_recorded'). The invariant in `project()` is tested here in
    isolation, directly on the function, with a minimal loop that declares a
    shortcut with no evidence -- proves that the check does not depend on the
    real manifest's topology to hold.
    """
    shortcut_manifest = {
        "loop": {
            "initial": "planned",
            "transitions": [
                {"from": "planned", "event": "work_started", "to": "active", "gate": "scope"},
                {"from": "active", "event": "verified", "to": "verified", "gate": "shortcut"},
            ],
        }
    }
    events = [{"type": "work_started"}, {"type": "verified"}]
    with pytest.raises(StateError, match="evidence"):
        project(events, shortcut_manifest)


def test_CONTROLE_a_log_with_a_corrupted_json_line_is_detected(tmp_path):
    path = event_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("isto nao e json\n", encoding="utf-8")
    with pytest.raises(StateError):
        read_events(path)


def test_CONTROLE_non_contiguous_seq_is_rejected(tmp_path):
    path = event_path(tmp_path)
    path.parent.mkdir(parents=True)
    record = json.dumps({"seq": 5, "id": "event:5", "type": "work_started"})
    path.write_text(record + "\n", encoding="utf-8")
    with pytest.raises(StateError):
        read_events(path)


def test_CONTROLE_id_that_does_not_match_the_line_is_rejected(tmp_path):
    path = event_path(tmp_path)
    path.parent.mkdir(parents=True)
    record = json.dumps({"seq": 1, "id": "event:999", "type": "work_started"})
    path.write_text(record + "\n", encoding="utf-8")
    with pytest.raises(StateError):
        read_events(path)


def test_CONTROLE_a_truly_empty_log_is_not_mistaken_for_a_corrupted_log(tmp_path):
    """Control: an empty file (or one with only blank lines) is a VALID and
    empty log, not an error -- proves that the corruption detector does not shout for nothing."""
    path = event_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("\n\n", encoding="utf-8")
    assert read_events(path) == []
