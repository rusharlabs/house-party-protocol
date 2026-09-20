# AGENTS.md — health-kit

Este kit mede saúde de serviço e mantém statusline cache-first.

## Codex CLI

- Instale por cópia com `kit_doctor.py install --kit <health-kit> --host codex --target <repo> --apply`.
- Scripts ficam em `.agents/hpp/health-kit/`; skills ficam em `.agents/skills`.
- O hook `SessionStart` do Claude Code não é ativado no Codex. Agende ou execute `health_probe.py` explicitamente.

## Verificação

```bash
python scripts/health_probe.py --self-test
python statusline/statusline.py --self-test
```
