[English](MANIFESTO.md) · [Português](MANIFESTO.pt-BR.md)

# Manifesto do House Party Protocol

## Agentes capazes ainda precisam de uma casa operacional

House Party Protocol é um harness para operar agentes de código sob evidência. O modelo raciocina.
O harness delimita, observa, registra, verifica e decide quando o trabalho pode avançar.

Uma resposta convincente não é prova. Uma sessão aberta não é coordenação. Um processo que
responde não é dado fresco. Um autor revisando o próprio trabalho não é revisão independente. O HPP
existe para transformar cada uma dessas diferenças num contrato que um comando consegue checar.

## O protocol

O protocol é o conjunto de invariantes que todo módulo e todo host precisam respeitar:

1. Estado declarado não substitui estado medido.
2. Maker e checker são atores diferentes, e o checker não tem caneta.
3. Conclusão exige um critério, um comando, a saída dele e o frescor dela.
4. Trabalho concorrente declara uma lane, um dono e um território.
5. Uma wave fecha a própria barreira antes de a próxima abrir.
6. Retomada deriva do event log, nunca da memória de uma conversa.
7. Um monitor mantém disponibilidade, frescor e correção separados.
8. Política distingue um aviso, um bloqueio e um gate humano.
9. Capacidade e confiabilidade são medidas separadamente, como `pass@k` e `pass^k`.
10. Um artefato distribuído é reaberto e verificado antes de ser chamado de release.

Quatro desses estão escritos em `hpp.manifest.json` como invariantes checados por máquina: um
resultado verificado tem evidência registrada e um gate humano explícito; um checker é read-only em
relação ao workspace do maker; um loop só avança por meio de um evento registrado; uma aprovação é
inválida assim que a spec, o commit ou o snapshot do repositório a que ela está vinculada mudam. Os
demais são impostos pelos módulos que os implementam e pelos testes que os forçam a falhar.

## O harness

O harness torna o protocol operável. Ele mantém um manifesto de capacidades, compila uma spec num
WorkGraph, ordena dependências em waves, projeta mapas de lane e de agente, compila contexto com
proveniência, acrescenta eventos, deriva a retomada e vincula evidência a um veredito.

Os módulos fornecem os mecanismos especializados. A distribuição os leva ao Claude Code e ao Codex
CLI sem fingir que os dois hosts oferecem os mesmos hooks de lifecycle.

## A ordem vem da spec, não da conversa

O trabalho entra na casa como uma spec: unidades com um id, as unidades de que dependem, os
critérios que as decidem e o risco que carregam. O harness a compila, recusa um ciclo com o
caminho nomeado e devolve waves. Uma dependência que foi discutida mas nunca escrita em
`depends_on` não existe para o harness, e nenhuma quantidade de contexto num transcript a faz
existir.

Paralelismo é consequência desse grafo, não meta. Unidades sem aresta entre si caem na mesma
wave; uma unidade espera a última de suas dependências. Ninguém define um número de agentes em
paralelo, e ninguém é perguntado se duas unidades "podem" rodar juntas: a ausência de aresta já
respondeu. Rodar tudo de uma vez ignoraria as arestas; rodar por wave não ignora nada e ainda
roda junto tudo o que pode.

A barreira é o que torna o progresso legível. Quando uma wave fecha, toda unidade dela cumpriu os
próprios critérios; uma unidade da wave seguinte que começa cedo constrói sobre uma dependência
que não passou, e a evidência dela descreve um checkout que pode não sobreviver. "A wave dois
fechou" é uma frase que um comando consegue checar. "Estamos uns setenta por cento prontos" não é.

O que isto não promete: o harness não descobre dependências. Ele não lê os arquivos que uma
unidade vai tocar, não deduz que duas unidades colidem a partir do que elas fazem, e não impede um
operador de começar uma unidade antes da wave dela. Ele compila as dependências que foram
declaradas, reporta onde está cada barreira, e deixa o declarar e o honrar com as pessoas e os
agentes que fazem o trabalho. Uma aresta que falta é um defeito na spec, e a spec é onde ele se
conserta.

## Por que isto não é burocracia

Processo falha em duas direções. Processo que protege torna o custo de um erro visível antes de o
erro ser cometido. Processo que obstrui faz as pessoas pagarem esse custo a cada passo, tenha ou
não havido a possibilidade de erro. A diferença não é a quantidade de cerimônia. É se cada passo
responde a uma pergunta que, de outro modo, seria respondida por adivinhação.

Todo gate no HPP é uma pergunta com resposta mensurável: o comando do critério saiu com 0; o
snapshot é o mesmo que o checker viu; esta lane está viva; este sinal é mais fresco que o frescor
declarado; este comando casa com uma forma destrutiva. Quando a resposta é sim, o gate custa um
comando e nada mais. Quando a resposta é não, o gate reporta o que foi medido, o que era esperado e
o que fazer em seguida, e a pessoa decide.

Três propriedades mantêm os gates do lado que protege. Primeira, um gate nunca pergunta o que
consegue medir: readiness, liveness, frescor e checksums são computados, não solicitados. Segunda,
um gate que dispararia sobre trabalho legítimo não é publicado; `hpp policy check` bloqueia
`rm -rf`, `rm -fr` e `rm --recursive --force`, e deixa `rm file.txt`, `grep -rf patterns.txt` e
`cp -rf a b` em paz, porque um guarda que grita com o inocente é desligado antes do dia em que
estaria certo. Terceira, todo gate é publicado com o teste que o força a falhar, para que um gate
que parou de guardar em silêncio seja pego pela suíte, e não por um incidente.

Burocracia é um passo cuja ausência ninguém notaria. Cada passo aqui tem uma falha para a qual foi
construído, escrita ao lado dele.

## O que o projeto se recusa a fazer

Estas são decisões, não lacunas. Cada uma tem uma razão que teria de mudar antes de a decisão
mudar.

- **Sem daemon, sem servidor, sem scheduler.** Uma checagem que não rodou não foi rodada. Um
  processo em segundo plano tornaria "está rodando?" uma segunda pergunta a verificar, e carregaria
  estado que o event log não vê.
- **Sem chamada a modelo.** O harness roteia trabalho para um tier e um id de provedor que você
  declarou. Ele não escolhe fornecedor, nome de modelo nem preço, e não guarda credencial. No
  momento em que chamasse um modelo, os vereditos dele dependeriam de algo que ele não consegue
  reproduzir.
- **Sem banco de grafo.** Todo mapa é uma projeção de manifestos, eventos e JSON que você fornece.
  A mesma entrada produz os mesmos nós e arestas, na mesma ordem, e você pode fazer hash do
  resultado. Um grafo armazenado seria uma segunda fonte de verdade que deriva da primeira.
- **Sem escrita silenciosa.** `hpp init` planeja primeiro e escreve um arquivo com `--apply`. O
  instalador de módulos planeja primeiro e aplica numa segunda invocação explícita. Nenhum dos dois
  toca `settings.json`, hooks ou `AGENTS.md`; esse wiring é impresso para uma pessoa colar.
- **Nenhuma promessa aceita como evidência.** Uma marca de conclusão num transcript não para um
  loop; o done gate reexecuta os comandos do critério fora do alcance do modelo. Uma saída vazia,
  um maker e um checker idênticos, ou um veredito diferente de `approved` nunca viram prova.
- **Sem paridade de host por afirmação.** O Claude Code executa hooks de lifecycle; o Codex CLI
  não. A cobertura é declarada por módulo como `native`, `explicit-command` ou `unsupported`, e um
  módulo não suportado interrompe o plano em vez de ser instalado como se funcionasse.
- **Sem número de manchete.** A contagem de módulos não é uma afirmação de qualidade. Um número
  aparece ao lado do comando que o produziu, ou não aparece.
- **Sem telemetria remota.** Nada sai da máquina a menos que uma pessoa rode um comando que envie,
  e esse comando é classificado como `MANUAL` pela política.

## Loops com freio e memória

Um loop útil tem um objetivo, uma observação, uma ação, um orçamento, um gate, uma condição de
parada e um caminho de escalonamento. Sem eles, repetição é insistência com temporizador.

O autoprompt preserva continuidade: ele responde "qual é o próximo passo derivável do estado
registrado?". Os gotchas preservam memória operacional: uma falha que recorre vira uma lição
injetada antes da próxima tentativa, e é redigida por forma antes de ser armazenada. Os monitores
preservam consciência do estado. Nenhum dos três concede a um loop o direito de passar do próprio
orçamento, do próprio território, do próprio gate de evidência ou do gate humano quando há um
declarado. Parar por orçamento é um fim legítimo, registrado como tal, não uma falha.

## Grafos sem teatro de infraestrutura

O HPP usa grafos como explicação, não como decoração e não como motivo para subir um banco de
dados. Os mapas de capability, agente, lane, trabalho, execução, evidência, contexto e monitor são
derivados de arquivos locais. Se uma aresta não muda uma decisão, ela não é desenhada.

## Portabilidade honesta

Dois hosts não são uma identidade só. O Claude Code consegue rodar hooks em `Stop`, `PreToolUse` e
`SessionStart`; o Codex CLI lê `AGENTS.md` e skills, e roda o resto como comandos explícitos. O
doctor mostra a diferença. Cobertura ausente é `unsupported`, nunca "provavelmente funciona".

## Prova antes de escala

O HPP não se chama de confiável por ter muitos componentes. Confiabilidade vem de controles
negativos, execução repetida, revisão independente e uma cadeia de release verificável. Uma release
crítica precisa demonstrar o próprio piso, `pass^k`, não o melhor resultado que já obteve.

## O compromisso

Operar agentes sob evidência. Manter maker e checker separados. Expor os limites de cada host.
Tornar o estado retomável a partir do que foi registrado. Bloquear a conclusão que não passou pelo
próprio gate.

Essa é a casa. O protocol são as regras. Os módulos são as ferramentas. Prova é o que abre a
próxima porta.
