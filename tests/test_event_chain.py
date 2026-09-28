"""The event log is a hash chain: every appended event carries the sha256 of the line before it.

A rewritten line breaks the link of the next one, and the reader names the FIRST step whose link no
longer matches instead of projecting a history that was edited. Logs written before the chain
existed carry no `prev_sha256`; they still read, and `verify` declares them `legacy` -- an upgrade
never fails an old repository. An edit of the LAST line is outside what the chain alone can see, and
the report says so by publishing `head_sha256`; only a copy of that head kept outside the line (the
next append, or one the operator keeps) anchors the tail -- an attestation does not record it.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest

from hpp import cli
from hpp.attest import create_attestation, verify_attestation
from hpp.manifest import load_manifest
from hpp.state import GENESIS_SHA256, StateError, append_event, event_path, read_events, verify_chain

PRODUCT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def manifest():
    data, _ = load_manifest()
    return data


def _lines(path):
    return path.read_bytes().split(b"\n")[:-1]


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _chained_log(path, manifest, count=3):
    for event_type in ("work_started", "evidence_recorded", "check_passed")[:count]:
        append_event(path, event_type, manifest)
    return path


# --------------------------------------------------------------------------- the chain

def test_every_appended_event_links_to_the_bytes_of_the_line_before_it(manifest, tmp_path):
    path = _chained_log(event_path(tmp_path), manifest)
    lines = _lines(path)
    events = [json.loads(line) for line in lines]
    assert events[0]["prev_sha256"] == GENESIS_SHA256
    assert GENESIS_SHA256 == _sha(b"")  # the chain starts at the hash of nothing, a documented constant
    assert events[1]["prev_sha256"] == _sha(lines[0])
    assert events[2]["prev_sha256"] == _sha(lines[1])


def test_a_rewritten_line_is_named_as_the_first_divergent_step(manifest, tmp_path):
    path = _chained_log(event_path(tmp_path), manifest)
    lines = _lines(path)
    second = json.loads(lines[1])
    second["data"] = {"edited": True}  # seq and id untouched: the old checks cannot see this
    lines[1] = json.dumps(second, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path.write_bytes(b"\n".join(lines) + b"\n")

    with pytest.raises(StateError, match=r"event:3"):
        read_events(path)
    report = verify_chain(path)
    assert report["status"] == "broken"
    assert report["first_divergent"] == "event:3"
    assert report["events"] == 3


def test_a_malformed_link_is_a_corrupt_log(manifest, tmp_path):
    path = _chained_log(event_path(tmp_path), manifest, count=1)
    event = json.loads(_lines(path)[0])
    event["prev_sha256"] = "not-a-digest"
    path.write_text(json.dumps(event) + "\n", encoding="utf-8")
    with pytest.raises(StateError, match="prev_sha256"):
        read_events(path)
    assert verify_chain(path)["status"] == "broken"


def test_the_head_is_published_so_the_tail_can_be_anchored_elsewhere(manifest, tmp_path):
    path = _chained_log(event_path(tmp_path), manifest)
    before = verify_chain(path)
    assert before["head_sha256"] == _sha(_lines(path)[-1])
    append_event(path, "human_approved", manifest)
    after = verify_chain(path)
    assert after["head_sha256"] != before["head_sha256"]
    assert json.loads(_lines(path)[-1])["prev_sha256"] == before["head_sha256"]


# --------------------------------------------------------------------------- legacy logs

def _legacy_log(path, types):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for index, event_type in enumerate(types, 1):
            handle.write(json.dumps({"seq": index, "id": f"event:{index}", "type": event_type, "data": {}}) + "\n")
    return path


def test_a_log_written_before_the_chain_still_reads_and_is_declared_legacy(manifest, tmp_path):
    path = _legacy_log(event_path(tmp_path), ["work_started", "evidence_recorded"])
    assert [event["type"] for event in read_events(path)] == ["work_started", "evidence_recorded"]
    report = verify_chain(path)
    assert report["status"] == "legacy"
    assert report["legacy"] == 2 and report["chained"] == 0 and report["first_divergent"] is None


def test_appending_to_a_legacy_log_starts_the_chain_from_its_last_line(manifest, tmp_path):
    path = _legacy_log(event_path(tmp_path), ["work_started", "evidence_recorded"])
    last_legacy = _lines(path)[-1]
    append_event(path, "check_passed", manifest)
    new = json.loads(_lines(path)[-1])
    assert new["prev_sha256"] == _sha(last_legacy)
    report = verify_chain(path)
    assert report["status"] == "legacy" and report["legacy"] == 2 and report["chained"] == 1


# --------------------------------------------------------------------------- controls

def test_CONTROLE_an_intact_chain_verifies_as_intact_with_no_divergent_step(manifest, tmp_path):
    report = verify_chain(_chained_log(event_path(tmp_path), manifest))
    assert report["status"] == "intact"
    assert report["chained"] == 3 and report["legacy"] == 0 and report["first_divergent"] is None


def test_CONTROLE_an_absent_log_is_empty_not_broken(tmp_path):
    report = verify_chain(event_path(tmp_path))
    assert report["status"] == "empty" and report["events"] == 0 and report["head_sha256"] is None


def test_CONTROLE_a_line_that_is_not_json_is_broken_at_that_line(tmp_path):
    path = event_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("not json\n", encoding="utf-8")
    report = verify_chain(path)
    assert report["status"] == "broken" and report["first_divergent"] == "line 1"


# --------------------------------------------------------------------------- the call sites

def test_event_verify_exits_0_on_an_intact_chain_and_2_on_a_broken_one(manifest, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    path = _chained_log(event_path(tmp_path), manifest)
    assert cli.main(["event", "verify"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "intact"

    lines = _lines(path)
    lines[0] = lines[0].replace(b'"data":{}', b'"data":{"x":1}')
    path.write_bytes(b"\n".join(lines) + b"\n")
    assert cli.main(["event", "verify"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "broken" and report["first_divergent"] == "event:2"


def test_status_refuses_a_broken_chain_and_names_the_step(manifest, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    path = _chained_log(event_path(tmp_path), manifest)
    lines = _lines(path)
    lines[1] = lines[1].replace(b'"data":{}', b'"data":{"x":1}')
    path.write_bytes(b"\n".join(lines) + b"\n")
    assert cli.main(["status"]) == 2
    captured = capsys.readouterr()
    assert "event:3" in captured.err


def test_status_json_carries_the_chain_summary(manifest, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _chained_log(event_path(tmp_path), manifest)
    assert cli.main(["status", "--json"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["chain"]["status"] == "intact" and status["chain"]["chained"] == 3
    assert status["chain"]["head_sha256"]


def test_CONTROLE_event_verify_exits_0_on_a_legacy_log(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _legacy_log(event_path(tmp_path), ["work_started"])
    assert cli.main(["event", "verify"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "legacy"


# --------------------------------------------------------------------------- what anchors the tail
#
# The documentation used to name an attestation among what anchors the tail. Measured here: the
# attestation record carries no `head_sha256`, and it binds the log only when `.hpp/events.jsonl` is
# inside its git snapshot -- which a checkout that ignores `.hpp/` (the published one does) leaves out.

def _repo(tmp_path, ignore_hpp: bool) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (("init", "-q"), ("config", "user.name", "HPP Test"), ("config", "user.email", "hpp@example.invalid")):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    (repo / ".gitignore").write_text(".hpp/\n" if ignore_hpp else "", encoding="utf-8")
    (repo / "SPEC.md").write_text("build the bounded change\n", encoding="utf-8")
    subprocess.run(["git", "add", ".gitignore", "SPEC.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=repo, check=True, capture_output=True)
    return repo


def _attest_then_edit_the_last_event(repo: Path, manifest) -> tuple[dict, dict]:
    log = _chained_log(event_path(repo), manifest)
    record = create_attestation(repo=repo, spec=repo / "SPEC.md", output=repo / "attestation.json",
                                maker="maker-a", checker="checker-b", session="review:001", verdict="approved")
    lines = _lines(log)
    last = json.loads(lines[-1])
    last["data"] = {"edited": True}
    lines[-1] = json.dumps(last, sort_keys=True, separators=(",", ":")).encode("utf-8")
    log.write_bytes(b"\n".join(lines) + b"\n")
    return record, verify_attestation(repo / "attestation.json", repo)


def test_an_attestation_does_not_record_the_chain_head(manifest, tmp_path):
    record, _ = _attest_then_edit_the_last_event(_repo(tmp_path, ignore_hpp=True), manifest)
    assert "head_sha256" not in json.dumps(record)


def test_where_hpp_is_ignored_an_attestation_does_not_see_an_edit_of_the_last_event(manifest, tmp_path):
    repo = _repo(tmp_path, ignore_hpp=True)
    _record, report = _attest_then_edit_the_last_event(repo, manifest)
    assert report["status"] == "valid", report
    assert verify_chain(event_path(repo))["status"] == "intact", "the chain alone cannot see a last-line edit"


def test_CONTROLE_where_the_log_is_in_the_snapshot_the_same_edit_blocks_the_attestation(manifest, tmp_path):
    _record, report = _attest_then_edit_the_last_event(_repo(tmp_path, ignore_hpp=False), manifest)
    assert report["status"] == "blocked" and "snapshot_digest" in report["mismatches"], report


@pytest.mark.parametrize("path, pattern", [
    ("docs/CONCEPTS.md", r"anchored[^.]*attestation"),
    ("docs/CONCEPTS.pt-BR.md", r"ancorada[^.]*attestation"),
    ("hpp/state.py", r"anchored[^.]*attestation"),
    ("tests/test_event_chain.py", r"anchored[^.]*attestation"),
])
def test_no_text_names_an_attestation_as_what_anchors_the_tail(path, pattern):
    """The three tests above are what is true; the text has to say that, not more."""
    text = " ".join((PRODUCT_ROOT / path).read_text(encoding="utf-8").split())
    found = re.findall(pattern, text)
    assert not found, f"{path} names an attestation as an anchor of the tail: {found}"


def test_CONTROLE_the_anchor_detector_fires_on_the_old_wording():
    # spelled in two pieces, so this file does not carry the sentence its own check forbids
    old = "The tail is anchored by whatever records the chain's `head_sha256` — the next append, an attest" + "ation"
    assert re.findall(r"anchored[^.]*attestation", old)
    assert re.findall(r"ancorada[^.]*attestation", "A cauda é ancorada por quem registra o `head_sha256` "
                                                   "da cadeia — o próximo append, uma attest" + "ation")
