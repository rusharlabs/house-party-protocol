# 00-STATE — {{project_name}}

> **Single-writer: only the PLANNER edits this file.** Executors write in their own
> `00-STATE-LANE-<your-lane-id>.md` (never here — avoids git index collisions).
> The sections `## Now` and `## OPEN ITEMS` are PARSED by hook (`_section()` —
> captures from the header up to the next `## ` of the same level). Do not break this format:
> the heading strings are the literals the hook matches — keep them exactly as written.
> A file scaffolded before 2.5.2 uses `## Agora` and `## PENDÊNCIAS ABERTAS`; both readers
> accept those until 2.7.0, so an existing document keeps working with no action.
>
> ⚠️ If this file grows past 64KB, `state_mirror.py --state-file` generates a
> `00-STATE.md.state-index.json` PROACTIVELY (index of the live sections) — do not wait for
> the file to become a slow-boot problem before acting.

## Now

{{one_to_three_sentences_on_the_current_focus}}

Phase: {{current_phase}}
Branch: {{branch}}
Last relevant commit: {{commit_hash}} — {{commit_desc}}

## OPEN ITEMS

- [ ] {{open_item_1}} — owner: {{owner_1}} · gate: {{gate_1_or_none}}
- [ ] {{open_item_2}} — owner: {{owner_2}} · gate: {{gate_2_or_none}}

## Log of progress

### {{date}} — {{entry_title}}
{{what_was_done}}
