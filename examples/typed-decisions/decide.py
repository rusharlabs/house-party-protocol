"""Ask a typed-decision endpoint ONE choice question and print an `hpp.decision/v1` record.

This is an example, not part of the harness. The `hpp` package never calls a model and never
reads a key; this script does both, only when a person runs it, with a key only that person holds.
Every call sends the state text off the machine.

Providers (declare one; nothing is chosen for you):
  typesafe    POST https://api.typesafe.ai/v1/systemone          key env TYPESAFE_API_KEY
  openrouter  POST https://openrouter.ai/api/alpha/decisions     key env OPENROUTER_API_KEY
  compatible  POST <--endpoint>  (a local or self-hosted server speaking the same wire format;
              key env optional, --key-env to name one)

Input: {"question": ..., "state": "..."} on stdin (what `hpp decide eval` sends), or
--question FILE with --state-file FILE. Output: one record on stdout.

Every way the call can go wrong — timeout, HTTP error, a redirect, an HTML page instead of JSON, an
answer outside the options — becomes `instrument-failure`. Low confidence becomes `abstention`.
Neither ever becomes a verdict. There is one attempt and no retry. The timeout bounds each socket
wait, and the response body is capped, so a slow or oversized answer cannot hold the call open.

    python examples/typed-decisions/decide.py --provider typesafe --model jev-1.13.0 \
        --question question.json --state-file error.txt --declared low
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import importlib.util
import json
import os
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

try:
    _HAS_DECISIONS = importlib.util.find_spec("hpp.decision") is not None
except ModuleNotFoundError:
    _HAS_DECISIONS = False
if not _HAS_DECISIONS:
    # Why: run as `python examples/typed-decisions/<script>.py` from a checkout, the script's own
    # directory is on sys.path and the checkout root is not; and an older installed hpp without
    # `hpp.decision` must not win over the checkout beside the script.
    sys.modules.pop("hpp", None)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hpp.decision import SCHEMA, DecisionError, digest, is_alias, normalise_question, validate

PROVIDERS = {
    "typesafe": {"endpoint": "https://api.typesafe.ai/v1/systemone", "key_env": "TYPESAFE_API_KEY",
                 "method": "external-model"},
    "openrouter": {"endpoint": "https://openrouter.ai/api/alpha/decisions", "key_env": "OPENROUTER_API_KEY",
                   "method": "external-model"},
    "compatible": {"endpoint": None, "key_env": None, "method": "local-model"},
}
USER_AGENT = "house-party-protocol-typed-decisions-example"
MAX_RESPONSE_BYTES = 1 << 20


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # Why: the default handler re-sends every header except Content-Length/Type to the host a
    # 3xx names — Authorization included. A redirect is refused, so the key goes to one host only.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, f"redirect refused ({msg})", headers, fp)


_OPENER = urllib.request.build_opener(_NoRedirect)


def _loopback(url: str) -> bool:
    host = urllib.parse.urlsplit(url).hostname or ""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _wire_question(question: dict[str, Any]) -> dict[str, Any]:
    wire: dict[str, Any] = {"type": "choice"}
    if question.get("instructions"):
        wire["instructions"] = question["instructions"]
    criteria = question.get("criteria") or {}
    wire["criteria"] = {option: criteria.get(option, option) for option in question["options"]}
    return wire


def _record(question: dict[str, Any], state: str, method: str, provider_id: str, model: str,
            outcome: dict[str, Any], raw_sha: Optional[str] = None, usage: Optional[dict] = None,
            declared: Optional[str] = None) -> dict[str, Any]:
    record = {"schema": SCHEMA, "question": question, "state_sha256": digest(state), "method": method,
              "provider": {"id": provider_id, "model_served": model}, "outcome": outcome,
              "authority": "advisory", "direction": "raise-only" if declared else "informational"}
    if declared:
        record["declared"] = declared
    if raw_sha:
        record["raw_response_sha256"] = raw_sha
    if usage:
        record["usage"] = usage
    return record


def ask(question: dict[str, Any], state: str, *, provider: str, model: str, endpoint: Optional[str] = None,
        key_env: Optional[str] = None, timeout: float = 8.0, abstain_below: float = 0.6,
        max_state_chars: int = 60000, raw_dir: Optional[Path] = None, declared: Optional[str] = None,
        env: Optional[dict] = None) -> dict[str, Any]:
    env = os.environ if env is None else env
    config = PROVIDERS[provider]
    question = normalise_question(question)
    url = endpoint or config["endpoint"]
    if not url:
        raise DecisionError("--endpoint is required for the compatible provider")
    method = config["method"]
    if is_alias(model):
        raise DecisionError(f"model {model!r} is an alias; pin the version (e.g. jev-1.13.0) so the record can say who answered")
    if declared is not None:
        if not question["ladder"]:
            raise DecisionError("--declared needs an ordered question (ladder: true)")
        if declared not in question["options"]:
            raise DecisionError(f"--declared {declared!r} is not one of the options")
    variable = key_env or config["key_env"]
    key = env.get(variable) if variable else None
    if variable and config["key_env"] and not key:
        raise DecisionError(f"{variable} is not set in this shell; hpp never stores a key, export it yourself")
    scheme = urllib.parse.urlsplit(url).scheme
    if scheme not in ("http", "https"):
        raise DecisionError(f"endpoint must be http or https, not {scheme or 'nothing'}")
    if key and scheme != "https" and not _loopback(url):
        raise DecisionError("a key is only sent over https, or to a loopback address")
    digest(state)  # refuses secret-like state before anything leaves the machine

    def failure(error: str, raw_sha: Optional[str] = None) -> dict[str, Any]:
        outcome = {"status": "instrument-failure", "value": None, "confidence": None,
                   "error": (error.replace(key, "<redacted>") if key else error)[:300]}
        return _record(question, state, method, provider, model, outcome, raw_sha, declared=declared)

    if len(state) > max_state_chars:
        return failure(f"state has {len(state)} chars > {max_state_chars} (size guard)")
    body = json.dumps({"model": model, "state": state, "questions": {question["id"]: _wire_question(question)}},
                      ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        kind = exc.headers.get("Content-Type", "?") if exc.headers else "?"
        return failure(f"HTTP {exc.code} ({kind}): {exc.reason}")
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
        return failure(f"transport: {exc}")
    if len(raw) > MAX_RESPONSE_BYTES:
        return failure(f"response larger than {MAX_RESPONSE_BYTES} bytes")
    raw_sha = hashlib.sha256(raw).hexdigest()
    if raw_dir is not None:
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / f"{raw_sha}.json").write_bytes(raw)
    if "json" not in content_type.lower():
        return failure(f"expected JSON, got {content_type or 'no content type'}", raw_sha)
    try:
        data = json.loads(raw.decode("utf-8"))
        answer = data["answers"][question["id"]]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        return failure(f"answer missing or malformed: {type(exc).__name__}", raw_sha)
    if not isinstance(answer, dict):
        return failure("answer missing or malformed: not an object", raw_sha)
    served = data.get("model") if isinstance(data.get("model"), str) and data.get("model") else model
    if is_alias(served):
        return failure(f"the server answered under the alias {served!r}, not a pinned version", raw_sha)
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
    confidence = answer.get("confidence")
    probabilities = answer.get("probabilities")
    if not isinstance(probabilities, dict) or set(probabilities) != set(question["options"]):
        probabilities = None
    number = isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
    if not number or confidence < abstain_below:
        outcome: dict[str, Any] = {"status": "abstention", "value": None, "confidence": confidence if number else None}
    else:
        outcome = {"status": "recommendation", "value": answer.get("choice"), "confidence": confidence}
    if probabilities is not None:
        outcome["probabilities"] = probabilities
    record = _record(question, state, method, provider, served, outcome, raw_sha, usage, declared)
    try:
        validate(record)
    except DecisionError as exc:
        return failure(f"answer broke the contract: {exc}", raw_sha)
    return record


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--provider", choices=sorted(PROVIDERS), required=True)
    parser.add_argument("--model", required=True, help="the PINNED version, e.g. jev-1.13.0 (aliases are refused)")
    parser.add_argument("--endpoint", help="required for --provider compatible")
    parser.add_argument("--key-env", dest="key_env", help="name of the environment variable holding the key")
    parser.add_argument("--question", help="question JSON file (otherwise read with the state from stdin)")
    parser.add_argument("--state-file", dest="state_file")
    parser.add_argument("--declared", help="the value already declared; advice may only raise it (ordered questions)")
    parser.add_argument("--timeout", type=float, default=8.0, help="seconds per socket wait")
    parser.add_argument("--abstain-below", dest="abstain_below", type=float, default=0.6)
    parser.add_argument("--raw-dir", dest="raw_dir", default=".hpp/decisions/raw",
                        help="where the raw response is kept, so the record stays re-derivable")
    args = parser.parse_args(argv)
    try:
        if args.question:
            question = json.loads(Path(args.question).read_text(encoding="utf-8"))
            state = Path(args.state_file).read_text(encoding="utf-8") if args.state_file else sys.stdin.read()
        else:
            request = json.loads(sys.stdin.read())
            question, state = request["question"], request["state"]
        record = ask(question, state, provider=args.provider, model=args.model, endpoint=args.endpoint,
                     key_env=args.key_env, timeout=args.timeout, abstain_below=args.abstain_below,
                     raw_dir=Path(args.raw_dir), declared=args.declared)
    except DecisionError as exc:
        print(f"decide: {exc}", file=sys.stderr)
        return 2
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"decide: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(record, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
