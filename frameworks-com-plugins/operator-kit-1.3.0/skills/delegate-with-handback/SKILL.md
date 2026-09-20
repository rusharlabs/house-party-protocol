---
name: delegate-with-handback
description: Delega tarefa longa/independente a um 2º agente com contexto explícito e gate de verificação no retorno
---

> **Auto-Trigger:** Tarefa longa/independente (audit, refactor amplo, pesquisa) que ganharia com um 2º agente ou segunda opinião
> **Keywords:** "delegar", "delega", "codex", "segundo agente", "segunda opinião", "rodar em paralelo", "offload", "revisar"
> **Prioridade:** MÉDIA
> **Tools:** Task/Agent, Bash, Read, Grep

# delegate-with-handback — delegar com handback verificado

Generaliza o `codex-delegate` para um framework **provider-agnóstico**. Nunca confia no "done" do delegado.

## Contrato

**ENTRADA:** o pacote de contexto explícito (path/branch/commit + objetivo + critério de aceite + constraints) montado pelo passo 2; o output do delegado no disco.

**SAÍDA:** aceite (item marcado feito) OU re-enfileiramento com o gap apontado.

**EXIT CODES** (do `done_gate.py`, usado no handback — passo 4):

| Exit | Significado |
|---|---|
| 0 | DONE — critério de aceite passou; aceitar o handback |
| 1 | NOT-DONE — critério falhou; re-enfileirar com o gap |
| 2 | uso inválido do done_gate |

**ESTADO QUE TOCA:**

| Recurso | Lê/Escreve | Propósito |
|---|---|---|
| output do delegado (arquivo/diff no disco) | Lê | verificação real (não a mensagem "pronto") |
| `operator-profile.yaml` (`autonomia`) | Lê | qual provider despachar |
| hook `rule_capture` (se wired) | Escreve | preserva o padrão em `.claude/memory/_captured-rules.md` p/ o `distill_corrections.py` destilar depois |

## Processo
1. **Decida delegar** quando: tarefa longa, independente, repetitiva, ou quando uma **segunda opinião** reduz risco.
2. **Monte o pacote de contexto explícito** (sem isso o output volta inútil):
   - `path/branch/commit` exatos · objetivo em 1 frase · **critério de aceite testável** · constraints (o que NÃO tocar) · formato de retorno.
3. **Despache** ao provider configurado (`autonomia`/ambiente define qual — Codex/outro). Em fan-out, respeite `parallel-dispatch` (teto + ondas).
4. **Handback = GATE, não confiança.** Ao receber o resultado:
   - Leia o output REAL no disco (não a mensagem "pronto").
   - Rode `python ${CLAUDE_PLUGIN_ROOT}/scripts/done_gate.py --profile <tipo>` (ou o teste/critério de aceite).
   - Só aceite se o gate passar; senão **re-enfileire** com o gap apontado.
5. **Registre** a falha recorrente (o hook `rule_capture`, se wired, preserva o padrão p/ o `distill_corrections.py` destilar depois).

## Quando NÃO Ativar
- Tarefa curta que você faz mais rápido direto.
- Sem provider secundário disponível → faça local + verifique.
- Quando o contexto não cabe num pacote explícito (refine o escopo antes).
- Fan-out de N tarefas independentes (sem handback individual) → use `parallel-dispatch`; esta skill é 1 delegação com gate no retorno.

## Exemplos executados

```console
$ python scripts/done_gate.py "python -c \"print(1)\""
  [OK ] (exit 0) python -c "print(1)"

DONE-GATE: DONE (1/1 criterios)
```
<!-- executado: 2026-07-10 · exit=0 -->

```console
$ python scripts/done_gate.py "python -c \"import sys; sys.exit(1)\""
  [FAIL] (exit 1) python -c "import sys; sys.exit(1)"

DONE-GATE: NOT-DONE (0/1 criterios)
```
<!-- executado: 2026-07-11 · exit=1 -->
(handback rejeitado — é exatamente o comportamento esperado do passo 4: "só aceite se o gate passar". Critério auto-contido — não depende de nenhum arquivo externo ao kit.)

```console
$ python scripts/done_gate.py --json "python -c \"import sys; sys.exit(0)\""
{"done": true, "results": [{"cmd": "python -c \"import sys; sys.exit(0)\"", "passed": true, "exit_code": 0, "tail": ""}]}
```
<!-- executado: 2026-07-10 · exit=0 -->

## Prova

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/done_gate.py --self-test
```
