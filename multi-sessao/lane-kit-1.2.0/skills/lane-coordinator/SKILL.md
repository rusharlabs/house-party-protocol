---
name: lane-coordinator
description: Coordena N sessões (lanes) concorrentes sobre o mesmo repo via um quadro-branco com máquina de estados (lane_board.py) — CLAIMED até MERGED, com maker≠checker cross-model enforçado em código, não em disciplina textual.
---

> **Auto-Trigger:** Quando 2+ sessões (planejadora/executora/revisora) trabalham no mesmo repo ao mesmo tempo, ou antes de uma executora reivindicar um item de trabalho, ou antes de uma revisora aprovar/rejeitar um item.
> **Keywords:** "lane", "lanes", "quadro-branco", "board", "coordenar sessões", "maker checker", "claimed", "checkpoint-ready", "verified", "colisão de sessão", "múltiplas sessões"
> **Prioridade:** ALTA
> **Tools:** Bash, Read

## Quando NÃO Ativar
- Sessão única (`solo`) sem concorrência — o board é overhead sem 2+ lanes vivas.
- Coordenação de handoff ENTRE sessões sequenciais (uma de cada vez) → use `continuity-kit` (handoff/pre-clear), não este kit (este é para sessões SIMULTÂNEAS).
- Decisão de merge de item 🔴 sem o humano — mesmo com `VERIFIED`, o `--human-approved` é literal: só o operador decide.

## Contrato

**ENTRADA:** `item_id` + papel (`executora`/`revisora`) + `lane_id` + `model` + (conforme o estado) evidência ou verdict.

**SAÍDA:** 1 evento append-only em `.claude/lanes/board.jsonl` + (via `render`) snapshot legível em `docs/plans/execucao/LANE-BOARD.md`.

**EXIT CODES:**

| Exit | Significado |
|---|---|
| 0 | transição aceita, evento gravado |
| 1 | transição recusada pelo enforcement (ver mensagem — maker=checker, sem evidência, lane errada, etc.) |
| 2 | uso inválido / lock não obtido em 2s |

**ESTADO QUE TOCA:**

| Arquivo | Lê/Escreve | Propósito |
|---|---|---|
| `.claude/lanes/board.jsonl` | Lê+Escreve (append, sob lock) | histórico de eventos do item |
| `.claude/lanes/.lock` (dir) | Cria+remove | serializa escritas concorrentes |
| `docs/plans/execucao/LANE-BOARD.md` | Escreve (via `render`) | snapshot legível, commitado só no session-harvest |

## Máquina de estados

```
CLAIMED → BUILDING → CHECKPOINT-READY → UNDER-REVIEW → VERIFIED | NEEDS-FIX → MERGED
                                                       ↘ DEFERRED (checker indisponível) ↗
```

- **CHECKPOINT-READY**: só `role=executora`, só a lane que deu `CLAIMED`, e exige `--evidencia` não-vazia (hash/exit-code colado — nunca "rodei").
- **VERIFIED/NEEDS-FIX**: só `role=revisora`, com `--verdict-by-lane` DIFERENTE da lane que construiu E `--verdict-by-model` de família DIFERENTE (maker≠checker cross-model, em código — não dá pra burlar).
- **Checker indisponível** (`--checker-indisponivel`): só `DEFERRED` é aceito — nunca `VERIFIED`.
- **MERGED**: exige um `VERIFIED` no histórico do item; se `--tag red`, exige também `--human-approved` (gate humano literal).

## Processo

1. **Claim o item** (vira dono, papel executora):
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py claim ITEM-1 --lane exec-a --model claude-opus-4-8
   ```
2. **Avance para BUILDING** enquanto trabalha:
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py set ITEM-1 BUILDING --lane exec-a --role executora --model claude-opus-4-8
   ```
3. **Ao terminar, CHECKPOINT-READY com evidência real** (comando + saída colados, não "terminei"):
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py set ITEM-1 CHECKPOINT-READY --lane exec-a --role executora --model claude-opus-4-8 --evidencia "pytest -q: 42 passed, exit=0"
   ```
4. **Revisora (outra lane, outra família de modelo) assume e verifica de verdade** — NUNCA aceite "está pronto" sem rodar:
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py set ITEM-1 UNDER-REVIEW --lane exec-a --role executora --model claude-opus-4-8
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py set ITEM-1 VERIFIED --lane exec-a --role revisora --model gpt-5.5 --verdict-by-lane rev-a --verdict-by-model gpt-5.5
   ```
5. **Merge** (gate humano se `--tag red`):
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py set ITEM-1 MERGED --lane rev-a --role revisora --model gpt-5.5
   ```
6. **Renderize o snapshot** quando quiser ver o board inteiro:
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py render
   ```

## Exemplos executados

```console
$ python scripts/lane_board.py claim ITEM-1 --lane exec-a --model claude-opus-4-8
{"ts": "2026-07-10T15:56:30", "item_id": "ITEM-1", "estado": "CLAIMED", "lane_id": "exec-a", "role": "executora", "model": "claude-opus-4-8", "tag": "green"}
```
<!-- executado: 2026-07-10 · exit=0 -->

```console
$ python scripts/lane_board.py set ITEM-1 BUILDING --lane exec-a --role executora --model claude-opus-4-8
$ python scripts/lane_board.py set ITEM-1 CHECKPOINT-READY --lane exec-a --role executora --model claude-opus-4-8 --evidencia "pytest -q: 42 passed"
$ python scripts/lane_board.py set ITEM-1 UNDER-REVIEW --lane exec-a --role executora --model claude-opus-4-8
$ python scripts/lane_board.py set ITEM-1 VERIFIED --lane exec-a --role revisora --model claude-opus-4-8 --verdict-by-lane exec-a --verdict-by-model claude-opus-4-8
lane_board: recusado — maker≠checker violado: revisora (exec-a) é a MESMA lane do builder (exec-a)
```
<!-- executado: 2026-07-10 · exit=1 -->
(depois do ciclo completo CLAIMED→BUILDING→CHECKPOINT-READY→UNDER-REVIEW, a MESMA lane tentando ser revisora do próprio trabalho é recusada EM CÓDIGO — não depende de disciplina.)

```console
$ bash evals/collision-2lanes.sh 10
[OK] zero corrupcao: 10/10 linhas validas, 10 items distintos, 0 processos com exit!=0
```
<!-- executado: 2026-07-10 · exit=0 -->
(10 processos concorrentes gravando no MESMO board — lock serializa, zero linha corrompida.)

## Prova

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py --self-test
```
