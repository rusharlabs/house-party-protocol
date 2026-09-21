[English](BENCHMARK.md) · [Português](BENCHMARK.pt-BR.md)

# Reproducible benchmark

The public benchmark measures the local harness without calling model APIs.

## Run

```bash
python -m hpp doctor
python -m hpp benchmark -k 3
python -m hpp benchmark -k 3 --json
```

## Scenarios

| Scenario | Positive control | Negative control | Gate |
|---|---|---|---|
| manifest | ten modules resolved | integration points at a missing module | validation blocks |
| policy | safe command | destructive operation | enforce returns 2 |
| event log | valid sequence reaches verified | verified without evidence | append is refused without creating the log |
| WorkGraph | DAG with two waves | cycle A→B→A | compilation fails |
| Lane Map | dead lane does not block | live overlap | collision appears |
| Monitor Map | fresh signal | service online/data stale | separate dimensions |
| context | source with hash and budget | secret-like material | compilation refuses |
| routing | safe work uses economy | high risk without frontier | floor is not lowered |
| graphs | same input twice | empty projection | identical and non-empty JSON |

## Criterion

The benchmark runs each local control `k=3`; it does not use replayed outcomes as ready-made
truth. Release-critical cases require `pass^k=1.00`. The JSON output includes version, platform,
suite hash, attempts and individual results. ZIP integrity is a separate release gate.

The benchmark proves only the checkout, the platform and the scenarios that ran. It does not
measure the general quality of a model and does not turn a host without lifecycle hooks into
automatic enforcement.
