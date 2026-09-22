# AGENTS.md — supabase-pack

This kit contains RLS audit workflows and Edge Function scaffolding.

## Codex CLI

- Install by copy with `kit_doctor.py install --kit <supabase-pack> --host codex --target <repo> --apply`.
- Skills live in `.agents/skills`; no credential is copied or written by the installer.
- Operations on a Supabase project remain an account gate and require human authorization.

## Verification

```bash
python <marketplace>/instaladores/kit-forge-*/tools/skill_lint.py --all skills
```
