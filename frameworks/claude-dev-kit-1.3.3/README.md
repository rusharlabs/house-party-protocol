[English](README.md) · [Português](README.pt-BR.md)

# Claude Dev Kit

Tools for **building tools** for Claude Code. 8 meta-skills (`ls skills | wc -l` = 8 on
the emitted module) with a vendored `docs/SKILL-CONTRACT.md` — they do not describe in
prose how to create a skill/hook/plugin, they enforce the same contract (header + I/O + at
least 3 real examples + proof) on whoever uses them to create their own:

| Skill | What it does |
|---|---|
| `skill-writer` | guides the creation of a skill — structure, frontmatter, effective descriptions, validation against the SKILL-CONTRACT |
| `skill-scout` | searches local skills, the marketplace, GitHub and the web BEFORE writing a new skill |
| `search-first` | searches for an existing library/tool/pattern (npm/PyPI, MCP, GitHub) BEFORE writing new code |
| `hookify` | creates REAL hooks — executable scripts (stdin JSON, exit 0/1/2), registered through a plugin `hooks.json` or pasted into settings |
| `plugin-dev` | packages skills/hooks/commands into an installable plugin (`.claude-plugin/plugin.json` + `hooks/hooks.json` + `${CLAUDE_PLUGIN_ROOT}`) |
| `claude-dev-setup` | installs the base hooks in a new project — idempotent, reversible settings wiring |
| `architecture-decision-records` | captures the architectural decisions of a session as structured ADRs in `docs/adr/` |
| `teaching` | turns any technical output into a learning opportunity (where it lives, what it connects to, why) |

Plus the tooling: `scripts/wire_settings.py` (idempotent, byte-stable merge into
`settings.local.json`, with `--undo`), `scripts/install_git_hook.py` (chains with an
existing `pre-commit` from someone else — never replaces it) and `tools/skill_lint.py`, a
vendored copy of the marketplace linter so the kit can check its own skills without the
installer around. It does not generate product code — it generates the tool that
generates/audits other tools.

## Prerequisites + external APIs

| Requirement | Minimum version | Required? |
|---|---|---|
| Python | 3.8 | yes |
| PyYAML | any | yes |

External services: **none — stdlib + PyYAML, touches only the local filesystem + the target project's git.**

## Install as a plugin (1-click auto-wire)

```bash
/plugin marketplace add rusharlabs/house-party-protocol
/plugin install claude-dev-kit@house-party-protocol
```
`.claude-plugin/plugin.json` declares `hooks/hooks.json`, which wires
`secret_scan_on_write.py` automatically (through `${CLAUDE_PLUGIN_ROOT}`, matcher
`Edit|Write|MultiEdit`). The 8 skills are auto-discovered.

## Install by copy

In the emitted distribution this module lives in
`frameworks/claude-dev-kit-1.3.3/` (the directory carries the version — state it
once, in `KIT`). The installer is `installers/kit-forge-1.4.2/kit_doctor.py`; run it from
the distribution root. It plans first and writes only on a second, explicit `--apply`:

```bash
KIT=frameworks/claude-dev-kit-1.3.3
cp -r "$KIT" ../your-repo/claude-dev-kit      # the copy itself (kit_doctor does not copy on claude-code)
python installers/kit-forge-1.4.2/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo
python installers/kit-forge-1.4.2/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo --apply
# Codex CLI: --host codex — the installer copies the module into .agents/hpp/claude-dev-kit
#            and each skill into .agents/skills/hpp-claude-dev-kit-<skill>; no cp -r needed
```

## What the installer detects

The `detect` stage classifies the target (read-only) with exactly these three labels:

```
greenfield    -> no prior config in the target; nothing to copy (this kit has no *.example.* file — YAGNI)
in-progress   -> .claude/ exists, or settings(.local).json already has hooks/statusLine, or the repo has
                 more than 3 commits: reported, never overwritten
re-run        -> this kit+target pair is already in the registry (~/.claude-kits/registry.json);
                 wire_settings.py is idempotent and reports an already-applied merge as no-op
```

## What is safe to run again

`wire_settings.py` is **idempotent and byte-stable**: running it twice produces the same
`settings.local.json` (it does not duplicate the entry). On conflict (a different entry
already exists at the same path), it preserves what is there **without `--force`** — it
only overwrites with an explicit `--force`. `install_git_hook.py` is **chain-preserving**:
if a `pre-commit` from another tool already exists, it chains (never replaces).

## Manual wiring (human gate — never automatic)

> Editing `.claude/settings.local.json` is a human gate. `wire_settings.py` is
> **programmatic** (a different format from the human-paste `wiring.settings.jsonc` of the
> other kits) — but it still NEVER runs on its own: the human gate is who invokes the command.
> The target file must already exist (`{}` is enough).

```bash
python scripts/wire_settings.py --spec hooks/wiring-spec.yaml --target .claude/settings.local.json
#                                                                          ^ idempotent merge; --undo reverts
```

`hooks/wiring-spec.yaml` declares what will be merged: one `PreToolUse` entry, matcher
`Edit|Write|MultiEdit`, matched by the substring `secret_scan_on_write`, running
`python "${CLAUDE_PLUGIN_ROOT}/hooks/secret_scan_on_write.py"` with `timeout: 30`.

Git hook (chains with someone else's `pre-commit`, never replaces it):
```bash
python scripts/install_git_hook.py --repo . --hook-name pre-commit --payload <payload.sh>
```

## Proof / acceptance (real output, executed)

```bash
python scripts/wire_settings.py --self-test
```
```
self-test OK — wire idempotent, conflict without --force preserved, --force overwrites, --undo byte-identical
```
<!-- executed: 2026-09-21 · exit=0 -->

```bash
python tools/skill_lint.py --all skills --run-proofs
```
Last line of the output (the 8 `[PASS]` lines above it carry OS-specific path separators):
```
skill_lint: 8 pass · 0 warn · 0 fail (of 8)
```
<!-- executed: 2026-09-21 · exit=0 -->

## Undo

```
- Plugin:  /plugin uninstall claude-dev-kit@house-party-protocol
- Copy:    remove the claude-dev-kit/ folder from the project
- wire_settings.py: python scripts/wire_settings.py --spec hooks/wiring-spec.yaml --target .claude/settings.local.json --undo
- install_git_hook.py: remove the chained block from .git/hooks/pre-commit by hand
           (the script keeps the original third-party pre-commit below the inserted block)
```
