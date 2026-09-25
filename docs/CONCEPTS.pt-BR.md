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

**Verifique:** `python -m hpp doctor` rejeita um manifesto cujo `protocol_version` não seja `2.1`,
cujos códigos de saída desviem de `0/1/2/3`, ou cujos módulos referenciem módulos ou hosts
desconhecidos. O `2.1` acrescentou duas chaves obrigatórias no topo, `hook_capabilities` e
`hooks`; um manifesto 2.0 que não declara hook nenhum é recusado, o que é mudança de contrato e
não acréscimo.

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

**Medido em 2026-09-22, Codex CLI 0.153.4:** o host *tem* superfície nativa de hook —
`codex features list` imprime `hooks  stable  true`, e `codex --help` traz
`--dangerously-bypass-hook-trust` ("run enabled hooks without requiring persisted hook trust"),
então ligar um é decisão explícita de confiança. Isso **não** promoveu nenhum módulo a `native`
no Codex, e o mesmo censo diz por quê: `plugin_hooks` imprime `removed  false`, e a string
`codex-hooks.json` não aparece no binário instalado (`hooks.json`, `SessionStart`, `PreToolUse`
e `hook_trust` aparecem). Um módulo instalado por cópia de arquivo continua, portanto, sem
conseguir wirar os próprios hooks nesse host; o operador cola no arquivo de hooks do Codex e
aceita o prompt de confiança. `explicit-command` segue sendo a cobertura honesta. Dois
instrumentos foram testados e recusados para esta pergunta porque não discriminam:
`codex features list` e `codex doctor` produzem saída idêntica byte a byte com um `hooks.json`
propositalmente malformado em `CODEX_HOME` e sem nenhum.

## gate

**É:** uma condição nomeada, com resposta mensurável, que um pedaço de trabalho precisa satisfazer
antes de passar ao próximo estado.

**Não é:** uma caixa de seleção, um comentário de revisão ou uma instrução de prompt. Um gate que
não pode ser forçado a falhar por um teste é uma hipótese de proteção, não um gate.

**Verifique:** os cinco gates do loop são `scope`, `fresh-evidence`, `read-only-checker`, `human`
e `closure` (`python -m hpp graph --view operational --format mermaid`). Acrescentar `verified`
como primeiro evento é recusado antes de qualquer escrita: `python -m hpp event append --type verified`
sai com 2 e não cria `.hpp/`.

## hook capability

**É:** o que um hook é capaz de fazer, declarado no manifesto antes de você instalá-lo, a partir
de um vocabulário fechado de seis grupos: `automatic-source-writes` (escreve arquivos dentro do
seu projeto por conta própria), `command-rewrite-and-process-control` (muda o que roda, ou o que
o modelo recebe antes de rodar), `transcript-derived-llm-egress` (manda texto derivado do
transcript para um modelo), `mcp-network-and-process-activity` (sonda a rede, fala com um servidor
MCP ou dispara um processo), `automatic-permission-gates` (pode recusar ou avisar sobre uma
chamada de ferramenta) e `session-observation-and-cost-records` (lê estado de sessão e mantém
registros). Cada hook também declara seus `events` e um `exit_policy` de `observe` (sempre exit 0),
`warn` (pode sair 1) ou `block` (pode sair 2, ou emitir uma decisão que bloqueia).

**Não é:** uma descrição do que o hook *serve*, e não é opcional. Hook sem declaração é recusado;
lista `capabilities` vazia é recusada; módulo que declara o componente `hooks` e não declara hook
nenhum é recusado. Ausente nunca se lê como vazio — uma declaração faltando que valesse como "não
faz nada" seria a permissão mais ampla do manifesto, escrita como silêncio.

**Verifique:** `python -m hpp doctor` imprime `hooks=<n>` com as contagens de permission gate e de
egresso a LLM, e o `--json` carrega o censo completo por grupo — inclusive os grupos que contam
zero, para que o zero seja medição e não omissão. `python -m hpp init` imprime a tabela de
capacidades dos módulos escolhidos *antes* dos comandos para colar; escolha um módulo sem hooks e
a tabela vem vazia, não ausente. Remova o `capabilities` de um hook no manifesto e o mesmo
`doctor` sai 2.

## evidência

**É:** a saída registrada de um comando que decide um critério, com contexto suficiente para
reexecutá-lo: o comando, o código de saída ou a saída dele, a versão contra a qual rodou, o escopo
e quando rodou.

**Não é:** uma frase num transcript, uma captura de tela sem comando, um teste que passou em outro
checkout, ou um status verde que ninguém re-derivou. Uma promessa não é evidência; uma tag
`<promise>` não passa pelo done gate.

**Verifique:** novo na 2.6.0 —
depois de `python -m hpp event append --type work_started`,
`python -m hpp evidence run --id smoke-page --artifact out/report.html --record-event -- python examples/evidence/smoke_page.py`
roda o critério, grava o pacote em `.hpp/evidence/` e acrescenta `evidence_recorded` só quando ele
passou; `python -m hpp evidence verify <record>` re-deriva o pacote a partir do disco. A alternativa
de nível mais baixo, `python -m hpp event append --type evidence_recorded --data '{"work":"ITEM-1","ref":"pytest.txt"}'`,
que as versões anteriores também têm, registra uma referência sem rodar nem hashear nada, depois do mesmo
`work_started`. Nos dois casos, o loop não consegue chegar a
`verified` sem ao menos um evento desses.

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

## decisão tipada

**É:** um registro, `hpp.decision/v1`, de uma pergunta pequena respondida fora do harness — por uma
regra, uma pessoa, um modelo local ou um modelo hospedado de decisão tipada — que o harness
consegue checar e medir. A `authority` dele é sempre `advisory`. Com `direction: raise-only` numa
pergunta ordenada (`ladder: true`), o valor sobre o qual um consumidor pode agir é o maior entre o
valor `declared` e o aconselhado: o conselho pode aumentar a cautela, nunca diminuí-la.
`abstention` e `instrument-failure` são desfechos, não erros, e nenhum dos dois muda um valor
declarado; um timeout, uma página HTML ou uma resposta malformada é falha de instrumento, nunca
veredito.

**Não é:** uma chamada de modelo, uma aprovação ou uma nota. O harness não chama modelo por conta
própria: `hpp decide eval` roda o decisor que você nomeia como comando (que pode chamar um, com a
sua chave), ou reexecuta os registros que já estão na suíte. Um registro nunca concede nem aprova
nada, e uma `authority` diferente de `advisory` é recusada. A versão 1 mede só perguntas `choice`;
uma nota ou uma probabilidade de sim não tem definição combinada de "correto", então esses tipos
são recusados em vez de reportados como um 0% vazio. O texto julgado nunca entra no registro, só o
sha256 dele, e texto que se pareça com segredo é recusado antes de virar hash. Um registro de
modelo precisa nomear a versão fixada que respondeu (um alias como `-latest` é recusado) e, salvo
quando registra uma falha de instrumento, o hash da resposta bruta.

**Verifique:** novo na 2.6.0 —
`python -m hpp decide validate <record.json>` imprime `"status": "valid"` e o valor
`effective` (`action` é `raised`, `kept`, `advised` ou `none`) e sai com 0; troque `authority` por
qualquer coisa diferente de `advisory` e ele sai com 2. `python -m hpp decide eval examples/typed-decisions/gotcha-family-suite.json --decider-command '["python", "examples/typed-decisions/baseline_decider.py"]'`
reporta cobertura, acurácia seletiva, abstenções e falhas de instrumento em separado, e sai com 0
quando todo limiar se sustenta, 1 quando o gate falha e 2 para uma suíte que quebra o contrato.

## pacote de evidência

**É:** um registro, `hpp.evidence/v1`, de uma execução de um comando de critério declarado: o
argv, o commit base, o código de saída medido fora do modelo, um veredito, a contagem de bytes e o
sha256 de stdout e stderr (nunca o texto), e o caminho, o tamanho e o sha256 de todo arquivo que
casa com um glob de artefato que você declarou. O veredito é `passed` só quando o comando saiu com 0
e cada padrão declarado casou com um arquivo que esta execução escreveu (um arquivo intocado desde
antes da execução sai como `unchanged` e não conta); senão é `failed`, `missing-artifacts`, `timeout` ou
`could-not-start`. O `run` sai com 0 quando o pacote passou, 1 quando não passou, e 2 quando foi
recusado ou o `--record-event` não conseguiu acrescentar o evento.

**Não é:** um controlador de navegador, uma chamada de modelo nem uma assinatura. O hpp não dirige
navegador e não chama modelo: ele roda o comando que você nomeia (uma spec ponta a ponta, uma suíte
de testes, qualquer script) com `shell=False`. O registro carrega um hash de si mesmo, o que torna
uma edição visível e não prova nada sobre quem o escreveu — quem consegue escrever o arquivo
consegue reescrever o hash. Por isso o `verify` é reconciliação, e um checker que não pode confiar
no maker reexecuta o `command` em vez disso. O `run` escreve o registro e o que o comando escrever;
um checker somente leitura aponta o `--out` para um diretório de rascunho próprio dentro do
workspace, ou reexecuta na própria lane. Uma linha de comando que pareça carregar um segredo, e um
caminho de artefato ou de `--out` fora do workspace, são recusados antes de qualquer coisa rodar.

**Verifique:** novo na 2.6.0 —
`python -m hpp evidence run --id smoke-page --artifact out/report.html --artifact out/smoke.log -- python examples/evidence/smoke_page.py`
imprime `passed` e sai com 0, e `python -m hpp evidence verify <record>`, sobre o `record_path` que
ele imprimiu, imprime `valid` e sai com 0. A mesma execução com `--break` depois do script escreve os dois
arquivos e ainda assim sai com 1 e `failed`; o registro dela verifica como `not-evidence` (saída
1). Altere `out/report.html` depois de uma execução que passou e o `verify` sai com 2 e `blocked`.

## sensibilidade do critério

**É:** uma medição de se um critério perceberia código quebrado. `hpp evidence mutate` roda o
comando do critério numa cópia do workspace, primeiro limpa — tem de passar, senão o veredito é
`no-control` e nada mais roda — depois uma vez por mutante, uma cópia com uma pequena mudança que
deixa o código errado, onde ele tem de falhar. Os mutantes são declarados (`hpp.mutants/v1`:
arquivo, find, replace) ou gerados a partir dos tokens Python com uma tabela fixa de operadores. Um
mutante que o critério deixa passar é um ponto cego, nomeado por arquivo e linha em `survivors`.

**Não é:** cobertura, nem prova de que um mutante sobrevivente é bug. O score é mortos ÷ (mortos +
sobreviventes), null quando nada foi medido; um mutante cujo texto não está no arquivo é
`not-applied`, nunca morto. Um mutante sobrevivente pode ser equivalente — uma mudança que não muda
o comportamento — e só um leitor sabe dizer. O hpp nunca escreve na árvore do usuário: cada execução
ganha uma cópia nova, e um arquivo de mutante alcançado por symlink é recusado. O comando roda
dentro da cópia, então os caminhos dele precisam ser relativos; um install editável ou um
`PYTHONPATH` apontando para o checkout faz todo mutante sobreviver.

**Verifique:** novo na 2.7.0 —
`python -m hpp evidence mutate --id weak --generate examples/criterion-sensitivity/discount.py -- python examples/criterion-sensitivity/check_weak.py`
relata `blind-spots` com três sobreviventes e sai com 1; o mesmo com `check_strong.py` relata
`sensitive` e sai com 0.

## régua de recuperação

**É:** uma medição de um recuperador que você declara, separada de qualquer etapa de geração. O
recuperador é um comando que lê `{"query", "k"}` como JSON no stdin e imprime ids ranqueados; a
régua pontua o top k de cada resposta contra os ids que uma suíte rotulada
(`hpp.retrieval-suite/v1`) marca como relevantes, e reporta hit@k, recall@k, precision@k, MRR e
nDCG@k. A ordem impressa é o ranking; um `score` é conferido, nunca usado para reordenar.

**Não é:** um índice, um mecanismo de busca nem um juiz da resposta final. O harness não roda
índice e não chama modelo; sem `--retriever-command` a régua reexecuta os resultados gravados na
suíte. Um recuperador que responde e não acha nada relevante marca um 0 de verdade. Um timeout, uma
saída diferente de zero, uma saída que não é JSON ou um id duplicado é falha de instrumento:
contada à parte e excluída das médias. Sem nenhum caso medido as métricas são nulas e o gate diz
por quê, nunca 0%.

**Verifique:** novo na 2.6.0 —
`python -m hpp retrieval eval examples/retrieval/suite.json --retriever-command '["python", "examples/retrieval/keyword_retriever.py"]'`
mede sete casos com zero falhas de instrumento e sai com 1: o recall@3 médio do baseline por
palavra-chave é 0.786, abaixo do `--min-recall 0.8` padrão, então a suíte que vem junto prova a
régua, não um recuperador. Com `--retriever-command '["python", "-c", "import sys; sys.exit(3)"]'`
a mesma suíte reporta sete falhas de instrumento e métricas nulas, e sai com 1. A saída é 0 quando
o gate passa, 1 quando falha e 2 para uma suíte ou um argumento recusado.

## checagem de citação

**É:** uma checagem determinística, `hpp.citation-check/v1`, dos marcadores de citação de um texto
contra os ids do contexto a partir do qual o texto foi escrito. Um marcador é `[ID:<id>]`, salvo
quando `--marker` dá uma regex com um grupo de captura para o id. Um marcador que nomeia um id
ausente do contexto (`UNKNOWN_ID`), um intervalo ou lista dentro de um marcador (`RANGE`) e um
marcador vazio (`EMPTY_MARKER`) bloqueiam com saída 2; mais de `--max-per-sentence` marcadores numa
frase (`TOO_MANY`, padrão 4) e uma frase que afirma um número, percentual, valor ou data sem
marcador (`UNCITED_CLAIM`) avisam com saída 1. Um texto limpo sai com 0.

**Não é:** uma checagem de fatos. Ela nunca lê uma fonte citada para ver se ela sustenta a frase:
um marcador que resolve prova que o id existe, não que a fonte diga o que a frase diz. A divisão em
frases e a detecção de números são heurísticas, descritas por inteiro em `hpp/citations.py`, e os
erros conhecidos delas são avisos, nunca bloqueios. Contexto que o texto nunca cita é reportado
como contagem, não como achado. Texto vazio, texto ou contexto com cara de segredo e uma regex de
marcador inutilizável são recusados com saída 2.

**Verifique:** novo na 2.6.0 —
`python -m hpp cite check --text examples/citations/answer.md --context examples/citations/context.json`
imprime o veredito `ok` e sai com 0. Numa cópia de `answer.md` com `[ID:glossary]` trocado por
`[ID:glossary-v2]` ela sai com 2 e `UNKNOWN_ID`; com `[ID:runbook-7]` removido no lugar disso, sai
com 1 e `UNCITED_CLAIM`.

## seleção best-of-N

**É:** N lanes constroem cada uma a própria tentativa de uma tarefa, e um revisor fica com uma. No
módulo de lane, `lane_board.py compete --task T --items A,B[,C...]` declara os candidatos, cada um
construído por uma lane diferente; `lane_board.py select --task T --winner A` registra o vencedor,
depois que todo candidato está `CHECKPOINT-READY` com evidência ou `VERIFIED`, e só um revisor cuja
lane difere de toda lane construtora e cuja família de modelo difere da família de todo construtor
pode escrevê-lo. Os perdedores viram `NOT-SELECTED`, um estado terminal do qual nenhuma transição
sai.

**Não é:** uma verificação, e não é uma medida de confiabilidade. Escolher 1 entre N é pass@N: uma
tentativa entre N foi boa o bastante, o que não diz nada sobre o vencedor passar em toda execução.
O vencedor mantém o próprio estado, ainda precisa do `VERIFIED` de sempre antes de `MERGED`, e o
critério dele ainda precisa de pass^k. Um candidato não pode ir a `MERGED` enquanto a tarefa não
tem vencedor, e `select --checker-unavailable` registra `DEFERRED`, nunca um vencedor.

**Verifique:** novo na 2.6.0 —
numa competição declarada com `compete` cujos candidatos estão `CHECKPOINT-READY`,
`lane_board.py select` por um revisor da mesma família de modelo de um construtor sai com 1 e
"SAME model family"; um revisor de outra lane e de outra família sai com 0, e mover o item perdedor
para qualquer estado depois disso sai com 1. `lane_board.py --self-test` roda toda recusa de
`compete` e de `select` ao lado do seu controle.

## House Session

**É:** uma deliberação entre decisores pinados, registrada para poder ser verificada e medida.
`hpp.panel/v1` nomeia a pergunta, o hash do estado julgado, cada assento
(`{id, role, provider, model_served, family, lane}`) e o orçamento (`max_rounds`, `max_chars`).
Um painel não começa sem duas famílias de modelo entre os participantes, exatamente um juiz numa
lane que nenhum participante usa, e os papéis que o `session_type` exige (`plan`, `review`,
`release-gate`, `incident`, `design`). Cada `hpp.turn/v1` carrega a posição de um assento, as
afirmações com os ids em que se apoiam, o hash do texto verbatim e `seen_turns`: um turno da
rodada 1 que viu qualquer coisa é recusado, então a rodada cega é verificável. A sessão para por
regra (`not-judged`, `grounded-convergence`, `paused-budget`, `no-new-evidence`, `max-rounds`), e
`hpp.deliberation/v1` sela o painel, os turnos, a contagem, a parada, o `hpp.decision/v1` do
juiz, o veredito e a dissidência que perdeu; `human_decision` fica fora do selo.

**Não é:** uma chamada de modelo, um voto que substitui uma pessoa, nem prova de que um painel
vence um agente sozinho. Os assentos e o juiz respondem fora do harness. Um assento que não
respondeu **não é julgado** — nunca é voto contra — e bloqueia o veredito. Uma posição é
fundamentada quando o turno afirma um `fact` com referência; se a referência existe no contexto
ainda não é conferido. O painel não publica confiança que não mediu. O selo não é assinatura: `verify` prova que tudo o
que é derivado bate com os turnos e o registro do juiz que o arquivo guarda, e esses só são
ancorados pelos hashes do texto verbatim e da resposta bruta guardados ao lado. A sessão termina na
primeira rodada em que uma regra vale; turnos de rodadas posteriores são recusados. Se um painel vale o custo é
medido com `hpp decide eval`, que lê o painel como um decisor só (`method: panel`), não afirmado
aqui.

**Verifique:** novo na 2.7.0 —
`python -m hpp deliberate record --panel examples/house-session/review/panel.json --turns examples/house-session/review/turns.json --judge examples/house-session/review/judge.json --out out/record.json`
sela a revisão com `stop` `max-rounds`, `escalate: true`, o veredito `high` e o assento `c`
mantido como dissidência, exit 0; `python -m hpp deliberate verify out/record.json` sai com 0, e
numa cópia com o veredito editado sai com 2. Um painel com assento servido por `-latest`, ou com
participantes de uma família só, sai com 2 em `deliberate plan`.

## maker e checker

**É:** dois papéis. O maker produz a mudança. O checker a revisa e reporta acertos e defeitos com
severidade, arquivo e linha, sem ferramentas de edição de arquivo: o host impõe a ausência de
`Write` e `Edit`. O `Bash` continua disponível, e um shell altera o que alcançar, então somente
leitura é uma promessa, verificada comparando a árvore de trabalho antes e depois da revisão — o
`git status --porcelain` capturado dos dois lados precisa bater, e um checker que alterou a árvore
invalida os próprios achados.

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
entradas. A partir de um clone deste repositório, a integridade da distribuição e os checksums dos
módulos são `verified`, porque o `marketplace.json` e o `CHECKSUMS.txt` de cada módulo ficam ao
lado do manifesto; a partir de uma instalação por pip, que não carrega nenhum dos dois, os mesmos
dois itens são `not-verified`.

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

## política de comandos

**É:** um classificador que lê um comando como texto e devolve um de três vereditos, `ALLOW`,
`MANUAL` ou `BLOCK`, com a regra que casou e o motivo dela. As regras são fixas em
`hpp/policy.py`; a primeira que casa vence, e toda regra `BLOCK` é testada antes de qualquer regra
`MANUAL`.

| veredito | regra | casa com |
|---|---|---|
| `BLOCK` | `recursive-delete` | `rm` com uma opção recursiva e uma de força em qualquer grafia (`-rf`, `-fr`, `-r -f`, `--recursive --force`), ou `rmdir /s` |
| `BLOCK` | `force-push` | `git push` com `--force` ou `-f` |
| `BLOCK` | `main-push` | `git push` que nomeia `main` ou `master` |
| `BLOCK` | `pipe-to-shell` | `curl` ou `wget` canalizado para um shell (`sh`, `bash`, `zsh`, `dash`, `ksh`), com ou sem `sudo` |
| `BLOCK` | `destructive-sql` | `DROP` ou `TRUNCATE` seguido de `TABLE` ou `DATABASE` |
| `MANUAL` | `external-push` | qualquer outro `git push` |
| `MANUAL` | `external-send` | `curl` ou `wget` cuja palavra seguinte é uma URL `http://` ou `https://` |
| `MANUAL` | `decision-advisor` | um comando que nomeia `typed-decisions/decide.py` — novo na 2.6.0 |

Qualquer outra coisa é `ALLOW` (regra `allow`), e um comando vazio é `ALLOW` (regra `empty`).

**Não é:** uma sandbox, um parser de shell nem uma afirmação de que um comando é seguro. Ele nunca
roda o comando, e `ALLOW` quer dizer que nenhuma regra casou: uma transferência feita por qualquer outra
ferramenta (`scp`, `rsync`, uma linha de Python) não casa regra nenhuma e é `ALLOW`. O modo muda só o código de saída, nunca o veredito: em
`audit` todo veredito sai com 0; em `enforce`, `BLOCK` sai com 2 e `MANUAL` sai com 1. Se um
veredito para alguma coisa depende de quem o chama — um hook no Claude Code, um comando de
preflight no Codex CLI.

**Verifique:** `python -m hpp policy check --mode enforce --command "rm -rf src"` imprime `BLOCK`
com a regra `recursive-delete` e sai com 2; `--command "git push origin feature"` imprime `MANUAL`
(regra `external-push`) e sai com 1; `--command "python -m pytest -q"` imprime `ALLOW` e sai com 0;
os mesmos três com `--mode audit` imprimem os mesmos vereditos e saem com 0.

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
