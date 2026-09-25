[English](README.md) · [Português](README.pt-BR.md)

# Criterion sensitivity — would your check notice if the code were wrong?

> New in 2.7.0.

A green criterion proves that nothing it checks is broken. It does not prove that it checks
anything that matters. `hpp evidence mutate` measures the other half: it runs the criterion on a
**copy** of the workspace, first on the clean tree (it must pass — otherwise the measurement has no
control), then once per **mutant**, a copy with one small change that makes the code wrong (it must
fail). A mutant the criterion lets through is a **blind spot**, named by file and line.

| piece | where |
|---|---|
| the code under test | `discount.py` — a price rule with two boundaries |
| a criterion that pins the boundaries | `check_strong.py` |
| a criterion that is green and checks comfortable cases only | `check_weak.py` |
| the ruler | `hpp/evidence.py` · `hpp evidence mutate` |

## Run it

From the repository root:

```bash
python -m hpp evidence mutate --id strong --generate examples/criterion-sensitivity/discount.py -- python examples/criterion-sensitivity/check_strong.py
python -m hpp evidence mutate --id weak --generate examples/criterion-sensitivity/discount.py -- python examples/criterion-sensitivity/check_weak.py
```

Both criteria pass on the clean code. The first kills all three mutants: verdict `sensitive`,
score 1.0, exit 0. The second lets all three through: verdict `blind-spots`, score 0.0, exit 1, and
`survivors` names each one — `examples/criterion-sensitivity/discount.py:6 and -> or`,
`examples/criterion-sensitivity/discount.py:6 >= -> >`, `examples/criterion-sensitivity/discount.py:8 >= -> >`. None of the second criterion's asserts is wrong; it simply never looks at
100.00 or 50.00, where the rule changes.

## Where mutants come from

- `--generate FILE` reads a Python file with the standard tokenizer and makes one mutant per
  operator token from a fixed table: `==`↔`!=`, `<`↔`<=`, `>`↔`>=`, `and`↔`or`, `True`↔`False`.
  Text inside strings and comments is never mutated: a swap there changes nothing and would read
  as a blind spot.
- `--mutants FILE` declares mutants by hand, for any language, as an `hpp.mutants/v1` file:

```json
{"schema": "hpp.mutants/v1", "mutants": [
  {"id": "member-threshold", "file": "examples/criterion-sensitivity/discount.py",
   "find": "total >= 50", "replace": "total >= 51"}
]}
```

The example ships this file as `mutants.json`; pass it with `--mutants`. `find` is replaced at its first occurrence, or at `occurrence` when given. A `find` that is not in
the file is `not-applied`, counted apart and never as killed. Both options can be combined.

## What the record says

The record (`hpp.mutation/v1`, written to `.hpp/evidence/<id>-mutate-<UTC>.json` with a self-hash)
holds the clean run, one entry per mutant with its outcome, and:

| verdict | meaning | exit |
|---|---|---|
| `sensitive` | the clean run passed and every applied mutant was killed | 0 |
| `blind-spots` | at least one mutant survived; `survivors` names them | 1 |
| `incomplete` | no survivor, but the criterion could not start on some mutant | 1 |
| `no-mutants` | no mutant could be applied | 1 |
| `no-control` | the criterion did not pass on the clean tree: no mutant runs, no score | 2 |

`score` is killed ÷ (killed + survived), or null when nothing was measured — never 0%. A run that
times out on a mutant did not pass, so it kills it; the entry says it timed out.

## Limits

Every run — the clean one and each mutant — gets its own fresh copy, so a criterion that creates
a directory or a table on its first run cannot fail the next ones for its own reasons. The copy
leaves out exactly `.git`, `.hpp`, `__pycache__`, `node_modules`, `.venv`, `venv` and `.tox`; a
mutant file under one of them, reached through a symlink, or not UTF-8 is refused before anything
runs. The command runs inside the copy: give it relative paths. Anything that makes the criterion
read the original tree instead — an absolute path, an editable install (`pip install -e .`), a
`PYTHONPATH` pointing at the checkout, an absolute symlink inside the tree — makes every mutant
survive, and the record cannot tell that apart from real blind spots. hpp writes only inside the
copies, but the criterion runs with your permissions: an absolute symlink kept in the copy still
lets it write into the original tree. The control for it: declare
one mutant you know the criterion kills; if it survives, the criterion is not looking at the copy.
A criterion that needs git history fails on the clean copy and reports `no-control` instead of a
false score. The operator table is small on purpose; a surviving mutant can also be equivalent (a
change that does not change behaviour), which only a reader can tell.
