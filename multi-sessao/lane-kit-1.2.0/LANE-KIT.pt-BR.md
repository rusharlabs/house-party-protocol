[English](LANE-KIT.md) · [Português](LANE-KIT.pt-BR.md)

# lane-kit — N sessões, 1 repo, zero colisão

> Ver `scripts/lane_board.py` (quadro-branco), `skills/lane-coordinator/SKILL.md` (uso),
> `evals/collision-2lanes.sh` (teste de concorrência), `templates/` (mailbox + status HTML).

## LANE-ENGINE — registry de lanes vivas + guards de concorrência

Além do board (estado por-item), o lane-kit mantém um **registry de lanes vivas**
(`.claude/lanes/registry.json`, runtime — nunca versionado) e dois guards que consultam
esse registry antes de uma ação arriscada:

| Peça | Papel | Hook |
|---|---|---|
| `hooks/_lane_io.py` | biblioteca: register/heartbeat/evict/who_owns/alive_count | (não é hook — importado pelos 3 abaixo) |
| `hooks/lane_register.py` | registra a lane no boot; avisa de mailbox não lido | SessionStart (register) + PostToolUse (`--heartbeat`) |
| `hooks/lane_git_guard.py` | impede `add -A`/`commit -a`/commit-sem-pathspec/`stash`/`reset --hard`/`checkout .`/`--amend` quando há outra lane viva — índice git é **compartilhado** entre sessões | PreToolUse (`Bash`) |
| `hooks/lane_territory_guard.py` | WARN (nunca bloqueia) se o path editado é zona vermelha ou território exclusivo de outra lane viva | PreToolUse (`Edit\|Write`) |

Liveness: heartbeat &lt;10min=viva, 10-30min=suspeita (guards degradam para warn mesmo em
modo `block`), &gt;30min=morta (evict automático, zero falso-positivo nos guards). Config em
`templates/lanes.example.yaml` → copiar para `.claude/lanes/lanes.yaml` (rastreado no git).
Wiring: `install/wiring.settings.jsonc`. Rollout do git-guard: **sempre** começar em
`git_guard.mode: warn` por ≥1 semana sem falso-positivo antes de considerar `block` (validar
com `evals/collision-git-guard.sh`, 3 rodadas verdes). Território (`evals/collision-territory-guard.sh`)
é sempre WARN-only — nunca vira `block`.

## WATCH.log — convenção de observabilidade read-only

Qualquer processo READ-ONLY que observa o board (dashboards, alertas, cron de saúde) escreve
o que viu em **`.claude/lanes/WATCH-<observador>.log`** — NUNCA edita `board.jsonl` nem os
artefatos de outra lane. Regra de ouro: **"read-only produz artefato PRÓPRIO, nunca edita o
do outro"**. Formato de linha (append-only, 1 linha por observação):

```
<ISO-8601> <observador> <resumo de 1 linha do que observou>
2026-07-10T16:00:00-03:00 status-dashboard-cron 3 lanes vivas, 2 itens em UNDER-REVIEW, 0 itens travados >30min
```

Um `WATCH.log` que cresce sem nunca ser lido é sinal de observador morto — rotação/retenção
fica a critério do projeto-alvo (não é parte do contrato do lane-kit).

## Denies-por-papel (extensão do artefato 15 — `settings-continuidade.template.json`)

O artefato 15 do TEMPLATE-SET (FASE 7) declara deny-rules GERAIS de continuidade (nunca
editar handoff/hooks pela própria sessão). O lane-kit ESTENDE isso por PAPEL, refletindo a
tabela §2.1: revisora é **read-only físico** (sem `Write`/`Edit` no `allowedTools` da sessão
revisora — a única escrita permitida é `lane_board.py --set ... VERIFIED|NEEDS-FIX|DEFERRED`,
via `Bash` escopado). Bloco de referência (aplicar no perfil/allowedTools da sessão-revisora,
não em settings.json global — é config por-sessão, não gate humano):

```yaml
papel: revisora
allowedTools: ["Read", "Glob", "Grep", "Bash(python scripts/lane_board.py set * VERIFIED:*)", "Bash(python scripts/lane_board.py set * NEEDS-FIX:*)", "Bash(python scripts/lane_board.py set * DEFERRED:*)"]
# NUNCA: Write, Edit, MultiEdit — reforça em código o "revisora não edita nada" da tabela §2.1
```

Zonas vermelhas (WARN para TODAS as lanes, qualquer papel): `.claude/settings*.json`,
`**/MEMORY.md`, `docs/plans/execucao/00-STATE.md` (single-writer = planejadora — executoras
escrevem em `00-STATE-LANE-<id>.md` próprio, nunca no arquivo compartilhado).

## Modo opcional — convergência de 2 lanes

Quando DUAS lanes precisam fundir trabalho no MESMO item (ex.: planejadora + executora
pareadas num item complexo), o modo de convergência permite que ambas apareçam no histórico
do item SEM violar maker≠checker:

1. Ambas dão `CLAIMED`/`BUILDING` no mesmo `item_id` (o board aceita — `_TRANSITIONS` permite
   `CLAIMED→CLAIMED` e `BUILDING→BUILDING`, cada evento carrega a lane que o gravou).
2. `CHECKPOINT-READY` só é aceito da lane que fez o ÚLTIMO `CLAIMED`/`BUILDING` (regra atual
   do enforcement) — ou seja, a convergência é **sequencial no board** mesmo que o trabalho
   real seja paralelo: a lane que "fecha" o checkpoint é quem grava por último.
3. A revisora, na hora do `VERIFIED`, ainda precisa ser de lane+família DIFERENTE do
   **builder registrado no evento `CLAIMED` original** (não do último `BUILDING`) — o
   enforcement busca o primeiro evento `CLAIMED` do item como "o builder", propositalmente,
   para que convergência de 2 lanes-construtoras não vire brecha de auto-aprovação.
4. Use o `REORIENT-MAILBOX.template.md` para a lane que está entrando no item avisar a que
   já estava (e vice-versa) — o board registra ESTADO, não a conversa de coordenação.

Este modo é **opcional e não tem enforcement extra no código** além do que já existe —
funciona porque o state machine já é permissivo o bastante para 2 builders na mesma lane
lógica; não há necessidade de um "modo" separado ativável, é o comportamento natural do
board quando 2 lanes cooperam no mesmo item_id.
