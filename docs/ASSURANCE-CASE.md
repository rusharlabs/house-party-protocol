[English](ASSURANCE-CASE.md) · [Português](ASSURANCE-CASE.pt-BR.md)

# Assurance case

This page argues why the project's security requirements are met: what is being protected, from
whom, where the trust boundaries are, which design principles are applied, which common weaknesses
are countered and by which code. Every counter names the file that implements it. What the design
does not claim is listed at the end, next to the commands that check the rest. Security reports go
through [SECURITY.md](../SECURITY.md).

Module files are cited at their path in the distribution, `<area>/<module>-<version>/`, as
`marketplace.json` lists them.

## The claim

Used as documented, House Party Protocol runs nothing its operator did not ask for, sends nothing
off the machine unless a person runs a command that sends it, stores no credential, and delivers
the bytes its release workflow built.

## Threat model

**What is protected**

- the operator's repository and working tree, which the agent and the modules act on;
- credentials in the operator's environment (model keys, tokens);
- the integrity of evidence records, attestations and verdicts, which decide what counts as done;
- the release artifacts: the wheel, the sdist and the module directories.

**Who the threats come from**

- a model or an agent that proposes a destructive command, or claims work is done when it is not;
- a web page open in the operator's browser that tries to reach a local server;
- a network attacker between the example adapter and its endpoint, or an endpoint that redirects;
- a tampered download, or a module changed after it was emitted;
- a compromised third-party action or package in CI;
- a contribution that carries malicious content.

**Out of scope**

- an attacker who already runs code under the operator's own account;
- the agent host itself (Claude Code, Codex CLI) and the model provider behind it;
- what a person decides to run by hand.

## Trust boundaries

### The user's machine

HPP is a command-line tool that runs as the operator, on demand. The `hpp` package starts no
daemon, server or scheduler and has no remote telemetry ([MANIFESTO.md](../MANIFESTO.md), "What the
project refuses to do"). It imports only the Python standard library (`pyproject.toml`:
`dependencies = []`; enforced by `tests/test_stdlib_only.py`). Every verdict is re-derived from
files on disk.

### The agent host

The host runs the model and its tools; HPP provides hooks and commands around it, and treats
whatever the model says as a claim to check, not as a fact:

- `hpp init --apply` writes one file, `.hpp/profile.json`, and only reads the host's
  `settings.json` (`hpp/wizard.py`). Wiring hooks into a host stays a human action.
- The policy classifier (`hpp/policy.py`) returns `ALLOW`, `MANUAL` or `BLOCK`; it never executes
  the command, and a user policy can only harden a built-in verdict, never soften it.
- A verdict from the builder's own lane or model family is refused, and the done gate re-runs the
  criterion commands instead of trusting a completion message ([MANIFESTO.md](../MANIFESTO.md)).
- Module hooks are WARN-only by default ([SECURITY.md](../SECURITY.md)); a hook never brings the
  host down.

### The modules

A module is code the operator installs. Its integrity is checked before it runs:

- every module directory ships `CHECKSUMS.txt` (sha256 per file), and
  `installers/kit-forge-1.5.2/kit_doctor.py verify <module>` compares every file against it;
- `kit_doctor.py install` plans first: a plan run executes every module self-test and writes
  nothing to the target project, and the install applies only on a second, explicit invocation
  (`--apply`), which copies the module's `*.example.*` files into the target before its own
  self-test stage (`run_install` in `kit_doctor.py`);
- before a module is emitted, an IP/PII linter refuses credentials, personal data and machine paths
  ([CONTRIBUTING.md](../CONTRIBUTING.md)).

### The example `decide.py` endpoint

`examples/typed-decisions/decide.py` is the one component whose purpose is to send data off the
machine: it sends the text a person gives it to the endpoint that person declared. It runs only
when a person runs it, and the policy classifies it `MANUAL`. Inside that purpose:

- the key is read from the environment at call time and never written anywhere; an error message
  that would contain it has it replaced by `<redacted>`;
- a key is sent only over `https`, or to a loopback address;
- a redirect is refused (`_NoRedirect`), so the `Authorization` header reaches one host only;
- state that looks like it carries a secret is refused before anything leaves the machine
  (`digest` in `hpp/decision.py`);
- one attempt, a timeout on each socket wait, and a response capped at 1 MiB.

### The loopback dashboard

The lane-kit's Lane Dashboard (`multi-session/lane-kit-1.8.1/scripts/lane_dashboard.py`) is a page
the operator starts and stops. It is the bounded exception the MANIFESTO allows a module:

- it binds loopback only: `--host` accepts only `127.0.0.1`, `::1` or `localhost` (`LOOPBACK`),
  and a write is refused unless the server's own address is one of them;
- reads and actions are refused unless the `Host` header names one of the three loopback names
  with the server's port (`_allowed_hosts`), which defeats DNS rebinding;
- each run issues its own token (`secrets.token_urlsafe(24)` in `make_server`); a write must carry
  it in the `X-HPP-Token` header, compared with `secrets.compare_digest`, with an
  `application/json` body of at most 65,536 bytes;
- the page is served with a Content-Security-Policy of `default-src 'none'`, `connect-src 'self'`,
  `form-action 'none'`, `base-uri 'none'` and `frame-ancestors 'none'`, plus
  `X-Frame-Options: DENY` and `Referrer-Policy: no-referrer`;
- a `GET` only reads; every action is the argv of a terminal command listed in `ROUTE_COMMANDS`,
  and the terminal command does the same thing.

### The CI supply chain

The workflows under `.github/workflows/` build and publish what users install:

- every third-party action is pinned to a full commit SHA, with its version as a comment (30 of the
  30 `uses:` lines across the four workflows on 2026-09-29, counted with
  `grep -hE 'uses: [^@]+@[0-9a-f]{40} # v' .github/workflows/*.yml` against
  `grep -h 'uses:' .github/workflows/*.yml`); Dependabot proposes the updates
  (`.github/dependabot.yml`);
- every `pip install` uses `--require-hashes` against the files in `.github/requirements/`;
- the default token is read-only (`permissions: contents: read`), and each job that needs more asks
  for it on its own; every checkout sets `persist-credentials: false`;
- the release attests build provenance for the wheel and the sdist in a job of its own
  (`actions/attest-build-provenance`), attaches `SHA256SUMS` and the provenance bundle to the
  release, and publishes to PyPI through trusted publishing — no workflow reads a stored token
  secret.

## Secure design principles applied

| principle | where it is applied | code |
|---|---|---|
| economy of mechanism | no runtime dependency, no daemon, no database; every map is a projection of files | `pyproject.toml`, `tests/test_stdlib_only.py` |
| fail-safe defaults | the dashboard binds loopback by default; a key is refused over plain `http`; a redirect is refused; `hpp init` writes nothing without `--apply` | `lane_dashboard.py`, `decide.py`, `hpp/wizard.py` |
| complete mediation | every dashboard write passes the loopback, `Host`, token, content-type and size checks before it runs | `DashboardHandler.do_POST` in `lane_dashboard.py` |
| least privilege | workflow tokens are read-only by default; the release job asks for `contents: write` and `discussions: write`, the attest job for `id-token: write` and `attestations: write` | `.github/workflows/release.yml` |
| separation of privilege | a maker cannot be its own checker; provenance is signed in a job apart from the build | `hpp/attest.py`, `release.yml` |
| least common mechanism | each dashboard run issues its own token, never shared with another run | `make_server` in `lane_dashboard.py` |
| open design | the controls are in the published source; the only secret the harness generates is the dashboard's per-run token | this page |
| psychological acceptability | every dashboard action is also a terminal command that does exactly the same | `ROUTE_COMMANDS`, `tests/test_lane_dashboard.py` |

## Common weaknesses and what counters them

| weakness | counter | code |
|---|---|---|
| OS command injection | commands run as an argv list with `shell=False`, never through a shell | `run_bounded` in `hpp/_process.py`; `hpp/evals.py` |
| a secret on a command line or in a record | a command line that looks like it carries a secret is refused before it runs; secret-like context and state are refused | `_carries_secret` in `hpp/evidence.py`; `_SECRET_PATTERN` in `hpp/context.py`; `digest` in `hpp/decision.py` |
| DNS rebinding | `Host` allowlist on every read and action | `_host_ok` in `lane_dashboard.py` |
| cross-site request forgery | per-run token in a custom header, JSON body only; the handler implements no `OPTIONS`, so a CORS preflight is never answered | `do_POST` in `lane_dashboard.py` |
| clickjacking | `frame-ancestors 'none'` and `X-Frame-Options: DENY` | `serve_page` in `lane_dashboard.py` |
| exposure of a local service to the network | loopback bind; `--host` limited to loopback names | `LOOPBACK` in `lane_dashboard.py` |
| timing attack on the token | constant-time comparison | `secrets.compare_digest` in `lane_dashboard.py` |
| credential forwarded on a redirect | redirects refused | `_NoRedirect` in `decide.py` |
| cleartext transmission of a key | a key only over `https` or to loopback | `ask` in `decide.py` |
| improper certificate validation | HTTPS goes through `urllib` with Python's default context, which verifies the certificate and the host name; no code turns it off | `decide.py`; the probes of the health-kit and the operator-kit |
| stored credentials | keys come from the environment at call time; no module contains a credential; PyPI accepts the workflow's identity instead of a token | `decide.py`, [SECURITY.md](../SECURITY.md), `release.yml` |
| uncontrolled resource consumption | timeouts that stop the whole process tree; capped response and request bodies | `hpp/_process.py`, `decide.py`, `lane_dashboard.py` |
| a tampered artifact or module | `CHECKSUMS.txt` per module, `SHA256SUMS` and signed build provenance per release | `kit_doctor.py`, `release.yml` |
| an edited evidence record | the record hashes what it holds and `hpp evidence verify` re-derives it; given an allowed-signers file, `verify` refuses a record that is unsigned, signed by someone else or changed after signing | `hpp/evidence.py`, `hpp/signing.py` |
| a compromised CI dependency | SHA-pinned actions, hash-pinned requirements, read-only default token | `.github/workflows/`, `.github/requirements/` |

"No code turns it off" was measured when this page was written: no `.py` file under `hpp/`,
`examples/`, `scripts/` or the modules contains `CERT_NONE`, `_create_unverified_context`,
`check_hostname` or `verify=False`.

## What this case does not claim

- **Hooks warn; they do not stop.** A module hook is WARN-only by default, so a warning does not
  stop an agent. A verdict stops something only when a hook, a CI job or a person calls it.
- **The policy classifier is small.** It is an explicit rule set, and it does not catch every
  destructive form of a command.
- **Loopback is not isolation from the operator's own account.** Any process running as the same
  user can reach the dashboard and read its page, token included.
- **The dashboard allows inline script.** Its CSP carries `script-src 'unsafe-inline'`, so escaping
  is the defence against markup in repository text: the page escapes that text with its `esc`
  function before inserting it. This case does not claim that every insertion point was audited.
- **A House Session seat is fingerprinted, not sandboxed.** The fingerprint does not see a write
  into a path the repository ignores, nor what a seat does outside its worktree
  ([MANIFESTO.md](../MANIFESTO.md)).
- **Code-owner review is a repository setting.** `.github/CODEOWNERS` names the maintainer for
  every path; it binds only while branch protection requires a code-owner review.
- **The example adapter sends what it is given.** `decide.py` sends the state text to the endpoint
  the person declared — that is its purpose.

## How to check this case

From the root of the repository:

```bash
python -m pytest tests/test_lane_dashboard.py tests/test_decision.py tests/test_evidence.py tests/test_process.py tests/test_stdlib_only.py -q
python installers/kit-forge-1.5.2/kit_doctor.py verify multi-session/lane-kit-1.8.1
gh attestation verify <file> --repo rusharlabs/house-party-protocol
```

The first command runs the tests that guard the controls above (among them
`test_a_page_on_another_origin_cannot_act`, `test_the_page_cannot_be_framed`,
`test_adapter_refuses_a_redirect_and_the_key_never_reaches_the_second_host` and
`test_a_secret_like_command_line_is_refused_before_it_runs`); the second proves a module's bytes;
the third proves where a release file came from. Who maintains this case and how it changes is in
[GOVERNANCE.md](../GOVERNANCE.md).
