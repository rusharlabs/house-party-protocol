[English](README.md) · [Português](README.pt-BR.md)

# Supabase Pack

Two SKILL-CONTRACT-compliant skills for projects with Supabase:

- **`rls-audit`** — audits RLS for real (permissive `anon` policies, not only the
  `relrowsecurity` flag). Its tools line declares the tools by CAPABILITY (`execute_sql`,
  `get_advisors`, `list_tables`) and says the MCP prefix varies per installation; its
  executed examples show one real prefix (`mcp__supabase__*`) as the sample.
- **`supabase-edge-scaffold`** — generates the skeleton of an Edge Function with CORS +
  service-role via env + correct error handling, with a real smoke test (`deno check`).
  Its tools line names one concrete prefix (`mcp__claude_ai_Supabase__deploy_edge_function`,
  `mcp__claude_ai_Supabase__list_edge_functions`) — read it as the example of the
  installation it was proven on, and swap the prefix for the one your Supabase MCP exposes.

Both inherited from the `operator-kit` (PHASE 3 of the kickoff), packaged here as a
standalone kit for whoever wants only the Supabase layer without the rest of the
operator-kit. It does not manage migrations or schema — it only audits RLS and scaffolds
Edge Functions.

## Prerequisites + external APIs

| Requirement | Minimum version | Required? |
|---|---|---|
| Python | any 3.x | only for the installer's `skill_lint.py` (proof/lint, not the skills' runtime) |
| `deno` | any | only for `supabase-edge-scaffold` (smoke test of the generated skeleton) |

External services: **Supabase, via MCP** (tools by capability: `execute_sql`,
`get_advisors`, `list_tables`, `deploy_edge_function`, `list_edge_functions`). The
`mcp__*` prefix in front of them depends on how the Supabase MCP is registered in your
environment (`mcp__supabase__*`, `mcp__claude_ai_Supabase__*`, ...) — where a `SKILL.md`
spells one out, it is the prefix of the installation the example ran on, not a
requirement. Credentials: project URL + anon key, configured in the Supabase MCP of your
environment (not in this kit). **Never `ANTHROPIC_API_KEY`** — not applicable here.

## Install as a plugin

```bash
/plugin marketplace add rushar-labs/house-party-protocol
/plugin install supabase-pack@house-party-protocol
```
The plugin has no hooks; the two skills are auto-discovered.

## Install by copy

In the emitted distribution this module lives in
`frameworks-com-plugins/supabase-pack-1.1.0/` (the directory carries the version — state it
once, in `KIT`). The installer is `instaladores/kit-forge-1.4.0/kit_doctor.py`; run it from
the distribution root. It plans first and writes only on a second, explicit `--apply`:

```bash
KIT=frameworks-com-plugins/supabase-pack-1.1.0
cp -r "$KIT" ../your-repo/supabase-pack       # the copy itself (kit_doctor does not copy on claude-code)
python instaladores/kit-forge-1.4.0/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo
python instaladores/kit-forge-1.4.0/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo --apply
# Codex CLI: --host codex — the installer copies the module into .agents/hpp/supabase-pack
#            and each skill into .agents/skills/hpp-supabase-pack-<skill>; no cp -r needed
```

## What the installer detects

The `detect` stage classifies the target (read-only) with exactly these three labels:

```
greenfield    -> no prior config in the target; nothing to copy (no profile/config of its own — YAGNI); the 2 skills become available
in-progress   -> .claude/ exists, or settings(.local).json already has hooks/statusLine, or the repo has
                 more than 3 commits: reported only — this kit touches no settings/hooks
re-run        -> this kit+target pair is already in the registry (~/.claude-kits/registry.json); nothing changes
```

## What is safe to run again

This kit neither generates nor modifies any file at installation — the two skills are
invoked on demand by the agent (`rls-audit` only reads via MCP; `supabase-edge-scaffold`
generates a new file per invocation, not during `kit_doctor.py install`). Running the
installer again is always a safe no-op.

## Manual wiring

None — this kit has no hooks and does not touch `settings.local.json`. The skills fire by
keyword/context (the `description` frontmatter of each `SKILL.md`), with no settings wiring.

## Proof / acceptance (real output, executed)

The kit ships no `tools/` of its own — the linter is the installer's. From the distribution
root:

```bash
python instaladores/kit-forge-1.4.0/tools/skill_lint.py --all frameworks-com-plugins/supabase-pack-1.1.0/skills --run-proofs
```
Last line of the output (the 2 `[PASS]` lines above it carry OS-specific path separators):
```
skill_lint: 2 pass · 0 warn · 0 fail (of 2)
```
<!-- executado: 2026-09-21 · exit=0 -->

## Undo

```
- Plugin:  /plugin uninstall supabase-pack@house-party-protocol
- Copy:    remove the supabase-pack/ folder from the project (nothing else to revert — no
           wiring/settings touched)
```
