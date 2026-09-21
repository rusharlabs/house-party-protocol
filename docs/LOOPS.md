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

## Evaluation

pass@k measures whether the system can; pass^k measures whether it repeats. The loop only treats
release-critical work as stable when the regression gate passes in the declared universe and `k`.
