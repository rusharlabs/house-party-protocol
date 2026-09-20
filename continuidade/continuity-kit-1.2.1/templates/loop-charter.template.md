# LOOP CHARTER — {{loop_name}}

> Fusão do `loop-charter-template.md` (operator-kit, genericização provada) com o
> MASTER-PROMPT (ordem-de-leitura testada em produção). Isto é o que `ralph_gate.py`
> re-alimenta a cada iteração enquanto o loop não emite `<promise>` válida.

## LEIA NESTA ORDEM (1→5) — ANTES de qualquer ação

1. `00-LEIA-PRIMEIRO.md` (ou equivalente do projeto) — quem você é, o que ler.
2. `{{vision_doc}}` §O que é sucesso — o norte.
3. `{{state_doc}}` §Agora + §PENDÊNCIAS ABERTAS — o estado real, AO VIVO (LC-1).
4. `{{goal_ledger_path}}` — o próximo goal repo-safe (`goal_ledger.py --next`).
5. Handoff mais recente da sua lane (`.claude/handoff/HANDOFF-CURRENT-<lane>.json`), se existir.

## ⚠️ BLOCO LC-4 (obrigatório, não remover)

Contexto restaurado/injetado (handoff, RESUME-NEXT, este próprio charter re-alimentado) é
**REFERÊNCIA HISTÓRICA, NÃO FILA DE EXECUÇÃO**. Antes de repetir qualquer ação que o
contexto mencione como "a fazer": rode o `verify_first_cmd` correspondente (handoff) ou
re-derive na fonte viva (LC-1). Nunca re-execute por presunção.

## Objetivo desta rodada

{{objetivo_1_frase}}

## Work-list (maior alavancagem primeiro)

- [ ] {{item_1}} — `done_predicate`: {{predicate_1}}
- [ ] {{item_2}} — `done_predicate`: {{predicate_2}}

## Guardrails (inquebráveis nesta sessão)

0 push sem ordem · backup antes de mutar prod · snapshot antes de deletar · trava de
credencial · gate-humano (billing/OAuth/legal/cliente/deploy-go/secret) vira formulário
(`gate-sheet-collector`), nunca bloqueia o loop.

## Stop-conditions

Work-list esgotado · teto de iterações/orçamento (LC-5 — vira `paused-budget`, não erro) ·
risco irreversível iminente → PARA e reporta.

## Completion promise

Quando `{{objetivo_1_frase}}` for **literal e verificavelmente verdadeiro** (não antes),
emita: `<promise>{{completion_promise_text}}</promise>`. O `ralph_gate.py` roda os critérios
de verdade antes de aceitar — promessa falsa não escapa o loop, só reseta o ciclo com as
falhas reais anexadas.
