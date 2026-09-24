[English](AGENTS.md) · [Português](AGENTS.pt-BR.md)

# AGENTS.md — House Party Protocol

House Party Protocol é um harness local-first de confiabilidade, governança e avaliação para
agentes de código em Claude Code e Codex CLI. Os módulos são capacidades instaláveis do harness;
o marketplace é apenas um canal de distribuição.

## Regras do repositório

- Trate `hpp.manifest.json` como contrato executável de módulos, relações, hosts e invariantes.
- Os diretórios versionados dos módulos são artefatos emitidos; não os edite à mão.
- Alterações nascem nas fontes, recebem teste vermelho→verde e passam pela forja.
- Nunca reduza um gate para obter verde. Corrija o artefato que o gate reprovou.
- Preserve MIT, NOTICE e atribuições de código adaptado.
- Não registre credenciais, caminhos pessoais, clientes ou infraestrutura privada.
- `examples/typed-decisions/decide.py` envia texto, e uma chave lida do ambiente, a um endpoint externo; o `hpp policy check` classifica rodá-lo como `MANUAL` (regra `decision-advisor`, nova na 2.6.0). Nunca o invoque sem supervisão nem a partir de um hook.
- `healthy` prova frescor do sinal declarado; não prova correção do trabalho.
- Waves vêm de dependências do WorkGraph; uma lane não recebe território conflitante.

## Códigos de saída

`0` ok · `1` warn/manual · `2` block · `3` erro.

## Codex CLI

Use `installers/kit-forge-1.4.2/kit_doctor.py install --kit <kit> --host codex --target <repo> --apply`.
As skills vão para `.agents/skills`; o runtime completo vai para `.agents/hpp`. Hooks declarados
em `hooks.json` pertencem ao Claude Code e não são ativados automaticamente no Codex.

Antes de declarar uma mudança concluída, rode o self-test do script alterado, `python -m hpp
doctor`, o benchmark, o verificador dos módulos e o gate de publicação.
