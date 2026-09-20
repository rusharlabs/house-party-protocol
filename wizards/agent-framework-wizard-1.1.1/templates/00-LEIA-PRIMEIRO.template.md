# 00-LEIA-PRIMEIRO — {{project_name}}

> Roteador de papel — o ÚNICO doc que toda sessão nova (humana ou IA) lê primeiro,
> independente do papel (planejadora/executora/revisora/solo). Se você não sabe por onde
> começar, comece aqui. Gerado do template do continuity-kit — substitua `{{placeholders}}`.

## Quem é você nesta sessão?

| Se você é... | Leia agora | Depois |
|---|---|---|
| **Planejadora** (arquiteta) | `{{vision_doc}}` (VISÃO) → `{{state_doc}}` (§Agora) | `{{goal_ledger_path}}` (próximo goal) |
| **Executora** (construtora) | `.claude/handoff/HANDOFF-CURRENT-<sua-lane>.json` (se existir) | `{{state_doc}}` §PENDÊNCIAS + seu item no board |
| **Revisora** (auditora) | o item em `UNDER-REVIEW` no board (`lane_board.py status <item>`) | `{{review_template}}` p/ o formato do veredito |
| **Solo** (sessão única, sem lanes) | `{{state_doc}}` completo | `{{goal_ledger_path}}` |

## Os 3 SSoT deste projeto (nunca duplicar, sempre re-verificar ao vivo — LC-1)

1. **`{{state_doc}}`** — o AGORA (foco + pendências). Muda toda sessão.
2. **`{{goal_ledger_path}}`** — os GOALS (o quê, por quê, quando "pronto"). Muda por goal.
3. **`{{vision_doc}}`** — a VISÃO (por que o projeto existe). Muda raramente, só por aprovação humana.

## Ponteiro de retomada automático

Se `.claude/RESUME-NEXT.md` ou um handoff JSON existir, ele já foi (ou será) injetado no
boot da sessão — trate como **REFERÊNCIA HISTÓRICA, NÃO FILA DE EXECUÇÃO** (LC-4): antes de
repetir qualquer ação que ele mencione, rode o `verify_first_cmd` correspondente.

## Regras que sobrepõem tudo

- `docs/plans/execucao/00-STATE.md` (ou o `{{state_doc}}` deste projeto) é **single-writer**
  da planejadora — executoras escrevem no `00-STATE-LANE-<id>.md` próprio.
- Nenhuma lane declara "pronto" maior do que a evidência (escada R0→R4, ver
  `00-PROCESSES.template.md`).
- `git push`/merge/deploy real = sempre gate humano, nunca automático.
