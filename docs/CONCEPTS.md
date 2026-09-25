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

**Verify:** `python -m hpp doctor` rejects a manifest whose `protocol_version` is not `2.1`,
whose exit codes deviate from `0/1/2/3`, or whose modules reference unknown modules or hosts.
`2.1` added two required top-level keys, `hook_capabilities` and `hooks`; a 2.0 manifest that
declares no hook is refused, which is a contract change and not an addition.

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

**Measured, 2026-09-22, Codex CLI 0.153.4:** the host *does* have a native hook surface —
`codex features list` prints `hooks  stable  true`, and `codex --help` carries
`--dangerously-bypass-hook-trust` ("run enabled hooks without requiring persisted hook trust"),
so enabling one is an explicit trust decision. That did **not** promote any module to `native`
on Codex, and the same census says why: `plugin_hooks` prints `removed  false`, and the string
`codex-hooks.json` does not appear in the installed binary (`hooks.json`, `SessionStart`,
`PreToolUse` and `hook_trust` do). A module installed by file copy therefore still cannot wire
its own hooks on this host; the operator pastes them into a Codex hook configuration and
accepts the trust prompt. `explicit-command` stays the honest coverage. Two instruments were
tried and rejected for this question because they do not discriminate: `codex features list`
and `codex doctor` produce byte-identical output with a deliberately malformed `hooks.json` in
`CODEX_HOME` and with none at all.

## gate

**Is:** a named condition, with a measurable answer, that a piece of work must satisfy before it
moves to the next state.

**Is not:** a checkbox, a review comment or a prompt instruction. A gate that cannot be forced to
fail by a test is a hypothesis of protection, not a gate.

**Verify:** the five loop gates are `scope`, `fresh-evidence`, `read-only-checker`, `human` and
`closure` (`python -m hpp graph --view operational --format mermaid`). Appending `verified` as the
first event is refused before anything is written: `python -m hpp event append --type verified`
exits 2 and creates no `.hpp/`.

## hook capability

**Is:** what a hook is able to do, declared in the manifest before you install it, from a
closed vocabulary of six groups: `automatic-source-writes` (it writes files inside your project
on its own), `command-rewrite-and-process-control` (it changes what runs, or what the model is
given before it runs), `transcript-derived-llm-egress` (it sends transcript-derived text to a
model), `mcp-network-and-process-activity` (it probes the network, talks to an MCP server or
spawns a process), `automatic-permission-gates` (it can refuse or warn on a tool call) and
`session-observation-and-cost-records` (it reads session state and keeps records). Each hook
also declares its `events` and an `exit_policy` of `observe` (always exit 0), `warn` (may exit
1) or `block` (may exit 2, or emit a blocking decision).

**Is not:** a description of what the hook is *for*, and not optional. A hook with no
declaration is refused; an empty `capabilities` list is refused; a module that declares the
`hooks` component and declares no hook is refused. Absent is never read as empty — a missing
declaration that validated as "does nothing" would be the widest permission in the manifest,
written as silence.

**Verify:** `python -m hpp doctor` prints `hooks=<n>` with the permission-gate and LLM-egress
counts, and `--json` carries the full census per group — including the groups that count zero,
so the zero is a measurement and not an omission. `python -m hpp init` prints the capability
table of the modules you chose *before* the commands to paste; choose a module with no hooks
and the table is empty rather than absent. Remove a hook's `capabilities` from the manifest and
the same `doctor` exits 2.

## evidence

**Is:** the recorded output of a command that decides a criterion, with enough context to rerun
it: the command, its exit code or output, the version it ran against, its scope, and when it ran.

**Is not:** a sentence in a transcript, a screenshot without a command, a test that passed on a
different checkout, or a green status that nobody re-derived. A promise is not evidence; a
`<promise>` tag does not pass the done gate.

**Verify:** new in 2.6.0 —
after `python -m hpp event append --type work_started`,
`python -m hpp evidence run --id smoke-page --artifact out/report.html --record-event -- python examples/evidence/smoke_page.py`
runs the criterion, writes the bundle under `.hpp/evidence/` and appends `evidence_recorded` only
when it passed; `python -m hpp evidence verify <record>` re-derives the bundle from disk. The
lower-level alternative, `python -m hpp event append --type evidence_recorded --data '{"work":"ITEM-1","ref":"pytest.txt"}'`,
which earlier releases also have, records a reference without running or hashing anything, after
the same `work_started`. Either way, the loop cannot reach
`verified` without at least one such event.

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

## typed decision

**Is:** a record, `hpp.decision/v1`, of a small question answered outside the harness — by a
rule, a person, a local model or a hosted typed-decision model — that the harness can check and
measure. Its `authority` is always `advisory`. With `direction: raise-only` on an ordered question
(`ladder: true`), the value a consumer may act on is the higher of the `declared` value and the
advised one: advice can raise caution, never lower it. `abstention` and `instrument-failure` are
outcomes, not errors, and neither changes a declared value; a timeout, an HTML page or a malformed
answer is an instrument failure, never a verdict.

**Is not:** a model call, an approval or a score. The harness calls no model itself:
`hpp decide eval` runs the decider you name as a command (which may call one, with your key), or
replays the records already in the suite. A record never grants or approves anything, and an
`authority` other than `advisory` is refused. Version 1 measures `choice` questions only; a score
or a probability of yes has no agreed definition of "correct", so those kinds are refused rather
than reported as a vacuous 0%. The judged text never enters the record, only its sha256, and
secret-like text is refused before it is hashed. A model record must name the pinned version that
answered (an alias such as `-latest` is refused) and, unless it records an instrument failure, the
hash of the raw response.

**Verify:** new in 2.6.0 —
`python -m hpp decide validate <record.json>` prints `"status": "valid"` and the `effective`
value (`action` is `raised`, `kept`, `advised` or `none`) and exits 0; set `authority` to anything
but `advisory` and it exits 2. `python -m hpp decide eval examples/typed-decisions/gotcha-family-suite.json --decider-command '["python", "examples/typed-decisions/baseline_decider.py"]'`
reports coverage, selective accuracy, abstentions and instrument failures separately, and exits 0
when every threshold holds, 1 when the gate fails and 2 for a suite that breaks the contract.

## evidence bundle

**Is:** a record, `hpp.evidence/v1`, of one run of a declared criterion command: the argv, the
base commit, the exit code measured outside the model, a verdict, the byte count and sha256 of
stdout and stderr (never the text), and the path, size and sha256 of every file that matches an
artifact glob you declared. The verdict is `passed` only when the command exited 0 and every
declared pattern matched a file this run wrote (a file left untouched from before the run is
listed as `unchanged` and does not count); otherwise it is `failed`, `missing-artifacts`, `timeout` or
`could-not-start`. `run` exits 0 when the bundle passed, 1 when it did not, and 2 when it was
refused or `--record-event` could not append the event.

**Is not:** a browser driver, a model call or a signature. hpp drives no browser and calls no
model: it runs the command you name (an end-to-end spec, a test suite, any script) with
`shell=False`. The record carries a hash of itself, which makes an edit visible and proves nothing
about who wrote it — anyone who can write the file can rewrite the hash. So `verify` is
reconciliation, and a checker that must not trust the maker re-runs `command` instead. `run` writes
the record and whatever the command writes; a read-only checker points `--out` at its own scratch
directory inside the workspace, or re-runs in its own lane. A command line that looks like it
carries a secret, and an artifact or `--out` path outside the workspace, are refused before
anything runs.

**Verify:** new in 2.6.0 —
`python -m hpp evidence run --id smoke-page --artifact out/report.html --artifact out/smoke.log -- python examples/evidence/smoke_page.py`
prints `passed` and exits 0, and `python -m hpp evidence verify <record>`, on the `record_path` it
printed, prints `valid` and exits 0. The same run with `--break` after the script writes both files and
still exits 1 with `failed`; its record verifies as `not-evidence` (exit 1). Change
`out/report.html` after a passed run and `verify` exits 2 with `blocked`.

## criterion sensitivity

**Is:** a measurement of whether a criterion would notice broken code. `hpp evidence mutate` runs
the criterion command on a copy of the workspace, first clean — it must pass, or the verdict is
`no-control` and nothing else runs — then once per mutant, a copy with one small change that makes
the code wrong, where it must fail. Mutants are declared (`hpp.mutants/v1`: file, find, replace) or
generated from Python tokens with a fixed operator table. A mutant the criterion lets through is a
blind spot, named by file and line in `survivors`.

**Is not:** coverage, and not proof that a surviving mutant is a bug. The score is killed ÷
(killed + survived), null when nothing was measured; a mutant whose text is absent is
`not-applied`, never killed. A surviving mutant can be equivalent — a change that does not change
behaviour — which only a reader can tell. hpp never writes to the user's tree: every run gets a fresh copy, and a mutant
file reached through a symlink is refused. The command runs inside the copy, so its paths must be
relative; an editable install or a `PYTHONPATH` pointing at the checkout makes every mutant survive.

**Verify:** new in 2.7.0 —
`python -m hpp evidence mutate --id weak --generate examples/criterion-sensitivity/discount.py -- python examples/criterion-sensitivity/check_weak.py`
reports `blind-spots` with three survivors and exits 1; the same with `check_strong.py` reports
`sensitive` and exits 0.

## retrieval ruler

**Is:** a measurement of a retriever you declare, apart from any generation step. The retriever is
a command that reads `{"query", "k"}` as JSON on stdin and prints ranked ids; the ruler scores the
top k of each answer against the ids a labelled suite (`hpp.retrieval-suite/v1`) marks relevant,
and reports hit@k, recall@k, precision@k, MRR and nDCG@k. The printed order is the ranking; a
`score` is checked, never used to re-sort.

**Is not:** an index, a search engine or a judge of the final answer. The harness runs no index
and calls no model; without `--retriever-command` the ruler replays the results recorded in the
suite. A retriever that answers and finds nothing relevant scores a real 0. A timeout, a non-zero
exit, output that is not JSON or a duplicate id is an instrument failure: counted apart and
excluded from the means. With no measured case the metrics are null and the gate says why, never
0%.

**Verify:** new in 2.6.0 —
`python -m hpp retrieval eval examples/retrieval/suite.json --retriever-command '["python", "examples/retrieval/keyword_retriever.py"]'`
measures seven cases with zero instrument failures and exits 1: the keyword baseline's mean
recall@3 is 0.786, under the default `--min-recall 0.8`, so the shipped suite proves the ruler,
not a retriever. With `--retriever-command '["python", "-c", "import sys; sys.exit(3)"]'` the same
suite reports seven instrument failures and null metrics, and exits 1. The exit is 0 when the gate
passes, 1 when it fails and 2 for a suite or argument that is refused.

## citation check

**Is:** a deterministic check, `hpp.citation-check/v1`, of the citation markers in a text against
the ids of the context the text was written from. A marker is `[ID:<id>]` unless `--marker` gives a
regex with one capture group for the id. A marker that names an id missing from the context
(`UNKNOWN_ID`), a range or list inside one marker (`RANGE`) and an empty marker (`EMPTY_MARKER`)
block with exit 2; more than `--max-per-sentence` markers in one sentence (`TOO_MANY`, default 4)
and a sentence that states a number, percentage, amount or date with no marker (`UNCITED_CLAIM`)
warn with exit 1. A clean text exits 0.

**Is not:** a fact check. It never reads a cited source to see whether it supports the sentence:
a marker that resolves proves the id exists, not that the source says what the sentence says.
Sentence splitting and number detection are heuristics, written out in `hpp/citations.py`, and
their known misses are warnings, never blocks. Context the text never cites is reported as a
count, not as a finding. Empty text, secret-like text or context, and an unusable marker regex are
refused with exit 2.

**Verify:** new in 2.6.0 —
`python -m hpp cite check --text examples/citations/answer.md --context examples/citations/context.json`
prints verdict `ok` and exits 0. On a copy of `answer.md` with `[ID:glossary]` changed to
`[ID:glossary-v2]` it exits 2 with `UNKNOWN_ID`; with `[ID:runbook-7]` removed instead it exits 1
with `UNCITED_CLAIM`.

## best-of-N selection

**Is:** N lanes each build their own attempt at one task, and a reviewer keeps one. In the lane
module, `lane_board.py compete --task T --items A,B[,C...]` declares the candidates, each built by
a different lane; `lane_board.py select --task T --winner A` records the winner, once every
candidate is `CHECKPOINT-READY` with evidence or `VERIFIED`, and only a reviewer whose lane differs
from every builder lane and whose model family differs from every builder's family may write it.
The losers become `NOT-SELECTED`, a terminal state that no transition leaves.

**Is not:** a verification, and not a reliability measure. Choosing 1 of N is pass@N: one attempt
out of N was good enough, which says nothing about whether the winner passes every run. The winner
keeps its state, still needs its ordinary `VERIFIED` before `MERGED`, and its criterion still needs
pass^k. A candidate cannot be `MERGED` while its task has no winner, and
`select --checker-unavailable` records `DEFERRED`, never a winner.

**Verify:** new in 2.6.0 —
on a competition declared with `compete` whose candidates are `CHECKPOINT-READY`,
`lane_board.py select` by a reviewer of the same model family as one builder exits 1 with
"SAME model family"; a reviewer of another lane and another family exits 0, and moving the losing
item to any state afterwards exits 1. `lane_board.py --self-test` runs every refusal of `compete`
and `select` next to its control.

## House Session

**Is:** a deliberation between pinned deciders, recorded so it can be verified and measured.
`hpp.panel/v1` names the question, the hash of the state judged, every seat
(`{id, role, provider, model_served, family, lane}`) and the budget (`max_rounds`, `max_chars`).
A panel does not start without two model families among the participants, exactly one judge in a
lane no participant uses, and the roles its `session_type` needs (`plan`, `review`,
`release-gate`, `incident`, `design`). Each `hpp.turn/v1` carries a seat's position, its claims
with the ids they rest on, the hash of the verbatim text and `seen_turns`: a round-1 turn that
saw anything is refused, so the blind round is checkable. The session stops by rule
(`not-judged`, `grounded-convergence`, `paused-budget`, `no-new-evidence`, `max-rounds`), and
`hpp.deliberation/v1` seals the panel, the turns, the tally, the stop, the judge's
`hpp.decision/v1`, the verdict and the dissent that lost; `human_decision` stays outside the seal.

**Is not:** a model call, a vote that replaces a person, or proof that a panel beats one agent.
The seats and the judge answer outside the harness. A seat that did not answer is **not judged**
— never a vote against — and it blocks the verdict. A position is grounded when its turn states a
`fact` with a reference; whether the reference exists in the context is not checked yet. The
panel publishes no confidence it did not measure. The seal is not a signature: `verify` proves
that everything derived matches the turns and the judge's record the file holds, and those are
anchored only by the hashes of the verbatim text and the raw response kept beside it. A session
ends at the first round where a rule holds; turns of later rounds are refused. Whether a panel is worth its cost is measured
with `hpp decide eval`, which reads the panel as one decider (`method: panel`), not asserted here.

**Verify:** new in 2.7.0 —
`python -m hpp deliberate record --panel examples/house-session/review/panel.json --turns examples/house-session/review/turns.json --judge examples/house-session/review/judge.json --out out/record.json`
seals the review with `stop` `max-rounds`, `escalate: true`, the verdict `high` and seat `c`
kept as dissent, exit 0; `python -m hpp deliberate verify out/record.json` exits 0, and on a copy
with the verdict edited exits 2. A panel whose seat is served by `-latest`, or whose participants
share one family, exits 2 on `deliberate plan`.

## maker and checker

**Is:** two roles. The maker produces the change. The checker reviews it and reports achievements
and defects with severity, file and line, without file-editing tools: the host enforces the
absence of `Write` and `Edit`. `Bash` remains available, and a shell can change whatever it
reaches, so read-only is a promise, verified by comparing the working tree before and after the
review — `git status --porcelain` captured on both sides must match, and a checker that changed
the tree invalidates its own findings.

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

## spec-driven work

**Is:** work that derives from a declared specification: a JSON object whose `work` list names
each unit with an `id`, its `depends_on`, non-empty `acceptance` criteria and a `tier`. The spec
is the input; the order, the waves and the edges are outputs of compiling it.

**Is not:** a waterfall, and not "write a document before coding". The spec is small enough to
be recompiled every time it changes, and compiling it costs one command. It is also not a
conversation: a dependency that was agreed in chat but not written in `depends_on` does not
exist for the harness.

**Verify:** `python -m hpp work plan examples/reliable-coding/workgraph.json` prints the compiled
form; remove an `acceptance` list and the same command exits 2 with "needs non-empty acceptance
criteria"; name a dependency that is not a unit and it exits 2 with "unknown dependency".

## wave-driven execution

**Is:** advancing by wave rather than by task: every unit in a wave may start once the wave
opens, and the next wave opens only after every unit in the current one has closed.

**Is not:** a queue of tasks picked in any order, and not a promise the harness enforces on its
own. `hpp work waves` computes where each barrier is; nothing in `python -m hpp` stops an
operator from starting a wave-2 unit early. Honouring the barrier is the operator's contract,
and the loop's events name no wave.

**Verify:** `python -m hpp work waves examples/reliable-coding/workgraph.json` returns
`waves` with an `index` per wave and the units that belong to it; `verify` appears only in
wave 3, after `build` and `docs`.

## parallel and sequential

**Is:** a consequence of the dependency graph, not a choice. Two units with no path between
them, whose dependencies have all closed, land in the same wave; a unit lands in the wave after
the latest of its dependencies. Nobody decides that `build` and `docs` may run together; the
absence of an edge between them decides it.

**Is not:** "run everything in parallel". Running everything at once ignores the edges; running
by wave ignores nothing. It is also not a safety claim about files: two units in the same wave
may still write the same paths, and the WorkGraph does not look at paths. That question is
answered by the Lane Map, whose collision is two live exclusive lanes whose territories are
equal or nested.

**Verify:** `python -m hpp work waves examples/reliable-coding/workgraph.json` places `build`
and `docs` in wave 2 together (both depend only on `spec`); `python -m hpp map lane examples/reliable-coding/lanes.json --now 1000`
reports `collisions: []` for two lanes on disjoint paths.

## topological order

**Is:** the order in which units are released, derived from the edges: a unit is never released
before every unit it depends on. Within one wave the order is alphabetical by `id`, so the same
spec yields the same output on every machine.

**Is not:** a priority list, and not the order in which units were written in the spec. The
person declares edges; the graph decides the order; neither the person nor the agent picks the
sequence by hand. A cycle is a spec that contradicts itself: `a` must finish before `c`, `c`
before `b`, `b` before `a`, and no order satisfies all three. The compiler refuses it and names
the path; it never breaks the cycle for you.

**Verify:** a spec with `a -> c -> b -> a` makes `python -m hpp work waves SPEC.json` exit 2 with
`dependency cycle: a -> c -> b -> a`; a unit that depends on itself exits 2 with
`dependency cycle: a -> a`. The benchmark control `workgraph-waves` runs the two-unit case.

## barrier

**Is:** the boundary between two waves: the point at which every unit of the current wave has
met its acceptance criteria and the next wave may open.

**Is not:** a checkpoint meeting or a status update. A unit in wave `n+1` depends, directly or
through other units, on something in an earlier wave; starting it before the barrier closes means
building on a dependency whose criteria have not passed. If that dependency then changes, the
early unit's evidence describes a checkout that no longer exists, and "wave `n` is closed" stops
being a sentence with a measurable meaning.

**Verify:** `python -m hpp work waves examples/reliable-coding/workgraph.json` shows three waves;
the barrier is the boundary between consecutive indices. The harness computes it and reports it,
and does not enforce it: there is no wave in the loop's events, only `work_started` through
`verified` (`python -m hpp graph --view operational --format mermaid`).

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
entries. From a clone of this repository, distribution integrity and module checksums are
`verified`, because `marketplace.json` and every module's `CHECKSUMS.txt` sit beside the manifest;
from a pip install, which carries neither, the same two items are `not-verified`.

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

## command policy

**Is:** a classifier that reads one command as text and returns one of three verdicts, `ALLOW`,
`MANUAL` or `BLOCK`, with the rule that matched and its reason. The rules are fixed in
`hpp/policy.py`; the first match wins, and every `BLOCK` rule is tried before any `MANUAL` rule.

| verdict | rule | matches |
|---|---|---|
| `BLOCK` | `recursive-delete` | `rm` with both a recursive and a force option in any spelling (`-rf`, `-fr`, `-r -f`, `--recursive --force`), or `rmdir /s` |
| `BLOCK` | `force-push` | `git push` with `--force` or `-f` |
| `BLOCK` | `main-push` | `git push` naming `main` or `master` |
| `BLOCK` | `pipe-to-shell` | `curl` or `wget` piped into a shell (`sh`, `bash`, `zsh`, `dash`, `ksh`), with or without `sudo` |
| `BLOCK` | `destructive-sql` | `DROP` or `TRUNCATE` followed by `TABLE` or `DATABASE` |
| `MANUAL` | `external-push` | any other `git push` |
| `MANUAL` | `external-send` | `curl` or `wget` whose next word is an `http://` or `https://` URL |
| `MANUAL` | `decision-advisor` | a command naming `typed-decisions/decide.py` — new in 2.6.0 |

Anything else is `ALLOW` (rule `allow`), and an empty command is `ALLOW` (rule `empty`).

**Is not:** a sandbox, a shell parser or a statement that a command is safe. It never runs the
command, and `ALLOW` means that no rule matched: a transfer made by any other tool (`scp`, `rsync`, a
Python one-liner) matches no rule and is `ALLOW`. The mode changes only the exit code, never the verdict: in
`audit` every verdict exits 0; in `enforce`, `BLOCK` exits 2 and `MANUAL` exits 1. Whether a
verdict stops anything depends on what calls it — a hook on Claude Code, a preflight command on
Codex CLI.

**Verify:** `python -m hpp policy check --mode enforce --command "rm -rf src"` prints `BLOCK` with
rule `recursive-delete` and exits 2; `--command "git push origin feature"` prints `MANUAL` (rule
`external-push`) and exits 1; `--command "python -m pytest -q"` prints `ALLOW` and exits 0; the
same three with `--mode audit` print the same verdicts and exit 0.

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
