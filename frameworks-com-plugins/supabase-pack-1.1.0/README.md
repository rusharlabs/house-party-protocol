[English](README.md) · [Português](README.pt-BR.md)

# Supabase Pack

Two SKILL-CONTRACT-compliant skills for projects with Supabase:

- **`rls-audit`** — audits RLS for real (permissive `anon` policies, not only the
  `relrowsecurity` flag). Tools declared by CAPABILITY (`execute_sql`, `get_advisors`,
  `list_tables`), never by a literal MCP prefix (the prefix varies per installation — it can
  be `mcp__supabase__*`, `mcp__claude_ai_Supabase__*`, etc.).
- **`supabase-edge-scaffold`** — generates the skeleton of an Edge Function with CORS +
  service-role via env + correct error handling, with a real smoke test (`deno check`).

Both inherited from the `operator-kit` (PHASE 3 of the kickoff), packaged here as a
standalone kit for whoever wants only the Supabase layer without the rest of the
operator-kit. It does not manage migrations or schema — it only audits RLS and scaffolds
Edge Functions.

## Prerequisites + external APIs

| Requirement | Minimum version | Required? |
|---|---|---|
| Python | any 3.x | only for `skill_lint.py` (proof/lint, not the skills' runtime) |
| `deno` | any | only for `supabase-edge-scaffold` (smoke test of the generated skeleton) |

External services: **Supabase, via MCP** (tools by capability: `execute_sql`,
`get_advisors`, `list_tables` — it never hardcodes a specific `mcp__*` prefix, since it
varies per installation). Credentials: project URL + anon key, configured in the Supabase
MCP of your environment (not in this kit). **Never `ANTHROPIC_API_KEY`** — not applicable
here.

## Install as a plugin

```bash
/plugin marketplace add .
/plugin install supabase-pack@house-party-protocol
```

## Install by copy

```bash
cp -r supabase-pack-1.0.0 <seu-projeto>/supabase-pack
cd <seu-projeto>
python supabase-pack/instaladores/kit-forge/kit_doctor.py install supabase-pack --target . --human
#                                                                                    ^ plano, zero escrita
python supabase-pack/instaladores/kit-forge/kit_doctor.py install supabase-pack --target . --apply
#                                                                                    ^ aplica de verdade
```

## What the installer detects

```
greenfield    → nada a copiar (kit sem profile/config próprio — YAGNI); só as 2 skills ficam disponíveis
em-andamento  → n/a (kit não toca settings/hooks nem arquivos do projeto-alvo)
re-run        → registry (~/.claude-kits/registry.json) marca re-run; nada muda (kit é read-only na instalação)
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

```bash
python ${CLAUDE_PLUGIN_ROOT}/tools/skill_lint.py --all skills --run-proofs
```
```
2/2 PASS
```

## Undo

```
- Plugin: /plugin uninstall supabase-pack@house-party-protocol
- Cópia: remover a pasta supabase-pack/ do projeto (nada mais para reverter — sem
  wiring/settings tocados)
```
