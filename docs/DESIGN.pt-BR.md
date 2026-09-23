[English](DESIGN.md) · [Português](DESIGN.pt-BR.md)

# DESIGN.pt-BR.md — como construir uma interface para este projeto

O [`BRAND.pt-BR.md`](BRAND.pt-BR.md) diz o que a marca **é**: quatro cores, um acento, as cinco
palavras, o que não usar. Este arquivo diz como **construir** com ela — os tokens como existem no
código, os componentes que já embarcam, e o que um pull request que acrescenta interface tem de
satisfazer.

Leia o `BRAND.pt-BR.md` primeiro. Onde os dois discordarem, o BRAND vence e este arquivo é o
defeito.

## A folha de estilo é um arquivo, e é a única

```
docs/hpp.css
```

Ela é **emitida**, não escrita à mão: o `tools/catalog_md.py` guarda uma constante e produz tanto
este arquivo quanto o bloco `<style>` embutido em cada página. É por isso que as duas não podem
divergir, e o `tests/test_design_system.py` reprova se um dia divergirem.

Duas formas de usar, as duas corretas:

```html
<!-- uma pagina dentro deste repositorio -->
<link rel="stylesheet" href="hpp.css">

<!-- uma pagina que tem de sobreviver sozinha: cole o conteudo do arquivo -->
<style>/* conteudo de docs/hpp.css */</style>
```

⚠️ **Nunca a referencie por URL.** Toda página publicada aqui é autossuficiente por regra — uma
página que busca a folha de estilo no domínio de outra pessoa para de funcionar no dia em que
aquele domínio parar, e a suíte recusa qualquer `@import`, qualquer `https://` dentro de `url()` e
qualquer `@font-face`.

## Tokens

Quatro vêm da marca e são as únicas cores do sistema. Quatro são derivados e existem para que
ninguém invente uma quinta.

| token | valor | para que serve |
|---|---|---|
| `--hpp-black` | `#000000` | fundo do material de marca e do lockup |
| `--hpp-ink` | `#0F1113` | fundo de interface, superfície elevada |
| `--hpp-paper` | `#F4F1EB` | texto principal sobre escuro |
| `--hpp-signal` | `#FF6A00` | o acento, único |
| `--line` | `rgba(15,17,19,.18)` | régua e borda — o ink a 18% |
| `--surface` | `rgba(15,17,19,.04)` | bloco elevado — o ink a 4% |
| `--muted` | `rgba(15,17,19,.72)` | texto secundário — o ink a 72% |
| `--max` | `1120px` | a medida do `.wrap` |

**Os derivados são o ink com alpha reduzido, nunca uma cor nova.** O BRAND declara isso: *um
passo mais claro é o mesmo token com opacidade reduzida*. Um teste lê cada `rgb()` da folha e
reprova qualquer trio que não seja `15,17,19` — porque uma quinta cor entrando por um `rgba()` é
invisível para uma varredura de hex.

## Os componentes que já existem

Use estes antes de inventar. Cada um está no `docs/hpp.css` e já é renderizado pelas cinco páginas
publicadas, então o que o senhor construir com eles fica parecido com o resto do projeto de graça.

| seletor | o que é |
|---|---|
| `.wrap` | o contêiner. Tudo mora dentro dele, na medida `--max` |
| `.lang` · `.lang a[aria-current]` | o seletor de idioma. O lado atual carrega `aria-current`, o outro é link |
| `.hero` | a abertura da página: lockup, `.eyebrow`, `h1`, um parágrafo |
| `.eyebrow` | o rótulo pequeno em monoespaçada acima do título — caixa alta, tracking largo |
| `.lead` | o primeiro parágrafo de uma seção, um passo maior |
| `section` · `h2` · `h2 .version` · `h3` | o corpo. O `h2 .version` imprime a versão ao lado de um título |
| `table` · `th` · `td` | dado. `td.n` / `th.n` alinham número à direita; `tr.total` marca a linha de totais |
| `.chips code` | uma lista de nomes curtos como chips em linha |
| `footer` · `footer .five` | o fecho. O `.five` carrega as cinco palavras |
| `a:focus-visible` | o anel de foco. Nunca remova |

## As regras que não se negociam

1. **Um acento só.** O laranja marca o ponto de atenção. Uma tela com dois pontos de atenção não
   tem nenhum — então, se algo novo precisa do laranja, algo perde o laranja.
2. **Cor nunca carrega significado sozinha.** Um rótulo ou um ícone vai sempre com ela. Quem não
   distingue o laranja ainda tem de conseguir ler o estado.
3. **Sem webfont, sem pedido externo.** A pilha de tipos é só de sistema (`Sora`, `Inter`,
   `Segoe UI` para títulos; `JetBrains Mono`, `Cascadia Code`, `Consolas` para código e rótulo).
4. **Sem vermelho na paleta, de propósito.** Para estado, use o vermelho do próprio terminal e
   nunca pinte fundo: um terminal claro tem de continuar legível.
5. **Declare o idioma.** `<html lang>`, e `lang` em qualquer bloco na outra língua. Leitor de tela
   que lê português com fonema inglês é página que excluiu alguém.
6. **O anel de foco fica.** Teclado não é plano B.
7. **Todo documento de raiz é um par bilíngue.** `X.md` e `X.pt-BR.md`, linkados um ao outro no
   topo. Há teste que cobra.

## O que um pull request com interface tem de satisfazer

```
[ ] usa o docs/hpp.css — linkado dentro do repo, ou embutido. Nunca por URL
[ ] nao acrescenta uma quinta cor, nem em hex nem em rgb()
[ ] nao busca nada: sem @import, sem @font-face, sem https:// em url()
[ ] reusa os componentes acima antes de acrescentar seletor
[ ] declara lang, e mantem o anel de foco
[ ] traz o par .pt-BR, se for documento de raiz
[ ] e' GERADO, se for morar junto das paginas geradas -- veja a secao seguinte
```

Depois: `python -m pytest tests/test_design_system.py tests/test_docs_index.py -q`.

## Se for morar em `docs/`, gere

As cinco páginas de `docs/` são **artefatos emitidos**. Editá-las à mão funciona até o próximo
`catalog_md.py --write`, que sobrescreve a edição sem avisar. Se o senhor quer uma página morando
ali, acrescente-a ao `render_all()` do `tools/catalog_md.py` e ao `OWN_FILES`, como o
`index.html` e o `hpp.css` já estão — aí ela é gerada, é listada uma vez, e não apodrece.

Página que mora em qualquer outro lugar (template, exemplo, relatório) é sua para escrever à mão.
O `multi-session/lane-kit-*/templates/status-stakeholder.template.html` é a referência desse caso:
mesmos tokens, escrito à mão, e lê o board sem nunca escrever nele.

## Onde mora a arte

O `BRAND.pt-BR.md` tem a tabela inteira. Os dois que o senhor vai buscar:

- `assets/hpp-logo-header.png` — o lockup para topo de página, 1440 px. É a arte aprovada
  redimensionada; **não redesenhar, não recolorir, não recortar.**
- `assets/hpp-mark.svg` — o símbolo em vetor, para impressão ou escala grande. Onde a fidelidade
  decidir, use o lockup raster.
