[English](README.md) · [Português](README.pt-BR.md)

# Policy contract fuzzing

The Fuzzing job builds the Python target with ClusterFuzzLite and runs Atheris/libFuzzer for 120
seconds on pull requests and pushes to main. Both the build and fuzz steps must succeed. The container image is
pinned by digest and the actions by commit SHA. Fuzzing dependencies live in that build image;
the HPP package keeps its standard-library runtime.

Every input exercises policy classification with generated literal rules, both action levels,
and optional raises of the built-in manual gates. The target checks that custom policy can
only strengthen the built-ins, repeated classifications and JSON round-trips agree, verdict
fields are valid, audit exits zero, and enforcement exits match the action. The same input is
also parsed as adversarial JSON for policy validation. Expected PolicyError rejections are
checked for determinism; unexpected errors escape to libFuzzer. Command strings are classified
in memory. The target does not execute them or use input as file paths or network addresses.

Arbitrary custom regexes are compiled by the JSON validation path. Custom regex searches use
generated literal patterns, keeping the campaign focused on the policy contract. Regex engine
performance on arbitrary user expressions is outside this target.

The corpus includes valid and rejected policy documents and fixed regex regressions. Replay
it with deterministic byte mutations from the product root, on Windows, macOS or Linux:

```sh
python3 -B fuzz/check_corpus.py --mutations 2000
```

That command verifies the properties without a coverage-guided engine. The native Atheris
campaign runs on Linux in CI. Atheris does not provide a Windows runtime. Its import
instrumentation covers the HPP policy code, rather than only the entry point.

For a local Linux build, use the ClusterFuzzLite build integration with this repository as the
external project. The three configuration files are in .clusterfuzzlite. The compiled target
is policy_fuzzer and its options bound inputs to 4096 bytes, each case to 5 seconds and RSS to
1024 MiB. The build produces a seed corpus and a dictionary beside the executable. The Python
wrapper uses Atheris' bundled libFuzzer without native sanitizer preloading, as required for
this pure-Python target. See the [Python build integration](https://google.github.io/clusterfuzzlite/build-integration/python-lang/)
and [Atheris runtime documentation](https://github.com/google/atheris).

A successful bounded campaign measures the cases and coverage it ran. Keep the CI log and any
reported reproducer when investigating a finding.

