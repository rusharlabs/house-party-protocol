# AGENTS.md — agent-framework-wizard

Este kit gera esqueletos de agente e skill por um wizard de seis passos.

## Codex CLI

- Instale por cópia com `kit_doctor.py install --kit <agent-framework-wizard> --host codex --target <repo> --apply`.
- O runtime fica em `.agents/hpp/agent-framework-wizard/`; a skill gerada fica em `.agents/skills`.
- Revise todo arquivo gerado antes de integrar ao projeto.

## Verificação

```bash
python wizard.py --self-test
```
