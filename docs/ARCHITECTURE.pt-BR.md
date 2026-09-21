[English](ARCHITECTURE.md) · [Português](ARCHITECTURE.pt-BR.md)

# Arquitetura

Como as peças do House Party Protocol se encaixam, onde o estado mora e o que deliberadamente não
existe.

## Quatro camadas

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ HARNESS       python -m hpp                                              │
│               doctor · init · event · status · resume · attest · policy  │
│               work · route · context · map · graph · eval · benchmark    │
├──────────────────────────────────────────────────────────────────────────┤
│ PROTOCOL      hpp.manifest.json                                          │
│               roles · loop transitions and gates · exit codes            │
│               host coverage · monitors · bundles · invariants            │
├──────────────────────────────────────────────────────────────────────────┤
│ MODULES       ten versioned directories, each installable on its own     │
│               skills · hooks · commands · agents · rules · scripts       │
├──────────────────────────────────────────────────────────────────────────┤
│ DISTRIBUTION  Claude Code: marketplace.json + plugin per module          │
│               Codex CLI:   verified copy into .agents/ by the installer  │
└──────────────────────────────────────────────────────────────────────────┘
```

O harness é stdlib-only e não executa modelo algum. Ele lê arquivos, roda os comandos que você
nomeia e escreve num pequeno número de caminhos declarados.

## O pacote `hpp/`

| arquivo | responsabilidade | superfície |
|---|---|---|
| `cli.py` | parsing de argumentos, despacho, o contrato de saída (`2` para entrada recusada, `3` para erro interno) | todo subcomando, `--self-test` |
| `manifest.py` | localizar, carregar e validar o manifesto; cruzar com `marketplace.json` e com o `plugin.json` de cada módulo quando presentes | `doctor` |
| `state.py` | event log append-only; projeção dos eventos sobre o loop; recusa de transições inválidas antes da escrita | `event append`, `status`, `resume` |
| `workgraph.py` | validar uma spec, rejeitar ciclos com o caminho nomeado, ordenar unidades em waves | `work plan`, `work waves` |
| `policy.py` | classificar um comando como `ALLOW`, `MANUAL` ou `BLOCK`; mapear para código de saída por modo | `policy check` |
| `attest.py` | vincular um veredito à identidade do repositório, ao commit base, ao hash da spec e a um snapshot completo de arquivos; verificar depois | `attest create`, `attest verify` |
| `context.py` | encaixar blocos inteiros sob um orçamento de caracteres com hashes de proveniência; recusar entrada que se pareça com segredo | `context compile`, `map context` |
| `routing.py` | escolher um tier e um id de provedor a partir de risco, complexidade, tamanho de contexto e estágio declarados; fazer fallback só para cima | `route` |
| `maps.py` | Lane Map, Agent Map, Context Map e Monitor Map como projeções ordenadas, só de dados | `map lane`, `map agent`, `map context`, `map monitor` |
| `graph.py` | visões de capability, operacional, agente, evidência e código a partir do manifesto; JSON ou Mermaid | `graph` |
| `evals.py` | runner de `pass@k` / `pass^k` sobre uma suíte de casos com três tipos de runner | `eval run`, `benchmark` |
| `controls.py` | os dez controles executáveis que o benchmark roda, cada um com um caso positivo e um negativo | `benchmark`, `--self-test` |
| `install.py` | recibo de instalação só de plano para um bundle num host; recusa cobertura não suportada | `install` |
| `wizard.py` | `hpp init`: seis estágios, readiness, plano versus aplicação, bloco de wiring | `init` |
| `term.py` | detecção de tier de cor, saída ANSI, fallback de glifo ASCII, comportamento sem TTY | usado por `init` |
| `brand.py` | paleta, wordmark em blocos e linhas de fechamento para o terminal | usado por `init` |

Os tamanhos são pequenos por desenho; o pacote inteiro é legível de uma sentada. Nada importa
fora da biblioteca padrão.

## O fluxo

```text
  spec (JSON)
     │  hpp work plan
     ▼
  WorkGraph ──── waves ───▶ wave 1 ──▶ wave 2 ──▶ ... (barrier between waves)
     │                        │
     │  hpp route             │  per unit: tier → provider id (never a model call)
     │                        ▼
     │                     lane claim ◀── hpp map lane (liveness from heartbeat)
     │                        │
     │                        ▼
     │                     work_started ─▶ evidence_recorded ─▶ check_passed
     │                        │                 ▲                    │
     │                        │      hpp context compile             │
     │                        │      (what the maker saw, hashed)    ▼
     │                        │                              hpp attest create
     │                        │                              (verdict bound to bytes)
     ▼                        ▼                                      │
  hpp map monitor        .hpp/events.jsonl  ◀── human_approved ◀─────┘
  (up · fresh · skew)         │
                              ▼
                          verified  ── hpp status / hpp resume derive the next step
```

Toda seta que muda estado é um evento acrescentado. Toda caixa que decide algo lê arquivos e
escreve no máximo um arquivo declarado.

## Onde o estado mora

| caminho | escrito por | conteúdo | tempo de vida |
|---|---|---|---|
| `.hpp/events.jsonl` | `hpp event append` | um objeto JSON por linha: `seq`, `id`, `type`, `data`; append-only | o histórico do loop do workspace |
| `.hpp/profile.json` | `hpp init --apply` | host, bundle, módulos, modo de política, versão do protocol e do produto | até o operador removê-lo |
| `.hpp/attestation.json` | `hpp attest create --output` | o veredito vinculado; o caminho é escolha sua | até os bytes que ele descreve mudarem |
| `hpp.manifest.json` | o projeto | o protocol; encontrado subindo a partir do diretório atual, depois ao lado do pacote-fonte, depois na cópia embarcada no pacote instalado | versionado com o produto |
| `CHECKSUMS.txt` do módulo | a forja | sha256 por arquivo distribuído | versionado com cada módulo emitido |

Todo o resto que o harness consome é uma entrada que você passa na linha de comando: specs, lanes,
monitores, provedores, pedidos de roteamento, blocos de contexto, suítes de avaliação. Não há cache
oculto, diretório de estado no nível do usuário nem variável de ambiente que mude um veredito; o
único ambiente que o harness lê é `NO_COLOR`, `FORCE_COLOR`, `TERM`, `COLORTERM`, `CI` e a flag de
sessão do terminal do Windows, e esses afetam apenas a renderização.

O event log é a fronteira de recuperação. Lê-lo valida que `seq` é contíguo e que `id` é igual a
`event:<seq>`; uma linha corrompida para a projeção com o número da linha em vez de pulá-la.
Acrescentar valida a transição contra o manifesto antes de abrir o arquivo, de modo que um evento
recusado não deixa rastro e não consegue criar o log.

## O manifesto como contrato executável

`hpp.manifest.json` declara a versão do protocol, os hosts, os módulos com os próprios caminhos,
versões, capacidades, relações e cobertura por host, os bundles, os papéis, os códigos de saída, os
tiers e a regra de roteamento, os nomes dos mapas, o caminho do instalador, os monitores e o loop.

`hpp doctor` rejeita um manifesto que viole qualquer um destes: hosts, módulos, capacidades,
caminhos e ids de monitor únicos; caminhos de módulo relativos; valores de cobertura fora de
`native` / `explicit-command` / `unsupported`; relações desconhecidas; ciclos em `requires`;
bundles nomeando módulos ou capacidades desconhecidos; códigos de saída diferentes de `0/1/2/3`;
tiers de roteamento diferentes de `economy/balanced/frontier`; monitores com cadência ou frescor
não positivos.

Quando `marketplace.json` fica ao lado do manifesto, o doctor também confere que a versão do
produto bate, que o conjunto de módulos bate, que o `source` e a `version` de cada módulo batem,
que o diretório do módulo existe dentro da raiz do produto e que o `.claude-plugin/plugin.json`
dele concorda em nome e versão. Num checkout de fonte sem marketplace o doctor diz isso
(`distribution: source-contract`) em vez de reportar uma checagem que não conseguiu rodar.

## Mapas

Os mapas não têm estado próprio. Cada um é uma projeção de uma ou duas entradas, ordenada de modo
que a mesma entrada produza a mesma saída byte a byte.

| mapa | entrada | pergunta que responde |
|---|---|---|
| capability | manifesto | qual módulo fornece qual capacidade, em qual host, em qual bundle |
| operational | `loop` do manifesto | qual evento move qual estado por qual gate |
| agent | papéis e módulos do manifesto, eventos opcionais | quem pode fazer, checar e aprovar; o que aconteceu, em ordem |
| evidence | fixa | como um critério, um registro e um veredito se relacionam |
| code | componentes do manifesto | quais superfícies cada módulo declara (não é uma AST) |
| lane | JSON de lanes, `--now`, limiares | quem possui o quê, quem está vivo, onde reivindicações vivas se sobrepõem |
| context | JSON de contexto, `--budget` | o que entrou no contexto compilado, o que foi omitido, com hashes |
| monitor | JSON de monitores, `--now`, `--skew-tolerance` | o que é observado, quão fresco, e qual gate o consome |
| work | JSON da spec | quais unidades podem rodar juntas e em que ordem |

O Context Map é proveniência de uma compilação; não é recuperação e não é uma base de
conhecimento. O Code Map inventaria componentes declarados; não é um grafo de chamadas.

## Dois hosts

| capacidade | Claude Code | Codex CLI |
|---|---|---|
| skills e instruções | plugin, nativo | copiadas para `.agents/skills`, com namespace |
| hooks de lifecycle (`Stop`, `PreToolUse`, `SessionStart`, ...) | nativos depois que uma pessoa faz o wiring | nenhum; os mesmos scripts rodam como comandos explícitos |
| política de comandos | hook mais CLI | CLI ou preflight |
| event log, attestation, mapas, WorkGraph, eval | CLI | CLI |
| instalação | plugin do marketplace, ou cópia pelo instalador para módulos `explicit-command` | cópia pelo instalador para `.agents/hpp/<module>` |

A costura de host é uma tabela pequena: caminho de settings e gates manuais para o Claude Code;
`AGENTS.md`, caminho de skills e caminho de runtime para o Codex CLI. `hpp init` a usa para nomear
os mesmos caminhos que o instalador de módulos vai tocar, e não toca em nenhum deles. Acrescentar
um host significa acrescentar uma linha e um valor de cobertura por módulo, não mudar os seis
estágios.

## Distribuição

A árvore publicada é emitida pela forja a partir das fontes dos módulos. Cada diretório de módulo
carrega `CHECKSUMS.txt` (sha256 por arquivo) e um `.zip` com os mesmos bytes; `marketplace.json`
lista os módulos com `source` e `version`; o instalador
(`instaladores/kit-forge-<version>/kit_doctor.py`) roda os seis estágios de instalação, verifica
checksums e executa os smokes declarados do módulo.

```text
sources ──forge──▶ module dir + CHECKSUMS.txt + .zip ──▶ marketplace.json
                        │                                     │
                        └── kit_doctor.py verify ◀────────────┘── hpp doctor (cross-check)
```

O checkout de fonte do harness não contém os módulos emitidos nem o instalador. O doctor, o
benchmark e a suíte rodam ali; a integridade da distribuição e os checksums dos módulos são
reportados como não verificados em vez de presumidos.

## Contrato de saída

| código | significado | onde |
|---|---|---|
| `0` | ok; no modo `audit`, sempre | todo comando |
| `1` | warn ou gate manual; um gate de eval que falhou | `policy check` (`MANUAL` em `enforce`), `eval run`, `benchmark`, `init` com avisos |
| `2` | block; uma entrada recusada (manifesto ruim, spec ruim, log corrompido, attestation inválida) | `policy check` (`BLOCK`), `attest`, todo erro de validação |
| `3` | erro de uso ou interno | erros de uso do `init`, exceções inesperadas |

`hpp init` reporta o código que vai devolver dentro do próprio relatório JSON (`exit_code`) e
interrompe os estágios restantes quando um estágio falha com uma dica bloqueante.

## Testes e CI

A suíte em `tests/` é stdlib-only e roda sem rede. Cada arquivo de teste carrega ao menos um teste
chamado `CONTROLE` que prova que o arquivo consegue falhar. Dois testes pulam num checkout de fonte
porque precisam de `marketplace.json`; eles rodam na distribuição emitida. A CI roda a suíte,
`hpp doctor` e `hpp benchmark -k 3` em Linux, macOS e Windows, de Python 3.10 a 3.13, com
permissões somente de leitura e nenhum passo autorizado a falhar em silêncio.

```bash
python -m pytest tests -q
python -m hpp doctor
python -m hpp benchmark -k 3
```

## O que deliberadamente não existe

| ausente | por que é uma escolha |
|---|---|
| daemon ou serviço em segundo plano | uma checagem que não rodou não foi rodada; um processo residente seria uma segunda coisa a verificar e guardaria estado que o log não vê |
| servidor, API ou control plane | o harness é operado a partir do repositório que protege; um plano remoto afastaria o veredito dos bytes sobre os quais ele fala |
| scheduler ou fila | a cadência no Monitor Map é declarada para o consumidor honrar; o harness não acorda sozinho |
| banco de grafo | todo mapa é re-derivável de arquivos; um grafo armazenado derivaria das fontes e exigiria o próprio doctor |
| execução de modelo | o roteamento devolve um tier e um id de provedor; chamar um modelo faria os vereditos dependerem de algo que o harness não consegue reproduzir nem se permitir guardar credenciais para |
| armazenamento de credenciais | não há nenhuma para vazar; entrada que se pareça com segredo no compilador de contexto é recusada, e a memória de falhas redige por forma |
| telemetria | nada sai da máquina; qualquer transferência de saída que um agente tente é classificada como `MANUAL` |
| wiring automático de settings ou hooks | ligar um hook muda o que roda em toda chamada de ferramenta futura; isso é ação humana, impressa para colar |
| contagem de tokens | o orçamento é em caracteres, que todo host mede do mesmo jeito; uma contagem de tokens amarraria o harness a um tokenizador |

Uma camada só é acrescentada quando há um consumidor para ela e um benchmark que mostre quanto ela
custa. Até lá, a ausência é a feature.
