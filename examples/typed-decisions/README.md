[English](README.md) · [Português](README.pt-BR.md)

# Typed decisions — an optional advisor you declare and measure

The harness calls no model and holds no key ([MANIFESTO](../../MANIFESTO.md)). That does not
change here. What this directory shows is how a decision made **outside** the harness — by a hosted
typed-decision model, a local model, a rule or a person — enters it as evidence you can check:

| piece | where | calls a model? |
|---|---|---|
| the record `hpp.decision/v1` | `hpp/decision.py` · `hpp decide validate` | no |
| the ruler | `hpp decide eval` | no — it runs the decider **you** name, as a command |
| a lexical baseline | `baseline_decider.py` | no |
| an HTTP adapter | `decide.py` | **yes**, only when you run it, with your own key |

`hpp init --decision-advisor typesafe|openrouter|compatible` records which advisor you declared
and prints these steps. The default is `off`.

## Read this before sending anything

Before you rely on any hosted decider, assume these until your own measurements say otherwise:

1. **A valid answer can be wrong.** The schema only guarantees that the answer is one of your
   options, not that it is correct.
2. **`confidence` is a formula over the distribution, not a probability of being right**, and its
   calibration depends on the question. Calibrate the floor per question, on your own labels.
3. **The vendor has no abstention state.** Abstention here is ours: low confidence → `abstention`.
4. **The judged text is not treated as hostile.** Instructions planted in the judged text can
   shift the answer. Pass `--declared <value>` and the record becomes `raise-only`: advice can
   raise the value you declared, never lower it.
5. **Shell text can be refused upstream.** A state that contains shell commands such as `curl` can
   come back as an HTML error page instead of JSON. That, a timeout, or any non-JSON answer is an `instrument-failure`.
6. **English is the vendor's primary language.** Portuguese and other languages: measure first.
7. **Nothing is reproducible by asking again.** The record keeps the pinned model that answered and
   the hash of the raw response, which is written beside it (`.hpp/decisions/raw/`).
8. **Every call sends the text off your machine.** Never call an advisor from a hook, never send
   secrets (the adapter refuses secret-like text), and read your provider's data terms.
   `hpp policy check` classifies running `decide.py` as `MANUAL`, like `curl` to a URL.

Version 1 measures **choice** questions only. A score or a probability of yes has no agreed
definition of "correct", so the contract refuses those kinds instead of reporting a vacuous 0%.

## The three outcomes

| outcome | meaning |
|---|---|
| `recommendation` | a value from your options, with the confidence the decider reported (or null) |
| `abstention` | the decider would not choose — changes nothing |
| `instrument-failure` | timeout, HTTP error, HTML, malformed answer — changes nothing, never a verdict |

With `direction: raise-only` and a `declared` value, `hpp decide validate` prints the **effective**
value: the higher of the two on the question's ordered options.

## Measure before you trust

```bash
# the baseline every advisor has to beat
python -m hpp decide eval examples/typed-decisions/gotcha-family-suite.json \
  --decider-command '["python", "examples/typed-decisions/baseline_decider.py"]'

# your advisor, on the same cases (the key lives only in your shell)
export TYPESAFE_API_KEY=<your key>
python -m hpp decide eval examples/typed-decisions/gotcha-family-suite.json \
  --decider-command '["python", "examples/typed-decisions/decide.py", "--provider", "typesafe", "--model", "jev-1.13.0"]'
```

The report separates **coverage** (how often it decided), **selective accuracy** (how often it was
right when it decided), **confident errors** (wrong above the suite's floor), correct and missed
abstentions, instrument failures, a **coverage curve** at floors 0.5–0.9 when confidences exist,
and Brier only when probabilities exist. No decision at all is reported as no sample, never as 0%.

⚠️ **About the shipped suite.** It is fifteen synthetic messages written by hand, and the lexical
baseline was written alongside it — so the baseline's score on it is circular and proves only that
the ruler works. Build your suite from your own labelled cases before reading any number as quality.

## One question at a time

```bash
python examples/typed-decisions/decide.py --provider typesafe --model jev-1.13.0 \
  --question examples/typed-decisions/route-risk-question.json --state-file change.txt --declared low > decision.json
python -m hpp decide validate decision.json
```

Providers: `typesafe` (`TYPESAFE_API_KEY`), `openrouter` (`OPENROUTER_API_KEY`, alpha endpoint),
`compatible` (`--endpoint`, for a local or self-hosted server that speaks the same wire format).
Aliases such as `jev-latest` are refused, including when the server answers under one: pin the
version so the record can say who answered. The adapter makes one attempt and never retries; the
timeout bounds each socket wait, the response body is capped at 1 MiB, redirects are refused (the
key goes to one host only), and a key is sent only over https or to a loopback address.
