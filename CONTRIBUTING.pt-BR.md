[English](CONTRIBUTING.md) · [Português](CONTRIBUTING.pt-BR.md)

# Contribuir

Obrigado. Este repositório é o **produto emitido** — módulos versionados, cada um selado com
`CHECKSUMS.txt`. Isso muda o jeito de contribuir: não se edita um módulo no lugar; edita-se a
fonte, re-emite-se o módulo pela forja, e o gate prova o resultado.

## Regras que não têm exceção

1. **Nenhum nome de cliente, e-mail pessoal, caminho de máquina, porta interna ou credencial.**
   O `ip_pii_linter` roda antes de qualquer emissão e não tem `--skip`. Se ele reprovar, o
   problema é o conteúdo, não o linter.
2. **Todo `.py` novo em módulo tem `--self-test`** que passa em Windows, macOS e Linux, e o
   self-test não pode depender de `python` a seco (use `sys.executable`).
3. **Toda `SKILL.md` passa no `skill_lint`**: contrato de I/O, ao menos 3 exemplos executados de
   verdade (com o marcador `<!-- executado: AAAA-MM-DD · exit=N -->`), seção `## Prova`, e
   caminhos ancorados em `${CLAUDE_PLUGIN_ROOT}`.
4. **Hooks são WARN-only** salvo decisão explícita documentada no `hooks.json` do módulo.
5. **Conserto de bug vem com o teste que falhava antes.** Um teste escrito depois do conserto
   prova que o código de agora funciona; não prova que consertou alguma coisa.

## Fluxo

```bash
# 1. verify the module you are about to touch
python instaladores/kit-forge-1.4.0/kit_doctor.py verify frameworks-com-plugins/operator-kit-1.4.0

# 2. make the change in the module SOURCE (open an issue first if it is large)

# 3. re-emit through the forge and prove it
python instaladores/kit-forge-1.4.0/kit_assembler.py --manifest <module-manifest> --out <dir>
python instaladores/kit-forge-1.4.0/kit_doctor.py verify <dir>/<module>-<version>
python instaladores/kit-forge-1.4.0/tools/skill_lint.py <dir>/<module>-<version>/skills/<skill>

# 4. bump the module version (semver) -- new behaviour under the same number breaks the
#    CHECKSUMS of whoever already has the module -- and record it in CHANGELOG.md
```

Em ordem: verifique o módulo que vai tocar; faça a mudança na fonte (abra uma issue antes se for
grande); re-emita pela forja e prove com `verify` e `skill_lint`; suba a versão do módulo
(semver) — comportamento novo sob o mesmo número quebra o `CHECKSUMS` de quem já tem o módulo — e
registre no `CHANGELOG.md`.

## Documentação em duas línguas

Documento que um **humano** lê antes de decidir usar o projeto existe nas duas línguas, pareado
como `NOME.md` (inglês, a fonte de verdade) e `NOME.pt-BR.md` (português do Brasil). A primeira
linha útil dos dois é o par de idiomas:

```
[English](NAME.md) · [Português](NAME.pt-BR.md)
```

Arquivo que um **agente** lê para executar — qualquer coisa sob `skills/`, `commands/` ou
`rules/` — fica só em inglês. Uma cópia traduzida ali dobra a manutenção e convida à divergência
silenciosa entre o que as duas cópias mandam fazer.

Um gate no repositório-fonte (`test_documentacao_bilingue.py`) reprova quem fura a regra: par
ausente, link de topo que não aponta para o irmão, divergência estrutural (os dois lados carregam
os mesmos títulos, na mesma ordem — tradução muda palavras, não estrutura), blocos de código
diferentes (comando é comando em qualquer língua) e qualquer `.pt-BR.md` dentro da camada de
agente. `NOTICE`, `CITATION.cff` e `LICENSE` são instrumentos legais e de citação e ficam só em
inglês: traduzir criaria ambiguidade sobre qual versão vale.

## Commits e licença

- Conventional commits (`feat(kit):`, `fix(kit-forge):`, `docs:`).
- Assine seus commits com o **Developer Certificate of Origin**: `git commit -s`. O sign-off
  declara que você tem o direito de contribuir o código sob a licença deste repositório.
- Contribuições entram sob a mesma licença do projeto (**MIT**). Não envie código que você
  não pode licenciar assim — inclusive código gerado a partir de repositório sem licença.

## O que não é bem-vindo

- Dependência nova onde a stdlib resolve.
- "Melhoria" em linha vizinha que não tem a ver com o pedido (o diff tem de rastrear ao problema).
- Exemplo executado que não foi executado.
