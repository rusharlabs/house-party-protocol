<p align="center">
  <img alt="House Party Protocol — by Rushar Labs" src="assets/hpp-logo.png" width="620">
</p>

<p align="center"><sub><code>AGENTS &nbsp;·&nbsp; EVIDENCE &nbsp;·&nbsp; MEMORY &nbsp;·&nbsp; PROTOCOL &nbsp;·&nbsp; CONTINUITY</code></sub></p>

<p align="center">
  <a href="LICENSE"><img alt="MIT" src="https://img.shields.io/badge/license-MIT-0F1113"></a>
  <a href="#quickstart"><img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-FF6A00"></a>
  <img alt="Claude Code and Codex CLI" src="https://img.shields.io/badge/hosts-Claude%20Code%20%7C%20Codex%20CLI-F4F1EB">
</p>

<p align="center"><sub>English &nbsp;·&nbsp; <a href="README.pt-BR.md">Português (Brasil)</a></sub></p>

# House Party Protocol

**Operate coding agents under evidence, not trust.**

House Party Protocol (HPP) is a local-first harness for coding agents. It sits around the work
an agent does in Claude Code or Codex CLI and turns four questions into executable contracts:
what may run, who may approve, what counts as proof, and where the next step comes from after an
interruption.

The harness is a Python package with no runtime dependencies (`python -m hpp`), a manifest that
declares the protocol, a set of installable modules, and one distribution channel per host.
Nothing runs in the background. Every verdict it produces can be re-derived from files on disk.

## The problem

An agent says "done". The sentence is fluent, the diff looks plausible, and nothing checked it.
The tests it reports may have run against a stale checkout, or may not have run at all; text in
a transcript is not an exit code. The approval a reviewer gave yesterday still reads "approved"
this morning, after the spec changed and three files moved. Nobody re-opened it, because nothing
tied the approval to the bytes it approved.

Two sessions share one repository. One rewrites a module while the other reviews it; the review
lands on a version that no longer exists. Or the agent that wrote the code is the one that
reviews it, with the same blind spots and a pen in hand: it "fixes and proceeds", and the defect
in the process never surfaces. A lock left by a session that died at 3 a.m. blocks every other
session at 9, because a stale lock and a live one look identical.

Then the failures that lie by being technically correct. A service answers 200 while its data is
from Tuesday. A signal stamped in the future is reported as fresh. A counter returns zero because
the pattern never matched, and zero is read as "no problems". A loop takes "one more iteration"
past its budget. A summary restored after a crash is treated as a to-do list, so a finished step
runs again and overwrites its own result. None of these raise an error. That is what makes them
expensive.

## How the harness responds

Each failure above has a mechanism in the code, and each mechanism has a command that shows it.

| failure | mechanism | command |
|---|---|---|
| "done" without proof | append-only event log; `verified` needs recorded evidence; an out-of-order event is refused before anything is written | `hpp event append` · `hpp status` |
| stale approval | attestation bound to spec hash, base commit and a full snapshot of tracked and untracked files; any divergence blocks reuse | `hpp attest create` · `hpp attest verify` |
| author reviewing own work | maker and checker must differ (case-insensitive) or the attestation is refused; module checkers ship without write tools | `hpp attest create --maker a --checker a` → exit 2 |
| stale lock, territory collision | Lane Map derives `alive` / `suspect` / `dead` from heartbeats; a dead lane never produces a collision | `hpp map lane --now` |
| service up, data old | Monitor Map separates `healthy`, `stale`, `skew` and `unknown`, with declared freshness and clock tolerance | `hpp map monitor --now` |
| dangerous command | policy classifier returns `ALLOW`, `MANUAL` or `BLOCK`; `enforce` maps them to exit 0, 1, 2 | `hpp policy check --mode enforce` |
| parallelism by guesswork | WorkGraph turns declared dependencies into topological waves; a cycle is an error, not an empty wave | `hpp work waves` |
| context silently truncated | compiler fits whole blocks under a character budget, records a hash per block, and refuses secret-like material | `hpp context compile` |
| one lucky run | `pass@k` and `pass^k` measured separately over `k` executions | `hpp eval run` · `hpp benchmark` |
| installer that writes before you read | `hpp init` prints a plan; `--apply` writes one file; host wiring stays a paste | `hpp init` |

## Quickstart

Requirements: Python 3.10 or newer (`pyproject.toml`), `git` on `PATH` for attestation, no
third-party packages. CI exercises Python 3.10 to 3.13 on Linux, macOS and Windows
(`.github/workflows/ci.yml`); older interpreters are not promised because nothing measures them.

```bash
git clone https://github.com/rushar-labs/house-party-protocol.git
cd house-party-protocol
python -m hpp doctor
python -m hpp init --target ../your-repo
```

`hpp init` runs six fixed stages and prints a plan. Each boot line completes only when its stage
has finished; readiness counts checks that ran, and each item carries the command that
reproduces it. This is the output on a fresh target from the source tree:

```text
> detecting host...           ✓ greenfield · 0 existing item(s) preserved
> checking prerequisites...   ✓ python 3.14.3 · protocol 2.0
> mounting profile...         ✓ would-write · host=claude-code · bundle=reliable-coding · policy=audit · 3 default(s)
> loading modules...          ✓ 6 modules · reliable-coding · claude-code
> wiring suggestions...       ✓ 7 commands to paste · 0 files written
> verifying evidence...       ✓ policy · graph · events · benchmark
> protocol online.

  READINESS  every line is a check that ran; the command below it reproduces it
  █████████████░░░░░░░  7/11 verified · 4 not verified · 0 failed
```

The four items not verified in that run are exactly the ones a source checkout cannot prove:
distribution integrity and module checksums (only the emitted distribution carries
`marketplace.json` and `CHECKSUMS.txt`), the profile (plan only) and the host wiring (a paste
you do yourself). Nothing is written until you re-run with `--apply`, and then exactly one file
is written: `.hpp/profile.json`. `hpp init --json` gives the same report as JSON for CI and
agents; `--non-interactive`, `--yes` and `--profile` answer the three questions without a prompt.

After `--apply`, paste the wire block the command printed. For Claude Code that is the native
plugin channel:

```text
/plugin marketplace add rushar-labs/house-party-protocol
/plugin install operator-kit@house-party-protocol
```

For Codex CLI, and for modules that have no plugin hook on Claude Code, the module installer
copies each module and runs its declared smokes. It plans first and applies only on a second,
explicit invocation:

```bash
python instaladores/kit-forge-1.4.0/kit_doctor.py install \
  --kit frameworks-com-plugins/operator-kit-1.4.0 --host codex --target ../your-repo
python instaladores/kit-forge-1.4.0/kit_doctor.py install \
  --kit frameworks-com-plugins/operator-kit-1.4.0 --host codex --target ../your-repo --apply
```

The installer ships with the emitted distribution, not with this source tree; `hpp init` says so
in its wire block when it cannot find it.

## Harness, protocol, modules, distribution

The product is layered, and the layers are not interchangeable.

```text
harness        python -m hpp          the operating surface: doctor, init, event log,
                                      attestation, maps, WorkGraph, policy, routing, eval
   │
protocol       hpp.manifest.json      the invariants: roles, loop transitions and gates,
                                      exit codes, host coverage, monitors, bundles
   │
modules        ten versioned dirs     installable capabilities; each stands alone
   │
distribution   marketplace · copy     Claude Code plugin channel · Codex CLI verified copy
```

`hpp doctor` validates the manifest and, when `marketplace.json` sits beside it, cross-checks
every module path, version and plugin manifest. On this checkout it reports `modules=10`; the
same command against the emitted distribution reports `distribution: checked, ok, 10 modules`.

The protocol's loop is five transitions, each behind a named gate:

```text
planned --work_started--> active --evidence_recorded--> evidenced --check_passed--> checked
        [scope]                   [fresh-evidence]                 [read-only-checker]

checked --human_approved--> approved --verified--> verified
        [human]                      [closure]
```

`hpp status` projects the event log onto this machine and names the next step; `hpp resume`
returns the same answer as JSON. Neither asks a model to remember anything.

## What each module solves

| module | version | one line |
|---|---|---|
| `operator-kit` | 1.4.0 | done gate with real exit codes, command policy in `audit` or `enforce`, governed loops with charter and stop conditions, standalone `pass@k` / `pass^k` runner, preflight, two read-only checker agents |
| `lane-kit` | 1.2.0 | a lane board for concurrent sessions: claim, territory, liveness, maker ≠ checker, and a router that picks a checker from a different provider |
| `continuity-kit` | 1.2.1 | handoff written before a stop or compaction, re-derivation commands instead of remembered state, guards against replaying finished steps |
| `health-kit` | 1.3.1 | config-driven service probes that write a cache a statusline reads without touching the network; service health kept apart from data health |
| `gotcha-memory` | 1.0.0 | records failed commands by error family, detects recurrence, injects the lesson before the next run; warn-only, secrets redacted by shape |
| `kit-forge` | 1.4.0 | assembles modules from source, lints for IP and PII, installs in six stages, writes and verifies `CHECKSUMS.txt`, checks the marketplace |
| `claude-dev-kit` | 1.3.1 | authoring of skills, hooks and plugins for Claude Code, reversible settings wiring, secret scan on write |
| `dev-squad-kit` | 1.0.0 | twelve development roles as commands and subagents with explicit tools, plus parallel read-and-consolidate skills |
| `agent-framework-wizard` | 1.1.1 | six-step scaffold for a new agent or skill project, answerable from a file for non-interactive runs |
| `supabase-pack` | 1.1.0 | RLS audit through `pg_policies` and advisors instead of a table flag; Edge Function scaffold |

The `reliable-coding` bundle is the first six. Each module installs on its own; `integrates_with`
in the manifest is optional composition, `requires` is a hard dependency, and today no module
requires another. Host coverage is declared per module as `native`, `explicit-command` or
`unsupported`; `claude-dev-kit` is `unsupported` on Codex CLI, and `hpp init` halts rather than
plan it there.

## Proving an installation

A claim about the harness is accepted only with its command. These are the ones the project runs
on itself.

```bash
python -m hpp doctor                      # manifest contract; distribution when present
python -m hpp benchmark -k 3              # ten executable controls, three runs each
python -m hpp --self-test                 # capability graph non-empty + benchmark gate
python -m pytest tests -q                 # stdlib-only suite, no network
python -m hpp policy check --mode enforce --command "rm -rf src"   # exit 2, BLOCK
python -m hpp graph --view operational --format json | sha256sum   # same hash on every run
```

The benchmark's ten controls each execute a real mechanism with a positive and a negative case:
manifest contract, policy enforcement, WorkGraph waves, lane collision, monitor freshness,
context provenance, routing floor, event/evidence gate, graph determinism and evidence
attestation. `pass^k = 1.00` is required for the gate to pass. The suite file and its hash are
in the JSON report (`hpp benchmark -k 3 --json`). See [PROOF.md](docs/PROOF.md) for the claim
matrix and [BENCHMARK.md](docs/BENCHMARK.md) for the scenarios.

In an emitted distribution, `kit_doctor.py verify <module>` compares every file against
`CHECKSUMS.txt`, and `kit_doctor.py marketplace .` checks the whole tree.

## Honest limits

- HPP is a CLI. There is no daemon, scheduler, queue, server, database or remote telemetry. If a
  check did not run, nothing ran it.
- HPP never calls a model. Routing returns a tier and a provider id from declarations you pass
  in; it does not pick a vendor, a model name or a price.
- Maps are projections of manifests, event logs and JSON you provide. The Monitor Map does not
  probe anything; you supply `last_signal`. The Lane Map does not know your sessions; you supply
  heartbeats. `--now` is explicit so that no projection depends on the ambient clock.
- The context budget is measured in characters, not tokens.
- The policy classifier is a small, explicit rule set (recursive delete in any flag order,
  force push, push to `main`/`master`, `curl | sh`, `DROP`/`TRUNCATE`, and `MANUAL` for any push
  or outbound transfer). It never executes the command and it does not claim to catch every
  destructive form.
- Attestation requires `git`. It hashes the remote identity and stores the hash, not the URL.
  It binds a verdict to bytes; it does not judge whether the verdict was right.
- On Claude Code, lifecycle hooks are native once you paste the wiring. On Codex CLI there are no
  lifecycle hooks; the same capabilities are explicit commands. `hpp doctor` and the manifest
  report this as `native`, `explicit-command` or `unsupported`, and no adapter pretends
  otherwise.
- `hpp init` writes one file with `--apply` and never edits `settings.json`, hooks or
  `AGENTS.md`. Enabling hooks remains a human action.
- The benchmark proves the harness on the checkout and platform where it ran. It says nothing
  about the quality of any model.

## Reading order

[MANIFESTO.md](MANIFESTO.md) — what the project defends and refuses ·
[CONCEPTS.md](docs/CONCEPTS.md) — the vocabulary, with what each term is not ·
[METHOD.md](docs/METHOD.md) — the working method, one command per practice ·
[ARCHITECTURE.md](docs/ARCHITECTURE.md) — how the pieces fit and what deliberately does not
exist · [GRAPH-MODEL.md](docs/GRAPH-MODEL.md) · [LOOPS.md](docs/LOOPS.md) ·
[BENCHMARK.md](docs/BENCHMARK.md) · [PROOF.md](docs/PROOF.md) · [BRAND.md](docs/BRAND.md) ·
[TIPS.md](docs/TIPS.md) · [manual](docs/MANUAL.html) · [catalogue](docs/CATALOGO.html) ·
[CHANGELOG.md](CHANGELOG.md) · [AGENTS.md](AGENTS.md) for agents working in this repository.

## Development

Module directories in the distribution are emitted artifacts. Changes start in the sources, get
a test that fails before the fix and passes after it, and go through the forge. Before declaring
anything done:

```bash
python -m pytest tests -q
python -m hpp doctor
python -m hpp benchmark -k 3
```

## License and credit

MIT. Copyright (c) 2026 Max Parisi, Rushar Labs. Adapted components keep their `NOTICE` files
and attributions; each module's README names its upstream sources and licenses.
