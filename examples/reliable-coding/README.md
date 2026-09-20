# Reliable coding example

This fixture is a deterministic, offline benchmark for the harness. Its nine
controls execute real HPP mechanisms with positive and negative cases; they do
not replay pre-approved outcomes. A passing result proves only those declared
controls, not model quality or remote service health.

```text
python -m hpp benchmark -k 3 --json
python -m hpp event append --type work_started
python -m hpp resume
```

The event sequence is intentionally strict: work, evidence, read-only check,
human gate, then verification. A recorded event is the recovery boundary; no
background process is required.
