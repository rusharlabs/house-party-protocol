# AGENTS.md — dev-squad-kit

Este kit oferece papéis de desenvolvimento como commands e subagents, além de três skills de leitura paralela.

## Codex CLI

- Instale por cópia com `kit_doctor.py install --kit <dev-squad-kit> --host codex --target <repo> --apply`.
- Skills são espelhadas em `.agents/skills`; `agents/*.md` são artefatos Claude Code e servem como especificações de papel no Codex.
- Checkers são read-only: nunca conceda `Write` ou `Edit` aos papéis de revisão.

## Verificação

```bash
python <marketplace>/instaladores/kit-forge-*/tools/skill_lint.py --all skills
```
