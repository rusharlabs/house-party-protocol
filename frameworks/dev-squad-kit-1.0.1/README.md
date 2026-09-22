[English](README.md) · [Português](README.pt-BR.md)

# Dev Squad Kit

## 1. What it is

A squad of 12 role agents via slash-command (`*master`, `*analyst`, `*architect`,
`*data-engineer`, `*dev`, `*devops`, `*pm`, `*po`, `*qa`, `*sm`, `*squad-creator`,
`*ux-design-expert`) — each with its own persona, numbered commands and a collaboration
checklist with the others — plus 3 token-safe parallel reading/consolidation skills
(`pp-discovery`, `pp-xray`, `pp-consolidate`).

**What this kit does NOT do:** it does not include the proprietary tree of
tasks/templates/checklists that the `*create`, `*task`, `*workflow`, `*execute-checklist`
commands expect to find in `.devsquad-core/{tasks,templates,checklists,data,utils,workflows}/`.
Without that tree, those specific commands will fail or improvise. Use the 12 agents for
persona, `*help`, `*guide` and delegation of reasoning between roles — or build/bring your
own task tree if you want the complete document-creation commands. Each of the 12 commands
carries this same notice at the top (the **Dependencies outside this kit:** block), before the
activation instructions, so the agent knows what to skip when the path does not exist.

## 2. Prerequisites + external APIs

| Requirement | Minimum version | Required? |
|---|---|---|
| Python | 3.9 | only for the installer's `skill_lint.py`/`kit_doctor.py` |

External services: **none — stdlib only.** The 12 agents are persona `.md` files (prompt),
not executable code, and call no API.

## 3. Install as a plugin

```bash
/plugin marketplace add rushar-labs/house-party-protocol
/plugin install dev-squad-kit@house-party-protocol
```
`.claude-plugin/plugin.json` declares `commands/`; `agents/` and `skills/` are
auto-discovered. No hooks.

## 4. Install by copy

In the emitted distribution this module lives in
`frameworks/dev-squad-kit-1.0.1/` (the directory carries the version — state it
once, in `KIT`). The installer is `installers/kit-forge-1.4.1/kit_doctor.py`; run it from
the distribution root. It plans first and writes only on a second, explicit `--apply`:

```bash
KIT=frameworks/dev-squad-kit-1.0.1
cp -r "$KIT" ../your-repo/dev-squad-kit       # the copy itself (kit_doctor does not copy on claude-code)
python installers/kit-forge-1.4.1/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo
python installers/kit-forge-1.4.1/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo --apply
# Codex CLI: --host codex — the installer copies the module into .agents/hpp/dev-squad-kit
#            and each skill into .agents/skills/hpp-dev-squad-kit-<skill>; no cp -r needed
```

## 5. What the installer detects

The `detect` stage classifies the target (read-only) with exactly these three labels:

```
greenfield    -> no prior config in the target; nothing to copy (there is no profile.yaml); the 12 commands + 3 skills become available
in-progress   -> .claude/ exists, or settings(.local).json already has hooks/statusLine, or the repo has
                 more than 3 commits: reported only — this kit touches no settings/hooks
re-run        -> this kit+target pair is already in the registry (~/.claude-kits/registry.json); nothing changes
```

## 6. What is safe to run again

Everything. There is no customisable profile and no generated state — the commands and
skills are static. Running the installation again only re-copies the same files.

## 7. Manual wiring

None. This kit has no hooks — only `commands/`, `agents/` and `skills/`, all picked up by
Claude Code through `.claude-plugin/plugin.json`.

## 8. Proof (real output, executed)

The kit ships no linter of its own — the linter is the installer's. From the distribution
root:

```bash
python installers/kit-forge-1.4.1/tools/skill_lint.py --all frameworks/dev-squad-kit-1.0.1/skills --run-proofs
```
Last line of the output (the 3 `[PASS]` lines above it carry OS-specific path separators):
```
skill_lint: 3 pass · 0 warn · 0 fail (of 3)
```
<!-- executado: 2026-09-21 · exit=0 -->

**Product honesty:** the 3 `pp-*` skills are investigation methodology (prose guiding how
to inventory/read a repo before diving in), not scripts with deterministic output. They now
meet the marketplace `SKILL-CONTRACT.md` (`## Contrato`, executed examples, `## Prova`) and
pass the linter above; what they prove is the method being followed, not a program's
output. They work as a reasoning guide — decide whether that serves your case before
installing.

The 12 persona agents have no self-test mechanism (they are prompt, not code) — the
possible proof is reading the `.md` itself, which deterministically and explicitly defines
commands, personas and collaboration rules.

## 9. Undo

```
- Plugin:  /plugin uninstall dev-squad-kit@house-party-protocol
- Copy:    remove the dev-squad-kit/ folder from the project (no other file was touched)
```
