[English](CONCEPTS.md) · [Português](CONCEPTS.pt-BR.md)

# Concepts

The vocabulary of House Party Protocol. Each term has a one-sentence definition, the confusion
it is most often mistaken for, and a way to verify it on your machine. Commands run from the
repository root unless stated otherwise.

## harness

**Is:** the layer that sits around an agent's work and decides, from measured state, whether the
work may advance.

**Is not:** an agent, a model, a prompt library or an IDE plugin. The harness never calls a
model and never edits the agent's settings.

**Verify:** `python -m hpp --help` lists the operating surface; `python -m hpp --self-test`
exercises it without touching a workspace.

## protocol

**Is:** the set of invariants every module and host must respect, written in
`hpp.manifest.json` as roles, loop transitions with named gates, exit codes, host coverage and
monitors.

**Is not:** a network protocol, a prompt format or a style guide. Nothing about the protocol
depends on which model is on the other side.

**Verify:** `python -m hpp doctor` rejects a manifest whose `protocol_version` is not `2.0`,
whose exit codes deviate from `0/1/2/3`, or whose modules reference unknown modules or hosts.

## module

**Is:** an installable, independently versioned capability with a declared path, declared
components (skills, hooks, commands, agents, rules, templates, scripts) and declared coverage per
host.

**Is not:** a plugin in the Claude Code sense only. The same module is a plugin on Claude Code
and a verified copy on Codex CLI. A module is also not a dependency of another by default: today
every `requires` list in the manifest is empty; `integrates_with` is optional composition.

**Verify:** `python -m hpp graph --view capability --format json` shows `provides`,
`supports:<coverage>`, `requires` and `integrates-with` edges per module.

## host

**Is:** the environment that runs the agent and can execute a module: Claude Code or Codex CLI.

**Is not:** interchangeable. Coverage is declared per module and per host as `native` (the host
fires the capability in its lifecycle), `explicit-command` (the capability exists as a CLI call)
or `unsupported` (no verified mechanism).

**Verify:** `python -m hpp init --target . --host codex --modules claude-dev-kit --json` halts at
`configure`, because that module is `unsupported` on Codex CLI.

## gate

**Is:** a named condition, with a measurable answer, that a piece of work must satisfy before it
moves to the next state.

**Is not:** a checkbox, a review comment or a prompt instruction. A gate that cannot be forced to
fail by a test is a hypothesis of protection, not a gate.

**Verify:** the five loop gates are `scope`, `fresh-evidence`, `read-only-checker`, `human` and
`closure` (`python -m hpp graph --view operational --format mermaid`). Appending `verified` as the
first event is refused before anything is written: `python -m hpp event append --type verified`
exits 2 and creates no `.hpp/`.

## evidence

**Is:** the recorded output of a command that decides a criterion, with enough context to rerun
it: the command, its exit code or output, the version it ran against, its scope, and when it ran.

**Is not:** a sentence in a transcript, a screenshot without a command, a test that passed on a
different checkout, or a green status that nobody re-derived. A promise is not evidence; a
`<promise>` tag does not pass the done gate.

**Verify:** `python -m hpp event append --type evidence_recorded --data '{"work":"ITEM-1","ref":"pytest.txt"}'`
records a reference; the loop cannot reach `verified` without at least one such event.

## attestation

**Is:** a JSON record that binds a checker's verdict to the repository identity, the base commit,
the spec's hash, the maker, the checker, a session id and a sha256 snapshot of every tracked and
untracked file.

**Is not:** a signature, a certificate or a proof that the verdict was right. It proves the
verdict was given on these bytes. It also does not store your remote URL; it stores a hash of it.

**Verify:** `python -m hpp attest create --repo . --spec SPEC.md --maker maker-a --checker checker-b --session review:001 --verdict approved --output .hpp/attestation.json`
then `python -m hpp attest verify .hpp/attestation.json --repo .` returns `valid`; change any
file and it returns `blocked` with `snapshot_digest` in `mismatches`. The benchmark control
`evidence-attestation` runs exactly this sequence.

## maker and checker

**Is:** two roles. The maker produces the change. The checker reviews it without the ability to
edit, and reports achievements and defects with severity, file and line.

**Is not:** two turns of the same agent, or the same agent under a different name. Attestation
refuses a maker and checker whose names match ignoring case. The modules' checker agents declare
tool sets without `Write` or `Edit`.

**Verify:** `python -m hpp attest create ... --maker a --checker A ...` exits 2 with "maker and
checker must be different non-empty actors". In the lane module,
`checker_router.py --maker claude --require` picks a checker from a different provider and exits
2 when none is available.

## lane

**Is:** one concurrent session's claim on a territory: an id, a list of paths, an exclusivity
flag and a heartbeat.

**Is not:** a branch, a worktree or a lock file. A lane's authority expires: with `--now`, a
heartbeat older than `--suspect-after` makes it `suspect`, older than `--dead-after` makes it
`dead`, and a dead lane never produces a collision. A heartbeat in the future is an error, not
liveness.

**Verify:** `python -m hpp map lane examples/reliable-coding/lanes.json --now 1000 --suspect-after 60 --dead-after 300`
reports liveness per lane and an empty `collisions` list; the benchmark control `lane-collision`
adds an overlapping live lane and a dead one and checks that only the live pair collides.

## wave

**Is:** a set of work units with no dependency among them, released together, whose barrier
closes before the next wave opens.

**Is not:** a batch size, a number of parallel agents, or a sprint. Parallelism is a consequence
of the dependency graph, not a parameter.

**Verify:** `python -m hpp work waves examples/reliable-coding/workgraph.json` yields
`spec` → `build, docs` → `verify`.

## WorkGraph

**Is:** the compiled form of a spec: work units with `id`, `depends_on`, non-empty `acceptance`
criteria and a `tier`, ordered into waves.

**Is not:** an executor. It schedules nothing and launches nothing. A cycle is a compilation
error with the cycle path in the message, never an empty wave.

**Verify:** `python -m hpp work plan examples/reliable-coding/workgraph.json` prints units, edges,
waves and tier counts; the benchmark control `workgraph-waves` feeds it `a -> b -> a` and expects
an error.

## context budget

**Is:** a character limit under which the context compiler fits whole input blocks, highest
priority first, recording for each block its source, size and sha256, and listing what it left
out.

**Is not:** a token count, a summariser or a retrieval system. A block that does not fit is
omitted entirely, never sliced. Content that looks like a secret (an API key assignment, a PEM
header, a provider-style key prefix) is refused, not redacted.

**Verify:** `python -m hpp context compile examples/reliable-coding/context.json --budget 160`
reports `used` and `remaining` in characters, with the separator between blocks charged to the
budget.

## readiness

**Is:** the count of checks that `hpp init` actually ran and their result, each with the command
that reproduces it: `verified`, `failed` or `not-verified`.

**Is not:** a percentage of completion or an estimate. A check that did not run is reported as
not verified, never as zero and never as one hundred.

**Verify:** `python -m hpp init --target <dir> --json` returns `readiness.items` with eleven
entries; in a source checkout, distribution integrity and module checksums are `not-verified`
because there is no `marketplace.json` or `CHECKSUMS.txt` to measure.

## monitor

**Is:** a declared observation contract: a target, a probe type, a cadence, a freshness window, a
severity, a cost and the gate that consumes it.

**Is not:** a running process. The Monitor Map projects the `last_signal` you supply against the
`--now` you supply. And a healthy monitor is not a correct result. Three questions stay separate:

| question | what answers it |
|---|---|
| is the service up? | the probe returned within its cadence |
| is the data fresh? | `now - last_signal <= freshness`, and `last_signal` is not in the future beyond `--skew-tolerance` |
| is the result correct? | a criterion command, recorded as evidence; no monitor answers this |

A signal stamped in the future is `skew`, not `healthy`; a missing signal is `unknown`, not
`stale`.

**Verify:** `python -m hpp map monitor examples/reliable-coding/monitors.json --now 1000` shows a
`healthy` service probe beside a `stale` data probe in the same projection.

## gotcha

**Is:** a lesson derived from a command failure that recurred, stored by error family and
injected as a preamble before the next run of the same kind of task.

**Is not:** a permanent rule created from one incident, and not a record of secrets. Promotion
from failure to gotcha requires recurrence within a window; ambiguous output does not count as a
failure; every stored entry is redacted by shape (private keys, credentials in URLs, bearer
tokens, JWTs, high-entropy blobs) before it is written. The hooks are warn-only and never block.

**Verify:** in an installed `gotcha-memory` module, the `gotcha-memory` skill lists, seeds and
inspects the store; the hooks exit 0 in every case.

## pass@k and pass^k

**Is:** two metrics over `k` executions of the same case. `pass@k` is true when at least one run
passed and measures capability. `pass^k` is true when every run passed and measures reliability.
The difference between them is the flake rate.

**Is not:** interchangeable, and not a model benchmark. A capability gate requires
`pass@k >= 0.90`; a regression gate requires `pass^k == 1.00`; `--gate both` requires both.

**Verify:** `python -m hpp eval run examples/reliable-coding/benchmark-suite.json -k 3 --gate both`
prints both metrics and the gate; exit 0 on pass, 1 on fail.

## exit contract

**Is:** four process exit codes with fixed meaning across the harness and every module:
`0` ok, `1` warn or manual gate, `2` block, `3` usage or internal error.

**Is not:** a suggestion. The manifest is rejected if it declares anything else. In `enforce`
mode, `BLOCK` exits 2 and `MANUAL` exits 1; in `audit` mode the verdict is printed and the exit
is always 0.

**Verify:** `python -m hpp policy check --mode enforce --command "rm -rf src"` exits 2;
`--command "git push origin feature"` exits 1; `--mode audit` with either exits 0.

## plan and apply

**Is:** the two-invocation contract for anything that writes: the first run prints what would
happen and exits 0 without writing; a second run with `--apply` performs it.

**Is not:** a confirmation prompt. Nothing in the harness blocks on `input()`; the "yes" is the
re-invocation, which is auditable and works when the operator is an agent.

**Verify:** `python -m hpp init --target <empty-dir>` leaves the directory empty (`find <dir> -type f | wc -l` is 0);
the same command with `--apply` writes exactly `.hpp/profile.json`. Wiring for settings and hooks
is printed in both cases and written in neither.

## control

**Is:** a known-good and a known-bad case run through the same instrument, so that the
instrument is shown to distinguish them before its verdict is trusted.

**Is not:** a test that only exercises the happy path. A gate that passes on good input and was
never shown to fail on bad input cannot be told apart from a gate that is absent.

**Verify:** every case in `examples/reliable-coding/benchmark-suite.json` is a control with both
directions: `policy-enforcement` checks that `python -m pytest -q` is `ALLOW` and `rm -rf src` is
`BLOCK`; `event-evidence-gate` checks that a valid sequence reaches `verified` and that a bare
`verified` is refused without creating the log. Each test file in `tests/` carries at least one
test named `CONTROLE` that proves the file knows how to fail.

## event log

**Is:** an append-only JSON-lines file at `.hpp/events.jsonl` in the workspace, where each line
carries a contiguous `seq`, an `id` of the form `event:<seq>`, a `type` and a `data` object.

**Is not:** a chat history, and not something the harness will repair. A line whose `seq` is not
contiguous or whose `id` does not match is a corrupt log, and the projection stops rather than
guessing. An event whose transition is not allowed from the current state is refused before the
write.

**Verify:** `python -m hpp status --json` shows the state, the count and the history;
`python -m hpp resume` returns the next step derived from the same log.

## bundle

**Is:** a named set of modules recommended for one objective, with the capabilities it is
expected to provide.

**Is not:** a dependency. `reliable-coding` names six modules; installing one of them alone is
valid.

**Verify:** `python -m hpp install --bundle reliable-coding --host codex --target <dir>` prints a
plan-only receipt listing each module and its integration mode on that host.
