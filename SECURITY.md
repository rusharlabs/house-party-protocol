[English](SECURITY.md) · [Português](SECURITY.pt-BR.md)

# Security

## Supported versions

Security fixes go to the current minor line only; each fix ships as a new patch version with
its note in `CHANGELOG.md`. Check yours with `hpp --version`.

| version | supported |
|---|---|
| 2.6.x | yes — current line |
| 2.0 – 2.5 | no — upgrade to 2.6.x |
| 1.x | no |

Modules carry their own version (`plugin.json`, `marketplace.json`); a module fix ships as a new
module version through the same release.

## Reporting a vulnerability

**Do not open a public issue** for a security flaw. Two channels, equally valid — use whichever
works for you:

1. **GitHub → Security tab → "Report a vulnerability"** (private report). If the button is not
   there — private reporting is a repository setting — use the e-mail channel; it is not a
   fallback of lesser standing.
2. **Contact channel on the site:** `https://rusharlabs.com`. No raw address is published here on
   purpose: an inbox in a public repository is harvested, and a harvested inbox is a channel that
   stops being read.

Include: the module and its version (`.claude-plugin/plugin.json`), how to reproduce it, and the
impact you measured. First response within 5 business days on either channel; the fix is
published as a new version of the module, with the note in `CHANGELOG.md`.

## What this project treats as a security flaw

- A module hook or script that **executes** something that is not in its own code (a download,
  `curl | bash`, `eval` over external input).
- A module that **reads or sends** a credential, `.env`, token or project data off the machine.
- In `examples/typed-decisions/decide.py`, which by design reads a key from the environment of the
  person who runs it and sends the text they give it to the endpoint they declared: sending anything
  else, sending the key to any other host (a redirect included), or running without a person
  invoking it.
- In `hpp evidence run`, `hpp retrieval eval` and `hpp decide eval` (new in
  2.6.0), which by design run the command the person
  declares — `evidence run` as an argv with no shell, after refusing a command line that looks like
  it carries a secret: running any other command, running it through a shell, or letting a
  secret-like command line through to `evidence run`.
- A gate that **passes** when it should block (the `ip_pii_linter` letting a secret into a module;
  the `done_gate` returning green without exit 0) — that is a vulnerability, not a bug.

## What is already in the design

- Each module ships `CHECKSUMS.txt` (sha256 per file) and a `.zip` with the same bytes;
  `kit_doctor.py verify <module>` proves integrity before installing.
- Every module `.py` has `--self-test`; `kit_doctor.py install` runs all of them before touching
  your project.
- Hooks are **WARN-only by default** — a hook never brings the tool down.
- No module contains a credential. The real IP/PII linter ruleset is never published; only
  `ip-ruleset.example.yaml` travels.

## Official surfaces

The project is published in these places and nowhere else. A copy found elsewhere — another
GitHub account, a package index the list below does not name, a download site, a fork that
keeps the name — is not this project and receives no security support.

- Source, issues, releases: `https://github.com/rusharlabs/house-party-protocol`
- Claude Code plugin channel: `/plugin marketplace add rusharlabs/house-party-protocol`
- pip: `pip install git+https://github.com/rusharlabs/house-party-protocol@<tag>`, or from 2.6.5 on
  `pip install house-party-protocol` from PyPI (project `house-party-protocol`, published only by
  this repository's release workflow)
- Web: `https://rusharlabs.com` (the contact channel for anything not suited to a public issue)

Every module directory ships `CHECKSUMS.txt`, and every GitHub Release ships `SHA256SUMS`; a
file whose hash is not in them did not come from here.

From 2.6.4 on, the wheel and the sdist of every release also carry build provenance: a
signed statement that the release workflow, at the tagged commit, produced those bytes.

```bash
gh attestation verify <file> --repo rusharlabs/house-party-protocol
```

The same statement is attached to the release as `house_party_protocol-<version>.intoto.jsonl`,
for an offline check:

```bash
gh attestation verify <file> --bundle house_party_protocol-<version>.intoto.jsonl --repo rusharlabs/house-party-protocol
```
