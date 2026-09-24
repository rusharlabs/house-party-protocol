[English](AGENTS.md) · [Português](AGENTS.pt-BR.md)

# AGENTS.md — House Party Protocol

House Party Protocol is a local-first harness for reliability, governance and evaluation of
coding agents on Claude Code and Codex CLI. The modules are installable capabilities of the
harness; the marketplace is only a distribution channel.

## Repository rules

- Treat `hpp.manifest.json` as the executable contract of modules, relations, hosts and invariants.
- The versioned module directories are emitted artifacts; do not edit them by hand.
- Changes are born in the sources, get a red-to-green test and go through the forge.
- Never lower a gate to get green. Fix the artifact the gate rejected.
- Preserve MIT, NOTICE and attributions of adapted code.
- Do not record credentials, personal paths, clients or private infrastructure.
- `examples/typed-decisions/decide.py` sends text, and a key read from the environment, to an external endpoint; `hpp policy check` classifies running it as `MANUAL` (rule `decision-advisor`, new in 2.6.0). Never invoke it unattended or from a hook.
- `healthy` proves freshness of the declared signal; it does not prove correctness of the work.
- Waves come from WorkGraph dependencies; a lane does not receive conflicting territory.

## Exit codes

`0` ok · `1` warn/manual · `2` block · `3` error.

## Codex CLI

Use `installers/kit-forge-1.4.2/kit_doctor.py install --kit <kit> --host codex --target <repo> --apply`.
Skills go to `.agents/skills`; the full runtime goes to `.agents/hpp`. Hooks declared in
`hooks.json` belong to Claude Code and are not activated automatically on Codex.

Before declaring a change complete, run the self-test of the changed script, `python -m hpp
doctor`, the benchmark, the module verifier and the publication gate.
