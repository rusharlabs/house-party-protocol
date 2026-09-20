# AGENTS.md — House Party Protocol

House Party Protocol é a fonte pública de dez kits verificáveis para Claude Code e Codex CLI.

## Regras do repositório

- Os diretórios versionados dos kits são artefatos emitidos; não os edite à mão.
- Alterações nascem nas fontes, recebem teste vermelho→verde e passam pela forja.
- Nunca reduza um gate para obter verde. Corrija o artefato que o gate reprovou.
- Preserve MIT, NOTICE e atribuições de código adaptado.
- Não registre credenciais, caminhos pessoais, clientes ou infraestrutura privada.

## Codex CLI

Use `instaladores/kit-forge-1.4.0/kit_doctor.py install --kit <kit> --host codex --target <repo> --apply`.
As skills vão para `.agents/skills`; o runtime completo vai para `.agents/hpp`. Hooks declarados
em `hooks.json` são do Claude Code e não são ativados automaticamente no Codex.

Antes de declarar uma mudança concluída, rode o self-test do script alterado, verifique o kit e
confira o gate de publicação.
