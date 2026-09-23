[English](BRAND.md) · [Português](BRAND.pt-BR.md)

# House Party Protocol identity

## Central idea

A harness is what sits **around** the work: what bounds, observes, records and decides when
something may advance. The brand represents that — a core of light held by a structure that does
not move. Nodes stand for agents, lanes and evidence; portals stand for criteria the work has to
cross.

Tone: precise, operational, curious and direct. The product speaks through demonstrable
mechanisms, never through adjectives. There are no characters and no reference to third-party
franchises.

## Signature

**Operate coding agents under evidence, not trust.**

Portuguese version for running text: **Opere agentes de código sob evidência, não confiança.**

Support lines, for opening, footer and release:

- *Open-source agentic tooling for people who build.*
- *Open. Modular. Auditable. Composable.*
- *Built in public. For a more capable tomorrow.*
- *Welcome to the party.* — the closing line of the installation, and only there.

## The five words

`AGENTS · EVIDENCE · MEMORY · PROTOCOL · CONTINUITY`

They appear in upper case, spaced, as a label — never as a sentence. They are the five things the
harness carries, and the order is fixed.

## Palette

| Token | Value | Use |
|---|---|---|
| black | `#000000` | background of the lockup and of brand material |
| charcoal | `#0F1113` | interface background, elevated surface |
| warm-white | `#F4F1EB` | primary text on dark, and the chrome of the wordmark |
| signal-orange | `#FF6A00` | single accent: focus, approved gate, the core of the symbol |

Four colours, one accent. The orange is **not** decoration: it marks the point of attention on the
screen, and a screen with two points of attention has none. Colour never carries meaning alone —
a label or an icon always goes with it.

For state, the interface uses the terminal's own red (the palette has no red on purpose) and never
paints a background: a light terminal stays readable.

The vector assets carry only these four values: a lighter step is the same token at reduced
opacity, never a fifth colour. Measure it with `grep -o '#[0-9A-Fa-f]\{6\}' assets/*.svg | sort -u`.

## Typography

| Role | Stack |
|---|---|
| display / lockup | custom drawing (the wordmark is artwork, not a font) |
| headings | `Sora`, `Inter`, `Segoe UI`, sans-serif — heavy weight, tight tracking |
| body | `Inter`, `Segoe UI`, `Arial`, sans-serif |
| code, metric and label | `JetBrains Mono`, `Cascadia Code`, `Consolas`, monospace |
| interface label | upper case, wide `letter-spacing`, monospace |

No published asset carries a webfont: the stack is system-only, and the self-contained material
makes no external request.

## Assets

| File | Use |
|---|---|
| `assets/hpp-logo.png` | **the official lockup** — chrome on black, with the core in orange. It is the approved artwork; do not redraw, recolour or crop |
| `assets/hpp-icon-512.png` · `-256` · `-128` · `-64` · `-32` | the badge alone, square — avatar, favicon and app icon. Derived from the lockup by cropping, never redrawn |
| `assets/hpp-logo-header.png` | the same lockup at 1440 px, for page headers. It is the approved artwork **resized** — not redrawn, not recoloured, not cropped — so a header and the README show one brand |
| `assets/hpp-mark.svg` | the symbol as vector, for where raster does not serve (print, large scale). Drawn after the approved badge, so it reads as the same mark; where fidelity decides, use the raster lockup |

⚰️ LEGADO 2026-09-23 · `assets/hpp-logo-light.svg` · `assets/hpp-logo-dark.svg` ·
`assets/hpp-banner-light.svg` · `assets/hpp-banner-dark.svg` — substituídos por
`assets/hpp-logo-header.png` (lockup) e `assets/hpp-mark.svg` (símbolo) · decidido em 2026-09-23,
ao medir que os quatro carregam um desenho **anterior** ao lockup aprovado (nasceram em 20/09; a
arte oficial, em 21/09) — flat em creme e laranja, não o cromado sobre preto. Esta tabela os
descrevia como "o mesmo lockup em vetor", e não eram: as quatro páginas HTML abriam com uma marca
que este documento veta na linha de cima. Os arquivos ficam no repositório como registro; usá-los
publica a marca errada.

The symbol does **not** encode the number of modules: the harness can grow without redrawing the
brand.

In the CLI, the lockup is rebuilt in terminal blocks (`█ ▓ ░`) in the same palette, with declared
degradation: truecolor → 256 colours → 16 colours → no colour at all when there is no TTY or when
`NO_COLOR` is set.

## Message architecture

1. **Harness** — the product.
2. **Protocol** — the executable rules.
3. **Modules** — the installable capabilities.
4. **Distribution** — the channels per host.

Do not open a page with the number of modules. Do not call distribution the product. Do not use
"autonomous", "deterministic", "learns" or "cross-host" without bounding mechanism and scope.

## Accessibility

- minimum WCAG AA contrast;
- visible focus in `#FF6A00` on `#0F1113`, and `#0F1113` on `#F4F1EB`;
- support for 320, 375, 768 and 1280 px;
- `prefers-reduced-motion` turns off all animation, and the information stays complete.

## Do not use

- gradient as subject — the gradient exists in the lockup and is not repeated in the interface;
- colour without a label;
- robot, brain or humanoid illustration;
- franchise, character or film metaphor;
- number of modules as a headline;
- emoji in CLI output.
