[English](README.md) · [Português](README.pt-BR.md)

# Cited and run — a criterion a test names is not a criterion a test ran

> New in 2.8.0.

A test cites an acceptance criterion by carrying `[spec: capability/scenario]` in its docstring,
and `hpp work coverage` links every criterion of a spec to the tests that cite it. That answers
"does a test name this criterion?". A skipped test still names it; so does a test the runner never
collected, and a test that fails. With a JUnit XML report of the run, the same command answers the
question that matters: **did a test that names it actually run and pass?**

| piece | where |
|---|---|
| the spec, three criteria | `workgraph.json` |
| three tests, one citing each criterion; one is skipped | `check_prices.py` |
| the ruler | `hpp/workgraph.py` · `hpp work coverage` |

`check_prices.py` is not named `test_*.py`, so the harness's own suite never collects it; pytest
runs it because the path is given on the command line.

## Run it

From the repository root:

```bash
python -m hpp work coverage examples/cited-and-run/workgraph.json --tests examples/cited-and-run/check_prices.py
python -m pytest examples/cited-and-run/check_prices.py -q -p no:cacheprovider --junitxml out/cited-and-run.xml
python -m hpp work coverage examples/cited-and-run/workgraph.json --tests examples/cited-and-run/check_prices.py --junit out/cited-and-run.xml
```

The first command reads citations only: all three criteria are cited, `complete: true`, exit 0.
The second runs the tests — two pass, one is skipped. The third joins the two: `member-discount`
and `rounding` are `executed`, `bulk-discount` is `cited_not_run` with its test marked `skipped`,
`complete: false`, exit 1. Nothing changed in the tests between the first answer and the third;
only the question did.

## What the report says

Without `--junit` the report is `hpp.spec-coverage/v1` (`covered`, `orphans`, `unknown`). With it,
`hpp.spec-execution/v1`:

| bucket | a criterion lands here when |
|---|---|
| `executed` | a citing test ran and passed, and none failed |
| `failed` | a citing test failed or errored — a pass elsewhere does not cancel it |
| `cited_not_run` | every citing test was `skipped`, is `not-in-junit` (deselected, never collected), is `not-a-test` (a module or class docstring), is `shadowed` (redefined later under the same name, so it never ran) or is `ambiguous` (its path matches cases of more than one module) |
| `orphans` | no test cites it |
| `unknown` | a marker names no declared criterion — a broken citation |

`complete` holds only when every criterion is `executed` and no citing source is newer than the oldest
report (`stale_sources`: a test edited after the run was not the test that ran); the exit code is 0
then and 1 otherwise. Each report is published with its sha256 (`reports`).
Two denominators come with it: `junit_testcases`, the cases read from the reports, and
`matched_testcases`, the ones joined to a citing test. Zero matched out of many read means the
report and the tests do not describe the same run — a wrong file or a wrong root — never that
nothing ran.

## Limits

Citations are read from docstrings only: a marker inside any other string is test data, not a
citation. A report case is joined to a test by pytest's convention — `classname` is the dotted
module path from the runner's root directory plus the class chain, `name` is the function plus
`[parameters]` — comparing the module by suffix, so the paths given to `--tests` and the runner's
root need not be the same directory. Other runners that write JUnit XML the same way are read the
same way; a runner with another convention matches nothing, and `matched_testcases: 0` says so. A
report that declares a DOCTYPE or an entity, or that is not UTF-8, is refused (exit 2), and so is a
`--tests` path with no Python file under it: an empty universe covers nothing.
