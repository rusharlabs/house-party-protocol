# Contribuir

Obrigado. Este repositório é o **produto emitido** — dez kits, cada um selado com `CHECKSUMS.txt`.
Isso muda o jeito de contribuir: não se edita um kit no lugar; edita-se a fonte, re-emite-se o
kit pela forja, e o gate prova o resultado.

## Regras que não têm exceção

1. **Nenhum nome de cliente, e-mail pessoal, caminho de máquina, porta interna ou credencial.**
   O `ip_pii_linter` roda antes de qualquer emissão e não tem `--skip`. Se ele reprovar, o
   problema é o conteúdo, não o linter.
2. **Todo `.py` novo em kit tem `--self-test`** que passa em Windows, macOS e Linux, e o
   self-test não pode depender de `python` a seco (use `sys.executable`).
3. **Toda `SKILL.md` passa no `skill_lint`**: contrato de I/O, ≥3 exemplos executados de
   verdade (com o marcador `<!-- executado: AAAA-MM-DD · exit=N -->`), seção `## Prova`, e
   caminhos ancorados em `${CLAUDE_PLUGIN_ROOT}`.
4. **Hooks são WARN-only** salvo decisão explícita documentada no `hooks.json` do kit.
5. **Conserto de bug vem com o teste que falhava antes.** Um teste escrito depois do conserto
   prova que o código de agora funciona; não prova que consertou alguma coisa.

## Fluxo

```bash
# 1. verifique o kit que vai tocar
python instaladores/kit-forge-1.4.0/kit_doctor.py verify frameworks-com-plugins/operator-kit-1.3.0

# 2. faça a mudança na FONTE do kit (abra uma issue antes se for grande)

# 3. re-emita pela forja e prove
python instaladores/kit-forge-1.4.0/kit_assembler.py --manifest <manifesto-do-kit> --out <dir>
python instaladores/kit-forge-1.4.0/kit_doctor.py verify <dir>/<kit>-<versao>
python instaladores/kit-forge-1.4.0/tools/skill_lint.py <dir>/<kit>-<versao>/skills/<skill>

# 4. suba a versão do kit (semver) — comportamento novo sob o mesmo número quebra o CHECKSUMS
#    de quem já tem o kit — e registre no CHANGELOG.md
```

## Commits e licença

- Conventional commits (`feat(kit):`, `fix(kit-forge):`, `docs:`).
- Assine seus commits com o **Developer Certificate of Origin**: `git commit -s`. O sign-off
  declara que você tem o direito de contribuir o código sob a licença deste repositório.
- Contribuições entram sob a mesma licença do projeto (**MIT**). Não envie código que você
  não pode licenciar assim — inclusive código gerado a partir de repositório sem licença.

## O que não é bem-vindo

- Dependência nova onde a stdlib resolve.
- "Melhoria" em linha que não tem a ver com o pedido (o diff tem de rastrear ao problema).
- Exemplo executado que não foi executado.
