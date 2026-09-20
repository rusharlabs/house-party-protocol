# AGENTS.md — lane-kit

Este kit coordena sessões concorrentes com claim, território e maker/checker separados.

## Codex CLI

- Instale por cópia com `kit_doctor.py install --kit <lane-kit> --host codex --target <repo> --apply`.
- Use os scripts a partir de `.agents/hpp/lane-kit/`.
- Hooks de território do Claude Code não são ativados no Codex; execute os checks explicitamente ou conecte-os ao mecanismo nativo do host.

## Verificação

```bash
python scripts/lane_board.py --self-test
python hooks/lane_git_guard.py --self-test
python hooks/lane_territory_guard.py --self-test
```
