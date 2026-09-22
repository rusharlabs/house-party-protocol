# 00-STATE — {{project_name}}

> **Single-writer: only the PLANNER edits this file.** Executors write in their own
> `00-STATE-LANE-<your-lane-id>.md` (never here — avoids git index collisions).
> The sections `## Agora` and `## PENDÊNCIAS ABERTAS` are PARSED by hook (`_section()` —
> captures from the header up to the next `## ` of the same level). Do not break this format:
> the heading strings are the literals the hook matches — keep them exactly as written.
>
> ⚠️ If this file grows past 64KB, `state_mirror.py --state-file` generates a
> `00-STATE.md.state-index.json` PROACTIVELY (index of the live sections) — do not wait for
> the file to become a slow-boot problem before acting.

## Agora

{{resumo_do_foco_atual_1_a_3_frases}}

Phase: {{fase_atual}}
Branch: {{branch}}
Last relevant commit: {{commit_hash}} — {{commit_desc}}

## PENDÊNCIAS ABERTAS

- [ ] {{pendencia_1}} — owner: {{dono_1}} · gate: {{gate_1_ou_nenhum}}
- [ ] {{pendencia_2}} — owner: {{dono_2}} · gate: {{gate_2_ou_nenhum}}

## Log of progress

### {{data}} — {{titulo_da_entrada}}
{{o_que_foi_feito}}
