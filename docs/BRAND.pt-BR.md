[English](BRAND.md) · [Português](BRAND.pt-BR.md)

# Identidade do House Party Protocol

## Ideia central

Um harness é o que fica **em volta** do trabalho: o que delimita, observa, registra e decide
quando algo pode avançar. A marca representa isso — um núcleo de luz contido por uma estrutura
que não se move. Nós indicam agentes, lanes e evidências; portais indicam critérios que o
trabalho precisa cruzar.

Tom: preciso, operacional, curioso e direto. O produto fala por mecanismos demonstráveis, nunca
por adjetivo. Não há personagens nem referência a franquia de terceiro.

## Assinatura

**Operate coding agents under evidence, not trust.**

Versão em português para texto corrido: **Opere agentes de código sob evidência, não confiança.**

Linhas de apoio, para abertura, rodapé e release:

- *Open-source agentic tooling for people who build.*
- *Open. Modular. Auditable. Composable.*
- *Built in public. For a more capable tomorrow.*
- *Welcome to the party.* — fecho da instalação, e só ali.

## As cinco palavras

`AGENTS · EVIDENCE · MEMORY · PROTOCOL · CONTINUITY`

Aparecem em caixa alta, espaçadas, como rótulo — nunca como frase. São as cinco coisas que o
harness carrega, e a ordem é fixa.

## Paleta

| Token | Valor | Uso |
|---|---|---|
| black | `#000000` | fundo do lockup e do material de marca |
| charcoal | `#0F1113` | fundo de interface, superfície elevada |
| warm-white | `#F4F1EB` | texto principal sobre escuro, e o cromo do wordmark |
| signal-orange | `#FF6A00` | acento único: foco, gate aprovado, o núcleo do símbolo |

Quatro cores, um acento só. O laranja **não** é decoração: ele marca o ponto de atenção da tela,
e uma tela com dois pontos de atenção não tem nenhum. Cor nunca carrega significado sozinha —
rótulo ou ícone sempre acompanha.

Para estado, a interface usa o vermelho do próprio terminal (a paleta não tem vermelho de
propósito) e nunca pinta fundo: um terminal claro continua legível.

Os ativos vetoriais carregam só esses quatro valores: um degrau mais claro é o mesmo token com
opacidade reduzida, nunca uma quinta cor. Meça com `grep -o '#[0-9A-Fa-f]\{6\}' assets/*.svg | sort -u`.

## Tipografia

| Papel | Pilha |
|---|---|
| display / lockup | desenho próprio (o wordmark é arte, não fonte) |
| títulos | `Sora`, `Inter`, `Segoe UI`, sans-serif — peso alto, tracking apertado |
| corpo | `Inter`, `Segoe UI`, `Arial`, sans-serif |
| código, métrica e rótulo | `JetBrains Mono`, `Cascadia Code`, `Consolas`, monospace |
| rótulo de interface | caixa alta, `letter-spacing` largo, monospace |

Nenhum ativo publicado carrega webfont: a pilha é de sistema, e o material self-contained não
faz requisição externa.

## Ativos

| Arquivo | Uso |
|---|---|
| `assets/hpp-logo.png` | **o lockup oficial** — cromo sobre preto, com o núcleo em laranja. É a arte aprovada; não redesenhar, não recolorir, não recortar |
| `assets/hpp-icon-512.png` · `-256` · `-128` · `-64` · `-32` | o distintivo sozinho, quadrado — avatar, favicon e ícone de app. Derivado do lockup por recorte, nunca redesenhado |
| `assets/hpp-mark.svg` | o símbolo em vetor, para onde o raster não serve (impressão, escala grande) |
| `assets/hpp-logo-light.svg` e `assets/hpp-logo-dark.svg` | lockup em linha, para onde o raster não cabe |
| `assets/hpp-banner-light.svg` e `assets/hpp-banner-dark.svg` | faixa horizontal para topo de página e material de apresentação — o README abre com o lockup, não com a faixa |

O símbolo **não** codifica a quantidade de módulos: o harness pode crescer sem redesenhar a marca.

Na CLI, o lockup é reconstruído em blocos de terminal (`█ ▓ ░`) na mesma paleta, com degradação
declarada: truecolor → 256 cores → 16 cores → sem cor nenhuma quando não há TTY ou quando
`NO_COLOR` está definido.

## Arquitetura de mensagem

1. **Harness** — o produto.
2. **Protocol** — as regras executáveis.
3. **Modules** — as capacidades instaláveis.
4. **Distribution** — os canais por host.

Não abrir uma página com quantidade de módulos. Não chamar distribuição de produto. Não usar
"autônomo", "determinístico", "aprende" ou "cross-host" sem delimitar mecanismo e escopo.

## Acessibilidade

- contraste mínimo WCAG AA;
- foco visível em `#FF6A00` sobre `#0F1113`, e `#0F1113` sobre `#F4F1EB`;
- suporte a 320, 375, 768 e 1280 px;
- `prefers-reduced-motion` desliga toda animação, e a informação continua completa.

## Não usar

- gradiente como assunto — o degradê existe no lockup e não se repete na interface;
- cor sem rótulo;
- ilustração de robô, cérebro ou humanoide;
- metáfora de franquia, personagem ou filme;
- número de módulos como manchete;
- emoji em saída de CLI.
