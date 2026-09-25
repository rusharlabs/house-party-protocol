[English](RALPH-GATE.md) · [Português](RALPH-GATE.pt-BR.md)

# /ralph-gate — o Ralph que não aceita promessa sem prova

> Ver `hooks/ralph_gate.py` (motor+trava), `commands/ralph-gate.md` (launcher),
> `evals/ralph-gate-T1-T4.sh` (teste-assinatura, pass^k=1.00 em k=3).

## O pitch (1 parágrafo)

Um loop de Stop hook `decision:block` que re-alimenta o prompt até o modelo emitir
`<promise>TEXTO</promise>` é um loop sólido, mas o "done" dele é **auto-declarado por tag de
texto, sem rodar nada** — o hook compara string e libera.
O nosso `done_gate.py` exige **exit-code 0 real** em N comandos. O `/ralph-gate` funde os
dois: a `<promise>` só destrava a saída se o `done_gate` passar, **re-executado DENTRO do
processo do hook** — depois da fala do modelo, fora do alcance dela. O modelo pode forjar
qualquer texto no transcript (inclusive fingir "DONE-GATE: DONE (2/2)"); não pode forjar o
exit-code de um subprocess do harness. Prova disso = teste T3 (`evals/ralph-gate-T1-T4.sh`).

## Modo A — unificado (DEFAULT, sem dependências)

`hooks/ralph_gate.py` é o motor E a trava no MESMO processo Python (stdlib only). Zero jq,
zero bash, zero corrida entre "remover o state" e "validar a promise". Éo modo que este kit
usa por padrão (wired em `hooks/hooks.json` → `Stop`, `timeout: 120`).

Por que este kit não usa o `stop-hook.sh` do plugin oficial `ralph-loop` como motor por padrão:
- **DOA em máquinas sem `jq`** — `stop-hook.sh` usa `jq` em 3 pontos + `set -euo pipefail`;
  sem `jq` no PATH, crash silencioso já na 1ª iteração.
- **Bug de acoplamento** — o `stop-hook.sh` oficial dá `rm` no arquivo de estado
  (`.claude/ralph-loop.local.md`) **ao ver a `<promise>`, ANTES de qualquer veto**. Se uma
  trava externa rejeitasse DEPOIS, o motor já teria morrido — não há como re-armar limpo.

## Modo B — oficial + sidecar de re-arme (OPT-IN, dependency-check obrigatório)

Para quem já usa o plugin `ralph-loop` oficial e quer só ADICIONAR a trava do `done_gate`
por cima, sem trocar de motor:

1. **Dependency-check primeiro:** `command -v jq` e `command -v bash` no PATH do runtime alvo.
   Sem os dois, Modo B não é viável ali — caia para o Modo A.
2. Mantenha o `stop-hook.sh` oficial como está.
3. Adicione um **sidecar** que roda ANTES do hook oficial no mesmo evento Stop (ordem dos
   hooks no array importa — o sidecar vem primeiro):
   - Lê o `.claude/ralph-loop.local.md` (frontmatter: `completion_promise`).
   - Se a última mensagem do transcript contém a promise **E** os critérios do `done_gate`
     (declarados à parte, ex.: `.claude/ralph-gate.criteria.json`) **falham**: o sidecar
     **reescreve** `.claude/ralph-loop.local.md` com a promise **temporariamente vazia**
     (`completion_promise: ""`) e injeta os motivos da falha no início do arquivo — assim,
     quando o `stop-hook.sh` oficial rodar em seguida, ele NÃO vai casar a promise (string
     vazia nunca bate) e vai re-alimentar o loop com o conteúdo atualizado.
   - Se os critérios PASSAM: o sidecar não mexe em nada — o oficial libera normalmente.
4. Isto é um **contorno**, não uma correção do bug de acoplamento: se o oficial já rodou
   e apagou o arquivo ANTES do sidecar (ordem trocada), o Modo B não protege nada naquele
   ciclo. **A ordem dos hooks no array é a garantia real — não uma convenção opcional.**

Modo B fica **documentado, não implementado como código neste kit** — é para quem já tem
investimento no plugin oficial e aceita o risco de ordenação acima. O Modo A (default) não
tem esse risco porque motor e trava são o MESMO processo.

## Timeout de critério e critérios end-to-end

Cada critério pode rodar por `--criterion-timeout` segundos (default 20; um número positivo e
finito, gravado no estado do loop pelo `start`). Critério que passa disso conta como falha. O Stop
hook tem um teto próprio — `timeout: 120` em `hooks/hooks.json` e no bloco manual do
`SETTINGS-WIRE.md` — e ele precisa cobrir a soma dos timeouts dos critérios: se os critérios
passarem dele, o host para o hook e a trava nunca responde. Para critérios longos, suba os dois.

Para um item end-to-end ou visual, o critério é `python -m hpp evidence run` (exige o núcleo
HPP):

```bash
/ralph-gate --charter "..." --criterion-timeout 300 --criteria "python -m hpp evidence run --id e2e-login --timeout 280 --artifact \"pw-out/**/trace.zip\" -- npx playwright test tests/login.spec.ts"
```

**Rodar, nunca verificar, como trava.** O `evidence run` re-executa a spec dentro do processo do
hook e grava um registro novo. O `evidence verify` só re-hasheia um registro gravado antes —
possivelmente pelo próprio modelo de quem a trava existe para desconfiar — e um registro tem
auto-hash, não assinatura. Trava construída só sobre `verify` confia no maker. Mantenha o
`--timeout` do hpp abaixo do `--criterion-timeout`: o hpp encerra a árvore de processos inteira no
próprio timeout e grava o veredito `timeout`. Use aspas duplas dentro do critério, porque ele roda
pelo shell do sistema e o cmd.exe mantém aspas simples como caractere literal.

## Integração goal-a-goal

```
goal_ledger.py --next  →  /ralph-gate --goal G-X --criteria "<PRD DoD>" --charter "..."
   → done_gate passes  →  --set G-X done  →  goal_review.py --goal G-X  →  next goal
```

Critérios do `--goal` vêm do DoD do PRD via `goal_review.extract_criteria` (cadeia que já
passa `--self-test` isolado). Kill-switches por referência: `loop-operator.md` (4
stop-conditions), `loop-cost-budget.md` (LC-5 — o teto de iterações É o orçamento
mecanicamente aplicável por um Stop hook; custo em token/$ é rastreado fora, pela sessão que
chama `/ralph-gate`), `stale-replay-guard.md` (LC-4 — antes de re-armar um goal, checar se
ele já não está `done` no ledger).
