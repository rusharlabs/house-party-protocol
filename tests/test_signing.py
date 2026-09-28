"""Attestations and evidence records can be signed with an SSH key and verified offline.

The self-hash of a record makes an edit visible and proves nothing about who wrote it. A signature
does: `--sign-key` signs the canonical bytes of the record with `ssh-keygen -Y sign` (namespace
`hpp`), and `--allowed-signers` verifies them with `ssh-keygen -Y verify` against the keys a
verifier trusts. No new dependency: the harness only runs the OpenSSH binary already on the machine,
and never reads the key itself. Signing stays optional -- an unsigned record verifies exactly as
before (the CONTROLE tests below) -- and the harness never says `verified` when it could not check:
a missing binary, a signer outside the allowed list, or bytes changed after signing all refuse.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from hpp import cli
from hpp.attest import AttestationError, create_attestation, verify_attestation
from hpp.evidence import EvidenceError, _canonical, _sha256, run_evidence, verify_evidence
import hpp.signing as signing

SSH_KEYGEN = shutil.which("ssh-keygen")
pytestmark = pytest.mark.skipif(SSH_KEYGEN is None, reason="ssh-keygen is not on PATH: OpenSSH is needed to sign")

WRITE_ONE = "import pathlib; p = pathlib.Path('out'); p.mkdir(exist_ok=True); (p / 'shot.png').write_bytes(b'png')"


def _keygen(directory: Path, name: str) -> tuple[Path, str]:
    private = directory / name
    subprocess.run([SSH_KEYGEN, "-q", "-t", "ed25519", "-N", "", "-C", f"{name}@hpp-test", "-f", str(private)],
                   check=True, capture_output=True)
    public = (directory / f"{name}.pub").read_text(encoding="utf-8").strip()
    return private, " ".join(public.split()[:2])


@pytest.fixture()
def keys(tmp_path):
    private, public = _keygen(tmp_path, "checker_key")
    return {"private": private, "public": public}


def _allowed(tmp_path: Path, *entries: tuple[str, str], name: str = "allowed_signers") -> Path:
    path = tmp_path / name
    path.write_text("".join(f"{principal} {public}\n" for principal, public in entries), encoding="utf-8")
    return path


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q")
    _git(work, "config", "user.name", "HPP Test")
    _git(work, "config", "user.email", "hpp@example.invalid")
    (work / ".gitignore").write_text(".hpp/\n", encoding="utf-8")
    (work / "SPEC.md").write_text("build the bounded change\n", encoding="utf-8")
    _git(work, "add", ".gitignore", "SPEC.md")
    _git(work, "commit", "-q", "-m", "fixture")
    return work


def _attest(repo: Path, **extra):
    return create_attestation(repo=repo, spec=repo / "SPEC.md", output=repo / ".hpp" / "attestation.json",
                              maker="maker-a", checker="checker-b", session="review:001", verdict="approved", **extra)


# --------------------------------------------------------------------------- attestation

def test_a_signed_attestation_verifies_against_the_allowed_signers(repo, keys, tmp_path):
    record = _attest(repo, sign_key=keys["private"])
    assert record["signature"]["scheme"] == "sshsig" and record["signature"]["namespace"] == "hpp"
    assert record["signature"]["signer"] == "checker-b"  # the checker signs its own verdict by default
    assert record["signature"]["signature"].startswith("-----BEGIN SSH SIGNATURE-----")
    report = verify_attestation(repo / ".hpp" / "attestation.json", repo,
                                allowed_signers=_allowed(tmp_path, ("checker-b", keys["public"])))
    assert report["status"] == "valid" and report["mismatches"] == []
    assert report["signature"]["status"] == "verified" and report["signature"]["signer"] == "checker-b"


def test_bytes_changed_after_signing_are_refused(repo, keys, tmp_path):
    _attest(repo, sign_key=keys["private"])
    path = repo / ".hpp" / "attestation.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["session"] = "review:002"  # still a valid session id: only the signature can see this
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = verify_attestation(path, repo, allowed_signers=_allowed(tmp_path, ("checker-b", keys["public"])))
    assert report["status"] == "blocked" and report["mismatches"] == ["signature"]
    assert report["signature"]["status"] == "refused"


def test_a_signer_outside_the_allowed_list_is_refused(repo, keys, tmp_path):
    _attest(repo, sign_key=keys["private"])
    path = repo / ".hpp" / "attestation.json"
    other_private, other_public = _keygen(tmp_path, "other_key")
    same_name_other_key = _allowed(tmp_path, ("checker-b", other_public), name="signers-a")
    other_name_same_key = _allowed(tmp_path, ("someone-else", keys["public"]), name="signers-b")
    for allowed in (same_name_other_key, other_name_same_key):
        report = verify_attestation(path, repo, allowed_signers=allowed)
        assert report["status"] == "blocked" and "signature" in report["mismatches"], allowed.name
        assert report["signature"]["status"] == "refused"


def test_an_unsigned_record_is_refused_by_a_verifier_that_requires_signers(repo, keys, tmp_path):
    _attest(repo)
    report = verify_attestation(repo / ".hpp" / "attestation.json", repo,
                                allowed_signers=_allowed(tmp_path, ("checker-b", keys["public"])))
    assert report["status"] == "blocked" and report["mismatches"] == ["signature"]
    assert report["signature"]["status"] == "refused" and "not signed" in report["signature"]["detail"]


def test_the_signer_can_be_named_explicitly(repo, keys, tmp_path):
    record = _attest(repo, sign_key=keys["private"], signer="release-desk")
    assert record["signature"]["signer"] == "release-desk"
    report = verify_attestation(repo / ".hpp" / "attestation.json", repo,
                                allowed_signers=_allowed(tmp_path, ("release-desk", keys["public"])))
    assert report["status"] == "valid" and report["signature"]["status"] == "verified"


def test_CONTROLE_an_unsigned_record_verifies_exactly_as_before(repo):
    _attest(repo)
    report = verify_attestation(repo / ".hpp" / "attestation.json", repo)
    assert report["status"] == "valid" and report["mismatches"] == []
    assert report["signature"] == {"status": "not-signed"}
    stored = json.loads((repo / ".hpp" / "attestation.json").read_text(encoding="utf-8"))
    assert "signature" not in stored


def test_CONTROLE_a_signed_record_without_allowed_signers_is_not_claimed_verified(repo, keys):
    _attest(repo, sign_key=keys["private"])
    report = verify_attestation(repo / ".hpp" / "attestation.json", repo)
    assert report["status"] == "valid"  # the verifier asked for no signature check
    assert report["signature"]["status"] == "not-verified" and report["signature"]["signer"] == "checker-b"


def test_without_ssh_keygen_signing_refuses_and_writes_nothing(repo, keys, monkeypatch):
    monkeypatch.setattr(signing.shutil, "which", lambda name: None)
    with pytest.raises(AttestationError, match="ssh-keygen"):
        _attest(repo, sign_key=keys["private"])
    assert not (repo / ".hpp" / "attestation.json").exists()


def test_without_ssh_keygen_a_signature_is_never_reported_verified(repo, keys, tmp_path, monkeypatch):
    _attest(repo, sign_key=keys["private"])
    monkeypatch.setattr(signing.shutil, "which", lambda name: None)
    report = verify_attestation(repo / ".hpp" / "attestation.json", repo,
                                allowed_signers=_allowed(tmp_path, ("checker-b", keys["public"])))
    assert report["status"] == "blocked" and report["mismatches"] == ["signature"]
    assert "ssh-keygen" in report["signature"]["detail"]


def test_a_missing_key_file_is_refused_before_anything_is_written(repo, tmp_path):
    with pytest.raises(AttestationError, match="sign key"):
        _attest(repo, sign_key=tmp_path / "no-such-key")
    assert not (repo / ".hpp" / "attestation.json").exists()


# --------------------------------------------------------------------------- evidence

def _py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_a_signed_evidence_record_verifies_and_a_consistent_rewrite_is_refused(tmp_path, keys):
    root = tmp_path / "ws"
    root.mkdir()
    record = run_evidence("e2e", _py(WRITE_ONE), ["out/*.png"], root=root, sign_key=keys["private"], signer="runner")
    assert record["verdict"] == "passed" and record["signature"]["signer"] == "runner"
    path = root / record["record_path"]
    allowed = _allowed(tmp_path, ("runner", keys["public"]))
    report = verify_evidence(path, root=root, allowed_signers=allowed)
    assert report["status"] == "valid" and report["signature"]["status"] == "verified"

    # A rewrite that recomputes the self-hash passes the hash check; only the signature catches it.
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored["duration_s"] = 0.001
    stored["record_sha256"] = _sha256(_canonical(stored))
    path.write_text(json.dumps(stored, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert verify_evidence(path, root=root)["status"] == "valid"  # the hash alone is fooled
    refused = verify_evidence(path, root=root, allowed_signers=allowed)
    assert refused["status"] == "blocked" and refused["signature"]["status"] == "refused"
    assert any("signature" in problem for problem in refused["problems"])


def test_signing_evidence_needs_a_named_signer(tmp_path, keys):
    with pytest.raises(EvidenceError, match="signer"):
        run_evidence("e2e", _py(WRITE_ONE), ["out/*.png"], root=tmp_path, sign_key=keys["private"])


def test_CONTROLE_an_unsigned_evidence_record_verifies_as_before_and_is_refused_only_when_signers_are_required(tmp_path, keys):
    record = run_evidence("e2e", _py(WRITE_ONE), ["out/*.png"], root=tmp_path)
    path = tmp_path / record["record_path"]
    assert "signature" not in json.loads(path.read_text(encoding="utf-8"))
    plain = verify_evidence(path, root=tmp_path)
    assert plain["status"] == "valid" and plain["signature"] == {"status": "not-signed"}
    required = verify_evidence(path, root=tmp_path, allowed_signers=_allowed(tmp_path, ("runner", keys["public"])))
    assert required["status"] == "blocked" and required["signature"]["status"] == "refused"


# --------------------------------------------------------------------------- the call sites

def test_attest_create_and_verify_expose_the_flags(repo, keys, tmp_path, capsys):
    allowed = _allowed(tmp_path, ("checker-b", keys["public"]))
    wrong = _allowed(tmp_path, ("checker-b", _keygen(tmp_path, "wrong")[1]), name="wrong_signers")
    output = repo / ".hpp" / "attestation.json"
    code = cli.main(["attest", "create", "--repo", str(repo), "--spec", str(repo / "SPEC.md"), "--output", str(output),
                     "--maker", "maker-a", "--checker", "checker-b", "--session", "review:001", "--verdict", "approved",
                     "--sign-key", str(keys["private"])])
    created = json.loads(capsys.readouterr().out)
    assert code == 0 and created["signature"]["scheme"] == "sshsig"
    assert cli.main(["attest", "verify", str(output), "--repo", str(repo), "--allowed-signers", str(allowed)]) == 0
    assert json.loads(capsys.readouterr().out)["signature"]["status"] == "verified"
    assert cli.main(["attest", "verify", str(output), "--repo", str(repo), "--allowed-signers", str(wrong)]) == 2
    assert json.loads(capsys.readouterr().out)["mismatches"] == ["signature"]


def test_evidence_run_and_verify_expose_the_flags(tmp_path, keys, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    allowed = _allowed(tmp_path, ("runner", keys["public"]))
    code = cli.main(["evidence", "run", "--id", "e2e", "--artifact", "out/*.png", "--sign-key", str(keys["private"]),
                     "--signer", "runner", "--", *_py(WRITE_ONE)])
    record = json.loads(capsys.readouterr().out)
    assert code == 0 and record["signature"]["signer"] == "runner"
    assert cli.main(["evidence", "verify", record["record_path"], "--allowed-signers", str(allowed)]) == 0
    assert json.loads(capsys.readouterr().out)["signature"]["status"] == "verified"
    assert cli.main(["evidence", "run", "--id", "e2e", "--artifact", "out/*.png", "--sign-key", str(keys["private"]),
                     "--", *_py(WRITE_ONE)]) == 2
    assert "signer" in capsys.readouterr().err
