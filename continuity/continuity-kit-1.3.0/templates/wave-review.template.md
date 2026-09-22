# REVIEW — {{item_id}} — {{date}}

> DoD executed with the OUTPUT and the EXIT CODE pasted in, never "I ran it and it passed".
> Mechanizable through `goal_review.py --goal {{item_id}}` (which reuses `done_gate.gate` — the
> same mechanism as `/ralph-gate`). This template is the HUMAN VIEW of the result; the board
> (`lane_board.py`) is the machine that enforces who may write VERIFIED/NEEDS-FIX.

## Reviewer

- Lane: {{reviewer_lane_id}}
- Model: {{reviewer_model}} (a different family from the builder: {{builder_model}})
- Role: reviewer (physically read-only — no Write/Edit in this session)

## DoD criteria (pasted from the PRD, see `wave-prd.template.md`)

```console
$ {{criterion_command_1}}
{{real_output_1}}
```
exit={{exit_code_1}}

```console
$ {{criterion_command_2}}
{{real_output_2}}
```
exit={{exit_code_2}}

## Verdict

- [ ] **VERIFIED** — every criterion passed, evidence pasted above
- [ ] **NEEDS-FIX** — {{what_failed_and_the_exact_gap}}
- [ ] **DEFERRED** — the cross-model checker was unavailable this round (never becomes VERIFIED by omission)

## Record it on the board

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py set {{item_id}} {{VERIFIED_or_NEEDS_FIX_or_DEFERRED}} \
  --lane {{builder_lane_id}} --role reviewer --model {{reviewer_model}} \
  --verdict-by-lane {{reviewer_lane_id}} --verdict-by-model {{reviewer_model}}
```
