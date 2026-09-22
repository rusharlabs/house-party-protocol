[English](CHANGELOG.md) · [Português](CHANGELOG.pt-BR.md)

# Changelog

All relevant changes to the harness are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[SemVer](https://semver.org/). The product version describes the harness contract; each module
keeps its own version in `plugin.json` and in `marketplace.json`.

## [Unreleased]

## [2.4.2] — 2026-09-21

### Added

- **The three root contracts ship in both languages.** `INSTALL-CONTRACT`, `SKILL-CONTRACT` and
  `INSTALL-GUIDE-TEMPLATE` gain an English `.md` (the source of truth) with the Portuguese text
  as `.pt-BR.md`; the emission copies both sides and the pair gate now covers them. Rule numbers,
  field names, exit codes, paths and code blocks are identical on both sides.
- **The wheel ships the benchmark suite.** `examples/reliable-coding` travels inside the package
  as a byte-identical copy (`hpp/examples/`, guarded by `tests/test_installed_package.py`), so
  `hpp benchmark` and `hpp --self-test` run from a pip install, and `hpp init` from that install
  measures the benchmark instead of reporting the suite as unshipped (readiness `7/11` there,
  `9/11` from a clone of the repository).
- **`docs/UX-INSTALL-JOURNEY` opens with the `hpp init` journey** — six stages, plan then
  `--apply`, readiness per channel, flags and exit codes, each with measured output — and keeps
  the module-installer journey as the second path.
- **Package metadata.** `pyproject.toml` declares readme, licence (SPDX expression), authors,
  keywords, classifiers and project URLs; `pip show -v house-party-protocol` reports them.
- **`CITATION.cff` is tied to the package** by `tests/test_citation.py`: its version equals
  `hpp.__version__`, its abstract equals the README's opening paragraph, its keywords name both hosts.

### Changed

- **The README, the manual, `ARCHITECTURE` and `CONCEPTS` describe the repository as what it
  is: the emitted distribution** — modules, `CHECKSUMS.txt`, `marketplace.json` and the installer
  beside the harness. The quoted `hpp init` output is the real one per channel (`9/11 verified`
  from a clone, `7/11` from a pip install, both measured on 2026-09-21), the installer is named
  where it lives, and `hpp doctor` is quoted as it prints
  (`HPP doctor: ok · modules=10 · hosts=claude-code, codex`; the distribution cross-check appears
  only in `--json`).
- **Brand vectors use only the four palette tokens.** `assets/*.svg` no longer carry `#E5484D`,
  `#FF8A3D`, `#A8ADB5` or `#6B7280`; lighter steps are `#FF6A00`, `#F4F1EB` or `#0F1113` at
  reduced opacity. The approved raster lockup and the icon PNGs are untouched.
- **The CI comment matches the tree it runs in.** The `CHECKSUMS.txt` step says it is a real gate
  in the published repository and a no-op only in the harness source tree.
- **`CONTRIBUTING` describes a flow a third party can actually run.** The module sources and the
  forge manifests are not published, so the flow is: edit inside the emitted module, prove with
  `kit_doctor.py verify` (checksum drift on your files is the expected signal), `skill_lint`,
  `hpp doctor`, `hpp benchmark` and `pytest`, and open the pull request; maintainers fold the
  change into the source, bump the version and re-emit. The DCO sign-off requirement is gone:
  opening a pull request is the agreement that the contribution is MIT-licensed. The bilingual
  rule now says what a contributor does in practice (agent layer in English, human docs in pairs).
- **`SECURITY` treats the e-mail channel as equal** to GitHub private vulnerability reporting,
  and says what to do when the private-report button is not there.
- **The agent layer is English.** Every file an agent reads to execute — 33 skills, 14 commands,
  14 agents, 13 rules, output styles — was translated from Portuguese with structure invariants
  checked (headings per level, code fences, frontmatter keys, links, table rows). `skill_lint`
  now treats the English schema tokens (`## Contract`, `## Proof`, `## When NOT to Activate`,
  `Priority:`, `INPUT/OUTPUT/STATE IT TOUCHES`, `<!-- executed: … -->`) as canonical and still
  accepts the Portuguese ones as legacy; `SKILL-CONTRACT.md` documents both.
- **Module `description` is English** in `marketplace.json` and in the ten `plugin.json` (the field
  the plugin UI shows); the Portuguese text moved to `description_pt`, which the catalogue uses.
- **The ten module READMEs were re-measured against the emitted tree**: copy-install commands
  point to the current module directory, the installer path is `instaladores/kit-forge-1.4.0/`,
  quoted outputs (`skill_lint`, `--interview`, `--self-test`, the health-kit probe) were re-run
  today, counts match `ls`, and the English side no longer carries Portuguese sections.
- **Each emitted module carries `SANITIZATION.md` + `SANITIZATION.pt-BR.md`** (generated) instead
  of a Portuguese-only `SANITIZACAO.md`.
- **The catalogue opens with the product lockup and the five words**, like the manual.

### Fixed

- **`hpp benchmark` and `hpp --self-test` from a pip install exited 3 with
  `internal error: FileNotFoundError`**, because the suite was resolved one level above the
  package and the wheel carried no `examples/`. The suite is now resolved from the package, and a
  missing suite path (`hpp eval run <missing>` included) is a one-line refusal with exit 2.
- **`hpp doctor` — and the one-line `status` and `benchmark` reports — on a cp1252 stream** wrote
  the middle dot as byte `0xB7`, which read as `�` downstream; they now go through the same console
  as `hpp init` and degrade to ASCII (`-`).
- **`.gitignore` covers `.hpp/`**, the directory the README's own `hpp event append` and
  `hpp init --apply` examples create inside a checkout.
- **`CITATION.cff` described version 1.4.0**, with a "ten kits for Claude Code" abstract and no
  Codex keyword; it now describes 2.4.1, dated 2026-09-21, with the README's opening paragraph and
  `codex-cli` among the keywords.
- **The manual's measurement stamp said 2.4.0** while its header said 2.4.1; it now stamps the
  date and the version the quoted outputs were measured against.
- **`continuity-kit` and `lane-kit` installed as plugins armed no hook.** Both ship hooks but
  their `plugin.json` had no `hooks` key and no `hooks/hooks.json`; both now declare their hooks
  (SessionStart/Stop/PreCompact; SessionStart/PreToolUse/PostToolUse) through the same `pyrun.sh`
  shim as the other modules.
- **`kit_doctor.py verify` reported `warn` after a module's own smoke tests** because it counted
  `__pycache__` and `.pyc` as extras. Bytecode and pytest caches are no longer extras; a stray
  real file still is.
- **The profile stage wrote a file the module never reads** (`profile.yaml` for modules whose
  loader reads `operator-profile.yaml`) and copied nothing for `lane-kit` (its example lives in
  `templates/`). The stage now derives the target name from the module's loader and looks in
  `templates/` too.
- **`skill_lint --run-proofs` on Windows created a stray `self-test` file**: a proof line's
  trailing `# -> …` comment was fed to `cmd.exe` and its `>` became a redirect, and
  `${CLAUDE_PLUGIN_ROOT}` was not expanded. Trailing comments are stripped and the variable is
  expanded to the module root before running.
- **`kit-forge`'s own install manifest said `plugin: false` for Claude Code** while it ships a
  `plugin.json` and is listed in the marketplace.

### Known limitation

- **Runtime messages are still Portuguese.** The Markdown an agent reads is English, but the
  hooks and scripts it runs print their messages in Portuguese (59 of 81 scripts, measured:
  `grep -rlE 'ção|não |você|é ' --include=*.py --include=*.sh`), and the skills quote those
  outputs verbatim. Translating them is a behaviour change with a test per script and is the next
  release; until then a non-Portuguese reader sees English instructions and Portuguese logs.

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
