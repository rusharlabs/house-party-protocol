# AGENTS.md — continuity-kit

Este kit preserva estado de retomada e exige rederivação antes de repetir trabalho.

## Codex CLI

- Instale por cópia com `kit_doctor.py install --kit <continuity-kit> --host codex --target <repo> --apply`.
- Templates e scripts ficam em `.agents/hpp/continuity-kit/`.
- Hooks de lifecycle do Claude Code não são ativados no Codex; invoque os scripts no fluxo da sessão.

## Verificação

```bash
python scripts/doc_rollup.py --self-test
python scripts/state_mirror.py --self-test
```
