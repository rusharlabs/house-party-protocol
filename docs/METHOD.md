[English](METHOD.md) · [Português](METHOD.pt-BR.md)

# Method

The way of working that the harness enforces. A team can adopt it in a day, because every
practice ends in a command that either passes or reports what it measured. The commands below
use the harness CLI (`python -m hpp`) and, where a module is involved, the scripts that module
installs. Module paths are shown relative to the emitted distribution.

## 1. Open a unit of work

Work starts as a spec, not as a conversation. A spec is a list of units, each with an `id`,
its `depends_on`, at least one acceptance criterion written as something a command can decide,
and a `tier` that states how much risk it carries. The harness compiles the spec into a WorkGraph
and derives waves from the dependencies. Units in the same wave may run in parallel; a unit whose
dependencies have not closed does not start.

Before touching files in a shared repository, the session claims a lane: an id, the paths it
will own, and a heartbeat it will keep updating. Two live lanes may not overlap on exclusive
territory. A lane that stops heartbeating loses its claim by time, not by someone deleting a lock.

Then the first event is recorded, and the loop leaves `planned`.

```bash
python -m hpp work plan SPEC.json
python -m hpp work waves SPEC.json
python multi-sessao/lane-kit-1.2.0/scripts/lane_board.py claim --help
python -m hpp event append --type work_started --data '{"work":"ITEM-1","actor":"maker-a"}'
```

## 2. Declare done

"Done" is a state the harness enters, not a word the agent says. It requires the acceptance
criteria to run as commands and exit 0, in the current checkout, now. The done gate takes the
criteria as arguments, runs each one, and prints `DONE-GATE: DONE` only when all pass. When some
criterion cannot pass yet, the correct output is a declared partial: the gate accepts
`--declare-partial "<what is missing>"` and reports `PARCIAL-DECLARADO` with that text and a
non-zero exit. Without the declaration it reports `NOT-DONE`. Silence is not a state; an
undeclared partial is a failure.

Once the criteria pass, the evidence is recorded in the event log with a reference to where the
output lives. The loop moves to `evidenced`. It cannot move to `verified` without at least one
such record.

```bash
python frameworks-com-plugins/operator-kit-1.4.0/scripts/done_gate.py "python -m pytest -q" "python -m py_compile app.py"
python frameworks-com-plugins/operator-kit-1.4.0/scripts/done_gate.py "python -m pytest -q" --declare-partial "external target not yet validated"
python -m hpp event append --type evidence_recorded --data '{"work":"ITEM-1","ref":"artifacts/pytest.txt"}'
```

## 3. What counts as proof

A proof is reproducible by someone who was not there. It carries the command, the output or exit
code, the version or commit it ran against, the scope it covered, and the time it ran. Any claim
that lacks one of the five is a report of a belief.

Two further rules separate proof from a green light. A number is published with the instrument
that produced it, so that the next person can re-derive it instead of trusting it. And an
instrument is trusted only after a control: pointed at a case known to be good and a case known
to be bad, it must answer differently. A checker that would say "zero problems" about a broken
tree cannot be used to say "zero problems" about a good one.

When a checker approves, the approval is bound to bytes. The attestation records the spec hash,
the base commit and a snapshot of every tracked and untracked file. If the checkout changes
afterwards, the approval is blocked on verification and must be given again on the new bytes.

```bash
python -m hpp attest create --repo . --spec SPEC.md \
  --maker maker-a --checker checker-b --session review:001 \
  --verdict approved --output .hpp/attestation.json
python -m hpp attest verify .hpp/attestation.json --repo .
```

## 4. Review without a pen

The checker is a different actor from the maker, preferably on a different provider, and holds
no write tools. Without a pen, the checker cannot "fix it and move on"; it has to point, with
severity, file and line, and the maker has to answer. That friction is the mechanism: it is what
makes a process defect visible instead of silently patched.

The checker's report keeps the same criteria across rounds, names findings by a stable code
rather than an adjective, and never asks the maker something it could verify itself by running a
command. When no checker from a different provider is available, the review is recorded as not
done, not as done by the maker.

The checker's pass is an event. The loop moves from `evidenced` to `checked`.

```bash
python multi-sessao/lane-kit-1.2.0/scripts/checker_router.py --maker claude --require
python -m hpp event append --type check_passed --data '{"work":"ITEM-1","checker":"checker-b"}'
```

## 5. When the budget runs out

Every loop declares its budget before the first iteration: iterations, time, and whatever the
host meters. Stopping on budget is one of three legitimate ends, next to "the criterion passed"
and "the circuit breaker tripped". It is not a failure and it is not a reason to try one more
time.

The loop driver in the operator module reads a charter with the criteria and a maximum number of
iterations. A completion tag in the model's output does not release the loop; the done gate is
re-run by the hook, outside the model's reach, and only its exit code counts. When the budget is
reached, the driver stops, reports where it stopped and what remains, and waits for a person to
extend the budget or close the work. Extending the budget is a human decision, never something
the loop grants itself.

```bash
python frameworks-com-plugins/operator-kit-1.4.0/hooks/ralph_gate.py start \
  --charter "<objective>" --criteria "python -m pytest -q" --max-iterations 10
python frameworks-com-plugins/operator-kit-1.4.0/hooks/ralph_gate.py status
python frameworks-com-plugins/operator-kit-1.4.0/hooks/ralph_gate.py cancel
```

## 6. Resume after an interruption

The recovery boundary is the last recorded event, not the last thing anyone remembers. After a
crash, a context reset or a new day, the next step is derived from the event log: `hpp status`
projects the log onto the loop and names the state; `hpp resume` returns the next step as JSON.
Neither consults a summary and neither asks the model to reconstruct what happened.

A restored summary or handoff is reference material. Before re-running anything it describes,
the session checks whether that step already produced its effect (a file, a commit, an event). A
step that already ran is not run again. When a step was accepted but its confirmation was lost,
it is marked as unknown together with the command that resolves the doubt, and it is inspected
before it is retried.

```bash
python -m hpp status --json
python -m hpp resume
```

## 7. Every gate is born with a test that forces it to fail

A gate that has only been seen passing cannot be distinguished from a gate that is missing. So
a gate enters the codebase with two proofs. The first is a test that feeds it the case it exists
to stop and asserts that it stops; if the gate were removed, this test would fail. The second is
the call site: evidence that the gate is actually invoked on the live path, not merely defined.

The same rule applies to bug fixes. The test is written first and run to see it fail for the
right reason; then the fix; then the test again. A test written after the fix proves that the
current code works, not that anything was fixed. When both sides of a fix produce the same
result, the proof does not discriminate, and the usual cause is an earlier guard stopping the
path before it reaches the defect.

The benchmark is this rule applied to the harness itself: ten controls, each with a positive and
a negative case, run `k` times, with `pass^k = 1.00` required.

```bash
python -m pytest tests/test_policy.py -q
python -m hpp eval run examples/reliable-coding/benchmark-suite.json -k 3 --gate both
python -m hpp benchmark -k 3 --json
```

## 8. Plan before apply

Anything that writes shows its plan first and writes on a second, explicit invocation. The plan
lists what exists in the target and will be preserved, what would be written, and what stays a
human action. Neither `hpp init` nor the module installer blocks on a terminal prompt; the "yes"
is the re-invocation with `--apply`, which works the same for a person and for an agent acting
on their behalf.

Settings, hooks and `AGENTS.md` are never written by the harness. The wire block is printed for a
person to paste, and the doctor is run afterwards to confirm the result.

```bash
python -m hpp init --target ../your-repo
python -m hpp init --target ../your-repo --apply
python instaladores/kit-forge-1.4.0/kit_doctor.py install --kit <module-dir> --host codex --target ../your-repo
python instaladores/kit-forge-1.4.0/kit_doctor.py install --kit <module-dir> --host codex --target ../your-repo --apply
python -m hpp doctor
```

## 9. A human gate where the action is irreversible

The command policy classifies what an agent is about to run. Recursive deletion in any flag
order, force pushes, pushes to `main` or `master`, piping a download into a shell and destructive
SQL are `BLOCK`. Any push and any outbound transfer are `MANUAL`: the action may be right, and a
person confirms it. In `enforce` mode the classifier returns exit 2 and 1 respectively; in
`audit` mode it reports the verdict and exits 0, so a team can measure false positives before
switching.

In the loop, the human gate is an event. `checked` becomes `approved` only through
`human_approved`, and the final `verified` requires that step to have happened.

```bash
python -m hpp policy check --mode audit --command "git push origin feature"
python -m hpp policy check --mode enforce --command "rm -rf build"
python -m hpp event append --type human_approved --data '{"work":"ITEM-1","by":"operator"}'
python -m hpp event append --type verified --data '{"work":"ITEM-1"}'
```

## The loop, end to end

```text
work_started ─▶ evidence_recorded ─▶ check_passed ─▶ human_approved ─▶ verified
   [scope]        [fresh-evidence]   [read-only-checker]   [human]        [closure]
```

Each arrow is an appended event. Each gate is a condition the harness checks before the append.
`hpp status` tells you where you are; `hpp resume` tells you what comes next.
