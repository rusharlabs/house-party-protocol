[English](README.md) · [Português](README.pt-BR.md)

# Retrieval ruler — measure the retriever apart from the answer

> New in 2.6.0.

When an answer built on retrieved text is wrong, two different things can have failed: the
retriever did not bring the right passage, or the generator misused a passage it had. This example
measures only the first. The harness still runs no index and calls no model
([MANIFESTO](../../MANIFESTO.md)): the retriever is a command **you** declare, and the ruler scores
the ids it ranks against the ids you labelled relevant.

| piece | where | runs anything? |
|---|---|---|
| the suite `hpp.retrieval-suite/v1` | `suite.json` | no |
| the ruler | `hpp/retrieval.py` · `hpp retrieval eval` | only the command you name |
| a keyword baseline | `keyword_retriever.py` over `corpus.json` | no model, no network, standard library only |

## The contract

The ruler sends one request per case on stdin, as ASCII-escaped JSON. The case id is not sent.

```json
{"query": "how do I restore a backup", "k": 3}
```

The retriever prints its ranking, best first: a list of ids, or objects with an `id` and an
optional `score`.

```json
{"results": [{"id": "backup-restore", "score": 2}]}
```

The printed order **is** the ranking. A `score` must be a finite number or null; it is checked and
never used to re-sort, because a distance and a similarity sort in opposite directions. Extra keys
are ignored. Print ASCII-escaped JSON (`json.dumps` does by default) so the answer reads the same in
any console codepage.

Return the unit the suite labels. If the suite labels documents and the index holds chunks, collapse
chunks to their document before answering: a duplicate id in one answer is an instrument failure,
because counting it twice would inflate precision and nDCG.

A case in the suite:

```json
{"id": "disk-full", "query": "the disk is full and uploads fail",
 "relevant": ["disk-full", "log-rotation"],
 "results": [{"id": "disk-full", "score": 3}]}
```

## Running it

```bash
echo '{"query": "how do I restore a backup", "k": 3}' | python examples/retrieval/keyword_retriever.py

python -m hpp retrieval eval examples/retrieval/suite.json

python -m hpp retrieval eval examples/retrieval/suite.json \
  --retriever-command '["python", "examples/retrieval/keyword_retriever.py"]'
```

Without `--retriever-command` the ruler replays the `results` each case carries — here, what
`keyword_retriever.py` returned when the suite was written (a test keeps the two in step). With it,
the ruler runs your command once per case, with `shell=False` and a timeout (`--timeout`, 10 s by
default). `-k` overrides the suite's k.

## What the report separates

Per case, over the top k: hit@k, recall@k, precision@k (divided by k, so an empty answer scores 0),
reciprocal rank, and nDCG@k with binary relevance and a log2 discount.

| outcome | meaning |
|---|---|
| `measured` | the retriever answered; an answer with nothing relevant is a real 0 |
| `instrument-failure` | could not start, timeout, non-zero exit, empty or non-JSON output, a duplicate or non-string id — counted apart, never scored |

Aggregates are means over **measured** cases only. With no measured case they are null and the gate
says `no case was measured (N instrument failures)`, never 0%. The gate passes when at least one
case was measured, instrument failures are at most `--max-failures` (default 0), and mean recall@k
is at least `--min-recall` (default 0.8). Exit 0 when it passes, 1 when it does not, 2 when the
suite or an argument is refused. A query that looks like it carries a secret is refused before
anything runs, and the error names the case.

⚠️ **About the shipped suite.** Seven questions over ten articles, all synthetic and written by
hand, and the keyword baseline was written alongside them — so its score proves only that the ruler
works. On it the baseline reaches a mean recall@3 of 0.786 and the default gate fails: it misses the
paraphrased question entirely (`paraphrase`) and finds one of the two articles that answer
`disk-full`. A case with more relevant ids than k cannot reach recall 1; choose k with that in mind.
Build your suite from your own labelled queries before reading any number as quality.
