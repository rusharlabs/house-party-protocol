---
name: gated-improvement-proposal
description: Toda auto-edição do harness (regra/CLAUDE.md/prompt/hook) vira PROPOSTA que passa por gate antes de aplicar — nunca auto-merge sensível
---

> **Auto-Trigger:** Quando se vai modificar o próprio harness — regra, CLAUDE.md, prompt de sistema, hook, settings, ou política do agente
> **Keywords:** "atualizar regra", "editar CLAUDE.md", "auto-melhoria", "mudar o hook", "alterar prompt", "self-improve", "evoluir o agente"
> **Prioridade:** ALTA
> **Tools:** Read, Write, Edit, Bash
> **Doutrina relacionada:** `rules/partial-autonomy-slider.md` (níveis 0-5), `rules/loop-maker-checker.md` (proposta ≠ quem aprova).

# gated-improvement-proposal — o harness muda a si mesmo SOB gate

Auto-editar regra/CLAUDE.md/prompt sem validação corrompe o harness; exigir humano em tudo trava a evolução. A saída é o **gate**.

## Contrato

**ENTRADA:** diff proposto + justificativa + critério de aceite testável.

**SAÍDA:** mudança aplicada (se gate verde E abaixo do teto de autonomia) OU proposta na `gate-sheet` (se gate vermelho OU path sensível).

**EXIT CODES** (do `done_gate.py`, rodado como gate ANTES de aplicar):

| Exit | Significado |
|---|---|
| 0 | DONE — critério passou; pode aplicar (se autonomia permitir) |
| 1 | NOT-DONE — critério falhou; NÃO aplica, vira proposta |
| 2 | uso inválido do done_gate |

**ESTADO QUE TOCA:**

| Recurso | Lê/Escreve | Propósito |
|---|---|---|
| `operator-profile.yaml` (`autonomia.por_acao`, `autonomia.paths_sensiveis_auto_gate`) | Lê | decide auto-aplicar vs propor |
| regra/CLAUDE.md/hook/prompt alvo | Escreve (se gate verde + autonomia permite) | a mudança em si |
| `gate-sheet` | Escreve (se gate vermelho ou path sensível) | proposta pendente de humano |

## Processo
1. **Vire PROPOSTA**, não edição direta: `diff` + justificativa + **critério de aceite testável** + qual `autonomia.por_acao` se aplica.
2. **Rode o gate ANTES de aplicar:** `python ${CLAUDE_PLUGIN_ROOT}/scripts/done_gate.py --profile <tipo>` e/ou `eval-driven-development`. Reuse o runner existente — **não reimplemente eval**.
3. **Consulte a autonomia** do `operator-profile.yaml`:
   - `autonomia.por_acao.auto_edit_harness` (default 1) decide auto-aplicar vs propor.
   - Qualquer alvo em `autonomia.paths_sensiveis_auto_gate` (`settings*.json`, `.claude/hooks/**`, `**/.env`, `.claude/rules/**`) = **gate humano forçado, nunca auto-merge**.
4. **Aplique só se** gate verde **E** abaixo do teto de autonomia; senão entregue como PR/proposta na `gate-sheet`.
5. **Registre** a mudança (rastreável: o que mudou, por quê, qual eval passou).

## Quando NÃO Ativar
- Edição de conteúdo de domínio comum (não-harness) — fluxo normal.
- Quando não há eval/critério possível — não auto-aplique; vire gate humano.

## Exemplos executados

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
(critério falhou → a proposta NÃO se auto-aplica; vira item da gate-sheet, exatamente o passo 4.)

```console
$ python scripts/done_gate.py --json "python -c \"import sys; sys.exit(0)\""
{"done": true, "results": [{"cmd": "python -c \"import sys; sys.exit(0)\"", "passed": true, "exit_code": 0, "tail": ""}]}
```
<!-- executado: 2026-07-10 · exit=0 -->

## Prova

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/done_gate.py --self-test
```

## Veja também
`done_gate.py` (o gate), `partial-autonomy-slider` (níveis 0-5), `distill_corrections.py` (a fonte mais comum de propostas de regra).
