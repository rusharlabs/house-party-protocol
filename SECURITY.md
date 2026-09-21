[English](SECURITY.md) · [Português](SECURITY.pt-BR.md)

# Security

## Reporting a vulnerability

**Do not open a public issue** for a security flaw. Use one of two channels:

1. **GitHub → Security tab → "Report a vulnerability"** (private report, the preferred one).
2. E-mail: `atendimento@rushar.com.br` with the subject `[house-party-protocol] security`.

Include: the module and its version (`.claude-plugin/plugin.json`), how to reproduce it, and the
impact you measured. First response within 5 business days; the fix is published as a new version
of the module, with the note in `CHANGELOG.md`.

## What this project treats as a security flaw

- A module hook or script that **executes** something that is not in its own code (a download,
  `curl | bash`, `eval` over external input).
- A module that **reads or sends** a credential, `.env`, token or project data off the machine.
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
