[English](CHANGELOG.md) · [Português](CHANGELOG.pt-BR.md)

# Changelog

All relevant changes to the harness are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[SemVer](https://semver.org/). The product version describes the harness contract; each module
keeps its own version in `plugin.json` and in `marketplace.json`.

## [Unreleased]

## [2.4.1] — 2026-09-21

### Added

- **The remaining human-facing documents got their Portuguese pair.** `CONTRIBUTING`, `SECURITY`
  and `docs/UX-INSTALL-JOURNEY` ship as `.pt-BR.md` siblings, and the operating manual as
  `docs/MANUAL.pt-BR.html`, all under the same pair gate.
- **The catalogue is generated in both languages and in the brand palette.** One pass of the
  generator writes `docs/CATALOGO.md`, `CATALOGO.pt-BR.md`, `CATALOGO.html` and
  `CATALOGO.pt-BR.html` from `marketplace.json` (which now carries `description_en` per module);
  the hand-written HTML page, Portuguese-only and in the retired palette, was replaced by the
  generated one so it cannot drift again.

### Changed

- **The operating manual was rewritten against measured behaviour.** Policy verdicts
  (`ALLOW / MANUAL / BLOCK` and what each mode exits with), the nine map projections, the monitor
  states including `skew`, the six stages of `hpp init` with the readiness it reports on an empty
  target, Codex CLI paths, attestation and exit codes are the ones the CLI produces today.
- **The public address of the author is `https://rusharlabs.com`** in the license, citation,
  notice, marketplace and every module manifest; the security contact e-mail is unchanged.
- **The Quickstart installs the CLI with `pip`** and keeps the checkout as the developer path.
  Packaging leftovers (`build/`, `*.egg-info/`) are ignored by the repository.

### Fixed

- **The pip-installed package shipped without its manifest.** `pip install` produced a
  `site-packages/hpp/` with no `hpp.manifest.json`, so from any directory outside a checkout
  `hpp doctor` and `hpp init` exited 2 with "hpp.manifest.json not found". The wheel now carries
  the manifest as package data, and the resolver falls back to it after the working directory and
  the source root — a checkout still wins, and site-packages is never treated as an emitted
  distribution. Guarded by tests that build a real wheel and drive it from an empty directory.

## [2.4.0] — 2026-09-21

### Added

- **Bilingual documentation.** Every document a person reads before deciding to use the project
  now exists in English and Portuguese, paired as `NAME.md` and `NAME.pt-BR.md` with reciprocal
  links at the top. Files an agent reads to execute — skills, commands and rules — stay in one
  language on purpose: translating them doubles the maintenance and invites silent divergence.
- **A gate that keeps the pair honest.** `test_documentacao_bilingue` rejects a missing
  counterpart, a broken top link, structural divergence (the two sides must carry the same
  headings, in the same order — translation changes words, not structure), differing code blocks
  (a command is a command in any language), and any attempt to translate a file from the agent
  layer. Nine controls prove the gate can reject.

### Fixed

Five defects from an external audit, each reproduced before the fix:

- **The failure memory could never fire.** It listened only for the success event, while a tool
  failure arrives on a separate one. Measured with a real payload: nothing was ever written. It
  now listens to both and deduplicates by tool call.
- **The skill generator could write outside its target.** A module name containing a traversal
  escaped the destination; a directory link caused a file from outside the tree to be copied
  without being reported; two module names differing only in separator collapsed into one, in
  silence.
- **A smoke test that ran out of time was recorded as success** and did not count as a failure.
- **An unreadable cache and an absent one were indistinguishable** in the service probe.
- **Twelve commands promised a directory tree that ships with zero files.** The capability was
  not invented: the external dependency is now declared, along with what still works without it.

- The published Python floor is now the lowest version the CI matrix actually exercises. The code
  carries no syntax exclusive to it, so the previous claim was plausible — and unverified.

## [2.3.0] — 2026-09-21

### Added

- **`hpp init` — installation became an experience.** A wizard that fulfils the six stages of the
  installation contract (`detect → prereqs → profile → configure → wire-suggest → smoke`), with
  an opening sequence where **each line appears when the corresponding stage has actually
  finished** — the movement is the progress, not decoration. It closes with the brand lockup in
  terminal blocks and the installation signature.
- **Readiness measured, not estimated.** A bar and a count (`7/11 verified`) derived from what was
  in fact verified — host, distribution integrity, checksum per module, policy classifier,
  benchmark gate. Each item shows the command that produced it, and what was not measured appears
  as **not verified**, never as zero and never as one hundred.
- **Declared degradation of colour and motion:** truecolor → 256 colours → 16 colours → none,
  with `NO_COLOR` and `--no-animation` honoured, glyph fallback when the terminal does not encode
  blocks, and full output without a TTY. `--non-interactive`, `--yes`, `--profile` and
  `--modules` for CI and agents: no prompt is reached in that mode.
- Without `--apply`, the wizard **prints the plan and writes nothing** — proven by hashing the
  tree before and after. `wire-suggest` shows the block to paste and never touches `settings`.

### Changed

- **Visual identity unified on the approved brand.** The previous material used a palette that
  predated the lockup and had no relation to it. There are now four colours and a single accent —
  black, charcoal, warm white and signal orange — measured on the lockup itself. The README opens
  with the official artwork, and `docs/BRAND.md` describes the system, including how the brand
  behaves in the terminal.

### Fixed

- The suite carried an **absolute path with a user name**, which tied it to a single machine and
  made that path travel in the published package. The root is now derived from the file's
  location, with `HPP_EMITTED_COPY` to point at another tree.

## [2.2.0] — 2026-09-21

### Added

- The harness's own test suite (`tests/`, 106 cases, stdlib-only, no network): CLI contract
  derived from the manifest, version coherence across manifest/package/module, destructive
  command classification, append-only event log and resumption, WorkGraph cycle and waves,
  context budget, and `CHECKSUMS.txt` verification. Each file carries at least one control that
  proves the test knows how to fail.
- Continuous integration across 12 combinations (Linux, macOS and Windows × Python 3.10–3.13),
  running the suite, `hpp doctor` and `hpp benchmark -k 3` — the product's own controls, through
  the real CLI. Minimal read permissions and no step masked by `continue-on-error`.
- `skew` state in the Monitor Map, with a declared and published tolerance (`--skew-tolerance`).

### Fixed

Seven defects reproduced before the fix, each with a test that fails before and passes after:

- **Command policy ignored flag order.** `rm -rf` was blocked, but `rm -fr`, `rm -r -f`,
  `rm --recursive --force` and the `sudo` form passed as allowed. Classification now reads the
  option set of each invocation, stops at `--` and splits on `| ; &` — without turning
  `rm arquivo.txt`, `grep -rf padroes.txt` or `cp -rf a b` into a block.
- **Context budget did not charge the separator between blocks**, so the published number was
  smaller than the delivered text and the ceiling could be exceeded. `used` is now the real size.
- **A monitor signal with a timestamp in the future was reported as healthy** — a fast clock or a
  fabricated timestamp became freshness.
- **Failure memory persisted secrets in clear text** and returned them in the report. Every entry
  now goes through redaction by shape (private key, credential in URL, `Bearer`/`Basic`, provider
  prefixes, JWT, `key=value`, high-entropy blob), recording type and length — never the value. An
  error without a secret stays readable.
- **Writing `settings.json` was not atomic** in the three installers that do it: a crash midway
  truncated the file and a concurrent update was lost silently. It is now a temporary file in the
  same directory, `fsync` and `os.replace`, with a byte-by-byte comparison before swapping —
  divergence refuses the write (exit `2`) instead of overwriting.
- **The secret scanner suppressed the whole line** when it contained an allowed example: a real
  value on the same line got through. Suppression now applies to the occurrence, not the line.
- **`CHECKSUMS.txt` verification accepted an empty inventory as success** and a path escaping the
  module (`../fora.txt`, absolute path). All three forms now fail with exit `2`.

## [2.1.0] — 2026-09-20

### Added

- Provider-neutral attestation that binds an approval to spec, repository identity, base commit,
  full snapshot, maker, checker and review identifier.
- `hpp attest create` and `hpp attest verify`, blocking when tracked, staged, removed or untracked
  content diverges after inspection.
- Executable control in the benchmark to prove a valid approval and its invalidation after
  mutation.

### Fixed

- Clone, marketplace and release URLs point to the canonical `rushar-labs` account.

## [2.0.0] — 2026-09-20

### Added

- Local-first, stdlib-only core in `python -m hpp`, with root manifest, doctor, planned
  installation, append-only state, resumption, evaluation and benchmark.
- Spec-driven WorkGraph with cycle rejection, acceptance criteria and topological waves.
- Capability, Agent, Lane, Code, Evidence, Monitor and operational graph as deterministic
  projections, with no daemon or graph database.
- Context compiler with budget, provenance and hash; refusal of secret-like material.
- Provider-neutral routing by `economy`, `balanced` and `frontier` tiers, with a risk floor and
  explicit fallback upward only.
- Monitor Map with target, cadence, freshness, severity, cost and consumer gate; no monitor is
  started covertly.
- Reproducible benchmark with declared controls and a standalone `pass@k` and `pass^k` runner.
- Signal Path visual identity applied to the README, manual, catalogue and SVG assets.

### Changed

- Positioning now leads with harness → protocol → modules → distribution.
- `operator-kit` 1.4.0 can block trusted families in `enforce` mode and keeps `audit` explicit
  for advisory rules.
- The documentation distinguishes service health, signal freshness and result correctness.
- Claude Code and Codex CLI share the same contract; host differences remain visible.

### Fixed

- `passk_eval.py` no longer depends on an external package or a degraded mode.
- The release does not publish two live versions of the same module.

## [1.5.0] — 2026-09-20

### Added

- Proven support for **Codex CLI**: `AGENTS.md` at the root and in the ten kits, installation by
  copy into `.agents/hpp/` and namespaced generation of the 33 skills into `.agents/skills/`.
- **14 subagents** with explicit `tools`: 12 development roles, one refuter and one silent-failure
  hunter; the three checkers are read-only.
- **Cross-provider checker** router that detects Codex, Cursor and Gemini without executing tools
  or changing permissions.
- `preflight.py` to validate Python, PyYAML, Git repository and writable settings before the done
  gate, plus `docs/MCP-RUNBOOK.md` and 24 patterns in `docs/TIPS.md`.
- Registry of candidate external skills with explicit origin, licence, blob and decision.

### Changed

- Publication now rejects skills outside the contract and covers review noise, house names and
  discarded brand narrative.
- The catalogue now inventories subagents, documents, registries and cross-cutting resources.
- The visual identity and the general description use the original metaphor of components under
  the same roof, with no reference to characters or external franchises.

### Fixed

- The Codex generator preserves LF or CRLF in the frontmatter and does not activate Claude Code
  hooks.
- Scripts that produced internal metadata now use impersonal rationale and public terms.

## [1.4.0] — 2026-09-20

First public version. Ten kits, a single exit contract (`0` ok · `1` warn · `2` block ·
`3` error), `CHECKSUMS.txt` per kit and `SANITIZACAO.md` declaring what was removed before
publishing.

### Added

| kit | version | what it delivers |
|---|---|---|
| operator-kit | 1.3.0 | three-state `done_gate`, `/ralph-gate`, debt ledger and 13 installable rules |
| kit-forge | 1.4.0 | assembler, IP/PII lint, six-stage installation and verified zip |
| lane-kit | 1.2.0 | session coordination, maker ≠ checker and per-directory lock |
| continuity-kit | 1.2.1 | handoff, re-derivation and verification before resuming |
| claude-dev-kit | 1.3.1 | creation of skills, hooks and plugins with reversible wiring |
| health-kit | 1.3.1 | config-driven probe and cache-first statusline |
| dev-squad-kit | 1.0.0 | 12 roles and parallel consolidation |
| agent-framework-wizard | 1.1.1 | six-step wizard for an agent or skill |
| supabase-pack | 1.1.0 | RLS audit and Edge Function scaffold |
| gotcha-memory | 1.0.0 | recurring failure turned into an operational lesson |

### Portability

- Hooks resolve `.venv`, `python3` or `python` through `hooks/pyrun.sh`.
- Kits are emitted in LF and carry checksums of the distributed bytes.

[1.4.0]: https://github.com/rushar-labs/house-party-protocol/releases/tag/v1.4.0
[1.5.0]: https://github.com/rushar-labs/house-party-protocol/releases/tag/v1.5.0
[2.0.0]: https://github.com/rushar-labs/house-party-protocol/releases/tag/v2.0.0
[2.1.0]: https://github.com/rushar-labs/house-party-protocol/releases/tag/v2.1.0
[2.2.0]: https://github.com/rushar-labs/house-party-protocol/releases/tag/v2.2.0
[2.3.0]: https://github.com/rushar-labs/house-party-protocol/releases/tag/v2.3.0
[2.4.0]: https://github.com/rushar-labs/house-party-protocol/releases/tag/v2.4.0
