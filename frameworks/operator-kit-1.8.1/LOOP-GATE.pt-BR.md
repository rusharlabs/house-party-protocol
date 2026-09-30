[English](LOOP-GATE.md) · [Português](LOOP-GATE.pt-BR.md)

# /loop-gate — o loop gate que não aceita promessa sem prova

> Ver `hooks/loop_gate.py` (motor+trava), `commands/loop-gate.md` (launcher),
> `evals/loop-gate-T1-T4.sh` (teste-assinatura, pass^k=1.00 em k=3).
> O gate carregava outro nome antes; até a 3.0 o caminho antigo do hook, os slash commands
> antigos e o nome antigo do arquivo de estado continuam funcionando como aliases deprecados,
> e cada alias diz isso no próprio texto.

## O pitch (1 parágrafo)

Um loop de Stop hook `decision:block` que re-alimenta o prompt até o modelo emitir
`<promise>TEXTO</promise>` é um loop sólido, mas o "done" dele é **auto-declarado por tag de
texto, sem rodar nada** — o hook compara string e libera.
O nosso `done_gate.py` exige **exit-code 0 real** em N comandos. O `/loop-gate` funde os
dois: a `<promise>` só destrava a saída se o `done_gate` passar, **re-executado DENTRO do
processo do hook** — depois da fala do modelo, fora do alcance dela. O modelo pode forjar
qualquer texto no transcript (inclusive fingir "DONE-GATE: DONE (2/2)"); não pode forjar o
exit-code de um subprocess do harness. Prova disso = teste T3 (`evals/loop-gate-T1-T4.sh`).

## Modo A — unificado (DEFAULT, sem dependências)

`hooks/loop_gate.py` é o motor E a trava no MESMO processo Python (stdlib only). Zero jq,
zero bash, zero corrida entre "remover o state" e "validar a promise". É o modo que este kit
usa por padrão (wired em `hooks/hooks.json` → `Stop`, `timeout: 120`).

Por que este kit não usa um motor de loop por tag de texto — um Stop hook, em geral um shell
script, que libera assim que vê a tag — como motor por padrão:
- **DOA em máquinas sem `jq`** — um motor em shell que lê o JSON com `jq` sob
  `set -euo pipefail` dá crash silencioso já na 1ª iteração quando o `jq` não está no PATH
  (medido no motor que motivou este kit: três chamadas a `jq`, nenhum fallback).
- **Bug de acoplamento** — um motor assim dá `rm` no próprio arquivo de estado **ao ver a
  `<promise>`, ANTES de qualquer veto**. Se uma trava externa rejeitasse DEPOIS, o motor já
  teria morrido — não há como re-armar limpo.

## Modo B — motor externo + sidecar de re-arme (OPT-IN, dependency-check obrigatório)

Para quem já roda um motor de loop por tag de texto e quer só ADICIONAR a trava do `done_gate`
por cima, sem trocar de motor:

1. **Dependency-check primeiro:** `command -v jq` e `command -v bash` no PATH do runtime alvo.
   Sem os dois, Modo B não é viável ali — caia para o Modo A.
2. Mantenha o Stop hook do motor como está.
3. Adicione um **sidecar** que roda ANTES do hook do motor no mesmo evento Stop (ordem dos
   hooks no array importa — o sidecar vem primeiro):
   - Lê o arquivo de estado do motor (tipicamente um Markdown sob `.claude/` cujo frontmatter
     carrega `completion_promise`).
   - Se a última mensagem do transcript contém a promise **E** os critérios do `done_gate`
     (declarados à parte, ex.: `.claude/loop-gate.criteria.json`) **falham**: o sidecar
     **reescreve** o arquivo de estado do motor com a promise **temporariamente vazia**
     (`completion_promise: ""`) e injeta os motivos da falha no início do arquivo — assim,
     quando o hook do motor rodar em seguida, ele NÃO vai casar a promise (string vazia
     nunca bate) e vai re-alimentar o loop com o conteúdo atualizado.
   - Se os critérios PASSAM: o sidecar não mexe em nada — o motor libera normalmente.
4. Isto é um **contorno**, não uma correção do bug de acoplamento: se o hook do motor já rodou
   e apagou o arquivo ANTES do sidecar (ordem trocada), o Modo B não protege nada naquele
   ciclo. **A ordem dos hooks no array é a garantia real — não uma convenção opcional.**

Modo B fica **documentado, não implementado como código neste kit** — é para quem já tem
investimento num motor externo e aceita o risco de ordenação acima. O Modo A (default) não
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
/loop-gate --charter "..." --criterion-timeout 300 --criteria "python -m hpp evidence run --id e2e-login --timeout 280 --artifact \"pw-out/**/trace.zip\" -- npx playwright test tests/login.spec.ts"
```

**Rodar, nunca verificar, como trava.** O `evidence run` re-executa a spec dentro do processo do
hook e grava um registro novo. O `evidence verify` só re-hasheia um registro gravado antes —
possivelmente pelo próprio modelo de quem a trava existe para desconfiar — e um registro tem
auto-hash; só é assinado quando o `evidence run` recebeu `--sign-key`, e o `verify` só exige a
assinatura sob `--allowed-signers`. Trava construída só sobre `verify` confia no maker. Mantenha o
`--timeout` do hpp abaixo do `--criterion-timeout`: o hpp encerra a árvore de processos inteira no
próprio timeout e grava o veredito `timeout`. Use aspas duplas dentro do critério, porque ele roda
pelo shell do sistema e o cmd.exe mantém aspas simples como caractere literal.

## Integração goal-a-goal

```
goal_ledger.py --next  →  /loop-gate --goal G-X --criteria "<PRD DoD>" --charter "..."
   → done_gate passes  →  --set G-X done  →  goal_review.py --goal G-X  →  next goal
```

Critérios do `--goal` vêm do DoD do PRD via `goal_review.extract_criteria` (cadeia que já
passa `--self-test` isolado). Kill-switches por referência: `loop-operator.md` (4
stop-conditions), `loop-cost-budget.md` (LC-5 — o teto de iterações É o orçamento
mecanicamente aplicável por um Stop hook; custo em token/$ é rastreado fora, pela sessão que
chama `/loop-gate`), `stale-replay-guard.md` (LC-4 — antes de re-armar um goal, checar se
ele já não está `done` no ledger).
