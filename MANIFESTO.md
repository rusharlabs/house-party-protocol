[English](MANIFESTO.md) · [Português](MANIFESTO.pt-BR.md)

# House Party Protocol Manifesto

## Capable agents still need an operating house

House Party Protocol is a harness for operating coding agents under evidence. The model reasons.
The harness bounds, observes, records, verifies and decides when work may advance.

A convincing answer is not proof. An open session is not coordination. A process that responds is
not fresh data. An author reviewing their own work is not independent review. HPP exists to turn
each of those differences into a contract that a command can check.

## The protocol

The protocol is the set of invariants every module and every host must respect:

1. Declared state does not replace measured state.
2. Maker and checker are different actors, and the checker holds no pen.
3. Completion requires a criterion, a command, its output and its freshness.
4. Concurrent work declares a lane, an owner and a territory.
5. A wave closes its barrier before the next one opens.
6. Resumption derives from the event log, never from the memory of a conversation.
7. A monitor keeps availability, freshness and correctness apart.
8. Policy distinguishes a warning, a block and a human gate.
9. Capability and reliability are measured separately, as `pass@k` and `pass^k`.
10. A distributed artifact is reopened and verified before it is called a release.

Four of these are written into `hpp.manifest.json` as machine-checked invariants: a verified
outcome has recorded evidence and an explicit human gate; a checker is read-only relative to the
maker's workspace (no `Write` or `Edit` tool; `Bash` stays, so the working tree is compared
before and after the review); a loop advances only through a recorded event; an approval is invalid once its
bound spec, commit or repository snapshot changes. The rest are enforced by the modules that
implement them and by the tests that force them to fail.

## The harness

The harness makes the protocol operable. It holds a manifest of capabilities, compiles a spec into
a WorkGraph, orders dependencies into waves, projects lane and agent maps, compiles context with
provenance, appends events, derives resumption and binds evidence to a verdict.

The modules provide the specialised mechanisms. Distribution carries them to Claude Code and Codex
CLI without pretending the two hosts offer the same lifecycle hooks.

## Order comes from the spec, not from the conversation

Work enters the house as a spec: units with an id, the units they depend on, the criteria that
decide them and the risk they carry. The harness compiles it, refuses a cycle with the path
named, and returns waves. A dependency that was discussed but never written in `depends_on` does
not exist for the harness, and no amount of context in a transcript makes it exist.

Parallelism is a consequence of that graph, not a goal. Units with no edge between them fall in
the same wave; a unit waits for the last of its dependencies. Nobody sets a number of parallel
agents, and nobody is asked whether two units "can" run together: the absence of an edge already
answered. Running everything at once would ignore the edges; running by wave ignores nothing and
still runs together everything that may.

The barrier is what makes progress legible. When a wave closes, every unit in it has met its
criteria; a unit of the next wave that starts early builds on a dependency that has not passed,
and its evidence describes a checkout that may not survive. "Wave two is closed" is a sentence a
command can check. "We are about seventy percent done" is not.

What this does not promise: the harness does not discover dependencies. It does not read the
files a unit will touch, it does not deduce that two units collide from what they do, and it does
not stop an operator from starting a unit before its wave. It compiles the dependencies that were
declared, reports where each barrier is, and leaves the declaring and the honouring to the people
and agents doing the work. A missing edge is a defect in the spec, and the spec is where it is
fixed.

## Why this is not bureaucracy

Process fails in two directions. Process that protects makes the cost of an error visible before
the error is committed. Process that obstructs makes people pay that cost on every step, whether
or not an error was possible. The difference is not the amount of ceremony. It is whether each
step answers a question that would otherwise be answered by guessing.

Every gate in HPP is a question with a measurable answer: did the criterion command exit 0; is the
snapshot the same one the checker saw; is this lane alive; is this signal fresher than its declared
freshness; does this command match a destructive form. When the answer is yes, the gate costs one
command and nothing else. When the answer is no, the gate reports what was measured, what was
expected and what to do next, and the person decides.

Three properties keep the gates on the protecting side. First, a gate never asks what it can
measure: readiness, liveness, freshness and checksums are computed, not requested. Second, a gate
that would fire on legitimate work is not shipped; `hpp policy check` blocks `rm -rf`, `rm -fr`
and `rm --recursive --force`, and leaves `rm file.txt`, `grep -rf patterns.txt` and `cp -rf a b`
alone, because a guard that shouts at the innocent is switched off before the day it is right.
Third, every gate ships with the test that forces it to fail, so that a gate that has quietly
stopped gating is caught by the suite and not by an incident.

Bureaucracy is a step whose absence nobody would notice. Each step here has a failure it was
built for, written down next to it.

## What the project refuses to do

These are decisions, not gaps. Each has a reason that would have to change before the decision
does.

- **No daemon, no server, no scheduler.** A check that did not run was not run. A background
  process would make "is it running?" a second question to verify, and would carry state that the
  event log does not see. The `hpp` package runs none. *A bounded exception, for modules only:* a
  module may serve a local page that the operator starts and stops (lane-kit's Lane Dashboard is
  the one that does), under all of these conditions: it binds loopback only and answers only its
  own page; every action carries a token issued for that run; the page refuses to be framed; a
  request that only reads writes nothing and starts nothing; every write goes through the module's
  own command-line tools, and every action is also a terminal command that does exactly the same;
  nothing schedules it, and what it runs stays within the bounds of the next item. The page itself
  sends nothing off the machine.
- **No model calls.** The harness routes work to a tier and a provider id you declared. It does
  not pick a vendor, a model name or a price, and it holds no credential. The moment it called a
  model, its verdicts would depend on something it cannot reproduce. A decision you obtain
  elsewhere can be recorded and measured (`hpp decide`); the example adapter that asks a hosted
  model lives in `examples/`, runs only when a person runs it, and the policy classifies it `MANUAL`.
  *A bounded exception, for modules only:* such a page may start an agent session, and only as an
  action the operator confirms, never from a request that only reads, never on a timer and never by
  itself, with the model the operator declared for it. A session that runs in the background runs
  under a supervisor with a timeout, a stop and a capped log. The session is the operator's agent,
  on the operator's own account; the `hpp` package still calls no model, picks none and holds no
  credential. The same exception covers lane-kit's `/deliberate` and its `house-session` skill:
  when the operator invokes them, `house_session.py seat` runs the agent CLI the operator gives
  each seat of a panel, and nothing schedules it. Before running anything it refuses a panel the
  core does not accept and a seat or a round outside that panel; it runs the command in the seat's
  worktree (`--root`) through the core's bounded runner, whose timeout (600 seconds unless the
  operator sets another) stops the command's whole process tree; and it fingerprints git's view of
  that worktree before and after (status, the diff against HEAD, untracked contents, HEAD and
  every ref, the worktree list, the config, the hooks and `info/exclude`). A seat that moved any of
  it gets no turn, and a seat that fails or times out is not judged. The fingerprint does not see
  a write into a path the repository ignores, nor what a seat does outside its worktree with the
  operator's permissions.
- **No graph database.** Every map is a projection of manifests, events and JSON you supply. The
  same input yields the same nodes and edges, in the same order, and you can hash the result. A
  stored graph would be a second source of truth that drifts from the first.
- **No silent writes.** `hpp init` plans first and writes one file on `--apply`. The module
  installer plans first and applies on a second explicit invocation. Neither touches
  `settings.json`, hooks or `AGENTS.md`; that wiring is printed for a person to paste.
- **No promise accepted as evidence.** A completion tag in a transcript does not stop a loop; the
  done gate re-runs the criterion commands outside the model's reach. An empty output, an
  identical maker and checker, or a verdict other than `approved` never becomes proof.
- **No host parity by assertion.** Claude Code runs a module's hooks once they are wired; Codex CLI
  has hooks of its own, and HPP does not load its hooks there. Coverage is declared per module as
  `native`, `explicit-command` or `unsupported`, and an unsupported
  module halts the plan instead of being installed as if it worked.
- **No headline numbers.** The count of modules is not a quality claim. A number appears next to
  the command that produced it or it does not appear.
- **No remote telemetry.** Nothing leaves the machine unless a person runs a command that sends
  it, and that command is classified `MANUAL` by the policy.

## Loops with brakes and memory

A useful loop has an objective, an observation, an action, a budget, a gate, a stop condition and
an escalation path. Without them, repetition is insistence with a timer.

Autoprompt preserves continuity: it answers "what is the next step derivable from the recorded
state?" Gotchas preserve operational memory: a failure that recurs becomes a lesson injected
before the next attempt, and is redacted by shape before it is stored. Monitors preserve awareness
of state. None of the three grants a loop the right to run past its budget, its territory, its
evidence gate or the human gate when one is declared. Stopping on budget is a legitimate end,
recorded as such, not a failure.

## Graphs without infrastructure theatre

HPP uses graphs as explanations, not as decoration and not as a reason to stand up a database.
Capability, agent, lane, work, execution, evidence, context and monitor maps are derived from
local files. If an edge does not change a decision, it is not drawn.

## Honest portability

Two hosts is not one identity. Claude Code can run hooks on `Stop`, `PreToolUse` and
`SessionStart`; Codex CLI reads `AGENTS.md` and skills, and runs the rest as explicit commands.
The doctor shows the difference. Missing coverage is `unsupported`, never "probably works".

## Proof before scale

HPP does not call itself reliable for having many components. Reliability comes from negative
controls, repeated execution, independent review and a verifiable release chain. A critical
release must demonstrate its floor, `pass^k`, not the best result it ever obtained.

## More agents, more claims

A team of agents multiplies what one agent already does: it claims. Each session reports its own
"done", a reviewer from the author's model family can share the author's blind spots, and a panel
drawn from one family can agree for the same reason it is wrong. Adding agents adds output; it adds
nothing to proof. The harness does not make a team more capable and does not decide how many agents
to run. It holds every member to the same contracts: work splits only where the spec has no edge, a
verdict comes from another lane and another model family, a deliberation keeps the dissent that
lost, and nothing reaches `verified` without a criterion, a command, its output and its freshness.
More agents is a reason for more evidence, not less.

## The commitment

Operate agents under evidence. Keep maker and checker apart. Expose the limits of each host. Make
state resumable from what was recorded. Block the completion that did not pass its gate.

That is the house. The protocol is the rules. The modules are the tools. Proof is what opens the
next door.
