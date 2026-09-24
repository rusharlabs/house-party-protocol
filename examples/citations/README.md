[English](README.md) · [Português](README.pt-BR.md)

# Citations — a claim bigger than its proof becomes an exit code

> New in 2.6.0.

An answer built from sources should say which source each claim rests on. Here each claim carries
`[ID:<id>]`, where `<id>` is one entry of the context the answer was given (`context.json`). The
check reads those two files and nothing else, calls no model, uses no network, and says what the
answer claims that its sources cannot back:

| code | class | exit | what it means |
|---|---|---|---|
| `UNKNOWN_ID` | block | 2 | a marker names an id that is not in the context |
| `RANGE` | block | 2 | one marker names a range or a list (`1-3`, `1,2`, `1..3`): write one id per marker |
| `EMPTY_MARKER` | block | 2 | a marker with no id in it |
| `TOO_MANY` | warn | 1 | more than 4 markers in one sentence (the limit is configurable) |
| `UNCITED_CLAIM` | warn | 1 | a sentence with a number, percentage, currency amount or date and no marker |
| `NO_MARKERS` | warn | 1 | the text has no marker and no uncited number: nothing was checked, so it is not reported as clean |

Context the answer never cites is not a finding — the sources may be larger than the answer — and is
reported as a count (`unused_context_ids`). Empty text, text that is only code, an empty context, secret-like text
or context, a malformed context and an unusable marker regex are refused (exit 2) before any report
exists.

## Run it

```bash
python -m hpp cite check --text examples/citations/answer.md --context examples/citations/context.json
```

The same check from Python, available now:

```python
from hpp.citations import check_files, exit_for

report = check_files("examples/citations/answer.md", "examples/citations/context.json")
print(report["verdict"], report["counts"])
raise SystemExit(exit_for(report))
```

The shipped answer is clean: verdict `ok`, 7 sentences, 5 markers, 4 of the 5 context ids cited.
Change `[ID:glossary]` to `[ID:glossary-v2]` in a copy and the same check blocks with `UNKNOWN_ID`.

## Another marker syntax

```bash
python -m hpp cite check --text answer.md --context context.json --marker '\{cite:([^}]*)\}' --max-per-sentence 3
```

The regex needs exactly one capture group — the id — and must not match empty text.

## What it does not do

It never reads a cited source to see whether it supports the sentence. A marker that resolves proves
the id exists, not that the source says what the sentence says; that needs a reader. What this check
removes is the cheaper failure: a citation to nothing, and a number with no citation at all.

The sentence splitter and the number detector are heuristics, written out in full in the docstring
of `hpp/citations.py`. In short:

- a sentence ends at `.`, `?` or `!` followed by whitespace; `3.5` does not end one, nor does a full
  stop inside a marker or inside `code`; common abbreviations (`e.g.`, `Dr.`, `Inc.`, `et al.`,
  month names) do not end one, an abbreviation outside that list does;
- a marker right after the full stop, on the same line, belongs to the sentence that just ended;
- headings, list numbering, `code`, URLs and versions written with a `v` (`v2.5.8`) are not scanned
  for numbers, and fenced code blocks are skipped entirely, including a fence indented inside a
  list item;
- accepted false positives, as warnings: ordinals (`1st`), labels (`Step 2`, `RFC 2119`), a bare
  version (`2.5.8` cannot be told apart from a dotted date), a table row cited only in its caption;
- false negatives: numbers written as words, digits glued to a letter on their left (`Q3`).

## The report

`hpp.citation-check/v1` carries the sha256 of the text and of the context (canonical JSON, so
indentation and key order do not change it), the marker regex, the per-sentence limit, the counts
(`sentences`, `quantitative_sentences`, `markers`, `cited_ids`, `unique_cited_ids`, `context_ids`,
`unused_context_ids`), the findings — each with its code, severity, 1-based sentence and line, an
excerpt of at most 120 characters and a message — the verdict and the exit code.
