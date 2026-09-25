[English](README.md) · [Português](README.pt-BR.md)

# House Session — a panel of pinned deciders, counted, stopped and sealed

> New in 2.7.0.

Several agents discussing a question is only worth its cost if the discussion can be checked: who
sat, which model answered for each seat, what each one said before seeing the others, when the
talk stopped and why, and what the dissent was. `hpp deliberate` records exactly that. The harness
still calls no model ([MANIFESTO](../../MANIFESTO.md)): the seats and the judge answer outside it,
in their own lanes or CLIs, and this command validates, counts, stops and seals what they said.

| piece | where | runs anything? |
|---|---|---|
| the panel `hpp.panel/v1` | `review/panel.json` | no |
| the turns `hpp.turn/v1` | `review/turns.json` | no |
| the judge's answer `hpp.decision/v1` | `review/judge.json` | no |
| the judge's rationale `hpp.rationale/v1` (new in 2.8.0) | `review/rationale.json`, texts in `review/steelman-low.txt` and `review/would-change-if.txt` | no |
| the context the seats were given (new in 2.8.0) | `review/context.json` | no |
| the contract, the count, the stop rule, the seal | `hpp/deliberation.py` · `hpp deliberate` | no |
| a replay of recorded sessions as one decider | `panel_decider.py` over `sessions.json` | no model, no network, standard library only |

Every session here is synthetic, written by hand for this example. It proves the contract works end
to end; it measures nothing about any model.

## The panel

A panel names the question, the hash of the state being judged, every seat and the budget. Each
seat is `{id, role, provider, model_served, family, lane}`. The panel does not start unless:

- every `model_served` is a pinned version — an alias such as `-latest` or `preview` is refused;
- the participants come from **at least two model families**;
- there is **exactly one judge**, in a lane no participant uses;
- every participant answers from its own lane;
- the roles fit the kind of question (`session_type`):

| `session_type` | participants it needs | round ceiling |
|---|---|---|
| `plan` | 2 `proponent` · 1 `dissent` · 1 `examiner` | 10 |
| `review` | 2 `examiner` · 1 `dissent` | 10 |
| `release-gate` | 1 `examiner` · 1 `dissent` | 10 |
| `incident` | 2 `proponent` (two blind diagnoses) | 2 — one reply at most |
| `design` | one `proponent` per option · 1 `dissent` | 10 |

- `budget` declares `max_rounds` and `max_chars` (the total length of the verbatim turns).

`judge_independence` is `full` when the judge's family is not among the participants', and
`partial` when it is — declared, never hidden.

```bash
python -m hpp deliberate plan examples/house-session/review/panel.json
```

## The turns

A turn records one seat's answer in one round: its `position` (an option or `abstain`), its
claims (`fact`, `inference` or `opinion`, each with the ids it rests on), the sha256 and length of
the verbatim text (the text itself stays with you), and `seen_turns` — the hashes of the turns this
seat had read before answering.

- **Round 1 is blind.** A round-1 turn with anything in `seen_turns` is refused.
- A later turn may only have seen turns of an **earlier** round.
- A seat speaks once per round; the judge takes no turns.

A position is **grounded** when its turn states at least one `fact` with a reference that
resolves. New in 2.8.0: a panel may declare `evidence.ids`, the ids its seats can cite — the
context they were given and the evidence records that verified. `plan --context` reads the same
context file `hpp cite check` reads and prints the panel with those ids; `--evidence` adds each
`hpp.evidence/v1` record that verifies now, and refuses one that does not.

```bash
python -m hpp deliberate plan examples/house-session/review/panel.json --context examples/house-session/review/context.json --out out/panel.json
```

With the ids declared, a reference to anything else is `unsupported`: `tally` lists it per round,
it grounds nothing, and it is never new evidence — an invented id cannot keep a session going or
excuse a change of position. A panel that declares no evidence keeps the 2.7.0 rule (any reference
grounds) and its record says `evidence_gate: not-declared`; ids typed by hand with no `sources` say
`declared-unsourced`, and only ids with a declared source (a context hash, a verified evidence record)
say `resolved`. Declaring evidence changes the panel's hash, so save the checked panel with
`plan ... --out FILE` and record every turn against that file.

## The count and the stop rule

```bash
python -m hpp deliberate tally --panel examples/house-session/review/panel.json --turns examples/house-session/review/turns.json
python -m hpp deliberate stop --panel examples/house-session/review/panel.json --turns examples/house-session/review/turns.json
```

`tally` reports, per round, grounded and ungrounded votes per option, abstentions, the seats **not
judged** (no turn in that round), the leading option, the grounded dissent, the seats that moved,
and the moves made **without new evidence** — a change of position whose turn cites nothing that
seat had not cited before. A seat that did not answer is never counted as a vote against.

`stop` answers `continue` with the next round, or `stop` with the first rule that holds, in this
order. A session ends at the first round where a rule holds: turns of later rounds are refused,
so a seat that missed the blind round cannot vote after reading the others.

| reason | when |
|---|---|
| `not-judged` | a participant has no turn in the latest round — the verdict is blocked |
| `grounded-convergence` | every participant chose the same option, all grounded, none abstained |
| `paused-budget` | the verbatim turns reached `max_chars` |
| `no-new-evidence` | from round 2: no reference the session had not seen, and nobody moved |
| `max-rounds` | the round ceiling was reached |

`escalate` is `true` when the session stops on `paused-budget`, `no-new-evidence` or `max-rounds`
with more than one grounded position still standing: the panel did not settle it, so it goes to a person as
options, with the dissent kept in the record.

## The record

```bash
python -m hpp deliberate record --panel examples/house-session/review/panel.json --turns examples/house-session/review/turns.json --judge examples/house-session/review/judge.json --rationale examples/house-session/review/rationale.json --out out/record.json
python -m hpp deliberate verify out/record.json
```

The judge reads the verbatim turns in its own lane and answers with an ordinary
`hpp.decision/v1` record, which must answer the panel's question about the panel's state and
come from the judge seat's provider and pinned model (a record with a rule, replay or human method
is refused: the seat pins a model). `record` refuses a session that has not
stopped and a verdict without a judge — except when a seat was not judged: then the verdict is
`blocked` and no judge is consulted.

The `hpp.deliberation/v2` record keeps the panel, every turn by hash, the tally of every round,
the stop, the budget used, the judge's record, the verdict, the **dissent that lost**, and four
measurements — agreement in the blind round, agreement at the end, moves without new evidence,
and the share of ungrounded votes. `record_sha256` seals all of it except `human_decision`, which
a person fills in afterwards (`{value, by, note?}`). `verify` checks the seal **and** re-derives
the tally, the stop and the verdict from the turns and the judge the record holds: an edit to
anything derived fails even when someone recomputed the hash. The seal is not a signature: a
consistent rewrite of a turn or of the judge's record, resealed, verifies. Those inputs are
anchored outside the record, by the hashes it carries of the verbatim text and of the judge's raw
response — keep those files beside the record.

**Dissent is answered, not just kept.** When the judge's verdict leaves grounded dissent standing,
`record` needs `--rationale`: an `hpp.rationale/v1` written by the judge seat with one **steelman**
per dissenting position — the strongest case for the side that lost — and at least one
**`would_change_if`**, what would overturn the verdict. Like turns, it carries the hash and length
of each verbatim text; here the texts are `review/steelman-low.txt` and
`review/would-change-if.txt`. A rationale that argues a position nobody dissented from, skips one,
or comes from another seat is refused. Without dissent it is optional. The record says whether a
steelman was written for each position; whether it is a good one, only a reader can tell.

A `hpp.deliberation/v1` record sealed by 2.7.0 still verifies, under the rules it was sealed with.

In this review the dissent held its ground: `stop` → `max-rounds`, `escalate: true`; the verdict is
the judge's `high`; `dissent` keeps seat `c` at `low`; seat `b` moved from `medium` to `high` and
is not marked, because its second turn cites a reference it had not cited before.

## Acting on a verdict (new in 2.9.0)

A sealed session feeds the commands that act on a verdict. Each one verifies the record, checks the
kind of session and the options it asked about, and refuses a judge of the maker's model family
(`--maker-family`). A panel can only make an outcome stricter:

```bash
python -m hpp route --request request.json --providers providers.json --deliberation plan-record.json --maker-family anthropic
python -m hpp attest create --spec spec.md --output att.json --maker exec-a --checker rev-b --session s1 --verdict approved --deliberation gate-record.json --maker-family anthropic
python multi-session/lane-kit-1.6.0/scripts/lane_board.py select --task TASK-1 --deliberation design-record.json
```

- **`route`** reads a `plan` session over `low`/`medium`/`high`: its verdict can raise the request's
  risk (and so the tier), never lower it.
- **`attest create`** reads a `release-gate` session over `approved`/`revise`/`blocked` whose facts
  rest only on `hpp.evidence/v1` records: the attestation records the stricter of the declared verdict
  and the panel's, and a panel that did not decide sends it back for revision. The record hash is kept.
- **`lane_board.py select`** reads a `design` session whose options are exactly the remaining
  candidates: the judge becomes the reviewer of record, so the board's lane and family rules apply to it.

## The whole panel, measured as one decider

`record` also prints the panel as one `hpp.decision/v1` record (`method: panel`, no confidence,
`raw_response_sha256` = the sealed record). That is what lets the ruler that measures a single
decider measure a panel, on the same suite:

```bash
python -m hpp decide eval examples/typed-decisions/gotcha-family-suite.json --decider-command '["python", "examples/house-session/panel_decider.py"]'
python -m hpp decide eval examples/typed-decisions/gotcha-family-suite.json --decider-command '["python", "examples/typed-decisions/baseline_decider.py"]'
```

`panel_decider.py` replays one recorded session per case (a two-seat `incident` panel from two
families, blind round, one reply where they disagreed), seals and verifies it, and answers with the
panel's decision. A panel with a dead seat is an instrument failure in this ruler, never an answer.

## Exit codes

| command | 0 | 1 | 2 |
|---|---|---|---|
| `deliberate plan` · `deliberate validate` | valid | — | refused, naming the first broken rule |
| `deliberate tally` · `deliberate stop` | reported | — | refused panel or turns |
| `deliberate record` | sealed, the judge answered | sealed, the verdict is blocked or the judge failed | refused: not stopped, no judge, a judge for another question, state or model, dissent without a steelman |
| `deliberate verify` | intact | — | broken: edited, or does not re-derive |

## What this does not do yet

A reference that resolves proves the id exists, not that the source says what the claim says — the
same limit as `hpp cite check`. Nothing in the core runs the seats; the lane module's
`house_session.py` does (new in 2.8.0): it seats a panel only on a host with two model families,
runs each seat's command in its own worktree, and refuses the turn of a seat that wrote to it.
Whether a panel beats one strong agent is a measurement, not a claim — it is not made here.
