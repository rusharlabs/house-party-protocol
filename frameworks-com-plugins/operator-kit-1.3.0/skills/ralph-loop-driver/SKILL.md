---
name: ralph-loop-driver
description: Vira o agente em engenheiro-líder autônomo — lê charter+work-list, executa até esgotar, self-prompta, para nas stop-conditions
---

> **Auto-Trigger:** Quando o operador autoriza execução ampla de um backlog (gatilhos em `loop.gatilho_autorizacao` do profile)
> **Keywords:** "/goal", "auto", "100%", "faça tudo", "máxima capacidade", "loop autônomo", "até concluir", "relentless"
> **Prioridade:** ALTA
> **Tools:** Read, Write, Edit, Bash, Task/Agent
> **Doutrina relacionada:** `rules/loop-operator.md` (pré-flight + 4 stop-conditions), `rules/loop-patterns-catalog.md` (qual arquitetura de loop usar), `rules/learned-corrections.md` (LC-1/LC-2), `rules/loop-cost-budget.md` (orçamento como parada de 1ª classe).

# ralph-loop-driver — o driver do loop autônomo

Generaliza o `/goal` (NÃO duplica). Transforma o agente em engenheiro-líder que esmaga o work-list sozinho, sem parar a cada item para perguntar "posso seguir?".

## Contrato

**ENTRADA:** `loop.charter` + `loop.work_list` + `loop.stop_conditions` (lidos do `operator-profile.yaml` via `_lib/profile_loader`); `paths.state_ssot` (fonte de verdade pro LC-1).

**SAÍDA:** work-list com itens marcados feitos (in-place); commits git por path (0 push); relatório de parada quando uma stop-condition dispara.

**EXIT CODES** (do `done_gate.py`, invocado a cada iteração — passo 5 do ciclo):

| Exit | Significado |
|---|---|
| 0 | DONE — todos os critérios do item passaram; pode marcar feito |
| 1 | NOT-DONE — ≥1 critério falhou (ou lista vazia); item volta pro work-list |
| 2 | uso inválido do done_gate (não deveria ocorrer em operação normal) |

**ESTADO QUE TOCA:**

| Arquivo/recurso | Lê/Escreve | Propósito |
|---|---|---|
| `operator-profile.yaml` (`loop.*`) | Lê | charter, work-list, stop-conditions |
| `paths.state_ssot` | Lê | fonte de verdade ao vivo (LC-1) |
| arquivo do work-list | Lê+Escreve | marca itens feitos |
| `.git` (commits) | Escreve | 1 commit por path tocado; NUNCA push |

## Ciclo (cada iteração)
1. **Re-alinhar:** ler `loop.charter` + o conceito-norte + o SSoT (`paths.state_ssot`) — *driftei? algo meio-feito?*
2. **Verificar live (LC-1):** estado real da fonte canônica antes de citar qualquer número/status.
3. **Escolher** o item não-feito de **maior alavancagem** do `loop.work_list`.
4. **Executar** — em ondas via `parallel-dispatch` quando paralelizável; com **adversarial verify** (refutar antes de aceitar).
5. **Verificar:** `python ${CLAUDE_PLUGIN_ROOT}/scripts/done_gate.py --profile <tipo>` antes de marcar feito.
6. **Marcar feito** no work-list + **commit por path** (0 push — guardrail).
7. **Capstone por onda:** testes + validadores do projeto.
8. **Continuar** direto para a próxima iteração, sem parar para perguntar "posso seguir?" — é o que "engenheiro-líder autônomo" significa. **Otimização opcional:** se esta skill estiver rodando DENTRO do main-loop `/loop` dinâmico, `ScheduleWakeup` pode espaçar o auto-pace entre ciclos — mas é exclusivo do main-loop (subagentes e sessões headless NÃO a enxergam; ver `loop-patterns-catalog`). Sem ela, o ciclo simplesmente continua na mesma sessão — nunca é bloqueante.
9. **A cada ~5 ciclos — revisão adversarial:** "que ponta ficou solta? driftei do conceito? duplicata/órfão novo?".

## Guardrails (do charter; inquebráveis)
0 push sem ordem · backup antes de mutar prod · snapshot antes de deletar · trava de credencial · **gate-humano** (billing/OAuth/legal/cliente/deploy-go/secret) vira formulário (ver `gate-sheet-collector`), nunca bloqueia o loop · LC-1.

## Stop-conditions (`loop.stop_conditions`)
Lane autônoma esgotada · teto de tempo · risco irreversível iminente → PARA + reporta.

## Quando NÃO Ativar
- Sem autorização explícita de execução ampla (tarefa pontual → execução direta).
- Sem charter/work-list definidos → primeiro use `loop-charter-template`.
- Tarefas que dependem majoritariamente de gate-humano (drene p/ a gate-sheet e pare).

## Exemplos executados

O passo 5 do ciclo (verificação antes de marcar feito) é o `done_gate.py` do kit. Exemplos reais:

```console
$ python scripts/done_gate.py "python -c \"print(1)\""
  [OK ] (exit 0) python -c "print(1)"

DONE-GATE: DONE (1/1 criterios)
```
<!-- executado: 2026-07-10 · exit=0 -->

```console
$ python scripts/done_gate.py --profile hooks
  [FAIL] (exit 2) python .claude/hooks/agentic_postflight.py --self-test
        ^ python.exe: can't open file '...\.claude\hooks\agentic_postflight.py': [Errno 2] No such file or directory

DONE-GATE: NOT-DONE (0/1 criterios)
```
<!-- executado: 2026-07-10 · exit=1 -->

```console
$ python scripts/done_gate.py --json "python -c \"import sys; sys.exit(0)\""
{
  "done": true,
  "results": [
    {"cmd": "python -c \"import sys; sys.exit(0)\"", "passed": true, "exit_code": 0, "tail": ""}
  ]
}
```
<!-- executado: 2026-07-10 · exit=0 -->

## Prova

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/done_gate.py --self-test
```
