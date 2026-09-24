[English](LANE-KIT.md) · [Português](LANE-KIT.pt-BR.md)

# lane-kit — N sessões, 1 repo, zero colisão

> Ver `scripts/lane_board.py` (quadro-branco), `skills/lane-coordinator/SKILL.md` (uso),
> `evals/collision-2lanes.sh` (teste de concorrência), `templates/` (mailbox + status HTML).

## LANE-ENGINE — registry de lanes vivas + guards de concorrência

Além do board (state por-item), o lane-kit mantém um **registry de lanes vivas**
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
<ISO-8601> <observador> <summary de 1 linha do que observou>
2026-07-10T16:00:00-03:00 status-dashboard-cron 3 lanes vivas, 2 itens em UNDER-REVIEW, 0 itens travados >30min
```

Um `WATCH.log` que cresce sem nunca ser lido é sinal de observador morto — rotação/retenção
fica a critério do projeto-alvo (não é parte do contrato do lane-kit).

## Denies-por-papel (extensão de `settings-continuidade.template.json`, do continuity-kit)

O template `settings-continuidade.template.json` do continuity-kit declara deny-rules GERAIS de continuidade (nunca
editar handoff/hooks pela própria sessão). O lane-kit ESTENDE isso por PAPEL, refletindo a
separação maker≠checker: revisora é **read-only físico** (sem `Write`/`Edit` no `allowedTools` da sessão
revisora — as únicas escritas permitidas são `lane_board.py set ... VERIFIED|NEEDS-FIX|DEFERRED` e `lane_board.py select`,
via `Bash` escopado). A revisora também pode rodar `python -m hpp evidence verify` (requer o núcleo
HPP): ele só lê, e reconcilia um registro que a construtora anexou com `--evidence-record`. Ela nunca
recebe `hpp evidence run`, que escreve um registro e tudo o que o comando escreve — o registro tem
auto-hash, não assinatura, então uma revisora que não pode confiar na construtora roda de novo o
comando do registro a partir da própria lane, fora deste perfil. Bloco de referência (aplicar no
perfil/allowedTools da sessão-revisora, não em settings.json global — é config por-sessão, não gate
humano):

```yaml
role: reviewer
allowedTools: ["Read", "Glob", "Grep", "Bash(python scripts/lane_board.py set * VERIFIED:*)", "Bash(python scripts/lane_board.py set * NEEDS-FIX:*)", "Bash(python scripts/lane_board.py set * DEFERRED:*)", "Bash(python scripts/lane_board.py select:*)", "Bash(python -m hpp evidence verify:*)"]
# NEVER: Write, Edit, MultiEdit - enforces in code that a reviewer edits nothing
# NEVER: python -m hpp evidence run - it writes; a re-run belongs in the reviewer's own lane
```

Zonas vermelhas (WARN para TODAS as lanes, qualquer papel): `.claude/settings*.json`,
`**/MEMORY.md`, `docs/plans/execution/00-STATE.md` (single-writer = planejadora — executoras
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

## Competições — N lanes tentam a mesma tarefa, um vencedor

O oposto da convergência: em vez de duas lanes num item SÓ, N lanes constroem cada uma o PRÓPRIO
item para a mesma tarefa, e uma revisora fica com a melhor tentativa. O board registra isso com três
comandos (`compete`, `select`, `withdraw`) e dois estados de item a mais (`NOT-SELECTED`,
`WITHDRAWN`):

1. **`compete --task T --items A,B[,C...]`** declara os itens como candidatos de `T`. Cada um
   precisa já ter claim e não estar finalizado, nenhuma lane construtora (qualquer lane que gravou
   `CLAIMED`/`BUILDING`/`CHECKPOINT-READY` nele) pode ser compartilhada entre dois candidatos —
   então o modo de convergência acima não consegue fazer uma tentativa passar por duas —, um item
   concorre em uma tarefa só, e uma tarefa é declarada uma vez.
2. **`select --task T --winner A`** exige todo candidato restante (não retirado) em
   `CHECKPOINT-READY` com evidência, ou `VERIFIED`, e uma revisora cuja lane difere de TODAS as
   lanes construtoras de TODOS os candidatos — inclusive os retirados: uma lane que tentou a
   tarefa nunca a julga — e cuja família de modelo difere da família das construtoras de todo
   candidato restante. O evento da competição guarda o vencedor, os perdedores, os itens
   retirados, a revisora, o motivo e a evidência comparada.
3. Os perdedores recebem um evento de item `NOT-SELECTED`: terminal, e nenhuma linha do
   `_TRANSITIONS` o lista como destino, então o `set` nunca consegue escrevê-lo e uma tentativa
   perdedora nunca chega a `MERGED`. As lanes deles ficam devendo o aviso pelo `lane_effects.py`,
   como qualquer veredito.
4. Um candidato não pode ir a `MERGED` enquanto a tarefa dele não tem vencedor, nem depois do
   próprio `VERIFIED` — senão quem termina primeiro vence sem comparação. O vencedor mantém o
   estado e ainda precisa do `VERIFIED` comum antes do `MERGED`: selecionar compara, não verifica.
5. **`select --task T --checker-unavailable`** registra `DEFERRED` para a competição, nunca um
   vencedor; um `select` posterior com revisora a decide.
6. **`withdraw --task T --item C --lane <coordinator> --model <m> --reason "<why>"`** retira um
   candidato de uma competição ainda sem vencedor — o caso em que a lane dele morreu e a tarefa
   ficaria indecidível para sempre. Grava um evento de competição (`state: WITHDRAWN`, `item`,
   `reason`) e um evento de item `WITHDRAWN`: terminal, escrito só pelo `withdraw`, e a lane dele
   fica devendo o aviso pelo `lane_effects.py`, como no `NOT-SELECTED`. O item deixa de contar
   para a prontidão e para a seleção. Recusados: tarefa já decidida, item que não é candidato
   restante (ou já foi retirado), motivo vazio, o último candidato restante (pelo menos 1 fica;
   com exatamente 1, o `select` dele é permitido) e uma lane que construiu um candidato rival. O
   `render` e o `status T` mostram a retirada.

Os eventos de competição vivem no `board.jsonl` ao lado dos eventos de item, com
`kind: competition` e um `task_id` no lugar do `item_id`; o `render` os imprime sob
**COMPETITIONS**.
