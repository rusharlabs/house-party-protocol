# AGENTS.md — kit-forge

Este kit monta, valida e instala os demais kits do House Party Protocol.

## Codex CLI

- Use `kit_doctor.py install --kit <kit> --host codex --target <repo> --apply` para instalação por cópia.
- O gerador `tools/codex_skills.py` cria skills namespaced em `.agents/skills` e mantém o runtime em `.agents/hpp`.
- Hooks de Claude Code não são ativados no Codex.

## Verificação

```bash
python kit_doctor.py --self-test
python tools/codex_skills.py --self-test
python tools/skill_lint.py --self-test
```

Nunca relaxe o linter para fazer um pacote passar; corrija a fonte.
