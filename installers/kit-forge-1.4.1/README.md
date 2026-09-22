[English](README.md) · [Português](README.pt-BR.md)

# Kit Forge

The IP/PII gate + the kit assembler of this marketplace, and the **installer of every
other module**. `ip_pii_linter.py` (scans for internal client/infra names before anything
becomes public), `kit_assembler.py` (assembles a kit from a declarative manifest + the
source, with `guard_origins` built in — aborts if the source changes mid-assembly),
`kit_doctor.py` (verify/install/registry/marketplace — the single installation engine of
the whole marketplace, 6 stages), `wire_settings.py` (idempotent merge into
`settings.local.json`), `install_git_hook.py` (chains with someone else's `pre-commit`),
`tools/skill_lint.py` (the linter that enforces the SKILL-CONTRACT on other kits' skills),
`tools/browse.py` (interactive marketplace menu), `tools/catalog_md.py` (bilingual module
catalogue derived from the emitted tree) and `tools/codex_skills.py` (installs a kit in the
layout Codex CLI discovers). A single exit contract everywhere: `0 ok/no-op`, `1 warn`,
`2 block`, `3 error`. No `--skip-lint` in any tool — the IP/PII gate is always mandatory.

## Prerequisites + external APIs

| Requirement | Minimum version | Required? |
|---|---|---|
| Python | 3.8 | yes |
| PyYAML | any | yes — `kit_assembler.py`/`ip_pii_linter.py`/`wire_settings.py` parse manifest/ruleset/spec with it; the core function of these 3 tools depends on it |

External services: **none — stdlib + PyYAML, touches only the local filesystem.**

## Install as a plugin

Kit Forge **is** a plugin: `.claude-plugin/plugin.json` ships in the emitted module
declares name, version, description and keywords, and `marketplace.json` at the
distribution root lists it under `installers`.

```bash
/plugin marketplace add rushar-labs/house-party-protocol
/plugin install kit-forge@house-party-protocol
```

What the plugin gives you is the **tools, at a stable path**: `${CLAUDE_PLUGIN_ROOT}`
resolves to the installed module, so the agent can run
`python "${CLAUDE_PLUGIN_ROOT}/kit_doctor.py" ...` or
`python "${CLAUDE_PLUGIN_ROOT}/tools/skill_lint.py" ...` without knowing where the
marketplace was cloned. It ships **no skills, no commands and no auto-wired hooks** — the
manifest has no `skills`/`commands`/`hooks` keys, and there is no `hooks/hooks.json`.
`hooks/guard_origins.py --hook` is an optional `PreToolUse` guard (blocks writes to the
source paths you list) that you wire by hand, if you want it.

## Install by copy

In the emitted distribution this module lives in `installers/kit-forge-1.4.1/` (the
directory carries the version — state it once, in `KIT`). It installs itself with its own
`kit_doctor.py`, run from the distribution root; plan first, write only on `--apply`:

```bash
KIT=installers/kit-forge-1.4.1
cp -r "$KIT" ../your-repo/kit-forge             # the copy itself (kit_doctor does not copy on claude-code)
python installers/kit-forge-1.4.1/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo
python installers/kit-forge-1.4.1/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo --apply
# Codex CLI: --host codex — the installer copies the module into .agents/hpp/kit-forge; no cp -r needed
```

## What the installer detects

The `detect` stage classifies the target (read-only) with exactly these three labels:

```
greenfield    -> no prior config in the target; profile stage would copy ip-ruleset.example.yaml -> ip-ruleset.yaml
                 (the real ruleset belongs to the BUSINESS that uses kit-forge, not to this kit — fill it in)
in-progress   -> .claude/ exists, or settings(.local).json already has hooks/statusLine, or ip-ruleset.yaml
                 is already present, or the repo has more than 3 commits: reported, never overwritten (skip-exists)
re-run        -> this kit+target pair is already in the registry (~/.claude-kits/registry.json)
```

## What is safe to run again

`wire_settings.py` is idempotent and byte-stable (running it twice does not duplicate). The
real `ip-ruleset.yaml` (with the client/port/domain names of YOUR business) is never
overwritten automatically by any tool here — only you edit it. `kit_assembler.py` always
assembles into a fresh output directory (it never writes over the kit already emitted to
production unless you point `--out` at it explicitly).

## Manual wiring

None required — the kit has no `hooks/hooks.json`. It is a collection of command-line tools
invoked on demand (e.g. by a CI cron, or by hand before publishing a new kit). The only
optional wiring is `hooks/guard_origins.py --hook` as a `PreToolUse` guard, and that is a
human paste into `settings.local.json`.

## Configure the IP/PII ruleset (the real step before assembling any kit)

```bash
cp ip-ruleset.example.yaml ip-ruleset.yaml
# edit ip-ruleset.yaml with the REAL client/infra names of your business
python ip_pii_linter.py --self-test
```
`ip-ruleset.example.yaml` is neutral (it can be part of a distributed kit); the real
`ip-ruleset.yaml` (with real names) **never** leaves in an assembled kit — it stays out of
the manifest of any `kit_assembler.py`.

## Proof / acceptance (real output, executed)

```bash
python kit_doctor.py --self-test
```
```
self-test OK — verify (ok/warn/corrupt/error) + positional compat + install (6 stages: detect/prereqs/profile/configure/wire/smoke, plan-first/--apply, --answers, re-run) + registry (kit+target, no duplicates) + render_plan + marketplace (out-of-place/version-mismatch + control)
```
<!-- executado: 2026-09-21 · exit=0 -->

```bash
python ip_pii_linter.py --self-test
```
```
self-test OK — 17 findings across 16 distinct rules
```
<!-- executado: 2026-09-21 · exit=0 -->

```bash
python wire_settings.py --self-test
```
```
self-test OK — wire idempotent, conflict without --force preserved, --force overwrites, --undo byte-identical, a crash mid-write does not truncate, a concurrent write is refused (exit 2)
```
<!-- executado: 2026-09-21 · exit=0 -->

## Undo

```
- Plugin:  /plugin uninstall kit-forge@house-party-protocol
- Copy:    remove the kit-forge/ folder from the project (nothing else to revert — this kit
           touches no wiring/settings by itself)
- ip-ruleset.yaml: delete it by hand if you no longer want to lint this business
```

## Extended documentation

- `INSTALL-CONTRACT.md` (distribution root) — the complete contract of the 6 stages of
  `kit_doctor.py install`, the `kit.install.yaml` schema, the cross-host seam.
- `SKILL-CONTRACT.md` (distribution root) — the `SKILL.md` contract enforced by
  `tools/skill_lint.py`.
- `docs/UX-INSTALL-JOURNEY.md` (distribution root) — the installation journey told in the
  conversation (greenfield/in-progress/re-run/failure), from the point of view of the agent
  guiding the human.
