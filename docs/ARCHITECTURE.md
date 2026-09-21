[English](ARCHITECTURE.md) · [Português](ARCHITECTURE.pt-BR.md)

# Architecture

How the pieces of House Party Protocol fit together, where state lives, and what deliberately
does not exist.

## Four layers

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ HARNESS       python -m hpp                                              │
│               doctor · init · event · status · resume · attest · policy  │
│               work · route · context · map · graph · eval · benchmark    │
├──────────────────────────────────────────────────────────────────────────┤
│ PROTOCOL      hpp.manifest.json                                          │
│               roles · loop transitions and gates · exit codes            │
│               host coverage · monitors · bundles · invariants            │
├──────────────────────────────────────────────────────────────────────────┤
│ MODULES       ten versioned directories, each installable on its own     │
│               skills · hooks · commands · agents · rules · scripts       │
├──────────────────────────────────────────────────────────────────────────┤
│ DISTRIBUTION  Claude Code: marketplace.json + plugin per module          │
│               Codex CLI:   verified copy into .agents/ by the installer  │
└──────────────────────────────────────────────────────────────────────────┘
```

The harness is stdlib-only and executes no model. It reads files, runs the commands you name,
and writes to a small number of declared paths.

## The `hpp/` package

| file | responsibility | surface |
|---|---|---|
| `cli.py` | argument parsing, dispatch, the exit contract (`2` for a refused input, `3` for an internal error) | every subcommand, `--self-test` |
| `manifest.py` | locate, load and validate the manifest; cross-check `marketplace.json` and each module's `plugin.json` when present | `doctor` |
| `state.py` | append-only event log; projection of events onto the loop; refusal of invalid transitions before the write | `event append`, `status`, `resume` |
| `workgraph.py` | validate a spec, reject cycles with the path named, order units into waves | `work plan`, `work waves` |
| `policy.py` | classify a command as `ALLOW`, `MANUAL` or `BLOCK`; map to exit code by mode | `policy check` |
| `attest.py` | bind a verdict to repo identity, base commit, spec hash and a full file snapshot; verify later | `attest create`, `attest verify` |
| `context.py` | fit whole blocks under a character budget with provenance hashes; refuse secret-like input | `context compile`, `map context` |
| `routing.py` | choose a tier and a provider id from declared risk, complexity, context size and stage; fall back only upward | `route` |
| `maps.py` | Lane Map, Agent Map, Context Map and Monitor Map as sorted, data-only projections | `map lane`, `map agent`, `map context`, `map monitor` |
| `graph.py` | capability, operational, agent, evidence and code views from the manifest; JSON or Mermaid | `graph` |
| `evals.py` | `pass@k` / `pass^k` runner over a suite of cases with three runner kinds | `eval run`, `benchmark` |
| `controls.py` | the ten executable controls the benchmark runs, each with a positive and a negative case | `benchmark`, `--self-test` |
| `install.py` | plan-only installation receipt for a bundle on a host; refuses unsupported coverage | `install` |
| `wizard.py` | `hpp init`: six stages, readiness, plan versus apply, wire block | `init` |
| `term.py` | colour tier detection, ANSI output, ASCII glyph fallback, no-TTY behaviour | used by `init` |
| `brand.py` | palette, block wordmark and closing lines for the terminal | used by `init` |

Sizes are small by design; the whole package is readable in one sitting. Nothing imports outside
the standard library.

## The flow

```text
  spec (JSON)
     │  hpp work plan
     ▼
  WorkGraph ──── waves ───▶ wave 1 ──▶ wave 2 ──▶ ... (barrier between waves)
     │                        │
     │  hpp route             │  per unit: tier → provider id (never a model call)
     │                        ▼
     │                     lane claim ◀── hpp map lane (liveness from heartbeat)
     │                        │
     │                        ▼
     │                     work_started ─▶ evidence_recorded ─▶ check_passed
     │                        │                 ▲                    │
     │                        │      hpp context compile             │
     │                        │      (what the maker saw, hashed)    ▼
     │                        │                              hpp attest create
     │                        │                              (verdict bound to bytes)
     ▼                        ▼                                      │
  hpp map monitor        .hpp/events.jsonl  ◀── human_approved ◀─────┘
  (up · fresh · skew)         │
                              ▼
                          verified  ── hpp status / hpp resume derive the next step
```

Every arrow that changes state is an appended event. Every box that decides something reads
files and writes at most one declared file.

## Where state lives

| path | written by | content | lifetime |
|---|---|---|---|
| `.hpp/events.jsonl` | `hpp event append` | one JSON object per line: `seq`, `id`, `type`, `data`; append-only | the workspace's loop history |
| `.hpp/profile.json` | `hpp init --apply` | host, bundle, modules, policy mode, protocol and product version | until the operator removes it |
| `.hpp/attestation.json` | `hpp attest create --output` | the bound verdict; the path is yours to choose | until the bytes it describes change |
| `hpp.manifest.json` | the project | the protocol; found by walking up from the current directory, then the package root | versioned with the product |
| module `CHECKSUMS.txt` | the forge | sha256 per distributed file | versioned with each emitted module |

Everything else the harness consumes is an input you pass on the command line: specs, lanes,
monitors, providers, routing requests, context blocks, evaluation suites. There is no hidden
cache, no user-level state directory and no environment variable that changes a verdict; the
only environment the harness reads is `NO_COLOR`, `FORCE_COLOR`, `TERM`, `COLORTERM`, `CI` and the
Windows terminal session flag, and those affect rendering only.

The event log is the recovery boundary. Reading it validates that `seq` is contiguous and that
`id` equals `event:<seq>`; a corrupt line stops the projection with the line number instead of
skipping it. Appending validates the transition against the manifest before opening the file, so
a refused event leaves no trace and cannot create the log.

## The manifest as executable contract

`hpp.manifest.json` declares the protocol version, the hosts, the modules with their paths,
versions, capabilities, relations and per-host coverage, the bundles, the roles, the exit codes,
the routing tiers and rule, the map names, the installer path, the monitors and the loop.

`hpp doctor` rejects a manifest that violates any of: unique hosts, modules, capabilities, paths
and monitor ids; relative module paths; coverage values outside `native` / `explicit-command` /
`unsupported`; unknown relations; cycles in `requires`; bundles naming unknown modules or
capabilities; exit codes other than `0/1/2/3`; routing tiers other than
`economy/balanced/frontier`; monitors with non-positive cadence or freshness.

When `marketplace.json` sits beside the manifest, the doctor also checks that the product version
matches, that the module set matches, that each module's `source` and `version` match, that the
module directory exists inside the product root, and that its `.claude-plugin/plugin.json` agrees
on name and version. In a source checkout without a marketplace the doctor says so
(`distribution: source-contract`) instead of reporting a check it could not run.

## Maps

Maps have no state of their own. Each is a projection of one or two inputs, sorted so that the
same input yields the same output byte for byte.

| map | input | question it answers |
|---|---|---|
| capability | manifest | which module provides which capability, on which host, in which bundle |
| operational | manifest `loop` | which event moves which state through which gate |
| agent | manifest roles and modules, optional events | who may make, check and approve; what has happened in order |
| evidence | fixed | how a criterion, a record and a verdict relate |
| code | manifest components | which surfaces each module declares (not an AST) |
| lane | lanes JSON, `--now`, thresholds | who owns what, who is alive, where live claims overlap |
| context | context JSON, `--budget` | what entered the compiled context, what was omitted, with hashes |
| monitor | monitors JSON, `--now`, `--skew-tolerance` | what is observed, how fresh, and which gate consumes it |
| work | spec JSON | which units can run together and in which order |

The Context Map is provenance for one compilation; it is not retrieval and not a knowledge base.
The Code Map inventories declared components; it is not a call graph.

## Two hosts

| capability | Claude Code | Codex CLI |
|---|---|---|
| skills and instructions | plugin, native | copied into `.agents/skills`, namespaced |
| lifecycle hooks (`Stop`, `PreToolUse`, `SessionStart`, ...) | native once wired by a person | none; the same scripts run as explicit commands |
| command policy | hook plus CLI | CLI or preflight |
| event log, attestation, maps, WorkGraph, eval | CLI | CLI |
| install | marketplace plugin, or installer copy for `explicit-command` modules | installer copy into `.agents/hpp/<module>` |

The host seam is a small table: settings path and manual gates for Claude Code; `AGENTS.md`,
skills path and runtime path for Codex CLI. `hpp init` uses it to name the same paths the module
installer will touch, and touches none of them. Adding a host means adding a row and a coverage
value per module, not changing the six stages.

## Distribution

The published tree is emitted by the forge from module sources. Each module directory carries
`CHECKSUMS.txt` (sha256 per file) and a `.zip` with the same bytes; `marketplace.json` lists the
modules with `source` and `version`; the installer (`instaladores/kit-forge-<version>/kit_doctor.py`)
runs the six install stages, verifies checksums and executes the module's declared smokes.

```text
sources ──forge──▶ module dir + CHECKSUMS.txt + .zip ──▶ marketplace.json
                        │                                     │
                        └── kit_doctor.py verify ◀────────────┘── hpp doctor (cross-check)
```

The source checkout of the harness does not contain the emitted modules or the installer. The
doctor, the benchmark and the suite run there; distribution integrity and module checksums are
reported as not verified rather than assumed.

## Exit contract

| code | meaning | where |
|---|---|---|
| `0` | ok; in `audit` mode, always | every command |
| `1` | warn or manual gate; an eval gate that failed | `policy check` (`MANUAL` in `enforce`), `eval run`, `benchmark`, `init` with warnings |
| `2` | block; a refused input (bad manifest, bad spec, corrupt log, invalid attestation) | `policy check` (`BLOCK`), `attest`, every validation error |
| `3` | usage or internal error | `init` usage errors, unexpected exceptions |

`hpp init` reports the code it will return inside its JSON report (`exit_code`) and halts the
remaining stages when a stage fails with a blocking hint.

## Tests and CI

The suite under `tests/` is stdlib-only and runs without network. Each test file carries at least
one test named `CONTROLE` that proves the file can fail. Two tests skip in a source checkout because
they need `marketplace.json`; they run in the emitted distribution. CI runs the suite,
`hpp doctor` and `hpp benchmark -k 3` on Linux, macOS and Windows across Python 3.10 to 3.13,
with read-only permissions and no step allowed to fail silently.

```bash
python -m pytest tests -q
python -m hpp doctor
python -m hpp benchmark -k 3
```

## What deliberately does not exist

| absent | why it is a choice |
|---|---|
| daemon or background service | a check that did not run was not run; a resident process would be a second thing to verify and would hold state the log cannot see |
| server, API or control plane | the harness is operated from the repository it protects; a remote plane would move the verdict away from the bytes it is about |
| scheduler or queue | cadence in the Monitor Map is declared for the consumer to honour; the harness does not wake itself up |
| graph database | every map is re-derivable from files; a stored graph would drift from its sources and require its own doctor |
| model execution | routing returns a tier and a provider id; calling a model would make verdicts depend on something the harness cannot reproduce or afford to hold credentials for |
| credential storage | there is none to leak; secret-like input to the context compiler is refused, and the failure memory redacts by shape |
| telemetry | nothing leaves the machine; any outbound transfer an agent attempts is classified `MANUAL` |
| automatic settings or hook wiring | enabling a hook changes what runs on every future tool call; that is a human action, printed for pasting |
| token counting | the budget is in characters, which every host measures the same way; a token count would tie the harness to a tokenizer |

A layer is added only when there is a consumer for it and a benchmark that shows what it costs.
Until then, the absence is the feature.
