[English](CONCEPTS.md) · [Português](CONCEPTS.pt-BR.md)

# Conceitos

O vocabulário do House Party Protocol. Cada termo tem uma definição de uma frase, a confusão com
que ele costuma ser trocado, e um jeito de verificá-lo na sua máquina. Os comandos rodam a partir
da raiz do repositório, salvo indicação em contrário.

## harness

**É:** a camada que fica em volta do trabalho de um agente e decide, a partir de estado medido, se
o trabalho pode avançar.

**Não é:** um agente, um modelo, uma biblioteca de prompts ou um plugin de IDE. O harness nunca
chama um modelo e nunca edita as configurações do agente.

**Verifique:** `python -m hpp --help` lista a superfície de operação; `python -m hpp --self-test`
a exercita sem tocar num workspace.

## protocol

**É:** o conjunto de invariantes que todo módulo e todo host precisam respeitar, escrito em
`hpp.manifest.json` como papéis, transições do loop com gates nomeados, códigos de saída,
cobertura por host e monitores.

**Não é:** um protocolo de rede, um formato de prompt ou um guia de estilo. Nada no protocol
depende de qual modelo está do outro lado.

**Verifique:** `python -m hpp doctor` rejeita um manifesto cujo `protocol_version` não seja `2.0`,
cujos códigos de saída desviem de `0/1/2/3`, ou cujos módulos referenciem módulos ou hosts
desconhecidos.

## módulo

**É:** uma capacidade instalável, versionada de forma independente, com um caminho declarado,
componentes declarados (skills, hooks, commands, agents, rules, templates, scripts) e cobertura
declarada por host.

**Não é:** um plugin só no sentido do Claude Code. O mesmo módulo é um plugin no Claude Code e uma
cópia verificada no Codex CLI. Um módulo também não é dependência de outro por padrão: hoje toda
lista `requires` do manifesto está vazia; `integrates_with` é composição opcional.

**Verifique:** `python -m hpp graph --view capability --format json` mostra as arestas
`provides`, `supports:<coverage>`, `requires` e `integrates-with` por módulo.

## host

**É:** o ambiente que executa o agente e consegue executar um módulo: Claude Code ou Codex CLI.

**Não é:** intercambiável. A cobertura é declarada por módulo e por host como `native` (o host
dispara a capacidade no próprio lifecycle), `explicit-command` (a capacidade existe como chamada
de CLI) ou `unsupported` (nenhum mecanismo verificado).

**Verifique:** `python -m hpp init --target . --host codex --modules claude-dev-kit --json` para
em `configure`, porque esse módulo é `unsupported` no Codex CLI.

## gate

**É:** uma condição nomeada, com resposta mensurável, que um pedaço de trabalho precisa satisfazer
antes de passar ao próximo estado.

**Não é:** uma caixa de seleção, um comentário de revisão ou uma instrução de prompt. Um gate que
não pode ser forçado a falhar por um teste é uma hipótese de proteção, não um gate.

**Verifique:** os cinco gates do loop são `scope`, `fresh-evidence`, `read-only-checker`, `human`
e `closure` (`python -m hpp graph --view operational --format mermaid`). Acrescentar `verified`
como primeiro evento é recusado antes de qualquer escrita: `python -m hpp event append --type verified`
sai com 2 e não cria `.hpp/`.

## evidência

**É:** a saída registrada de um comando que decide um critério, com contexto suficiente para
reexecutá-lo: o comando, o código de saída ou a saída dele, a versão contra a qual rodou, o escopo
e quando rodou.

**Não é:** uma frase num transcript, uma captura de tela sem comando, um teste que passou em outro
checkout, ou um status verde que ninguém re-derivou. Uma promessa não é evidência; uma tag
`<promise>` não passa pelo done gate.

**Verifique:** `python -m hpp event append --type evidence_recorded --data '{"work":"ITEM-1","ref":"pytest.txt"}'`
registra uma referência; o loop não consegue chegar a `verified` sem ao menos um evento desses.

## attestation

**É:** um registro JSON que vincula o veredito de um checker à identidade do repositório, ao commit
base, ao hash da spec, ao maker, ao checker, a um id de sessão e a um snapshot sha256 de todo
arquivo rastreado e não rastreado.

**Não é:** uma assinatura, um certificado ou uma prova de que o veredito estava certo. Ela prova
que o veredito foi dado sobre estes bytes. Ela também não armazena a URL do seu remoto; armazena um
hash dela.

**Verifique:** `python -m hpp attest create --repo . --spec SPEC.md --maker maker-a --checker checker-b --session review:001 --verdict approved --output .hpp/attestation.json`
e em seguida `python -m hpp attest verify .hpp/attestation.json --repo .` devolve `valid`; altere
qualquer arquivo e ele devolve `blocked` com `snapshot_digest` em `mismatches`. O controle
`evidence-attestation` do benchmark roda exatamente esta sequência.

## maker e checker

**É:** dois papéis. O maker produz a mudança. O checker a revisa sem a capacidade de editar, e
reporta acertos e defeitos com severidade, arquivo e linha.

**Não é:** dois turnos do mesmo agente, nem o mesmo agente com outro nome. A attestation recusa um
maker e um checker cujos nomes coincidam ignorando caixa. Os agentes checker dos módulos declaram
conjuntos de ferramentas sem `Write` nem `Edit`.

**Verifique:** `python -m hpp attest create ... --maker a --checker A ...` sai com 2 e "maker and
checker must be different non-empty actors". No módulo de lane,
`checker_router.py --maker claude --require` escolhe um checker de outro provedor e sai com 2
quando nenhum está disponível.

## lane

**É:** a reivindicação de uma sessão concorrente sobre um território: um id, uma lista de
caminhos, uma flag de exclusividade e um heartbeat.

**Não é:** uma branch, um worktree ou um arquivo de lock. A autoridade de uma lane expira: com
`--now`, um heartbeat mais velho que `--suspect-after` a torna `suspect`, mais velho que
`--dead-after` a torna `dead`, e uma lane morta nunca produz colisão. Um heartbeat no futuro é um
erro, não liveness.

**Verifique:** `python -m hpp map lane examples/reliable-coding/lanes.json --now 1000 --suspect-after 60 --dead-after 300`
reporta liveness por lane e uma lista `collisions` vazia; o controle `lane-collision` do benchmark
acrescenta uma lane viva sobreposta e uma morta, e confere que só o par vivo colide.

## wave

**É:** um conjunto de unidades de trabalho sem dependência entre si, liberadas juntas, cuja
barreira fecha antes de a próxima wave abrir.

**Não é:** um tamanho de lote, um número de agentes em paralelo ou um sprint. Paralelismo é
consequência do grafo de dependências, não um parâmetro.

**Verifique:** `python -m hpp work waves examples/reliable-coding/workgraph.json` produz
`spec` → `build, docs` → `verify`.

## WorkGraph

**É:** a forma compilada de uma spec: unidades de trabalho com `id`, `depends_on`, critérios de
`acceptance` não vazios e um `tier`, ordenadas em waves.

**Não é:** um executor. Ele não agenda nada e não lança nada. Um ciclo é um erro de compilação com
o caminho do ciclo na mensagem, nunca uma wave vazia.

**Verifique:** `python -m hpp work plan examples/reliable-coding/workgraph.json` imprime unidades,
arestas, waves e contagens por tier; o controle `workgraph-waves` do benchmark o alimenta com
`a -> b -> a` e espera um erro.

## trabalho derivado de spec

**É:** trabalho que deriva de uma especificação declarada: um objeto JSON cuja lista `work`
nomeia cada unidade com um `id`, o próprio `depends_on`, critérios de `acceptance` não vazios e
um `tier`. A spec é a entrada; a ordem, as waves e as arestas são saídas de compilá-la.

**Não é:** uma cascata, e não é "escrever documento antes de codar". A spec é pequena o bastante
para ser recompilada toda vez que muda, e compilá-la custa um comando. Também não é uma conversa:
uma dependência combinada no chat mas não escrita em `depends_on` não existe para o harness.

**Verifique:** `python -m hpp work plan examples/reliable-coding/workgraph.json` imprime a forma
compilada; remova uma lista `acceptance` e o mesmo comando sai com 2 e "needs non-empty
acceptance criteria"; nomeie uma dependência que não é unidade e ele sai com 2 e "unknown
dependency".

## execução por waves

**É:** avançar por wave em vez de por tarefa: toda unidade de uma wave pode começar quando a wave
abre, e a wave seguinte só abre depois que toda unidade da atual fechou.

**Não é:** uma fila de tarefas pegas em qualquer ordem, e não é uma promessa que o harness impõe
sozinho. `hpp work waves` calcula onde está cada barreira; nada em `python -m hpp` impede um
operador de começar cedo uma unidade da wave 2. Honrar a barreira é contrato do operador, e os
eventos do loop não nomeiam wave nenhuma.

**Verifique:** `python -m hpp work waves examples/reliable-coding/workgraph.json` devolve `waves`
com um `index` por wave e as unidades que pertencem a ela; `verify` aparece só na wave 3, depois
de `build` e `docs`.

## paralelo e sequencial

**É:** uma consequência do grafo de dependências, não uma escolha. Duas unidades sem caminho entre
si, cujas dependências já fecharam, caem na mesma wave; uma unidade cai na wave seguinte à da
mais tardia de suas dependências. Ninguém decide que `build` e `docs` podem rodar juntas; a
ausência de aresta entre elas decide.

**Não é:** "rodar tudo em paralelo". Rodar tudo de uma vez ignora as arestas; rodar por wave não
ignora nada. Também não é uma afirmação de segurança sobre arquivos: duas unidades na mesma wave
ainda podem escrever os mesmos caminhos, e o WorkGraph não olha caminhos. Essa pergunta é
respondida pelo Lane Map, cuja colisão é duas lanes vivas e exclusivas cujos territórios são
iguais ou aninhados.

**Verifique:** `python -m hpp work waves examples/reliable-coding/workgraph.json` coloca `build` e
`docs` juntas na wave 2 (as duas dependem só de `spec`); `python -m hpp map lane examples/reliable-coding/lanes.json --now 1000`
reporta `collisions: []` para duas lanes em caminhos disjuntos.

## ordem topológica

**É:** a ordem em que as unidades são liberadas, derivada das arestas: uma unidade nunca é liberada
antes de toda unidade de que depende. Dentro de uma wave a ordem é alfabética por `id`, então a
mesma spec produz a mesma saída em toda máquina.

**Não é:** uma lista de prioridade, e não é a ordem em que as unidades foram escritas na spec. A
pessoa declara arestas; o grafo decide a ordem; nem a pessoa nem o agente escolhem a sequência à
mão. Um ciclo é uma spec que se contradiz: `a` precisa terminar antes de `c`, `c` antes de `b`,
`b` antes de `a`, e nenhuma ordem satisfaz as três. O compilador a recusa e nomeia o caminho;
ele nunca quebra o ciclo por você.

**Verifique:** uma spec com `a -> c -> b -> a` faz `python -m hpp work waves SPEC.json` sair com 2
e `dependency cycle: a -> c -> b -> a`; uma unidade que depende de si mesma sai com 2 e
`dependency cycle: a -> a`. O controle `workgraph-waves` do benchmark roda o caso de duas unidades.

## barreira

**É:** a fronteira entre duas waves: o ponto em que toda unidade da wave atual cumpriu os próprios
critérios de aceite e a wave seguinte pode abrir.

**Não é:** uma reunião de checkpoint nem uma atualização de status. Uma unidade da wave `n+1`
depende, diretamente ou por meio de outras unidades, de algo de uma wave anterior; começá-la antes
de a barreira fechar é construir sobre uma dependência cujos critérios não passaram. Se essa
dependência então muda, a evidência da unidade adiantada descreve um checkout que não existe mais,
e "a wave `n` fechou" deixa de ser uma frase com significado mensurável.

**Verifique:** `python -m hpp work waves examples/reliable-coding/workgraph.json` mostra três waves;
a barreira é a fronteira entre índices consecutivos. O harness a calcula e a reporta, e não a
impõe: não há wave nos eventos do loop, só `work_started` até `verified`
(`python -m hpp graph --view operational --format mermaid`).

## orçamento de contexto

**É:** um limite em caracteres sob o qual o compilador de contexto encaixa blocos de entrada
inteiros, do de maior prioridade para o de menor, registrando para cada bloco a fonte, o tamanho e
o sha256, e listando o que ficou de fora.

**Não é:** uma contagem de tokens, um sumarizador ou um sistema de recuperação. Um bloco que não
cabe é omitido por inteiro, nunca fatiado. Conteúdo que se parece com segredo (uma atribuição de
chave de API, um cabeçalho PEM, um prefixo de chave no estilo de provedor) é recusado, não
redigido.

**Verifique:** `python -m hpp context compile examples/reliable-coding/context.json --budget 160`
reporta `used` e `remaining` em caracteres, com o separador entre blocos cobrado do orçamento.

## readiness

**É:** a contagem das checagens que o `hpp init` de fato rodou e o resultado delas, cada uma com o
comando que a reproduz: `verified`, `failed` ou `not-verified`.

**Não é:** um percentual de conclusão ou uma estimativa. Uma checagem que não rodou é reportada
como não verificada, nunca como zero e nunca como cem.

**Verifique:** `python -m hpp init --target <dir> --json` devolve `readiness.items` com onze
entradas; num checkout de fonte, a integridade da distribuição e os checksums dos módulos são
`not-verified`, porque não há `marketplace.json` nem `CHECKSUMS.txt` para medir.

## monitor

**É:** um contrato de observação declarado: um alvo, um tipo de sonda, uma cadência, uma janela de
frescor, uma severidade, um custo e o gate que o consome.

**Não é:** um processo em execução. O Monitor Map projeta o `last_signal` que você fornece contra
o `--now` que você fornece. E um monitor saudável não é um resultado correto. Três perguntas
permanecem separadas:

| pergunta | o que a responde |
|---|---|
| o serviço está no ar? | a sonda respondeu dentro da cadência |
| o dado está fresco? | `now - last_signal <= freshness`, e `last_signal` não está no futuro além de `--skew-tolerance` |
| o resultado está correto? | um comando de critério, registrado como evidência; nenhum monitor responde isso |

Um sinal carimbado no futuro é `skew`, não `healthy`; um sinal ausente é `unknown`, não `stale`.

**Verifique:** `python -m hpp map monitor examples/reliable-coding/monitors.json --now 1000` mostra
uma sonda de serviço `healthy` ao lado de uma sonda de dado `stale` na mesma projeção.

## gotcha

**É:** uma lição derivada de uma falha de comando que recorreu, armazenada por família de erro e
injetada como preâmbulo antes da próxima execução do mesmo tipo de tarefa.

**Não é:** uma regra permanente criada a partir de um incidente, e não é um registro de segredos.
A promoção de falha a gotcha exige recorrência dentro de uma janela; saída ambígua não conta como
falha; toda entrada armazenada é redigida por forma (chaves privadas, credenciais em URLs, tokens
bearer, JWTs, blobs de alta entropia) antes de ser escrita. Os hooks são warn-only e nunca
bloqueiam.

**Verifique:** num módulo `gotcha-memory` instalado, a skill `gotcha-memory` lista, semeia e
inspeciona o store; os hooks saem com 0 em todos os casos.

## pass@k e pass^k

**É:** duas métricas sobre `k` execuções do mesmo caso. `pass@k` é verdadeiro quando ao menos uma
execução passou e mede capacidade. `pass^k` é verdadeiro quando toda execução passou e mede
confiabilidade. A diferença entre os dois é a taxa de flake.

**Não é:** intercambiável, e não é um benchmark de modelo. Um gate de capacidade exige
`pass@k >= 0.90`; um gate de regressão exige `pass^k == 1.00`; `--gate both` exige os dois.

**Verifique:** `python -m hpp eval run examples/reliable-coding/benchmark-suite.json -k 3 --gate both`
imprime as duas métricas e o gate; saída 0 quando passa, 1 quando falha.

## contrato de saída

**É:** quatro códigos de saída de processo com significado fixo em todo o harness e em todo
módulo: `0` ok, `1` warn ou gate manual, `2` block, `3` erro de uso ou interno.

**Não é:** uma sugestão. O manifesto é rejeitado se declarar qualquer outra coisa. No modo
`enforce`, `BLOCK` sai com 2 e `MANUAL` sai com 1; no modo `audit` o veredito é impresso e a saída
é sempre 0.

**Verifique:** `python -m hpp policy check --mode enforce --command "rm -rf src"` sai com 2;
`--command "git push origin feature"` sai com 1; `--mode audit` com qualquer um dos dois sai com 0.

## plano e aplicação

**É:** o contrato de duas invocações para qualquer coisa que escreve: a primeira execução imprime o
que aconteceria e sai com 0 sem escrever; uma segunda execução com `--apply` executa.

**Não é:** um prompt de confirmação. Nada no harness bloqueia em `input()`; o "sim" é a
reinvocação, que é auditável e funciona quando o operador é um agente.

**Verifique:** `python -m hpp init --target <empty-dir>` deixa o diretório vazio (`find <dir> -type f | wc -l` é 0);
o mesmo comando com `--apply` escreve exatamente `.hpp/profile.json`. O wiring de settings e hooks
é impresso nos dois casos e escrito em nenhum.

## controle

**É:** um caso sabidamente bom e um caso sabidamente ruim passados pelo mesmo instrumento, de modo
que o instrumento demonstre distingui-los antes de o veredito dele ser confiado.

**Não é:** um teste que só exercita o caminho feliz. Um gate que passa com entrada boa e nunca foi
visto falhar com entrada ruim não se distingue de um gate ausente.

**Verifique:** todo caso em `examples/reliable-coding/benchmark-suite.json` é um controle nas duas
direções: `policy-enforcement` confere que `python -m pytest -q` é `ALLOW` e `rm -rf src` é
`BLOCK`; `event-evidence-gate` confere que uma sequência válida chega a `verified` e que um
`verified` solto é recusado sem criar o log. Cada arquivo de teste em `tests/` carrega ao menos um
teste chamado `CONTROLE` que prova que o arquivo sabe falhar.

## event log

**É:** um arquivo JSON-lines append-only em `.hpp/events.jsonl` no workspace, em que cada linha
carrega um `seq` contíguo, um `id` na forma `event:<seq>`, um `type` e um objeto `data`.

**Não é:** um histórico de chat, e não é algo que o harness vá reparar. Uma linha cujo `seq` não é
contíguo ou cujo `id` não bate é um log corrompido, e a projeção para em vez de adivinhar. Um
evento cuja transição não é permitida a partir do estado atual é recusado antes da escrita.

**Verifique:** `python -m hpp status --json` mostra o estado, a contagem e o histórico;
`python -m hpp resume` devolve o próximo passo derivado do mesmo log.

## bundle

**É:** um conjunto nomeado de módulos recomendado para um objetivo, com as capacidades que ele deve
fornecer.

**Não é:** uma dependência. `reliable-coding` nomeia seis módulos; instalar um deles sozinho é
válido.

**Verifique:** `python -m hpp install --bundle reliable-coding --host codex --target <dir>` imprime
um recibo só de plano listando cada módulo e o modo de integração dele nesse host.
