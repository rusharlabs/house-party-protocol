---
description: "Arma o /ralph-gate: loop autônomo que só aceita <promise> se o done_gate passar de verdade"
argument-hint: "--goal G-X | --charter \"prompt\" --criteria \"cmd1\" [\"cmd2\" ...] [--max-iterations N]"
allowed-tools: ["Bash(python ${CLAUDE_PLUGIN_ROOT}/hooks/ralph_gate.py:*)"]
hide-from-slash-command-tool: "true"
---

# /ralph-gate — o Ralph que não aceita promessa sem prova

Arma o loop autônomo unificado (motor + trava no mesmo processo — ver `hooks/ralph_gate.py`).
Diferença do ralph-loop oficial: a `<promise>` só destrava a parada se o `done_gate.py` passar
de verdade, RE-EXECUTADO dentro do processo do hook — depois da sua fala, fora do seu alcance.
Você não pode forjar o exit-code de um subprocess do harness.

```!
python "${CLAUDE_PLUGIN_ROOT}/hooks/ralph_gate.py" start --session "${CLAUDE_SESSION_ID}" $ARGUMENTS
```

Trabalhe na tarefa. Quando você tentar parar (Stop), o `ralph_gate.py` vai:
1. Procurar `<promise>TEXTO</promise>` na sua última mensagem.
2. Se NÃO achar → re-alimenta o charter (você continua, sem perguntar "posso seguir?").
3. Se achar → roda os critérios de verdade (`done_gate.gate`). Só PASSA se TODOS saírem exit 0.
4. Se passou → libera a parada, registra `gate-passed` no ledger, some o estado.
5. Se falhou → re-alimenta com as falhas reais e a instrução "NÃO emita `<promise>` até passar DE VERDADE".

REGRA CRÍTICA: só emita `<promise>DONE</promise>` quando a afirmação for literal e
verificavelmente verdadeira. Emitir promessa falsa para escapar do loop não funciona —
o gate roda o critério de novo, não acredita no texto. Se o teto de iterações (`--max-iterations`)
for atingido antes de terminar, o loop libera sozinho e registra `paused-budget` no ledger
(LC-5) — não é um "não terminei", é uma parada legítima de orçamento.

Use `/cancel-ralph-gate` para cancelar manualmente.
