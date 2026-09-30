[English](ROADMAP.md) · [Português](ROADMAP.pt-BR.md)

# Roadmap

Para onde o trabalho vai nos próximos doze meses, e o que o projeto não vai fazer. Isto é uma
direção, não uma promessa: o que foi lançado está registrado no [CHANGELOG.pt-BR.md](CHANGELOG.pt-BR.md)
e nas notas de release, e só ali. O plano é discutido em público na
[discussão do roadmap](https://github.com/rusharlabs/house-party-protocol/discussions/28), na
categoria Announcements; como as decisões são tomadas está no [GOVERNANCE.pt-BR.md](GOVERNANCE.pt-BR.md).

## Onde os mapas estão na 2.11

Todo mapa do HPP é uma projeção de arquivos que você já tem — manifestos, event logs, JSON que você
fornece — e a mesma entrada imprime a mesma saída.

| comando | formatos |
|---|---|
| `hpp graph --view capability\|operational\|agent\|evidence\|code` | JSON ou Mermaid |
| `hpp map lane\|agent\|monitor\|context` | JSON ou Mermaid |
| `hpp work plan\|waves` | JSON ou Mermaid |
| `hpp doctor --matrix` | Markdown: host × módulo × canal |

A view `code` mostra quais superfícies cada módulo declara; ela não é um grafo do seu código. O Lane
Dashboard do lane-kit, desde a 2.10.0, é uma página no endereço de loopback que você liga e desliga,
mostrando o lane board, as lanes vivas, a caixa de mensagens de cada lane e o backlog com as suas
waves; toda ação que ele oferece também é um comando de terminal.

## 2.12: ver o estado

Mermaid para os mapas e para o WorkGraph, o primeiro item planejado para esta etapa, saiu na 2.11.0
(a tabela acima). Os outros três vêm a seguir:

1. **Um mapa de feed.** Uma linha do tempo do que aconteceu entre as lanes — claims, vereditos,
   mensagens enviadas e lidas, entregas, handoffs, heartbeats — derivada de registros que o harness
   já escreve.
2. **Um atlas HTML estático.** `hpp atlas --html` escreveria uma página autocontida com todas as
   views de um projeto, desenhadas a partir do mesmo JSON. Cada view mostra o comando que a
   reproduz e o hash da sua fonte. Ela abre como arquivo; não há servidor.
3. **As views no Lane Dashboard.** O dashboard mostra as mesmas views, desenhadas a partir do mesmo
   JSON, ao lado das ações que ele já oferece.

## 2.13: um grafo de código do seu projeto

Uma base construída sobre a biblioteca padrão do Python — módulos, imports, definições e chamadas
lidos com `ast`; para outras linguagens, só um grafo de imports, declarado como tal — mais um
contrato, `hpp.codegraph/v1`, para um indexador externo que você declara. O HPP normalizaria e
mediria essa entrada; não dependeria dela. O grafo é construído sob demanda, guardado pelo hash do
commit e reportado como `stale` quando está velho, sem watcher. Ele alimentaria o território de
lane por dependência, as checagens do WorkGraph, o raio de impacto de uma attestation e a view de
código do atlas.

## Depois da 2.13

Nada está planejado ainda. O que vem depois é decidido a partir das respostas na discussão do
roadmap e das propostas na categoria Ideas das Discussões, e esta página é atualizada quando isso
acontecer.

## O que o projeto não vai fazer

Estas recusas são as do [MANIFESTO.pt-BR.md](MANIFESTO.pt-BR.md), "O que o projeto se recusa a
fazer". Elas são decisões, não lacunas, e nada neste roadmap as muda. O manifesto traz o motivo de
cada uma e as exceções delimitadas para módulos; onde este resumo e o manifesto divergirem, vale o
manifesto.

- **Sem daemon, sem servidor, sem scheduler.** Uma checagem que não rodou não foi rodada. O atlas
  planejado acima abre como arquivo por esse motivo.
- **Sem chamada de modelo.** O harness roteia o trabalho para um tier e um id de provedor que você
  declarou, e não guarda credencial.
- **Sem banco de grafos.** Todo mapa é uma projeção de arquivos que você fornece; o grafo de código
  planejado para a 2.13 é construído sob demanda, indexado pelo hash do commit e reportado como
  `stale` quando está velho.
- **Sem escrita silenciosa.** Os instaladores planejam primeiro e só escrevem num segundo passo
  explícito; o wiring de settings e hooks é impresso para uma pessoa colar.
- **Nenhuma promessa aceita como evidência.** O done gate roda de novo os comandos do critério; uma
  tag de conclusão numa transcrição não para nada.
- **Sem paridade de host por afirmação.** A cobertura é declarada por módulo como `native`,
  `explicit-command` ou `unsupported`.
- **Sem números de manchete.** Um número aparece ao lado do comando que o produziu, ou não aparece.
- **Sem telemetria remota.** Nada sai da máquina a menos que uma pessoa rode um comando que o envie.

## Como participar

Responda na [discussão do roadmap](https://github.com/rusharlabs/house-party-protocol/discussions/28)
com o seu setup — host, bundle e o comando que você rodaria — um ponto por comentário; um voto
positivo num comentário conta como concordância. Uma proposta que precisa de desenho próprio vai
para a categoria Ideas, como o [SUPPORT.pt-BR.md](SUPPORT.pt-BR.md) descreve. Esta página muda por
pull request, e a mudança fica registrada no CHANGELOG.
