# NOTICE — inspiração ECC (evolve/instinct_promote.py)

`evolve/instinct_promote.py` implementa um padrão **inspirado** no mecanismo de
"instinct + confidence-scoring" do projeto **ECC** (Excellence Compounding Cycle):

- Repositório: https://github.com/affaan-m/ECC
- Autor: Affaan Mustafa
- Licença: MIT, © 2026 Affaan Mustafa

**Nenhuma linha de código do ECC foi copiada.** O CLI original do ECC
(`skills/continuous-learning-v2/scripts/instinct-cli.py`, ~2000 linhas) resolve um escopo
muito maior — instincts por-projeto e globais, import/export remoto com validação SSRF-safe,
clustering em skills/comandos/agentes, TTL/prune entre múltiplos projetos. `instinct_promote.py`
é uma reimplementação mínima e nova, escrita do zero para este kit, cobrindo só o pedaço que o
`/ralph-gate` deste kit precisa: falha recorrente do `done_gate` vira candidato; confiança =
contagem de recorrência (via cursor idempotente sobre `HANDOFF-LEDGER.jsonl`); promoção para
`LEARNINGS.md` é **sempre ato humano** (nunca automático — mesmo princípio do
`partial-autonomy-slider`: propor, não auto-executar em algo que persiste/ensina o time).

Também é dado crédito ao plugin oficial **`ralph-loop`** (Anthropic) pela mecânica original de
Stop-hook com `<promise>` — ver `RALPH-GATE.md` na raiz deste kit.

Se algum dia este arquivo (ou `instinct_promote.py`) for expandido incorporando texto/código
literal do ECC, esta seção deve ser atualizada para "Portions derived from ECC
(github.com/affaan-m/ECC), MIT, © 2026 Affaan Mustafa" — hoje isso NÃO é o caso; o que existe é
inspiração de padrão, não derivação de código.
