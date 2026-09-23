[English](DESIGN.md) · [Português](DESIGN.pt-BR.md)

# DESIGN.md — how to build an interface for this project

[`BRAND.md`](BRAND.md) says what the brand **is**: four colours, one accent, the five words, what
not to use. This file says how to **build** with it — the tokens as they exist in code, the
components that already ship, and what a pull request that adds an interface has to satisfy.

Read `BRAND.md` first. Where the two disagree, `BRAND.md` wins and this file is the bug.

## The stylesheet is a file, and it is the only one

```
docs/hpp.css
```

It is **emitted**, not written by hand: `tools/catalog_md.py` holds one constant and produces
both this file and the `<style>` block inlined in every page. That is why they cannot drift, and
`tests/test_design_system.py` fails if they ever do.

Two ways to use it, and both are correct:

```html
<!-- a page inside this repository -->
<link rel="stylesheet" href="hpp.css">

<!-- a page that must survive on its own: paste the file's contents -->
<style>/* contents of docs/hpp.css */</style>
```

⚠️ **Never link it from a URL.** Every published page here is self-contained by rule — a page
that fetches its stylesheet from someone else's domain stops working the day that domain does,
and the test suite refuses any `@import`, any `https://` in `url()`, and any `@font-face`.

## Tokens

Four come from the brand and are the only colours in the system. Four are derived and exist so
that nobody invents a fifth.

| token | value | what it is for |
|---|---|---|
| `--hpp-black` | `#000000` | background of brand material and of the lockup |
| `--hpp-ink` | `#0F1113` | interface background, elevated surface |
| `--hpp-paper` | `#F4F1EB` | primary text on dark |
| `--hpp-signal` | `#FF6A00` | the single accent |
| `--line` | `rgba(15,17,19,.18)` | rules and borders — the ink at 18% |
| `--surface` | `rgba(15,17,19,.04)` | a raised block — the ink at 4% |
| `--muted` | `rgba(15,17,19,.72)` | secondary text — the ink at 72% |
| `--max` | `1120px` | the measure of `.wrap` |

**The derived tokens are the ink at reduced alpha, never a new colour.** `BRAND.md` states it:
*a lighter step is the same token at reduced opacity*. A test reads every `rgb()` in the
stylesheet and fails on any triple that is not `15,17,19`, because a fifth colour arriving
through an `rgba()` is invisible to a hex scan.

## The components that already exist

Use these before inventing. Each one is in `docs/hpp.css` and is already rendered by the five
published pages, so anything you build with them looks like the rest of the project for free.

| selector | what it is |
|---|---|
| `.wrap` | the container. Everything sits inside it, at `--max` |
| `.lang` · `.lang a[aria-current]` | the language switcher. The current side carries `aria-current`, the other is a link |
| `.hero` | the page opening: lockup, `.eyebrow`, `h1`, one paragraph |
| `.eyebrow` | the small monospace label above the title — upper case, wide tracking |
| `.lead` | the first paragraph of a section, one step larger |
| `section` · `h2` · `h2 .version` · `h3` | the body. `h2 .version` prints a version next to a heading |
| `table` · `th` · `td` | data. `td.n` / `th.n` right-align a number; `tr.total` marks the totals row |
| `.chips code` | a list of short names as inline chips |
| `footer` · `footer .five` | the close. `.five` carries the five words |
| `a:focus-visible` | the focus ring. Never remove it |

## The rules that are not negotiable

1. **One accent.** The orange marks the point of attention. A screen with two points of
   attention has none — so if something new needs the orange, something else loses it.
2. **Colour never carries meaning alone.** A label or an icon always goes with it. Someone who
   cannot distinguish the orange must still be able to read the state.
3. **No webfont, no external request.** The type stack is system-only (`Sora`, `Inter`,
   `Segoe UI` for headings; `JetBrains Mono`, `Cascadia Code`, `Consolas` for code and labels).
4. **No red in the palette, on purpose.** For state, use the terminal's own red and never paint
   a background: a light terminal has to stay readable.
5. **Declare the language.** `<html lang>`, and `lang` on any block in the other language. A
   screen reader that reads Portuguese with English phonemes is a page that excluded someone.
6. **The focus ring stays.** Keyboard is not a fallback.
7. **Every root document is a bilingual pair.** `X.md` and `X.pt-BR.md`, linked to each other at
   the top. A test enforces it.

## What a pull request that adds an interface has to satisfy

```
[ ] uses docs/hpp.css — linked inside the repo, or inlined. Never a URL
[ ] adds no fifth colour, in hex or in rgb()
[ ] fetches nothing: no @import, no @font-face, no https:// in url()
[ ] reuses the components above before adding a selector
[ ] declares lang, and keeps the focus ring
[ ] ships the .pt-BR pair if it is a root document
[ ] is generated, if it belongs next to generated pages -- see the next section
```

Then: `python -m pytest tests/test_design_system.py tests/test_docs_index.py -q`.

## If it belongs in `docs/`, generate it

The five pages in `docs/` are **emitted artefacts**. Editing them by hand works until the next
`catalog_md.py --write`, which overwrites the edit without warning. If you want a page to live
there, add it to `render_all()` in `tools/catalog_md.py` and to `OWN_FILES`, as `index.html` and
`hpp.css` already are — then it is generated, it is listed once, and it cannot rot.

A page that belongs anywhere else (a template, an example, a report) is yours to write by hand.
`multi-session/lane-kit-*/templates/status-stakeholder.template.html` is the reference for that
case: same tokens, written by hand, and it reads the board without ever writing to it.

## Where the artwork lives

`BRAND.md` has the whole table. The two you will reach for:

- `assets/hpp-logo-header.png` — the lockup for a page header, 1440 px. It is the approved
  artwork resized; **do not redraw, recolour or crop it.**
- `assets/hpp-mark.svg` — the symbol as vector, for print or large scale. Where fidelity
  decides, use the raster lockup.
