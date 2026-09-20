# AGENTS.md — supabase-pack

Este kit contém workflows de auditoria RLS e scaffold de Edge Functions.

## Codex CLI

- Instale por cópia com `kit_doctor.py install --kit <supabase-pack> --host codex --target <repo> --apply`.
- Skills ficam em `.agents/skills`; nenhuma credencial é copiada ou escrita pelo instalador.
- Operações em projeto Supabase continuam gate de conta e autorização humana.

## Verificação

```bash
python <marketplace>/instaladores/kit-forge-*/tools/skill_lint.py --all skills
```
