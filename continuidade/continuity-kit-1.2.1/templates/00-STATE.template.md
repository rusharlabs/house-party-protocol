# 00-STATE — {{project_name}}

> **Single-writer: só a PLANEJADORA edita este arquivo.** Executoras escrevem em
> `00-STATE-LANE-<seu-lane-id>.md` próprio (nunca aqui — evita colisão de índice git).
> Seções `## Agora` e `## PENDÊNCIAS ABERTAS` são PARSEÁVEIS por hook (`_section()` —
> captura do header até o próximo `## ` do mesmo nível). Não quebre esse formato.
>
> ⚠️ Se este arquivo passar de 64KB, `state_mirror.py --state-file` gera um
> `00-STATE.md.state-index.json` PROATIVAMENTE (índice das seções vivas) — não espere
> o arquivo virar um problema de boot lento antes de agir.

## Agora

{{resumo_do_foco_atual_1_a_3_frases}}

Fase: {{fase_atual}}
Branch: {{branch}}
Último commit relevante: {{commit_hash}} — {{commit_desc}}

## PENDÊNCIAS ABERTAS

- [ ] {{pendencia_1}} — dono: {{dono_1}} · gate: {{gate_1_ou_nenhum}}
- [ ] {{pendencia_2}} — dono: {{dono_2}} · gate: {{gate_2_ou_nenhum}}

## Log de progresso

### {{data}} — {{titulo_da_entrada}}
{{o_que_foi_feito}}
