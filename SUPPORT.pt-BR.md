[English](SUPPORT.md) · [Português](SUPPORT.pt-BR.md)

# Suporte

## Dúvidas e conversas sobre design

Para dúvidas de uso ou conversas sobre design, use as [Discussões do GitHub](https://github.com/rusharlabs/house-party-protocol/discussions). Dúvidas vão para a categoria [Q&A](https://github.com/rusharlabs/house-party-protocol/discussions/categories/q-a), em português ou em inglês; uma ideia inicial ou uma pergunta de design que ainda não cabe no formulário de ideia abaixo vai para [Ideas](https://github.com/rusharlabs/house-party-protocol/discussions/categories/ideas). Cole o comando que você rodou e a saída, sem tokens nem caminhos pessoais.

## Relatar divergência na documentação

Se um comando se comportar de forma diferente do que a documentação descreve, abra um [relato de problema](https://github.com/rusharlabs/house-party-protocol/issues/new?template=problem.yml). Inclua o comando exato e a saída. Remova tokens e outros segredos antes de publicar.

## Dar feedback

Se algo foi confuso, mais lento do que devia ou fez você deixar de usar uma peça do harness, abra o [formulário de feedback](https://github.com/rusharlabs/house-party-protocol/issues/new?template=feedback.yml). Ele não pede reprodução: uma frase basta, e deixar um módulo de fora ou desligar um hook também conta. Rode o comando abaixo e cole no formulário o relatório que ele imprime:

```bash
hpp doctor --report
```

Ele imprime o link do formulário com o título preenchido e, abaixo, o relatório: versões, Python, plataforma e as contagens do doctor, sem nenhum caminho da sua máquina. O comando não faz chamada de rede; nada é enviado até você mesmo abrir o link. Num clone sem o pacote instalado, rode `python -m hpp doctor --report`.

## Propor uma ideia

Para uma capacidade, um módulo ou um contrato que o harness deveria ter, abra o [formulário de ideia](https://github.com/rusharlabs/house-party-protocol/issues/new?template=idea.yml). Ele pede a falha que a ideia remove, o que o harness faria de diferente e o comando ou teste que a provaria, com o caso negativo que a mostraria recusando. Uma ideia também precisa caber nos [limites honestos](README.pt-BR.md#limites-honestos), ou dizer qual deles mudaria e por quê.

## Relatar uma vulnerabilidade

Não abra uma issue pública para relatar uma vulnerabilidade. Use o [canal privado de vulnerabilidades do GitHub](https://github.com/rusharlabs/house-party-protocol/security/advisories/new) ou o canal de contato no [site do projeto](https://rusharlabs.com), conforme descrito em [SECURITY.pt-BR.md](SECURITY.pt-BR.md).

## Manual e catálogo

Consulte o [manual](https://rusharlabs.github.io/house-party-protocol/MANUAL.pt-BR.html) e o [catálogo](https://rusharlabs.github.io/house-party-protocol/CATALOG.pt-BR.html) no site do projeto.
