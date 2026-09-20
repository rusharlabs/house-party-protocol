# AGENTS.md — claude-dev-kit

Este kit constrói e valida skills, hooks e plugins; o nome histórico não limita o uso das skills no Codex.

## Codex CLI

- Instale por cópia com `kit_doctor.py install --kit <claude-dev-kit> --host codex --target <repo> --apply`.
- Skills são geradas em `.agents/skills`; ferramentas ficam em `.agents/hpp/claude-dev-kit/`.
- `wire_settings.py`, `hooks.json` e plugins `.claude-plugin` continuam específicos do Claude Code.

## Verificação

```bash
python tools/skill_lint.py --self-test
python scripts/wire_settings.py --self-test
python scripts/install_git_hook.py --self-test
```
