---
name: parallel-dispatch
description: Dispara tarefas independentes em ondas com teto de concorrência + fallback sequencial em rate-limit
---

> **Auto-Trigger:** Quando há 2+ tarefas independentes (paths/domínios disjuntos) que podem rodar em paralelo
> **Keywords:** "paralelo", "fan-out", "em paralelo", "vários ao mesmo tempo", "dispatch", "ondas", "lotes"
> **Prioridade:** ALTA
> **Tools:** Task/Agent, Bash, Read

# parallel-dispatch — fan-out com teto e fallback

Generaliza o `dispatching-parallel-agents` de forma **portátil e config-driven**. Resolve a lição "ondas de ≤3 vencem onde 8-16 explodem (rate-limit do servidor)".

## Contrato

**ENTRADA:** lista de tarefas independentes (escopo disjunto); `concorrencia.teto`/`concorrencia.fallback` do `operator-profile.yaml`.

**SAÍDA:** resultados das tarefas, verificados no disco (não a mensagem "pronto" do agente); ondas fechadas em barreira.

**EXIT CODES** (do `${CLAUDE_PLUGIN_ROOT}/_lib/concurrency.py`, invocado no passo 2 para ler o teto):

| Exit | Significado |
|---|---|
| 0 | teto/wave_size/fallback impressos com sucesso (sempre — degrada para defaults sem profile) |

**ESTADO QUE TOCA:**

| Recurso | Lê/Escreve | Propósito |
|---|---|---|
| `operator-profile.yaml` (`concorrencia.*`) | Lê | teto, wave_size, fallback |
| stderr dos agentes despachados | Lê | detectar rate-limit (`is_rate_limited`) |
| output de cada tarefa no disco | Lê | verificação real (passo 6) |

## Processo
1. **Confirme independência.** Só paralelize tarefas com **escopo disjunto** (paths/domínios que não se sobrepõem). Se há dependência sequencial ou estado compartilhado, NÃO paralelize.
2. **Leia o teto.** `python ${CLAUDE_PLUGIN_ROOT}/_lib/concurrency.py` imprime `teto`/`wave_size`/`fallback` do `operator-profile.yaml` (default teto=3). Nunca exceda o teto.
3. **Agrupe em ondas** de tamanho ≤ teto. Despache uma onda, **só abra a próxima quando a anterior fechar** (barreira).
4. **Cada tarefa carrega contrato:** objetivo + escopo + **constraint de não tocar arquivos fora do seu escopo** + formato de retorno.
5. **Fallback em rate-limit.** Se `is_rate_limited(stderr)` (casa "429"/"rate limit"/"quota"/"overloaded"), degrade conforme `concorrencia.fallback` do profile — default `sequential-local`: termine as tarefas restantes **sequencialmente e localmente** (bash/diretamente), imune ao rate-limit do servidor.
6. **Verifique o retorno.** O "done" de agente delegado mente — confirme no disco/fonte (ver `adversarial-refuter` / `delegate-with-handback`).

## Quando NÃO Ativar
- Tarefa única, ou tarefas com dependência sequencial / estado compartilhado.
- Quando o custo de coordenação supera o ganho (2 tarefas triviais).
- Quando o ambiente não tem um 2º executor disponível.
- 1 delegação só, com handback individual → use `delegate-with-handback` (esta skill é fan-out de N; aquela é 1-para-1).

## Exemplos executados

```console
$ python ${CLAUDE_PLUGIN_ROOT}/_lib/concurrency.py
teto=3 wave_size=3 fallback=sequential-local signals=['429', 'rate limit', 'quota', 'overloaded']
```
<!-- executado: 2026-07-10 · exit=0 -->

```console
$ python ${CLAUDE_PLUGIN_ROOT}/_lib/concurrency.py --self-test
self-test OK
```
<!-- executado: 2026-07-10 · exit=0 -->

```console
$ python ${CLAUDE_PLUGIN_ROOT}/scripts/done_gate.py --profile hooks
  [FAIL] (exit 2) python .claude/hooks/agentic_postflight.py --self-test
        ^ python.exe: can't open file '...\.claude\hooks\agentic_postflight.py': [Errno 2] No such file or directory

DONE-GATE: NOT-DONE (0/1 criterios)
```
<!-- executado: 2026-07-10 · exit=1 -->
(passo 6 — "o done de agente delegado mente": o gate confirma no disco e rejeita quando o critério não bate.)

## Prova

```bash
python ${CLAUDE_PLUGIN_ROOT}/_lib/concurrency.py --self-test
```
