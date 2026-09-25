[English](INSTALL_FOR_AGENTS.md) · [Português](INSTALL_FOR_AGENTS.pt-BR.md)

# Instalando o House Party Protocol — um guia para agentes

Você é um agente a quem pediram para instalar o House Party Protocol num repositório. Este
arquivo é a instrução inteira. Leia até o fim antes de rodar qualquer coisa: o passo 4 contém um
portão que você não pode pular, e saber que ele existe muda o que você faz no passo 3.

O House Party Protocol é um harness local-first de confiabilidade, governança e avaliação de
agentes de código. Ele não tem dependência de runtime e não fala com serviço de rede. Instalar
escreve arquivos num repositório e os liga a um host; nada além disso acontece.

## Passo 0 — identifique o seu host

Os dois hosts se ligam de formas diferentes, e a diferença não é cosmética.

| você é | vá para |
|---|---|
| **Claude Code** | passos 1 → 4, depois o 6 |
| **Codex CLI** | passos 1 → 4, depois o 5, depois o 6 |
| nenhum dos dois | a CLI instala e o `hpp doctor` responde, mas não existe wiring de host para você; pare depois do passo 3 e avise a pessoa |

## Passo 1 — confira os pré-requisitos, não os presuma

- **Python 3.10 ou mais novo.** A CI exercita 3.10 a 3.13 em Linux, macOS e Windows.
  Interpretadores mais antigos não são prometidos, porque nada os mede.
- **`git` no `PATH`**, para attestation.
- **Um repositório-alvo.** Instalar num diretório vazio funciona e é assim que o wizard é
  testado, mas o harness só é útil onde há trabalho a governar.

Se um pré-requisito falhar, diga qual e pare. Não instale um Python, não troque o interpretador
da pessoa, não contorne a ausência do `git`.

## Passo 2 — instale a CLI

```bash
pip install git+https://github.com/rusharlabs/house-party-protocol@v2.7.0
```

`pipx install git+…` funciona igual. O pacote traz o próprio manifesto e a própria suíte de
benchmark, então a CLI responde de qualquer diretório depois de instalada.

## Passo 3 — prove a instalação antes de usá-la

```bash
hpp doctor
```

Ele imprime uma linha e sai com `0`:

```
HPP doctor: ok - modules=10 - hosts=claude-code, codex - hooks=18 (permission gates=9 - llm egress=0)
```

Saída diferente de zero aqui significa instalação quebrada. Reporte a linha e pare; não siga
para o passo 4 esperando que se resolva sozinho.

## Passo 4 — leia o plano para a pessoa. NÃO PULE

```bash
hpp init --target <path-to-the-repository>
```

Sem `--apply`, o `hpp init` **não escreve nada**. Ele roda seis estágios fixos e imprime um
plano do que escreveria.

Leia o plano em voz alta, e não só as linhas a colar. Quando os módulos escolhidos declaram
hooks, ele imprime uma tabela HOOK CAPABILITIES antes do bloco WIRE: para cada hook, seus eventos,
sua política de saída (`observe`, `warn` ou `block`) e seus grupos de capacidade. Essa tabela é o
que os hooks conseguem fazer depois de ligados; as linhas a colar sozinhas são só nomes de
arquivo. Deixe o `--decision-advisor` em `off`, a menos que a pessoa tenha pedido (novo na
2.6.0).

**Mostre esse plano à pessoa e espere o sim dela.** Só então:

```bash
hpp init --target <path-to-the-repository> --apply
```

Isso não é cerimônia. O plano é o único instante em que a pessoa consegue ver o que está prestes
a entrar no repositório dela, e um instalador que escreve antes de você ler é exatamente a falha
que este harness existe para impedir. Se você pular, instalou o harness violando-o.

## Passo 5 — wiring do Codex CLI

O Claude Code é ligado pelo passo 4. O Codex CLI precisa de um comando a mais por módulo:

```bash
installers/kit-forge-1.4.2/kit_doctor.py install --kit <kit> --host codex --target <repo> --apply
```

As skills vão para `.agents/skills`; o runtime completo vai para `.agents/hpp`. Os hooks
declarados em `hooks.json` pertencem ao Claude Code e **não** são ativados no Codex. O
`hpp init --host codex` imprime a tabela HOOK CAPABILITIES mesmo assim; leia-a em voz alta como o
que esses hooks fariam no Claude Code, e diga que nenhum deles roda aqui, em vez de deixar a
pessoa acreditar que um portão está armado quando não está.

## Passo 6 — verifique, e reporte o código de saída, não a sua impressão

```bash
hpp doctor
hpp benchmark
```

O `hpp benchmark` reporta `pass@k` e `pass^k` separadamente e imprime o próprio veredito de
gate. Cite as duas saídas à pessoa. Transcrição não é código de saída.

Se o `hpp init` imprimiu uma seção DOCUMENTATION, aponte à pessoa as páginas que ela nomeia; cada
uma foi encontrada no disco. Uma instalação por pip não carrega páginas de documentação, então
depois do passo 2 a seção não aparece — não invente caminhos.

## Códigos de saída

`0` ok · `1` warn/manual · `2` block · `3` error.

## Não faça

- **Não edite os diretórios versionados de módulo.** Eles são artefatos emitidos. Uma edição à
  mão faz o checksum divergir, e a próxima instalação os recusa.
- **Não baixe um gate para ficar verde.** Conserte o artefato que o gate reprovou.
- **Não registre credencial, caminho pessoal, cliente ou infraestrutura privada** em lugar
  nenhum onde o harness escreve.
- **Não trate `healthy` como correto.** Ele prova o frescor do sinal declarado, nada mais.

## Atualizando

Refaça o passo 2 com a tag nova e o passo 3. O `hpp init` é idempotente: rode de novo e leia o
plano de novo. O plano é o que mudou.

## Se falhar

Rode `hpp doctor` e cite a linha inteira. Abra uma issue em
<https://github.com/rusharlabs/house-party-protocol/issues> com essa linha, a sua versão de
Python e o seu host. Não cole credencial, token nem caminho absoluto da máquina da pessoa.
