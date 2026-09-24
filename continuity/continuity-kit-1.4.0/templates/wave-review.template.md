# REVIEW — {{item_id}} — {{date}}

> DoD executed and recorded as `hpp evidence` records (exit code measured outside the model),
> never "I ran it and it passed".
> Mechanizable through `goal_review.py --goal {{item_id}}` (which reuses `done_gate.gate` — the
> same mechanism as `/ralph-gate`). This template is the HUMAN VIEW of the result; the board
> (`lane_board.py`) is the machine that enforces who may write VERIFIED/NEEDS-FIX.

## Reviewer

- Lane: {{reviewer_lane_id}}
- Model: {{reviewer_model}} (a different family from the builder: {{builder_model}})
- Role: reviewer (physically read-only — no Write/Edit in this session)

## DoD criteria (from the PRD, see `wave-prd.template.md`)

One record per criterion, written by `python -m hpp evidence run` (requires the HPP core):

- record: `{{record_path_1}}` · `python -m hpp evidence verify {{record_path_1}}` -> exit {{verify_exit_1}}
- record: `{{record_path_2}}` · `python -m hpp evidence verify {{record_path_2}}` -> exit {{verify_exit_2}}

`verify` exits 0 only for an intact record of a PASSED run (1 = the run did not pass, 2 = the record
or an artifact changed). It is reconciliation, not proof: the record is self-hashed, not signed, so
the reviewer also re-runs `record.command` from its own lane, or with `--out` in a scratch directory of
its own (relative, inside the workspace), never into the builder's records (a write there would
invalidate this review):
`python -m hpp evidence run --id {{item_id}}-recheck --out {{reviewer_scratch_dir}} -- {{record_command}}`

## Verdict

- [ ] **VERIFIED** — every record verified with exit 0 and its re-run passed
- [ ] **NEEDS-FIX** — {{what_failed_and_the_exact_gap}}
- [ ] **DEFERRED** — the cross-model checker was unavailable this round (never becomes VERIFIED by omission)

## Record it on the board

The builder's checkpoint carries the record (`--evidence-record` refuses anything but a record that
`verify` calls valid; it requires the HPP core):

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py set {{item_id}} CHECKPOINT-READY \
  --lane {{builder_lane_id}} --role executor --model {{builder_model}} \
  --evidence-record {{record_path_1}}
```

The verdict:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py set {{item_id}} {{VERIFIED_or_NEEDS_FIX_or_DEFERRED}} \
  --lane {{builder_lane_id}} --role reviewer --model {{reviewer_model}} \
  --verdict-by-lane {{reviewer_lane_id}} --verdict-by-model {{reviewer_model}}
```

Best-of-N: when {{item_id}} is one candidate of a competition, the selection is recorded with
`select`, by a reviewer of another lane AND another model family than every candidate. The winner
still needs VERIFIED before MERGED — choosing 1 of N is pass@N, not reliability:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py select --task {{task_id}} --winner {{item_id}} \
  --lane {{reviewer_lane_id}} --model {{reviewer_model}} --reason "{{why_this_candidate}}"
```
