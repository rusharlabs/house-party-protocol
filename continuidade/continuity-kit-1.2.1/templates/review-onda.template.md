# REVIEW — {{item_id}} — {{data}}

> DoD executado com SAÍDA + EXIT-CODE colados, nunca "rodei e passou". Mecanizável via
> `goal_review.py --goal {{item_id}}` (que reusa `done_gate.gate` — mesmo mecanismo do
> `/ralph-gate`). Este template é a VISTA HUMANA do resultado; o board (`lane_board.py`)
> é a máquina que enforça quem pode escrever VERIFIED/NEEDS-FIX.

## Revisor

- Lane: {{revisor_lane_id}}
- Modelo: {{revisor_model}} (família diferente do builder: {{builder_model}})
- Papel: revisora (read-only físico — sem Write/Edit nesta sessão)

## Critérios do DoD (colados do PRD, ver `prd-onda.template.md`)

```console
$ {{comando_criterio_1}}
{{saida_real_1}}
```
exit={{exit_code_1}}

```console
$ {{comando_criterio_2}}
{{saida_real_2}}
```
exit={{exit_code_2}}

## Veredito

- [ ] **VERIFIED** — todos os critérios passaram, evidência colada acima
- [ ] **NEEDS-FIX** — {{o_que_falhou_e_o_gap_exato}}
- [ ] **DEFERRED** — checker cross-model indisponível nesta rodada (nunca vira VERIFIED por omissão)

## Registro no board

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py set {{item_id}} {{VERIFIED_ou_NEEDS_FIX_ou_DEFERRED}} \
  --lane {{builder_lane_id}} --role revisora --model {{revisor_model}} \
  --verdict-by-lane {{revisor_lane_id}} --verdict-by-model {{revisor_model}}
```
