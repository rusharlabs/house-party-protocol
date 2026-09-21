# AGENTS.md — gotcha-memory

Este kit transforma falhas recorrentes em lições operacionais consultáveis.

## Codex CLI

- Instale por cópia com `kit_doctor.py install --kit <gotcha-memory> --host codex --target <repo> --apply`.
- Runtime e memória de exemplo ficam em `.agents/hpp/gotcha-memory/`.
- Hooks `PreToolUse`/`PostToolUse`/`PostToolUseFailure` do Claude Code não são ativados no Codex; use os scripts explicitamente.

## Verificação

```bash
python hooks/gotcha_preflight.py --self-test
python hooks/gotcha_postflight.py --self-test
```
