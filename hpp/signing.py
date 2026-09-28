"""SSH signatures for records, made and checked by the OpenSSH binary already on the machine.

The harness holds no key and never reads one. Signing runs `ssh-keygen -Y sign` over the canonical
bytes of a record (the record without its `signature` field, sorted keys, compact separators) in the
fixed namespace `hpp`; verifying runs `ssh-keygen -Y verify` against the allowed-signers file the
verifier trusts, for the principal the signature names. The signed digest is stored beside the
signature so bytes changed after signing are named as such before the binary is even called.

Without the binary there is no signature and no verification: creating refuses, checking answers
`refused`. The word `verified` appears only when ssh-keygen accepted the signature of exactly these
bytes by a key the allowed-signers file lists for that principal.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

NAMESPACE = "hpp"
SCHEME = "sshsig"
_SIGNER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,127}$")
_TIMEOUT = 60.0
_MARKER = "BEGIN SSH SIGNATURE"


class SigningError(ValueError):
    """A signature could not be made truthfully; nothing was written."""


def ssh_keygen() -> Optional[str]:
    """The OpenSSH binary on PATH, or None: the harness never bundles one."""
    return shutil.which("ssh-keygen")


def canonical(record: dict[str, Any], *, exclude: tuple[str, ...] = ("signature",)) -> bytes:
    """The bytes a signature covers: the record without the excluded fields, in a fixed serialisation."""
    body = {key: value for key, value in record.items() if key not in exclude}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def check_signer(signer: Any) -> str:
    if not isinstance(signer, str) or not _SIGNER.fullmatch(signer):
        raise SigningError("signer must be 1-128 portable identifier characters (letters, digits, . _ : @ + -)")
    return signer


def _tail(text: str, limit: int = 300) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[-limit:]


def sign(data: bytes, key: Path, signer: str) -> dict[str, Any]:
    """Sign `data` with the private key at `key` as `signer`; the key is read by ssh-keygen alone."""
    principal = check_signer(signer)
    key_path = Path(key)
    if not key_path.is_file():
        raise SigningError(f"sign key not found: {key_path}")
    binary = ssh_keygen()
    if binary is None:
        raise SigningError("ssh-keygen not found on PATH: cannot sign (OpenSSH is needed)")
    with tempfile.TemporaryDirectory(prefix="hpp-sign-") as scratch:
        payload = Path(scratch) / "record"
        payload.write_bytes(data)
        # Why: a passphrase-protected key without an agent would prompt on stdin; with no stdin the
        # binary fails instead of hanging, and the failure is reported.
        result = subprocess.run(
            [binary, "-Y", "sign", "-f", str(key_path), "-n", NAMESPACE, str(payload)],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=_TIMEOUT,
        )
        if result.returncode != 0:
            raise SigningError(f"ssh-keygen could not sign: {_tail(result.stderr) or 'no detail'}")
        signature_path = Path(str(payload) + ".sig")
        if not signature_path.is_file():
            raise SigningError("ssh-keygen exited 0 and wrote no signature")
        armored = signature_path.read_text(encoding="utf-8")
    return {"scheme": SCHEME, "namespace": NAMESPACE, "signer": principal,
            "sha256": hashlib.sha256(data).hexdigest(), "signature": armored}


def verify(data: bytes, signature: Any, allowed_signers: Path) -> dict[str, Any]:
    """`verified` only when ssh-keygen accepted the signature of exactly these bytes by an allowed key."""
    if not isinstance(signature, dict):
        return {"status": "refused", "signer": None, "detail": "the record is not signed"}
    signer = signature.get("signer")
    refused: dict[str, Any] = {"status": "refused", "signer": signer if isinstance(signer, str) else None}
    if signature.get("scheme") != SCHEME or signature.get("namespace") != NAMESPACE:
        return {**refused, "detail": f"unknown signature form; expected {SCHEME} in namespace {NAMESPACE}"}
    if not isinstance(signer, str) or not _SIGNER.fullmatch(signer):
        return {**refused, "detail": "the signature names no valid signer"}
    armored = signature.get("signature")
    if not isinstance(armored, str) or _MARKER not in armored:
        return {**refused, "detail": "the signature is not an SSH signature"}
    if signature.get("sha256") != hashlib.sha256(data).hexdigest():
        return {**refused, "detail": "the record's bytes changed after it was signed"}
    allowed = Path(allowed_signers)
    if not allowed.is_file():
        return {**refused, "detail": f"allowed signers file not found: {allowed}"}
    binary = ssh_keygen()
    if binary is None:
        return {**refused, "detail": "ssh-keygen not found on PATH: the signature could not be checked"}
    with tempfile.TemporaryDirectory(prefix="hpp-verify-") as scratch:
        signature_path = Path(scratch) / "record.sig"
        signature_path.write_text(armored, encoding="utf-8", newline="\n")
        result = subprocess.run(
            [binary, "-Y", "verify", "-f", str(allowed), "-I", signer, "-n", NAMESPACE, "-s", str(signature_path)],
            input=data, capture_output=True, timeout=_TIMEOUT,
        )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip() or "ssh-keygen refused the signature"
        return {**refused, "detail": _tail(detail)}
    return {"status": "verified", "signer": signer, "sha256": signature["sha256"]}


def signature_report(data: bytes, signature: Any, allowed_signers: Optional[Path]) -> dict[str, Any]:
    """What a verify report says about a record's signature.

    Without an allowed-signers file the verifier asked for no check: an unsigned record is
    `not-signed`, a signed one is `not-verified` (present, never claimed). With one, an unsigned
    record and every signature ssh-keygen does not accept are `refused`.
    """
    if allowed_signers is None:
        if signature is None:
            return {"status": "not-signed"}
        signer = signature.get("signer") if isinstance(signature, dict) else None
        return {"status": "not-verified", "signer": signer,
                "detail": "no allowed-signers file was given; the signature was not checked"}
    if signature is None:
        return {"status": "refused", "signer": None, "detail": "the record is not signed"}
    return verify(data, signature, allowed_signers)
