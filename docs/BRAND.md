# Identidade do House Party Protocol

## Ideia central

O sistema visual representa um **caminho de sinal atravessando gates**. Nós indicam agentes,
lanes e evidências; portais indicam critérios que o trabalho precisa cruzar. Não há personagens
nem referência a outra franquia.

Tom: preciso, operacional, curioso e direto. O produto fala por mecanismos demonstráveis.

## Assinatura

**Operate coding agents under evidence, not trust.**

Versão em português para texto corrido: **Opere agentes de código sob evidência, não confiança.**

## Paleta Signal Path

| Token | Valor | Uso |
|---|---|---|
| ink | `#0C0F0E` | fundo escuro e texto principal |
| paper | `#F2F0E9` | fundo claro |
| signal | `#D7FF64` | gate aprovado e foco principal |
| trace | `#5DE4C7` | conexões, links e estado ativo |
| alert | `#FF6B5F` | bloqueio e conflito |
| slate | `#66706B` | texto secundário em fundo claro |
| mist | `#B8C2BC` | texto secundário em fundo escuro |

Signal, trace e alert não carregam significado sozinhos: rótulo ou ícone sempre acompanha a cor.

## Tipografia

- interface e leitura: `Inter`, `Segoe UI`, `Arial`, sans-serif;
- código e métricas: `JetBrains Mono`, `Cascadia Code`, `Consolas`, monospace.

## Ativos

- `assets/hpp-mark.svg` — símbolo compacto para avatar e favicon;
- `assets/hpp-logo-light.svg` — lockup em fundo claro;
- `assets/hpp-logo-dark.svg` — lockup em fundo escuro;
- `assets/hpp-banner-light.svg` — abertura do README em tema claro;
- `assets/hpp-banner-dark.svg` — abertura do README em tema escuro.

O símbolo não codifica a quantidade de módulos; o harness pode crescer sem redesenhar a marca.

## Arquitetura de mensagem

1. Harness: o produto.
2. Protocol: as regras executáveis.
3. Modules: as capacidades instaláveis.
4. Distribution: os canais por host.

Não abrir uma página com quantidade de módulos. Não chamar distribuição de produto. Não usar
“autônomo”, “determinístico”, “aprende” ou “cross-host” sem delimitar mecanismo e escopo.

## Acessibilidade

- contraste mínimo WCAG AA;
- foco visível em `#D7FF64` sobre ink e `#0C0F0E` sobre paper;
- suporte a 320, 375, 768 e 1280 px;
- zoom 200% sem perda de conteúdo;
- `prefers-reduced-motion` desativa animação não essencial;
- headings em ordem e landmarks semânticos;
- SVGs com `role`, `title` e descrição quando exibidos fora de `<img alt>`.

## Não usar

- gradiente neon genérico sem função;
- metáfora de super-herói ou assistente pessoal;
- nós decorativos sem relação com o sistema;
- claim “top-tier” sem benchmark ao lado;
- mock de dashboard apresentado como runtime real.
