[English](README.md) · [Português](README.pt-BR.md)

# Review lenses — one reviewer per kind of defect, one shape for every answer

> New in 2.8.0.

A reviewer asked to "look for problems" finds the problems it happens to look for. A **lens**
looks for one kind of defect, and every lens answers in the same shape, so two reviews of the same
change can be counted, compared and set side by side. The operator module ships four lenses as
sub-agents; the core only checks what they answer. They carry no file-editing tool; their read-only is **proved** when they are seated through the lane module's `house_session.py` (the worktree is fingerprinted around each answer), and is an instruction otherwise.

| lens | what it looks for |
|---|---|
| `verification-gap` | behaviour the change adds or alters that no test would notice breaking |
| `partial-set` | a change applied to some members of a set and not the others |
| `deletion` | something removed while something still depends on it |
| `stale-evidence` | proof cited for the change that predates it or was never re-run |

| piece | where |
|---|---|
| the change reviewed | `change.diff` (its sha256 is each document's `subject_sha256`) |
| a lens that found nothing, and says where it looked | `deletion-clean.json` |
| a lens that found one caller left behind | `partial-set.json` |
| the shape and its check | `hpp/findings.py` · `hpp findings check` |

## Run it

From the repository root:

```bash
python -m hpp findings check examples/review-lenses/deletion-clean.json
python -m hpp findings check examples/review-lenses/deletion-clean.json examples/review-lenses/partial-set.json
```

The first review passes: no finding, and `inspected` says what was read. Exit 0. With the second,
one `CALLER_NOT_UPDATED` at `checkout.py:18`, severity `medium`: verdict `warn`, exit 1.

## The shape — `hpp.findings/v1`

```json
{"schema": "hpp.findings/v1", "lens": "partial-set", "subject_sha256": "<sha256 of the change>",
 "inspected": ["what was read or run"],
 "findings": [{"code": "CALLER_NOT_UPDATED", "severity": "medium", "file": "checkout.py", "line": 18,
               "claim": "one sentence", "evidence": ["the command and what it returned"],
               "fix": "optional"}]}
```

| rule | why |
|---|---|
| a key the contract does not define refuses the whole document (exit 2) | a reviewer that improvises the form is improvising the judgement |
| `inspected` is never empty | "found nothing" without the universe reads the same as "looked at nothing" |
| every finding carries `evidence` | a finding without what was run or read is an opinion |
| `code` is stable `UPPER_SNAKE` | the same finding in the next round reads the same way |
| the same code, file and line twice is refused | rephrasing a finding does not make it two |
| the verdict is derived: `fail` on any `high`, `warn` on any other finding, `pass` on none | a reviewer cannot declare its own verdict |
| with `--subject FILE`, every document must name that file by its sha256 | a review of another change is refused, not read as a review of this one |

## Limits

The check reads the answer, never the change: it proves the review has the shape, not that the
review is right. What makes a lens worth running is the lens itself — a narrow question, asked
read-only, with the search it made declared — and whether it catches planted defects is measured
the same way as any reviewer.
