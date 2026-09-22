---
paths:
  - "**/evals/**/*"
  - "**/eval/**/*"
  - "**/*eval*.py"
  - "**/loop/**/*"
  - "**/_autonomy-registry.yaml"
  # Why (cross-model review of 2.5.0): `python scripts/passk_eval.py suite.json` via Bash opens
  # nothing under evals/; the suite file and its result are what the operator touches.
  - "**/*passk*"
  - "**/suites/**/*"
  - "**/*.suite.json"
---
# LOOP-PASSK — capability and reliability are different gates

> **Auto-Trigger:** eval of an agent, skill, workflow or release; autonomy promotion; flakiness investigation.
> **Keywords:** pass@k, pass^k, eval, k-runs, capability, regression, determinism, flaky, release.
> **Priority:** HIGH
> **Version:** 2.0.0

## Principle

A green result does not prove repeatability. For each case, run the same verification `k`
times and answer two separate questions:

- `pass@k`: did the case pass in at least one of the `k` attempts? Measures capability.
- `pass^k`: did the case pass in all `k` attempts? Measures reliability.

`pass^k <= pass@k` always holds. The difference between the metrics is the flakiness zone.

## Default gates

| Gate | Criterion | Decision |
|---|---:|---|
| Capability | `pass@k >= 0.90`, with `k=3` | below that, the implementation goes back to the maker |
| Regression | `pass^k == 1.00`, with `k=3` | below that, the release stays blocked |
| Both | both criteria | required for promotion of critical autonomy |

The threshold may be raised per domain. Lowering it to obtain green invalidates the measurement.

## Portable runner

The kit includes `scripts/passk_eval.py`, which reads a JSON suite and works without an external package:

```json
{
  "version": "1",
  "suite": "quality-gates",
  "cases": [
    {
      "id": "unit-tests",
      "runner": "command",
      "command": ["python", "-m", "pytest", "-q"],
      "expect_exit": 0
    },
    {
      "id": "known-replay",
      "runner": "replay",
      "outcomes": [true, true, true]
    }
  ]
}
```

```bash
python scripts/passk_eval.py --suite eval-suite.json -k 3 --gate both
python scripts/passk_eval.py --suite eval-suite.json -k 3 --gate regression --json
python scripts/passk_eval.py --self-test
```

`command` receives an argv and runs with `shell=False`. `replay` measures declared fixtures; it does not
simulate an agent call. Exit `0` approves, `2` blocks and `3` indicates a suite or
execution error.

## Choosing the verifier

Use the most deterministic verifier that measures the real behavior:

1. code: test, schema, exit code or checksum;
2. rule: format, presence, absence or explicit pattern;
3. model: rubric for open-ended quality, assuming variation of the judge itself;
4. human: sensitive or ambiguous decision that cannot be safely automated.

A case judged by a model may oscillate because of the object or because of the judge. Investigate both
before classifying the cause.

## Integration with the loop

1. Define positive, negative and regression cases before the implementation.
2. Run `k=3` during construction.
3. If capability fails, go back to the maker.
4. If capability passes and regression fails, remove the source of flakiness.
5. The independent checker validates the diff; pass@k/pass^k validates the behavior.
6. Only promote state or autonomy after the corresponding gate passes.

## Anti-patterns

- one green execution treated as stability;
- happy path only;
- a known case memorized by the agent;
- a stochastic grader as the only release-critical gate;
- a result without suite, hash, `k` and individual cases;
- runner unavailability treated as an approved self-test.

## Checklist

- [ ] Does the suite have a version, a name and unique IDs?
- [ ] Does each case use a real `command` or a declared `replay`?
- [ ] Are there positive and negative controls?
- [ ] Were `k` executions completed?
- [ ] Were pass@k and pass^k reported separately?
- [ ] Was the flakiness zone resolved or declared?
- [ ] Did the gate block the promotion when it should have?
