# Changelog

Todas as mudanças relevantes deste marketplace são registradas aqui. O formato segue
[Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e as versões seguem
[SemVer](https://semver.org/lang/pt-BR/). Cada kit tem a própria versão, declarada no seu
`plugin.json` e espelhada no `marketplace.json`; a versão do marketplace acompanha a do
`kit-forge`, que é a fábrica de todos os outros.

## [1.4.0] — 2026-09-20

Primeira versão pública. Dez kits, um contrato de saída único (`0` ok · `1` warn · `2` block ·
`3` erro), `CHECKSUMS.txt` por kit e `SANITIZACAO.md` declarando o que foi retirado antes de
publicar.

### Adicionado

| kit | versão | o que entrega |
|---|---|---|
| operator-kit | 1.3.0 | camada portátil de operação: `done_gate` de três estados, `/ralph-gate`, ledger de dívida, 13 regras instaláveis, `claude-md-from-profile` |
| kit-forge | 1.4.0 | a fábrica: `kit_assembler` (zip verificado, sanitize por modo `word`/`literal`/`regex`, LF determinístico), `ip_pii_linter`, `kit_doctor` de 6 estágios |
| lane-kit | 1.2.0 | N sessões sem colisão: board de estados, maker ≠ checker, lock por diretório |
| continuity-kit | 1.2.1 | handoff que sobrevive a `/clear` e crash, com re-derivação e verificação-primeiro |
| claude-dev-kit | 1.3.1 | `skill-writer`, `hookify`, `plugin-dev`, `teaching`; wiring idempotente com `--undo` |
| health-kit | 1.3.1 | sonda config-driven e segmento de statusline cache-first |
| dev-squad-kit | 1.0.0 | 12 agentes de papel e 3 skills de consolidação paralela |
| agent-framework-wizard | 1.1.1 | wizard de 6 passos para agente ou skill novo |
| supabase-pack | 1.1.0 | auditoria de RLS via `pg_policies` + advisors; scaffold de Edge Function |
| gotcha-memory | 1.0.0 | postflight classifica falhas por família; recorrência vira lição injetada no preflight |

Três decisões de desenho desta versão que valem ser lidas:

- **`done_gate` tem três estados.** `DONE` · `PARCIAL-DECLARADO` · `NOT-DONE`. Um gate
  binário empurra o agente para um de dois erros — pintar de verde o que não terminou, ou
  travar sem dizer o que falta. O estado parcial é declarado por quem executou, legível por
  máquina, e **vence o verde**: critérios todos passando mais uma declaração continuam sendo
  parcial. O exit é `1` nos dois estados não-verdes.
- **O assembler prova o zip que emite.** `verify_zip()` reabre o artefato e confere CRC,
  fidelidade byte a byte contra o disco, ausência de caminho que escape da extração e
  higiene (nada de `.bak`, `.env` ou ruleset real). Zip reprovado é parado como `.INVALIDO`,
  nunca apagado.
- **`gotcha-memory` classifica com fronteira de palavra** e conhece duas famílias que não
  existem em tabela genérica: `instrument` (o comando respondeu e o número não mede o que
  parece — a estratégia é re-medir, nunca repetir) e `lock` (outro processo segura o recurso).

### Portabilidade

- Todo hook roda via `hooks/pyrun.sh`: `.venv` do projeto → `python3`/`python` conforme o
  SO → nunca o stub da Microsoft Store. macOS, Linux e Windows (Git Bash) sem alias.
- Os kits são emitidos em LF independentemente do SO de quem emite; o `CHECKSUMS.txt`
  descreve os mesmos bytes em qualquer clone.

### Autoria e licença

- MIT. Copyright © 2026 Max Parisi (Rushar Labs) — `LICENSE` na raiz e em cada kit.
- `NOTICE`, `CITATION.cff`, `SECURITY.md` e `CONTRIBUTING.md` (DCO).

[1.4.0]: https://github.com/rushar-labs/house-party-protocol/releases/tag/v1.4.0
