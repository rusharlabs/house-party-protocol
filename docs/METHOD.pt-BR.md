[English](METHOD.md) · [Português](METHOD.pt-BR.md)

# Método

O modo de trabalhar que o harness impõe. Um time consegue adotá-lo em um dia, porque toda prática
termina num comando que ou passa ou reporta o que mediu. Os comandos abaixo usam a CLI do harness
(`python -m hpp`) e, onde um módulo está envolvido, os scripts que esse módulo instala. Os caminhos
de módulo aparecem relativos à distribuição emitida.

## 1. Abra uma unidade de trabalho

O trabalho começa como uma spec, não como uma conversa. Uma spec é uma lista de unidades, cada uma
com um `id`, o próprio `depends_on`, ao menos um critério de aceite escrito como algo que um comando
consegue decidir, e um `tier` que diz quanto risco ela carrega. O harness compila a spec num
WorkGraph e deriva waves das dependências. Unidades na mesma wave podem rodar em paralelo; uma
unidade cujas dependências não fecharam não começa.

Antes de tocar arquivos num repositório compartilhado, a sessão reivindica uma lane: um id, os
caminhos que ela vai possuir e um heartbeat que ela vai manter atualizado. Duas lanes vivas não
podem se sobrepor em território exclusivo. Uma lane que para de emitir heartbeat perde a
reivindicação por tempo, não porque alguém apagou um lock.

Então o primeiro evento é registrado, e o loop sai de `planned`.

```bash
python -m hpp work plan SPEC.json
python -m hpp work waves SPEC.json
python multi-session/lane-kit-1.6.0/scripts/lane_board.py claim --help
python -m hpp event append --type work_started --data '{"work":"ITEM-1","actor":"maker-a"}'
```

## 2. Declare pronto

"Pronto" é um estado em que o harness entra, não uma palavra que o agente diz. Ele exige que os
critérios de aceite rodem como comandos e saiam com 0, no checkout atual, agora. O done gate recebe
os critérios como argumentos, roda cada um e imprime `DONE-GATE: DONE` somente quando todos passam.
Quando algum critério ainda não consegue passar, a saída correta é um parcial declarado: o gate
aceita `--declare-partial "<o que falta>"` e reporta `PARCIAL-DECLARADO` com esse texto e uma
saída diferente de zero. Sem a declaração ele reporta `NOT-DONE`. Silêncio não é um estado; um
parcial não declarado é uma falha.

Quando os critérios passam, a evidência é registrada no event log com uma referência a onde a
saída mora. O caminho principal é o `hpp evidence run --record-event` (novo na
2.6.0): ele mesmo roda o critério, mede o código
de saída, faz hash dos arquivos declarados com `--artifact`, escreve um registro em
`.hpp/evidence/` e acrescenta `evidence_recorded` somente quando esse bundle passou. Ele exige ao
menos um `--artifact`, porque um código de saída sozinho não deixa nada para re-derivar depois.
Numa versão sem ele, o mesmo evento é acrescentado à mão com `hpp event append`, e então carrega
só o que a pessoa escreveu. O loop passa a `evidenced`. Ele não consegue passar a `verified` sem
ao menos um registro desses.

```bash
python frameworks/operator-kit-1.7.0/scripts/done_gate.py "python -m pytest -q" "python -m py_compile app.py"
python frameworks/operator-kit-1.7.0/scripts/done_gate.py "python -m pytest -q" --declare-partial "external target not yet validated"
python -m hpp evidence run --id ITEM-1 --artifact artifacts/pytest.xml --record-event -- python -m pytest -q --junitxml=artifacts/pytest.xml
python -m hpp event append --type evidence_recorded --data '{"work":"ITEM-1","ref":"artifacts/pytest.txt"}'
```

## 3. O que conta como prova

Uma prova é reproduzível por alguém que não estava lá. Ela carrega o comando, a saída ou o código
de saída, a versão ou o commit contra o qual rodou, o escopo que cobriu e a hora em que rodou.
Qualquer afirmação que careça de um dos cinco é o relato de uma crença.

Duas regras adicionais separam prova de luz verde. Um número é publicado com o instrumento que o
produziu, para que a próxima pessoa possa re-derivá-lo em vez de confiar nele. E um instrumento só
recebe confiança depois de um controle: apontado para um caso sabidamente bom e um caso sabidamente
ruim, ele precisa responder de modo diferente. Um checker que diria "zero problemas" sobre uma
árvore quebrada não pode ser usado para dizer "zero problemas" sobre uma boa.

O mesmo controle vale para os instrumentos em que um agente se apoia (todos novos na 2.6.0).
Um retriever só recebe confiança depois que o `hpp retrieval eval` o mediu em consultas rotuladas,
e um decisor só depois que o `hpp decide eval` o mediu, cada um com as falhas de instrumento
contadas à parte. Um relatório escrito a partir de fontes marca cada afirmação com o id da fonte
em que ela se apoia, e o `hpp cite check` prova que todo marcador resolve para uma fonte que o
relatório recebeu e sinaliza um número sem marcador; ele não prova que a fonte diz o que a frase
diz.

Quando um checker aprova, a aprovação fica vinculada a bytes. A attestation registra o hash da
spec, o commit base e um snapshot de todo arquivo rastreado e não rastreado. Se o checkout mudar
depois, a aprovação é bloqueada na verificação e precisa ser dada de novo sobre os novos bytes.
Por isso a evidência vem primeiro e a attestation por último. No seu próprio projeto, ponha `.hpp/`
no `.gitignore`: o event log e os registros de evidência são estado por checkout, e o snapshot
cobre todo arquivo não rastreado que não esteja ignorado, então sem essa linha um evento ou um
registro escrito depois do `attest create` bloqueia o `attest verify`.

```bash
python -m hpp cite check --text examples/citations/answer.md --context examples/citations/context.json
python -m hpp retrieval eval examples/retrieval/suite.json \
  --retriever-command '["python", "examples/retrieval/keyword_retriever.py"]'
python -m hpp decide eval examples/typed-decisions/gotcha-family-suite.json \
  --decider-command '["python", "examples/typed-decisions/baseline_decider.py"]'
python -m hpp attest create --repo . --spec SPEC.md \
  --maker maker-a --checker checker-b --session review:001 \
  --verdict approved --output .hpp/attestation.json
python -m hpp attest verify .hpp/attestation.json --repo .
```

## 4. Revise sem caneta

O checker é um ator diferente do maker, de preferência em outro provedor, e não tem ferramentas de
edição de arquivo: o host impõe a ausência de `Write` e `Edit`. O `Bash` continua disponível, então
somente leitura é uma promessa, verificada comparando a árvore de trabalho antes e depois da
revisão — o `git status --porcelain` capturado dos dois lados precisa bater, e um checker que
alterou a árvore invalida os próprios achados. Sem caneta, o checker não consegue "consertar e
seguir"; ele tem de apontar, com severidade, arquivo e linha, e o maker tem de responder. Esse
atrito é o mecanismo: é o que torna um defeito de processo visível em vez de remendado em silêncio.

O relatório do checker mantém os mesmos critérios entre rodadas, nomeia achados por um código
estável em vez de por um adjetivo, e nunca pergunta ao maker algo que ele mesmo poderia verificar
rodando um comando. Quando não há checker de outro provedor disponível, a revisão é registrada como
não feita, não como feita pelo maker.

A aprovação do checker é um evento. O loop passa de `evidenced` a `checked`.

```bash
python multi-session/lane-kit-1.6.0/scripts/checker_router.py --maker claude --require
python -m hpp event append --type check_passed --data '{"work":"ITEM-1","checker":"checker-b"}'
```

## 5. Quando o orçamento acaba

Todo loop declara o próprio orçamento antes da primeira iteração: iterações, tempo e o que mais o
host medir. Parar por orçamento é um de três fins legítimos, ao lado de "o critério passou" e "o
circuit breaker disparou". Não é uma falha e não é motivo para tentar mais uma vez.

O driver de loop do módulo operator lê um charter com os critérios e um número máximo de iterações.
Uma marca de conclusão na saída do modelo não libera o loop; o done gate é reexecutado pelo hook,
fora do alcance do modelo, e só o código de saída dele conta. Quando o orçamento é atingido, o
driver para, reporta onde parou e o que falta, e espera que uma pessoa estenda o orçamento ou feche
o trabalho. Estender o orçamento é uma decisão humana, nunca algo que o loop concede a si mesmo.

```bash
python frameworks/operator-kit-1.7.0/hooks/ralph_gate.py start \
  --charter "<objective>" --criteria "python -m pytest -q" --max-iterations 10
python frameworks/operator-kit-1.7.0/hooks/ralph_gate.py status
python frameworks/operator-kit-1.7.0/hooks/ralph_gate.py cancel
```

## 6. Retome depois de uma interrupção

A fronteira de recuperação é o último evento registrado, não a última coisa de que alguém lembra.
Depois de uma queda, de um reset de contexto ou de um novo dia, o próximo passo é derivado do event
log: `hpp status` projeta o log sobre o loop e nomeia o estado; `hpp resume` devolve o próximo passo
como JSON. Nenhum dos dois consulta um resumo e nenhum pede ao modelo que reconstrua o que
aconteceu.

Um resumo ou handoff restaurado é material de referência. Antes de reexecutar qualquer coisa que
ele descreva, a sessão confere se aquele passo já produziu o próprio efeito (um arquivo, um commit,
um evento). Um passo que já rodou não roda de novo. Quando um passo foi aceito mas a confirmação se
perdeu, ele é marcado como desconhecido junto com o comando que resolve a dúvida, e é inspecionado
antes de ser tentado de novo.

```bash
python -m hpp status --json
python -m hpp resume
```

## 7. Todo gate nasce com um teste que o força a falhar

Um gate que só foi visto passando não se distingue de um gate que está faltando. Então um gate
entra na base de código com duas provas. A primeira é um teste que o alimenta com o caso que ele
existe para barrar e afirma que ele barra; se o gate fosse removido, esse teste falharia. A segunda
é o call site: evidência de que o gate é de fato invocado no caminho vivo, não apenas definido.

A mesma regra vale para consertos de bug. O teste é escrito primeiro e rodado para vê-lo falhar
pelo motivo certo; depois o conserto; depois o teste de novo. Um teste escrito depois do conserto
prova que o código atual funciona, não que algo foi consertado. Quando os dois lados de um conserto
produzem o mesmo resultado, a prova não discrimina, e a causa habitual é uma guarda anterior parando
o caminho antes de ele chegar ao defeito.

O benchmark é esta regra aplicada ao próprio harness: dez controles, cada um com um caso positivo e
um negativo, rodados `k` vezes, com `pass^k = 1.00` exigido.

```bash
python -m pytest tests/test_policy.py -q
python -m hpp eval run examples/reliable-coding/benchmark-suite.json -k 3 --gate both
python -m hpp benchmark -k 3 --json
```

## 8. Planeje antes de aplicar

Qualquer coisa que escreve mostra o plano primeiro e escreve numa segunda invocação explícita. O
plano lista o que existe no alvo e será preservado, o que seria escrito e o que continua sendo ação
humana. Nem `hpp init` nem o instalador de módulos bloqueiam num prompt de terminal; o "sim" é a
reinvocação com `--apply`, que funciona do mesmo modo para uma pessoa e para um agente agindo em
nome dela.

Settings, hooks e `AGENTS.md` nunca são escritos pelo harness. O bloco de wiring é impresso para
uma pessoa colar, e o doctor é rodado depois para confirmar o resultado.

```bash
python -m hpp init --target ../your-repo
python -m hpp init --target ../your-repo --apply
python installers/kit-forge-1.4.2/kit_doctor.py install --kit <module-dir> --host codex --target ../your-repo
python installers/kit-forge-1.4.2/kit_doctor.py install --kit <module-dir> --host codex --target ../your-repo --apply
python -m hpp doctor
```

## 9. Um gate humano onde a ação é irreversível

A política de comandos classifica o que um agente está prestes a rodar. Remoção recursiva em
qualquer ordem de flags, force push, push em `main` ou `master`, download encanado num shell e SQL
destrutivo são `BLOCK`. Qualquer push e qualquer transferência de saída são `MANUAL`: a ação pode
estar certa, e uma pessoa a confirma. No modo `enforce` o classificador devolve saída 2 e 1,
respectivamente; no modo `audit` ele reporta o veredito e sai com 0, para que um time consiga medir
falsos positivos antes de trocar de modo.

No loop, o gate humano é um evento. `checked` vira `approved` somente por meio de
`human_approved`, e o `verified` final exige que esse passo tenha acontecido.

```bash
python -m hpp policy check --mode audit --command "git push origin feature"
python -m hpp policy check --mode enforce --command "rm -rf build"
python -m hpp event append --type human_approved --data '{"work":"ITEM-1","by":"operator"}'
python -m hpp event append --type verified --data '{"work":"ITEM-1"}'
```

## 10. Deixe o grafo decidir a ordem

### Escreva uma spec pequena o bastante para compilar

Uma spec é um objeto JSON com uma lista `work`. Cada unidade tem um `id`, uma lista `depends_on`
(vazia quando não depende de nada), ao menos um critério de `acceptance` escrito como algo que um
comando consegue decidir, e um `tier`. Uma unidade é pequena o bastante quando uma pessoa consegue
dizer, num comando, o que a fecha; quando uma unidade precisa de um parágrafo, ela é duas
unidades. O compilador não mede tamanho; mede forma. Dependências são escritas, não lembradas: uma
aresta que vive só na conversa não existe para o compilador. Ele recusa uma spec com id duplicado,
dependência desconhecida, lista de aceite vazia ou tier inválido, e diz qual unidade.

```bash
python -m hpp work plan SPEC.json
```

### Leia as waves antes de começar

`hpp work waves` imprime as waves em ordem com as unidades de cada uma. Leia como o plano do dia:
tudo da wave 1 pode começar agora; nada da wave 2 pode começar até que toda unidade da wave 1
tenha passado nos próprios critérios. Uma wave com uma unidade só é um passo serial, e não há o
que fazer a respeito além de terminar a unidade. A ordem dentro de uma wave é alfabética, não é
prioridade: escolha qualquer ordem, ou todas de uma vez. Duas unidades na mesma wave ainda podem
tocar os mesmos caminhos; o grafo não conhece os arquivos, então as lanes são declaradas à parte,
e o Lane Map é o que reporta sobreposição entre territórios vivos e exclusivos.

```bash
python -m hpp work waves SPEC.json
python -m hpp map lane LANES.json --now "$(date +%s)"
```

### Quando o grafo acusa ciclo

`dependency cycle: a -> c -> b -> a` quer dizer que a spec se contradiz: cada unidade do caminho
pede para rodar depois da seguinte, e nenhuma ordem satisfaz todas. O harness nomeia o caminho e
sai com 2; ele nunca descarta uma aresta para fazer a spec compilar. O conserto está na spec, e é
um de três: uma aresta foi declarada ao contrário, duas unidades são na verdade uma, ou uma
unidade faz duas coisas e a segunda metade pertence a uma unidade nova que depende da primeira.
Mude a spec e recompile; o compilador é o teste.

```bash
python -m hpp work waves SPEC.json
```

### Decidir que uma unidade não pode rodar em paralelo

Uma unidade roda depois de outra somente quando uma aresta diz isso, e a aresta vale ser declarada
quando a unidade posterior lê o que a anterior produz: um schema antes do código que o usa, um
build antes da checagem que o executa, um rename antes das referências ao nome novo. Quando a
resposta é "elas tocam os mesmos arquivos", isso é pergunta de lane, não de dependência: dê às duas
unidades territórios disjuntos, ou faça uma depender da outra e aceite o passo serial. Uma vez
declarada, a aresta aparece em `edges`, da dependência para a unidade que espera por ela, com a
relação `depends-on`, e a unidade posterior passa para uma wave mais tarde; se ela não se moveu,
a aresta não é a que você queria.

```bash
python -m hpp work plan SPEC.json
```

## O loop, de ponta a ponta

```text
work_started ─▶ evidence_recorded ─▶ check_passed ─▶ human_approved ─▶ verified
   [scope]        [fresh-evidence]   [read-only-checker]   [human]        [closure]
```

Cada seta é um evento acrescentado. Cada gate é uma condição que o harness checa antes de
acrescentar. `hpp status` diz onde você está; `hpp resume` diz o que vem a seguir.
