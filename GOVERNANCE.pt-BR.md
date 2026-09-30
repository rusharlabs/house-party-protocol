[English](GOVERNANCE.md) · [Português](GOVERNANCE.pt-BR.md)

# Governança

O House Party Protocol tem um mantenedor. Esta página diz quem decide, onde cada decisão fica
registrada, como um desacordo termina, como uma release é feita e o que acontece se o mantenedor
sair de cena. Ela descreve como o projeto funciona hoje; onde uma parte do plano ainda não está de
pé, ela diz isso.

## Quem decide

O projeto segue um modelo de mantenedor único. O mantenedor é Max Parisi, que age no GitHub pela
conta de mantenedor que o `.github/CODEOWNERS` nomeia para todo caminho do repositório.

O mantenedor decide o que entra por merge, o que é lançado e quando, o que o roadmap diz e o que o
projeto recusa. Qualquer pessoa pode propor qualquer uma dessas coisas. A decisão é tomada em
público, na thread em que foi pedida, com o motivo ao lado.

## Papéis

| responsabilidade | papel | quem exerce |
|---|---|---|
| triagem de issues e discussões | mantenedor | Max Parisi |
| revisão e merge de pull requests | mantenedor | Max Parisi |
| releases | mantenedor | Max Parisi |
| resposta de segurança ([SECURITY.pt-BR.md](SECURITY.pt-BR.md)) | mantenedor | Max Parisi |
| aplicação do código de conduta ([CODE_OF_CONDUCT.pt-BR.md](CODE_OF_CONDUCT.pt-BR.md)) | mantenedor | Max Parisi |
| issues, discussões, pull requests e revisões sob o [CONTRIBUTING.pt-BR.md](CONTRIBUTING.pt-BR.md) | contribuidor | qualquer pessoa |

Hoje não há um segundo mantenedor. Veja [Continuidade](#continuidade).

## Onde as decisões ficam registradas

- **`CHANGELOG.md` e `CHANGELOG.pt-BR.md`** registram toda mudança que é lançada, por versão. O
  workflow de release recusa uma tag cuja versão não tenha seção não vazia nos dois arquivos.
- **As notas de release.** O corpo de cada GitHub Release é a seção do CHANGELOG daquela versão,
  primeiro em inglês e o português abaixo; quem escreve é o workflow, ninguém redigita.
- **Discussões, categoria Announcements.** Cada release abre a sua própria discussão ali, e o
  roadmap é discutido ali. O mantenedor publica; qualquer pessoa comenta.
- **A própria issue ou o próprio pull request** carrega o raciocínio de uma mudança isolada.
- **[MANIFESTO.pt-BR.md](MANIFESTO.pt-BR.md), "O que o projeto se recusa a fazer"**, guarda as
  recusas permanentes. Mudar uma delas é mudar esse arquivo, com registro no CHANGELOG como qualquer
  outra mudança.

## Como um desacordo é resolvido

1. Diga onde a pergunta mora: na issue, no pull request, ou na categoria Ideas das Discussões
   quando não estiver ligada a uma mudança. Nomeie a falha, a mudança que você propõe e a
   evidência — o comando que você rodou e a saída.
2. O mantenedor responde na mesma thread com uma decisão e o motivo. Evidência pesa mais que
   preferência: uma reprodução vale mais que um argumento, dos dois lados.
3. Evidência nova reabre uma decisão; repetir o argumento não. Uma enquete na categoria Polls
   informa uma decisão; não a toma.
4. O código é licenciado sob MIT. Quem continuar discordando pode fazer um fork; o fork é outro
   projeto, e uma cópia que mantém o nome não é este ([SECURITY.pt-BR.md](SECURITY.pt-BR.md),
   "Superfícies oficiais").

Uma questão de conduta segue a seção de aplicação do
[CODE_OF_CONDUCT.pt-BR.md](CODE_OF_CONDUCT.pt-BR.md), e uma vulnerabilidade vai pelos canais
privados do [SECURITY.pt-BR.md](SECURITY.pt-BR.md) — nenhuma das duas se discute em thread pública.

## Como uma release é feita

Uma release é uma tag `vX.Y.Z`. Empurrá-la roda o `.github/workflows/release.yml`, que:

1. se recusa a seguir a menos que as quatro fontes de versão (`pyproject.toml`, `hpp/__init__.py`,
   `hpp.manifest.json`, `CITATION.cff`) sejam iguais à tag e os dois arquivos de CHANGELOG tenham
   uma seção não vazia para ela;
2. constrói o wheel e o sdist uma vez e escreve o `SHA256SUMS`;
3. instala esse wheel, sem checkout, no Ubuntu, no macOS e no Windows, e roda `hpp --version`,
   `hpp doctor`, `hpp benchmark -k 3` e `hpp init` a partir de um diretório vazio;
4. assina a proveniência de build do wheel e do sdist num job só dela;
5. cria a GitHub Release com o wheel, o sdist, o `SHA256SUMS` e o bundle de proveniência, a seção
   do CHANGELOG como notas, e abre a discussão da release em Announcements;
6. publica no PyPI por trusted publishing, sem token guardado, quando a variável de repositório
   `PYPI_PUBLISH` é `true`.

Uma execução manual existe só para recuperar uma tag cujo push não disparou o workflow; ela exige
uma tag existente, e essa tag passa pelos mesmos passos. Qualquer pessoa confere de onde um arquivo
veio:

```bash
gh attestation verify <file> --repo rusharlabs/house-party-protocol
```

Quais versões recebem correção está no [SECURITY.pt-BR.md](SECURITY.pt-BR.md), "Versões
suportadas".

## Continuidade

Esta seção é um plano, não um relatório. Ela diz do que o projeto precisa para que alguém além do
mantenedor consiga mantê-lo de pé, e quais partes ainda não estão de pé.

Do que um sucessor precisa:

- o papel de **owner** na organização `rusharlabs` do GitHub — as configurações do repositório, a
  proteção de branch, as Discussões, o ambiente `pypi`, a variável `PYPI_PUBLISH` e o relato
  privado de vulnerabilidade moram ali;
- o papel de **owner** no projeto `house-party-protocol` do PyPI, cujo único publicador é o
  workflow de release deste repositório;
- o controle do domínio do site que o [SECURITY.pt-BR.md](SECURITY.pt-BR.md) e o
  [CODE_OF_CONDUCT.pt-BR.md](CODE_OF_CONDUCT.pt-BR.md) indicam como canal de contato para relatos
  de segurança e de conduta.

Os códigos de recuperação das contas que detêm esses três devem ficar guardados num cofre que a
segunda pessoa consiga abrir.

| parte do plano | estado |
|---|---|
| do que um sucessor precisa, listado acima | escrito aqui |
| códigos de recuperação guardados num cofre | plano — esta página não o atesta |
| uma segunda pessoa nomeada, com os acessos acima | **pendente — ninguém foi nomeado ainda** |
| fazer triagem, aceitar mudanças e lançar uma release em até uma semana depois de o mantenedor ficar indisponível | o compromisso quando a segunda pessoa for nomeada; não vale antes disso |

Até uma segunda pessoa ser nomeada, o projeto depende de uma pessoa. A licença já garante o resto:
qualquer pessoa pode fazer um fork do código e continuá-lo com outro nome.

## Mudando este documento

Esta página muda por pull request como qualquer outro arquivo, e a mudança fica registrada no
CHANGELOG.
