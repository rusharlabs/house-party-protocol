[English](LOOPS.md) · [Português](LOOPS.pt-BR.md)

# Loops, autoprompt and waves

## Governed loop

An HPP loop has:

1. objective and spec;
2. observable state;
3. next action;
4. time/iteration budget;
5. evidence gate;
6. stop conditions;
7. human escalation;
8. persisted feedback.

`ralph_gate.py` implements the stop gate: a textual completion mark does not release the loop
unless the corresponding `done_gate` passes. `autoprompt_resume.py` produces resumption; it does
not change the verdict.

For an end-to-end or visual criterion the latch is `hpp evidence run` (new in
2.6.0): it re-executes the declared command, measures its
exit code outside the model and hashes the artifacts it left. `hpp evidence verify` is later
reconciliation — it re-derives a record from the files on disk — and never the latch: the record's
self-hash makes an edit visible, it is not a signature, so whoever must not trust the maker runs
the command again. hpp drives no browser; the browser runs inside the command you declare.

## Autoloop and LoopGraph

Autoloop is the finite cycle `observe → choose → act → verify → record → stop/continue`. In HPP it
does not mean autonomy without a ceiling. The `loop` in `hpp.manifest.json` is the minimal
LoopGraph: states, events, gates and allowed transitions. Intentional repetition lives in the
charter with a budget and an exit; an accidental cycle in the WorkGraph is an error.

## Spec-driven

The spec is compiled into a WorkGraph. Acceptance criteria travel with each unit. Dependencies
become topological waves and each wave closes tests and review before releasing the next one.

## Autoprompt

Autoprompt answers "what is the next step derivable from the state?". It does not decide risk,
does not approve a sensitive change and does not replace a checker. If the state is insufficient,
the correct output is to declare the missing data.

## Failure memory

Gotcha Memory classifies failures, measures recurrence and proposes a lesson. Promotion is
controlled to avoid turning an isolated or ambiguous incident into a permanent rule.

A failure that matches no family stays `unknown` and is never relabelled automatically. An
advisory relabel through `hpp decide` (new in 2.6.0) is offline: a person runs it, never a hook,
after measuring the decider with `hpp decide eval`; the record stays advisory, and a new family
enters the classifier only as a reviewed change.

## Evaluation

pass@k measures whether the system can; pass^k measures whether it repeats. The loop only treats
release-critical work as stable when the regression gate passes in the declared universe and `k`.

The same rule applies to the instruments a loop leans on. `hpp retrieval eval` measures a
retriever and `hpp decide eval` a decider (both new in 2.6.0), each on labelled cases, with
instrument failures — a timeout, a crash, a malformed answer — counted apart and never scored.
Best-of-N, where N lanes build alternatives and a reviewer from another lane and model family
selects one (`lane_board.py compete` and `select`, new in 2.6.0), is pass@N: choosing 1 of N measures
that the system can, not that it repeats, so the winner still needs its own verification and
pass^k.
