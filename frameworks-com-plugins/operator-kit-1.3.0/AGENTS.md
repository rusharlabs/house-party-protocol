# AGENTS.md — operator-kit

Este kit fornece gates, regras e scripts portáteis para operação verificável.

## Codex CLI

- Trabalhe a partir da raiz do kit.
- Instale por cópia com `kit_doctor.py install --kit <operator-kit> --host codex --target <repo> --apply`.
- As skills ficam em `<repo>/.agents/skills/`; o runtime completo fica em `<repo>/.agents/hpp/operator-kit/`.
- Hooks em `hooks/hooks.json` são exclusivos do Claude Code e não são ativados no Codex. Rode os gates explicitamente.

## Verificação

```bash
python scripts/done_gate.py --self-test
python scripts/live_count.py --self-test
python scripts/claude_md_from_profile.py --self-test
```

Não edite `CHECKSUMS.txt` nem o kit emitido; alterações nascem na fonte e passam pela forja.
