<p align="center">
  <img alt="House Party Protocol — by Rushar Labs" src="assets/hpp-logo.png" width="620">
</p>

<p align="center"><sub><code>AGENTS &nbsp;·&nbsp; EVIDENCE &nbsp;·&nbsp; MEMORY &nbsp;·&nbsp; PROTOCOL &nbsp;·&nbsp; CONTINUITY</code></sub></p>

<p align="center">
  <a href="LICENSE"><img alt="MIT" src="https://img.shields.io/badge/license-MIT-0F1113"></a>
  <a href="#quickstart"><img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-FF6A00"></a>
  <img alt="Claude Code and Codex CLI" src="https://img.shields.io/badge/hosts-Claude%20Code%20%7C%20Codex%20CLI-F4F1EB">
</p>

<p align="center"><sub><a href="README.md">English</a> &nbsp;·&nbsp; Português (Brasil)</sub></p>

# House Party Protocol

**Opere agentes de código sob evidência, não confiança.**

House Party Protocol (HPP) é um harness local-first para agentes de código. Ele fica em volta do
trabalho que um agente faz no Claude Code ou no Codex CLI e transforma quatro perguntas em
contratos executáveis: o que pode rodar, quem pode aprovar, o que conta como prova, e de onde vem
o próximo passo depois de uma interrupção.

O harness é um pacote Python sem dependência de runtime (`python -m hpp`), um manifesto que
declara o protocol, um conjunto de módulos instaláveis e um canal de distribuição por host. Nada
roda em segundo plano. Todo veredito que ele produz pode ser re-derivado de arquivos em disco.

## O problema

Um agente diz "pronto". A frase é fluente, o diff parece plausível e nada conferiu. Os testes que
ele relata podem ter rodado contra um checkout velho, ou não ter rodado; texto num transcript não
é exit code. A aprovação que um revisor deu ontem continua lendo "aprovado" hoje de manhã, depois
de a spec mudar e três arquivos se moverem. Ninguém reabriu, porque nada amarrava a aprovação aos
bytes que ela aprovou.

Duas sessões dividem um repositório. Uma reescreve um módulo enquanto a outra o revisa; a revisão
cai numa versão que não existe mais. Ou o agente que escreveu o código é o que revisa, com os
mesmos pontos cegos e uma caneta na mão: ele "conserta e segue", e o defeito de processo nunca
aparece. Um lock deixado por uma sessão que morreu às 3 da manhã bloqueia todas as outras às 9,
porque um lock morto e um vivo são idênticos.

Depois vêm as falhas que mentem por estarem tecnicamente corretas. Um serviço responde 200 enquanto
o dado é de terça. Um sinal com timestamp no futuro é reportado como fresco. Um contador devolve
zero porque o padrão nunca casou, e zero é lido como "sem problemas". Um loop toma "só mais uma
iteração" além do orçamento. Um resumo restaurado depois de uma queda é tratado como lista de
tarefas, e um passo já concluído roda de novo e sobrescreve o próprio resultado. Nenhuma dessas
levanta erro. É isso que as torna caras.

## Como o harness responde

Cada falha acima tem um mecanismo no código, e cada mecanismo tem um comando que o mostra.

| falha | mecanismo | comando |
|---|---|---|
| "pronto" sem prova | event log append-only; `verified` exige evidência registrada; evento fora de ordem é recusado antes de qualquer escrita | `hpp event append` · `hpp status` |
| aprovação velha | attestation vinculada ao hash da spec, ao commit-base e a um snapshot completo de arquivos rastreados e não rastreados; qualquer divergência bloqueia o reuso | `hpp attest create` · `hpp attest verify` |
| autor revisando o próprio trabalho | maker e checker precisam diferir (ignorando caixa) ou a attestation é recusada; os checkers dos módulos vêm sem ferramenta de escrita | `hpp attest create --maker a --checker a` → exit 2 |
| lock morto, colisão de território | o Lane Map deriva `alive` / `suspect` / `dead` dos heartbeats; lane morta nunca produz colisão | `hpp map lane --now` |
| serviço no ar, dado velho | o Monitor Map separa `healthy`, `stale`, `skew` e `unknown`, com frescor declarado e tolerância de relógio | `hpp map monitor --now` |
| comando perigoso | o classificador de política devolve `ALLOW`, `MANUAL` ou `BLOCK`; `enforce` mapeia para exit 0, 1, 2 | `hpp policy check --mode enforce` |
| paralelismo no chute | o WorkGraph transforma dependências declaradas em waves topológicas; ciclo é erro, não wave vazia | `hpp work waves` |
| contexto truncado em silêncio | o compilador encaixa blocos inteiros sob um orçamento em caracteres, registra um hash por bloco e recusa material com cara de segredo | `hpp context compile` |
| uma rodada com sorte | `pass@k` e `pass^k` medidos separadamente em `k` execuções | `hpp eval run` · `hpp benchmark` |
| instalador que escreve antes de você ler | `hpp init` imprime um plano; `--apply` escreve um arquivo; o wiring do host continua sendo um colar | `hpp init` |

## Quickstart

Requisitos: Python 3.10 ou mais novo (`pyproject.toml`), `git` no `PATH` para attestation,
nenhum pacote de terceiro. A CI exercita Python 3.10 a 3.13 em Linux, macOS e Windows
(`.github/workflows/ci.yml`); interpretadores mais antigos não são prometidos porque nada os mede.

```bash
pip install git+https://github.com/rushar-labs/house-party-protocol
hpp doctor
hpp init --target ../your-repo
```

O pacote não tem dependência de runtime e carrega o próprio manifesto e a suíte de benchmark,
então `hpp` — inclusive `hpp benchmark` e `hpp --self-test` — responde de qualquer diretório
depois de instalado (`pipx install git+…` funciona igual). A partir de um checkout, a CLI é o módulo:

```bash
git clone https://github.com/rushar-labs/house-party-protocol.git
cd house-party-protocol
python -m hpp doctor
```

`hpp init` roda seis estágios fixos e imprime um plano. Cada linha de abertura completa só quando
o estágio terminou; a prontidão conta checagens que rodaram, e cada item carrega o comando que o
reproduz. O que ele consegue verificar depende de onde o `hpp` roda. Este repositório é a
distribuição emitida — harness, manifesto, os dez diretórios de módulo com seus `CHECKSUMS.txt`,
`marketplace.json` e o instalador de módulos — e, a partir de um clone dele, contra um alvo vazio
(`python -m hpp init --target <dir-vazio> --non-interactive --no-animation`), a saída é:

```text
> detecting host...           ✓ greenfield · 0 existing item(s) preserved
> checking prerequisites...   ✓ python 3.14.3 · protocol 2.0
> mounting profile...         ✓ would-write · host=claude-code · bundle=reliable-coding · policy=audit · 3 default(s)
> loading modules...          ✓ 6 modules · reliable-coding · claude-code · 6/6 checksums verified
> wiring suggestions...       ✓ 7 commands to paste · 0 files written
> verifying evidence...       ✓ policy · graph · events · benchmark
> protocol online.

  READINESS  every line is a check that ran; the command below it reproduces it
  ████████████████░░░░  9/11 verified · 2 not verified · 0 failed
```

Os dois itens não verificados são os dois que só uma ação posterior prova: o profile (só plano;
`--apply` o escreve) e o wiring do host (um colar que você faz). A instalação por pip é outro
canal: o wheel carrega o harness, o manifesto e a suíte de benchmark, mas nenhum diretório de
módulo e nenhum `marketplace.json`. O mesmo comando a partir dessa instalação, no mesmo alvo
vazio, mostra:

```text
> detecting host...           ✓ greenfield · 0 existing item(s) preserved
> checking prerequisites...   ✓ python 3.14.3 · protocol 2.0
> mounting profile...         ✓ would-write · host=claude-code · bundle=reliable-coding · policy=audit · 3 default(s)
> loading modules...          ✓ 6 modules · reliable-coding · claude-code
> wiring suggestions...       ✓ 7 commands to paste · 0 files written
> verifying evidence...       ✓ policy · graph · events · benchmark
> protocol online.

  READINESS  every line is a check that ran; the command below it reproduces it
  █████████████░░░░░░░  7/11 verified · 4 not verified · 0 failed
```

Os dois itens a mais ali — integridade da distribuição e checksums dos módulos — são reportados
como não verificados porque não há contra o que medi-los, nunca como aprovados. Em qualquer dos
canais nada é escrito até você rodar de novo com `--apply`, e aí exatamente um arquivo é escrito:
`.hpp/profile.json`. `hpp init --json` devolve o mesmo relatório em JSON para CI e agentes;
`--non-interactive`, `--yes` e `--profile` respondem às três perguntas sem prompt.

Depois do `--apply`, cole o bloco de wiring que o comando imprimiu. Para Claude Code é o canal
nativo de plugin:

```text
/plugin marketplace add rushar-labs/house-party-protocol
/plugin install operator-kit@house-party-protocol
```

Para Codex CLI o instalador de módulos copia cada módulo para `.agents/hpp/<módulo>` e roda os
smokes declarados. No Claude Code, um módulo sem hook de plugin é copiado à mão (o README de cada
módulo mostra a linha `cp -r`) e o instalador detecta, liga e verifica. Nos dois casos ele planeja
primeiro e aplica só numa segunda invocação explícita:

```bash
python instaladores/kit-forge-1.4.0/kit_doctor.py install \
  --kit frameworks-com-plugins/operator-kit-1.4.0 --host codex --target ../your-repo
python instaladores/kit-forge-1.4.0/kit_doctor.py install \
  --kit frameworks-com-plugins/operator-kit-1.4.0 --host codex --target ../your-repo --apply
```

O instalador faz parte deste repositório, em `instaladores/kit-forge-1.4.0/kit_doctor.py`, ao
lado dos diretórios de módulo a partir dos quais ele instala. Uma instalação por pip não carrega
nem um nem outro, e o `hpp init` avisa isso no bloco de wiring quando não encontra o instalador
ao lado do manifesto.

## Harness, protocol, módulos, distribuição

O produto é em camadas, e as camadas não se trocam entre si.

```text
harness        python -m hpp          the operating surface: doctor, init, event log,
                                      attestation, maps, WorkGraph, policy, routing, eval
   │
protocol       hpp.manifest.json      the invariants: roles, loop transitions and gates,
                                      exit codes, host coverage, monitors, bundles
   │
modules        ten versioned dirs     installable capabilities; each stands alone
   │
distribution   marketplace · copy     Claude Code plugin channel · Codex CLI verified copy
```

`hpp doctor` valida o manifesto e, quando `marketplace.json` está ao lado dele, cruza cada caminho
de módulo, versão e manifesto de plugin. Neste repositório ele imprime
`HPP doctor: ok · modules=10 · hosts=claude-code, codex`; o cruzamento só aparece em
`hpp doctor --json`, onde `distribution` lê `{"checked": true, "modules": 10, "status": "ok"}`.
A partir de uma instalação por pip a linha única é a mesma e o campo lê
`{"checked": false, "status": "source-contract"}`, porque nenhum `marketplace.json` está ao lado
do manifesto empacotado.

O loop do protocol são cinco transições, cada uma atrás de um gate nomeado:

```text
planned --work_started--> active --evidence_recorded--> evidenced --check_passed--> checked
        [scope]                   [fresh-evidence]                 [read-only-checker]

checked --human_approved--> approved --verified--> verified
        [human]                      [closure]
```

`hpp status` projeta o event log nessa máquina e nomeia o próximo passo; `hpp resume` devolve a
mesma resposta em JSON. Nenhum dos dois pede a um modelo que lembre de alguma coisa.

## O que cada módulo resolve

| módulo | versão | uma linha |
|---|---|---|
| `operator-kit` | 1.4.0 | done gate com exit code real, política de comando em `audit` ou `enforce`, loops governados com charter e condições de parada, runner standalone de `pass@k` / `pass^k`, preflight, dois agentes checkers read-only |
| `lane-kit` | 1.2.0 | um quadro de lanes para sessões concorrentes: claim, território, liveness, maker ≠ checker, e um roteador que escolhe checker de outro provedor |
| `continuity-kit` | 1.2.1 | handoff escrito antes de parada ou compactação, comandos de re-derivação em vez de estado lembrado, guardas contra replay de passo concluído |
| `health-kit` | 1.3.1 | sondas de serviço config-driven que gravam um cache que a statusline lê sem tocar a rede; saúde de serviço separada de saúde de dado |
| `gotcha-memory` | 1.0.0 | registra comandos que falharam por família de erro, detecta recorrência, injeta a lição antes da próxima execução; warn-only, segredo redigido por forma |
| `kit-forge` | 1.4.0 | monta módulos a partir das fontes, faz lint de IP e PII, instala em seis estágios, escreve e verifica `CHECKSUMS.txt`, confere o marketplace |
| `claude-dev-kit` | 1.3.1 | autoria de skills, hooks e plugins para Claude Code, wiring reversível de settings, secret scan na escrita |
| `dev-squad-kit` | 1.0.0 | doze papéis de desenvolvimento como comandos e subagents com tools explícitos, mais skills de leitura e consolidação paralelas |
| `agent-framework-wizard` | 1.1.1 | scaffold em seis passos para um projeto novo de agente ou skill, respondível por arquivo em execução não interativa |
| `supabase-pack` | 1.1.0 | auditoria de RLS por `pg_policies` e advisors em vez de flag de tabela; scaffold de Edge Function |

O bundle `reliable-coding` são os seis primeiros. Cada módulo instala sozinho; `integrates_with`
no manifesto é composição opcional, `requires` é dependência dura, e hoje nenhum módulo requer
outro. A cobertura por host é declarada módulo a módulo como `native`, `explicit-command` ou
`unsupported`; `claude-dev-kit` é `unsupported` no Codex CLI, e o `hpp init` para em vez de
planejá-lo ali.

## Provando uma instalação

Uma afirmação sobre o harness só é aceita com o comando ao lado. Estes são os que o projeto roda
sobre si mesmo.

```bash
python -m hpp doctor                      # manifest contract; distribution when present
python -m hpp benchmark -k 3              # ten executable controls, three runs each
python -m hpp --self-test                 # capability graph non-empty + benchmark gate
python -m pytest tests -q                 # stdlib-only suite, no network
python -m hpp policy check --mode enforce --command "rm -rf src"   # exit 2, BLOCK
python -m hpp graph --view operational --format json | sha256sum   # same hash on every run
```

Os dez controles do benchmark executam, cada um, um mecanismo real com caso positivo e negativo:
contrato do manifesto, enforcement de política, waves do WorkGraph, colisão de lane, frescor de
monitor, proveniência de contexto, piso de roteamento, gate de evento/evidência, determinismo de
grafo e attestation de evidência. `pass^k = 1.00` é exigido para o gate passar. O arquivo da suíte
e o hash dele estão no relatório JSON (`hpp benchmark -k 3 --json`). Veja [PROOF.pt-BR.md](docs/PROOF.pt-BR.md)
para a matriz de claims e [BENCHMARK.pt-BR.md](docs/BENCHMARK.pt-BR.md) para os cenários.

Neste repositório, `python instaladores/kit-forge-1.4.0/kit_doctor.py verify <dir-do-módulo>`
compara cada arquivo de um módulo com o seu `CHECKSUMS.txt`, e
`python instaladores/kit-forge-1.4.0/kit_doctor.py marketplace .` confere a árvore inteira.

## Limites honestos

- HPP é uma CLI. Não há daemon, scheduler, fila, servidor, banco ou telemetria remota. Se uma
  checagem não rodou, nada a rodou.
- HPP nunca chama modelo. O roteamento devolve um tier e um id de provedor a partir de declarações
  que você passa; não escolhe fornecedor, nome de modelo nem preço.
- Os mapas são projeções de manifestos, event logs e JSON que você fornece. O Monitor Map não sonda
  nada; você fornece `last_signal`. O Lane Map não conhece suas sessões; você fornece heartbeats.
  `--now` é explícito para que nenhuma projeção dependa do relógio ambiente.
- O orçamento de contexto é medido em caracteres, não em tokens.
- O classificador de política é um conjunto de regras pequeno e explícito (remoção recursiva em
  qualquer ordem de flags, force push, push em `main`/`master`, `curl | sh`, `DROP`/`TRUNCATE`, e
  `MANUAL` para qualquer push ou transferência de saída). Ele nunca executa o comando e não afirma
  pegar toda forma destrutiva.
- A attestation exige `git`. Ela faz hash da identidade do remoto e guarda o hash, não a URL. Ela
  amarra um veredito a bytes; não julga se o veredito estava certo.
- No Claude Code, hooks de lifecycle são nativos depois que você cola o wiring. No Codex CLI não
  há hooks de lifecycle; as mesmas capacidades são comandos explícitos. `hpp doctor` e o
  manifesto reportam isso como `native`, `explicit-command` ou `unsupported`, e nenhum adaptador
  finge o contrário.
- `hpp init` escreve um arquivo com `--apply` e nunca edita `settings.json`, hooks ou
  `AGENTS.md`. Ligar hooks continua sendo ação humana.
- O benchmark prova o harness no checkout e na plataforma em que rodou. Não diz nada sobre a
  qualidade de modelo algum.

## Ordem de leitura

Cada documento existe em inglês (a fonte) e em português (`.pt-BR.md`); os links abaixo apontam para
a versão em português. [MANIFESTO.pt-BR.md](MANIFESTO.pt-BR.md) — o que o projeto defende e recusa ·
[CONCEPTS.pt-BR.md](docs/CONCEPTS.pt-BR.md) — o vocabulário, com o que cada termo não é ·
[METHOD.pt-BR.md](docs/METHOD.pt-BR.md) — o método de trabalho, um comando por prática ·
[ARCHITECTURE.pt-BR.md](docs/ARCHITECTURE.pt-BR.md) — como as peças se encaixam e o que deliberadamente não
existe · [GRAPH-MODEL.pt-BR.md](docs/GRAPH-MODEL.pt-BR.md) · [LOOPS.pt-BR.md](docs/LOOPS.pt-BR.md) ·
[BENCHMARK.pt-BR.md](docs/BENCHMARK.pt-BR.md) · [PROOF.pt-BR.md](docs/PROOF.pt-BR.md) · [BRAND.pt-BR.md](docs/BRAND.pt-BR.md) ·
[TIPS.pt-BR.md](docs/TIPS.pt-BR.md) · [manual](docs/MANUAL.html) · [catálogo](docs/CATALOGO.pt-BR.html) ·
[CHANGELOG.pt-BR.md](CHANGELOG.pt-BR.md) · [AGENTS.pt-BR.md](AGENTS.pt-BR.md) para agentes trabalhando neste
repositório.

## Desenvolvimento

Os diretórios de módulo na distribuição são artefatos emitidos. Mudanças nascem nas fontes,
ganham um teste que falha antes do conserto e passa depois, e passam pela forja. Antes de declarar
qualquer coisa pronta:

```bash
python -m pytest tests -q
python -m hpp doctor
python -m hpp benchmark -k 3
```

## Licença e crédito

MIT. Copyright (c) 2026 Max Parisi, Rushar Labs. Componentes adaptados preservam seus arquivos
`NOTICE` e atribuições; o README de cada módulo nomeia suas fontes e licenças de origem.
