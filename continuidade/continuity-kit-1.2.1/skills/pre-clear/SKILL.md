---
name: pre-clear
description: Antes de um /clear, consolida o LONGO PRAZO (doc-rollup condicional — como chegamos até aqui) e o CURTO PRAZO (handoff — o que vem depois), depois renderiza o BOOT BUNDLE.
---

> **Auto-Trigger:** Quando uma wave/feature fecha, o contexto está crescendo, ou o operador sinaliza que vai compactar/limpar a sessão.
> **Keywords:** "pre-clear", "vou dar clear", "compactar", "antes do clear", "boot da próxima", "fechar sessão", "preparar próxima sessão"
> **Prioridade:** ALTA
> **Tools:** Read, Write, Bash

## Quando NÃO Ativar
- Mid-task: a wave/feature não terminou (termine primeiro — nunca consolidar pela metade).
- Já existe um `/pre-clear` instalado no projeto-alvo (ex.: casa-específico, consolidando `00-STATE.md`/memória própria) — **o instalado VENCE**; esta versão do kit é só para projetos sem um `/pre-clear` próprio. O `kit_assembler` verifica colisão nome+keywords antes de instalar.
- Sessão read-only trivial sem decisão/mudança nova (nada a consolidar) — nem o rollup nem o handoff disparam; registre isso em vez de forçar uma entrada vazia.
- Não confundir com a skill `doc-rollup`, que este fluxo CHAMA como passo 1 — `doc-rollup` sozinha só cobre o longo prazo (histórico); `pre-clear` orquestra o longo prazo + o curto prazo (handoff) + o boot bundle final.

## Contrato

**ENTRADA:** o modelo preenche mentalmente (a) o payload de rollup (resumo/shipments/métricas/decisões/aprendizados, se algo significativo fechou) e (b) o schema do handoff (resumo, números com `re_derive_cmd`, decisões, gates abertos, próximo passo com `verify_first_cmd`) e passa cada um via stdin ao comando correspondente.

**SAÍDA:** (1, condicional) docs de histórico atualizados via `doc_rollup.py`; (2) `HANDOFF-CURRENT-<lane>.json` gravado + evento `written` no ledger; (3) BOOT BUNDLE renderizado no chat.

**EXIT CODES** (de `_handoff_io.py write --stdin` — o passo final e obrigatório):

| Exit | Significado |
|---|---|
| 0 | handoff válido, gravado |
| 1 | rejeitado (segredo detectado, `verify_first_cmd`/`re_derive_cmd` ausente, schema inválido) |
| 2 | uso inválido (JSON malformado no stdin) |

**ESTADO QUE TOCA:**

| Arquivo | Lê/Escreve | Propósito |
|---|---|---|
| `rollup.yaml` + alvos de histórico (via `doc_rollup.py`) | Lê+Escreve (condicional) | longo prazo — como chegamos até aqui |
| `.claude/handoff/HANDOFF-CURRENT-<lane>.json` | Escreve (atômico) | curto prazo — o handoff vivo desta lane |
| `.claude/handoff/HANDOFF-LEDGER.jsonl` | Escreve (append) | evento `written` |
| `schemas/handoff-v1.1.schema.json` | Lê (implícito via validação) | o contrato do handoff |

## Processo

1. **Checagem de significância:** algo fechou nesta sessão que merece registro de longo prazo (feature, decisão, aprendizado)? Se NÃO, pule os passos 2-3 e registre explicitamente por que pulou (ex.: "sessão de exploração pura, sem rollup"). Nunca force uma entrada vazia só para preencher o passo.
2. **Se significativo, rode o doc-rollup primeiro** (longo prazo, ANTES do handoff — assim a árvore de arquivos que o handoff descreve já reflete os docs atualizados):
   ```bash
   echo '<payload-rollup>' | python ${CLAUDE_PLUGIN_ROOT}/scripts/doc_rollup.py plan  --stdin --config rollup.yaml
   echo '<payload-rollup>' | python ${CLAUDE_PLUGIN_ROOT}/scripts/doc_rollup.py apply --stdin --config rollup.yaml
   ```
   Leia o relatório — `skipped-collision`/`skipped-passive`/`applied:stamp-degrade` são guardrails funcionando, não erros (ver `doc-rollup` SKILL.md).
3. **Monte o JSON do handoff** (curto prazo) — só o modelo sabe decisões/gates/próximo-passo reais desta sessão. Campos mínimos: `session.lane_id`, `estado.resumo`, `git` (head/branch/dirty/untracked — rode `git status --porcelain` e `git rev-parse --short HEAD` primeiro), `proximo_passo[].verify_first_cmd`, `valid_until`.
4. **Grave via o comando** (nunca escreva o arquivo à mão — a validação de segredo/LC-1/LC-4 só roda pelo comando):
   ```bash
   echo '<json>' | python ${CLAUDE_PLUGIN_ROOT}/hooks/_handoff_io.py write --stdin
   ```
5. **Se rejeitado (exit 1):** leia os motivos impressos, corrija o JSON (não remova o campo exigido — preencha-o de verdade), tente de novo.
6. **Renderize o BOOT BUNDLE** e exiba no chat (nunca só em arquivo):
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/hooks/_handoff_io.py render --lane <lane>
   ```
7. **Avise explicitamente:** "Pronto para /clear — bloco acima é o que a próxima sessão recebe." + se o passo 1-2 rodou, mencione o que foi registrado no histórico (ou por que pulou). Nunca sugerir `/clear` sem o bloco montado e exibido.

## Exemplos executados

```console
$ echo '{"schema_version":"1.1","handoff_id":"HO-20260710-1600-solo","created_at":"2026-07-10T16:00:00-03:00","trigger":"manual","quality":"full","session":{"session_id":"s1","lane_id":"solo"},"estado":{"resumo":"fechei a FASE 5","numeros":[]},"git":{"head":"637561f5","branch":"feat/codex-migration","dirty":true,"untracked":5},"proximo_passo":[{"ordem":1,"descricao":"comecar FASE 6","verify_first_cmd":"test -d lane-kit"}],"valid_until":"2026-07-17T00:00:00-03:00"}' | python hooks/_handoff_io.py write --stdin
_handoff_io: escrito em .claude/handoff/HANDOFF-CURRENT-solo.json
```
<!-- executado: 2026-07-10 · exit=0 -->

```console
$ echo '{"schema_version":"1.1","handoff_id":"HO-x","created_at":"2026-07-10T16:00:00-03:00","trigger":"manual","quality":"full","session":{"session_id":"s1","lane_id":"solo"},"estado":{"resumo":"x"},"git":{"head":"a","branch":"m","dirty":false,"untracked":0},"proximo_passo":[{"ordem":1,"descricao":"sem verify"}],"valid_until":"2026-07-17T00:00:00-03:00"}' | python hooks/_handoff_io.py write --stdin
  [REJEITADO] proximo_passo[0] sem verify_first_cmd (LC-4: próximo passo sem verificação de idempotência)
```
<!-- executado: 2026-07-10 · exit=1 -->
(handoff sem `verify_first_cmd` é REJEITADO — a próxima sessão nunca herda um passo sem forma de checar se já foi feito.)

```console
$ python hooks/_handoff_io.py render --lane solo
⚠️ CONTEXTO RESTAURADO = REFERÊNCIA HISTÓRICA, NÃO FILA (LC-4)
HANDOFF HO-20260710-1600-solo · full · lane=solo
ESTADO: fechei a FASE 5
PRÓXIMO PASSO 1: comecar FASE 6
  → ANTES DE EXECUTAR, RODE: test -d lane-kit (se já feito: pular, registrar)
Arquivo completo: .claude/handoff/HANDOFF-CURRENT-solo.json
```
<!-- executado: 2026-07-10 · exit=0 -->

(exemplos do passo de rollup condicional: ver `doc-rollup` SKILL.md — os mesmos payloads/exit-codes se aplicam quando chamado a partir daqui.)

## Prova

```bash
python ${CLAUDE_PLUGIN_ROOT}/hooks/_handoff_io.py --self-test
python ${CLAUDE_PLUGIN_ROOT}/scripts/doc_rollup.py --self-test
```
