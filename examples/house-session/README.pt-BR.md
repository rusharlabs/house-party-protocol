[English](README.md) · [Português](README.pt-BR.md)

# House Session — um painel de decisores pinados, contado, parado e selado

> Novo na 2.7.0.

Vários agentes discutindo uma pergunta só valem o custo se a discussão puder ser conferida: quem
sentou, qual modelo respondeu por cada assento, o que cada um disse antes de ver os outros, quando a
conversa parou e por quê, e qual foi a dissidência. `hpp deliberate` registra exatamente isso. O
harness continua sem chamar modelo ([MANIFESTO](../../MANIFESTO.pt-BR.md)): os assentos e o juiz
respondem fora dele, nas próprias lanes ou CLIs, e este comando valida, conta, para e sela o que
eles disseram.

| peça | onde | executa algo? |
|---|---|---|
| o painel `hpp.panel/v1` | `review/panel.json` | não |
| os turnos `hpp.turn/v1` | `review/turns.json` | não |
| a resposta do juiz `hpp.decision/v1` | `review/judge.json` | não |
| o rationale do juiz `hpp.rationale/v1` (novo na 2.8.0) | `review/rationale.json`, textos em `review/steelman-low.txt` e `review/would-change-if.txt` | não |
| o contexto que os assentos receberam (novo na 2.8.0) | `review/context.json` | não |
| o contrato, a contagem, a regra de parada, o selo | `hpp/deliberation.py` · `hpp deliberate` | não |
| um replay de sessões gravadas como um decisor só | `panel_decider.py` sobre `sessions.json` | sem modelo, sem rede, só biblioteca padrão |

Toda sessão aqui é sintética, escrita à mão para este exemplo. Ela prova que o contrato funciona de
ponta a ponta; não mede nada sobre modelo nenhum.

## O painel

Um painel nomeia a pergunta, o hash do estado julgado, cada assento e o orçamento. Cada assento é
`{id, role, provider, model_served, family, lane}`. O painel não começa a menos que:

- todo `model_served` seja uma versão pinada — um alias como `-latest` ou `preview` é recusado;
- os participantes venham de **pelo menos duas famílias de modelo**;
- haja **exatamente um juiz**, numa lane que nenhum participante usa;
- cada participante responda da própria lane;
- os papéis sirvam ao tipo de pergunta (`session_type`):

| `session_type` | participantes exigidos | teto de rodadas |
|---|---|---|
| `plan` | 2 `proponent` · 1 `dissent` · 1 `examiner` | 10 |
| `review` | 2 `examiner` · 1 `dissent` | 10 |
| `release-gate` | 1 `examiner` · 1 `dissent` | 10 |
| `incident` | 2 `proponent` (dois diagnósticos cegos) | 2 — no máximo uma réplica |
| `design` | um `proponent` por opção · 1 `dissent` | 10 |

- `budget` declara `max_rounds` e `max_chars` (o comprimento total dos turnos verbatim).

`judge_independence` é `full` quando a família do juiz não está entre as dos participantes, e
`partial` quando está — declarado, nunca escondido.

```bash
python -m hpp deliberate plan examples/house-session/review/panel.json
```

## Os turnos

Um turno registra a resposta de um assento numa rodada: a `position` (uma opção ou `abstain`), as
afirmações (`fact`, `inference` ou `opinion`, cada uma com os ids em que se apoia), o sha256 e o
comprimento do texto verbatim (o texto fica com você) e `seen_turns` — os hashes dos turnos que o
assento tinha lido antes de responder.

- **A rodada 1 é cega.** Um turno da rodada 1 com qualquer coisa em `seen_turns` é recusado.
- Um turno posterior só pode ter visto turnos de uma rodada **anterior**.
- Um assento fala uma vez por rodada; o juiz não tem turno.

Uma posição é **fundamentada** quando o turno afirma ao menos um `fact` com uma referência que
resolve. Novo na 2.8.0: um painel pode declarar `evidence.ids`, os ids que os seus assentos podem
citar — o contexto que receberam e os registros de evidência que verificaram. `plan --context` lê o
mesmo arquivo de contexto que o `hpp cite check` lê e imprime o painel com esses ids; `--evidence`
acrescenta cada registro `hpp.evidence/v1` que verifica agora, e recusa o que não verifica.

```bash
python -m hpp deliberate plan examples/house-session/review/panel.json --context examples/house-session/review/context.json --out out/panel.json
```

Com os ids declarados, uma referência a qualquer outra coisa é `unsupported`: o `tally` a lista por
rodada, ela não fundamenta nada e nunca é evidência nova — um id inventado não segura uma sessão
nem justifica uma mudança de posição. Um painel que não declara evidência mantém a regra da 2.7.0
(qualquer referência fundamenta) e o registro diz `evidence_gate: not-declared`; ids digitados à mão
sem `sources` dizem `declared-unsourced`, e só ids com fonte declarada (um hash de contexto, um registro
de evidência verificado) dizem `resolved`. Declarar evidência muda o hash do painel, então salve o
painel conferido com `plan ... --out FILE` e grave todo turno contra esse arquivo.

## A contagem e a regra de parada

```bash
python -m hpp deliberate tally --panel examples/house-session/review/panel.json --turns examples/house-session/review/turns.json
python -m hpp deliberate stop --panel examples/house-session/review/panel.json --turns examples/house-session/review/turns.json
```

`tally` relata, por rodada, votos fundamentados e não fundamentados por opção, abstenções, os
assentos **não julgados** (sem turno naquela rodada), a opção à frente, a dissidência fundamentada,
os assentos que mudaram de posição e as mudanças feitas **sem evidência nova** — uma troca de
posição cujo turno não cita nada que aquele assento já não tivesse citado. Um assento que não
respondeu nunca conta como voto contra.

`stop` responde `continue` com a próxima rodada, ou `stop` com a primeira regra que vale, nesta
ordem. A sessão termina na primeira rodada em que uma regra vale: turnos de rodadas posteriores
são recusados, então um assento que faltou à rodada cega não vota depois de ler os outros.

| motivo | quando |
|---|---|
| `not-judged` | um participante não tem turno na última rodada — o veredito fica bloqueado |
| `grounded-convergence` | todos os participantes escolheram a mesma opção, todos fundamentados, nenhuma abstenção |
| `paused-budget` | os turnos verbatim chegaram a `max_chars` |
| `no-new-evidence` | a partir da rodada 2: nenhuma referência que a sessão ainda não tinha visto, e ninguém mudou |
| `max-rounds` | o teto de rodadas foi atingido |

`escalate` é `true` quando a sessão para em `paused-budget`, `no-new-evidence` ou `max-rounds` com
mais de uma posição fundamentada de pé: o painel não resolveu, então a questão vai a uma pessoa como opções,
com a dissidência mantida no registro.

## O registro

```bash
python -m hpp deliberate record --panel examples/house-session/review/panel.json --turns examples/house-session/review/turns.json --judge examples/house-session/review/judge.json --rationale examples/house-session/review/rationale.json --out out/record.json
python -m hpp deliberate verify out/record.json
```

O juiz lê os turnos verbatim na própria lane e responde com um registro `hpp.decision/v1` comum,
que precisa responder à pergunta do painel sobre o estado do painel e vir do provedor e do
modelo pinado do assento do juiz (um registro com método de regra, replay ou humano é recusado: o
assento pina um modelo). `record` recusa uma sessão que não parou e um
veredito sem juiz — exceto quando um assento não foi julgado: aí o veredito é `blocked` e nenhum
juiz é consultado.

O registro `hpp.deliberation/v2` guarda o painel, cada turno por hash, a contagem de cada rodada, a
parada, o orçamento usado, o registro do juiz, o veredito, **a dissidência que perdeu** e quatro
medições — concordância na rodada cega, concordância no fim, mudanças sem evidência nova e a
proporção de votos não fundamentados. `record_sha256` sela tudo isso menos `human_decision`, que uma
pessoa preenche depois (`{value, by, note?}`). `verify` confere o selo **e** re-deriva a contagem, a
parada e o veredito a partir dos turnos e do juiz que o registro guarda: uma edição em qualquer
coisa derivada reprova mesmo quando alguém recalculou o hash. O selo não é assinatura: uma
reescrita coerente de um turno ou do registro do juiz, selada de novo, verifica. Essas entradas
são ancoradas fora do registro, pelos hashes que ele carrega do texto verbatim e da resposta bruta
do juiz — guarde esses arquivos ao lado do registro.

**A dissidência é respondida, não só guardada.** Quando o veredito do juiz deixa de pé uma
dissidência fundamentada, o `record` exige `--rationale`: um `hpp.rationale/v1` escrito pelo
assento do juiz com um **steelman** por posição dissidente — a versão mais forte do lado que
perdeu — e ao menos um **`would_change_if`**, o que derrubaria o veredito. Como os turnos, ele
carrega o hash e o tamanho de cada texto verbatim; aqui os textos são `review/steelman-low.txt` e
`review/would-change-if.txt`. Um rationale que defende uma posição da qual ninguém dissentiu, que
pula uma, ou que vem de outro assento é recusado. Sem dissidência ele é opcional. O registro diz se
houve steelman para cada posição; se ele é bom, só um leitor sabe.

Um registro `hpp.deliberation/v1` selado pela 2.7.0 continua verificando, pelas regras com que foi
selado.

Nesta revisão a dissidência se manteve: `stop` → `max-rounds`, `escalate: true`; o veredito é o
`high` do juiz; `dissent` mantém o assento `c` em `low`; o assento `b` passou de `medium` para
`high` e não é marcado, porque o segundo turno dele cita uma referência que ele ainda não tinha
citado.

## Agindo sobre um veredito (novo na 2.9.0)

Uma sessão selada alimenta os comandos que agem sobre um veredito. Cada um verifica o registro, confere
o tipo de sessão e as opções perguntadas, e recusa um juiz da família de modelo do maker
(`--maker-family`). Um painel só pode tornar o resultado mais estrito:

```bash
python -m hpp route --request request.json --providers providers.json --deliberation plan-record.json --maker-family anthropic
python -m hpp attest create --spec spec.md --output att.json --maker exec-a --checker rev-b --session s1 --verdict approved --deliberation gate-record.json --maker-family anthropic
python multi-session/lane-kit-1.6.0/scripts/lane_board.py select --task TASK-1 --deliberation design-record.json
```

- **`route`** lê uma sessão `plan` sobre `low`/`medium`/`high`: o veredito dela pode subir o risco do
  pedido (e o tier), nunca baixar.
- **`attest create`** lê uma sessão `release-gate` sobre `approved`/`revise`/`blocked` cujos fatos se
  apoiam só em registros `hpp.evidence/v1`: a attestation grava o mais estrito entre o veredito
  declarado e o do painel, e um painel que não decidiu manda para revisão. O hash do registro fica guardado.
- **`lane_board.py select`** lê uma sessão `design` cujas opções são exatamente os candidatos restantes:
  o juiz vira o revisor de registro, então as regras de lane e de família do board valem para ele.

## O painel inteiro, medido como um decisor só

`record` também imprime o painel como um único registro `hpp.decision/v1` (`method: panel`, sem
confiança, `raw_response_sha256` = o registro selado). É isso que deixa a régua que mede um decisor
medir um painel, na mesma suíte:

```bash
python -m hpp decide eval examples/typed-decisions/gotcha-family-suite.json --decider-command '["python", "examples/house-session/panel_decider.py"]'
python -m hpp decide eval examples/typed-decisions/gotcha-family-suite.json --decider-command '["python", "examples/typed-decisions/baseline_decider.py"]'
```

`panel_decider.py` reproduz uma sessão gravada por caso (um painel `incident` de dois assentos de
duas famílias, rodada cega, uma réplica onde discordaram), sela e verifica, e responde com a decisão
do painel. Um painel com assento morto é falha de instrumento nesta régua, nunca resposta.

## Códigos de saída

| comando | 0 | 1 | 2 |
|---|---|---|---|
| `deliberate plan` · `deliberate validate` | válido | — | recusado, nomeando a primeira regra quebrada |
| `deliberate tally` · `deliberate stop` | relatado | — | painel ou turnos recusados |
| `deliberate record` | selado, o juiz respondeu | selado, o veredito está bloqueado ou o juiz falhou | recusado: não parou, sem juiz, juiz de outra pergunta, estado ou modelo, dissidência sem steelman |
| `deliberate verify` | íntegro | — | quebrado: editado, ou não re-deriva |

## O que isto ainda não faz

Uma referência que resolve prova que o id existe, não que a fonte diz o que a afirmação diz — o
mesmo limite do `hpp cite check`. Nada no núcleo executa os assentos; quem executa é o
`house_session.py` do módulo de lanes (novo na 2.8.0): ele só senta um painel num host com duas
famílias de modelo, roda o comando de cada assento no seu próprio worktree e recusa o turno de um
assento que escreveu nele.
Se um painel vence um agente forte sozinho é uma medição, não uma afirmação — e ela não é feita aqui.
