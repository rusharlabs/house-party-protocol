[English](UX-INSTALL-JOURNEY.md) · [Português](UX-INSTALL-JOURNEY.pt-BR.md)

# UX-INSTALL-JOURNEY — a jornada de instalação, contada na conversa

> **Versão:** 2.0.0 — camada de apresentação sobre dois contratos congelados.
> **Caminho 1** é o `hpp init`, o instalador do harness (`hpp/wizard.py`, seis estágios, plano e
> depois `--apply`). **Caminho 2** é o instalador de módulos, `installers/kit-forge-1.4.1/kit_doctor.py`,
> cuja mecânica vive em `INSTALL-CONTRACT.md` e cujo README por módulo segue o
> `INSTALL-GUIDE-TEMPLATE.md`; os dois viajam na raiz deste repositório. Este documento descreve
> a EXPERIÊNCIA: como um AGENTE (Claude Code ou Codex CLI) guia um HUMANO pela instalação, numa
> conversa. Nada aqui muda a mecânica — se este documento contradisser o código ou o
> `INSTALL-CONTRACT.md`, eles vencem. Toda saída citada abaixo foi medida em 2026-09-21 contra a
> versão 2.4.1, a partir de um clone deste repositório, salvo onde o texto diz "instalação por pip".

## Princípio

**O humano nunca vê um prompt de terminal. Ele vê uma conversa.** O agente roda o plano, traduz
o plano para a língua do humano, e espera o humano dizer "pode aplicar" em linguagem natural. Só
então re-invoca com `--apply`. Nenhum `input()` é alcançado numa sessão de agente — o `hpp init`
só pergunta num TTY, e `--non-interactive`, `--yes`, `--json` ou `CI` no ambiente tiram esse
caminho; o "Confirm" é a dupla invocação.

Três papéis, sem sobreposição:

| Papel | Faz | Nunca faz |
|---|---|---|
| **instalador** (`hpp init` · `kit_doctor.py`) | executa os seus estágios; em modo plano, zero escrita | pergunta em stdin numa sessão de agente; escreve settings/hooks |
| **agente** | roda comandos, traduz o plano, pede confirmação, reporta com saída real | aplica sem confirmação; edita `settings.local.json`/hooks por conta própria |
| **humano** | lê o plano na conversa, decide, confirma em linguagem natural | precisa decorar flags — o agente carrega o comando |

## Caminho 1 — `hpp init`, a jornada do harness (principal)

O `hpp init` é a porta de entrada: ele planeja a instalação inteira para um host, verifica o que
consegue, escreve no máximo um arquivo e imprime no bloco de wiring as linhas do instalador de
módulos do Caminho 2. O agente começa por aqui, sempre.

### Os seis estágios

Os estágios são fixos e rodam nesta ordem; cada linha de abertura completa só quando o estágio
terminou.

| Estágio | Linha de abertura | O que mede | O que pode pará-lo |
|---|---|---|---|
| `detect` | `detecting host...` | `greenfield`, `in-progress` ou `re-run`, a partir de `.claude/settings*.json`, `AGENTS.md`, `.agents/`, `.hpp/events.jsonl`, um `.hpp/profile.json` anterior e a contagem de commits do git; lista o que existe e é mantido | um log de eventos ou profile corrompido é um aviso com o arquivo a inspecionar |
| `prereqs` | `checking prerequisites...` | Python igual ou acima de 3.10; o contrato do manifesto; a distribuição quando o `marketplace.json` está ao lado do manifesto; `git` no `PATH` | Python abaixo do piso ou divergência manifesto/marketplace interrompe (exit 2) |
| `profile` | `mounting profile...` | as três respostas — host, bundle, modo de política — vindas de flags, de `--profile`, do prompt (só em TTY) ou do default, com a origem de cada uma registrada | um profile gravado com respostas diferentes é um `conflict`; nada é sobrescrito |
| `configure` | `loading modules...` | o plano de módulos para o host, `native` ou `explicit-command` por módulo, e o `CHECKSUMS.txt` de cada diretório de módulo presente | um módulo sem suporte no host, ou um checksum divergente, interrompe (exit 2) |
| `wire-suggest` | `wiring suggestions...` | o bloco a colar: linhas de plugin para Claude Code, linhas do instalador de módulos para Codex CLI e para módulos explicit-command, o comando de política como configurado | nada; ele nunca escreve |
| `smoke` | `verifying evidence...` | quatro controles: classificador de política, grafo de capacidades, log de eventos, benchmark em `k=1` | um controle reprovado põe exit 1 e se nomeia |

### Plano, depois `--apply`

1. **Plano.** O agente roda `python -m hpp init --target <projeto> --non-interactive --no-animation`
   (a partir de um clone deste repositório) ou `hpp init --target <projeto> --non-interactive --no-animation`
   (a partir de uma instalação por pip). Modo plano é o default: nada é escrito, o alvo tem os
   mesmos arquivos depois, exit 0.
2. **Tradução.** O agente cola na conversa o bloco de confirmação (molde abaixo): o que o
   `detect` viu, as três respostas e de onde cada uma veio, a linha de prontidão com o que foi e
   o que não foi verificado, e o bloco de wiring.
3. **Confirmação humana.** O humano responde em linguagem natural — "pode aplicar", "aplica",
   "sim". Qualquer coisa que não seja confirmação clara = não aplica. Se o humano quiser outra
   resposta (outro host, `enforce` em vez de `audit`, uma lista explícita de módulos), o agente
   roda o plano de novo com `--host`, `--bundle`, `--policy-mode` ou `--modules` e pergunta outra vez.
4. **Apply.** O agente re-invoca o MESMO comando com `--apply`. Exatamente um arquivo é escrito,
   `.hpp/profile.json` dentro do alvo; a linha de abertura diz `written` e a linha de prontidão
   ganha um item verificado:

```text
> mounting profile...         ✓ written · host=claude-code · bundle=reliable-coding · policy=audit

  ██████████████████░░  10/11 verified · 1 not verified · 0 failed
    ✓ profile recorded        .hpp/profile.json written
    · host wiring             not verified — manual gate — paste the block, then run doctor

  APPLIED  1 file(s) written inside the target
    .hpp/profile.json    written      host=claude-code · bundle=reliable-coding · policy=audit
```

5. **Wiring, pelo humano.** O agente mostra o bloco de wiring como impresso e **o humano cola**:
   linhas `/plugin marketplace add` e `/plugin install` no Claude Code, linhas do instalador de
   módulos no Codex CLI e para módulos explicit-command. O `hpp init` nunca edita `settings.json`,
   hooks ou `AGENTS.md`; o wiring do host continua `not verified` até o humano tê-lo feito.

Rodar o mesmo comando de novo é seguro: o `detect` reporta `re-run · 1 existing item(s) preserved`
e o `profile` reporta `unchanged`. Respostas diferentes contra um profile gravado são um
`conflict`: as chaves divergentes são nomeadas, nada é sobrescrito, exit 1.

```text
> mounting profile...         ! conflict · host=claude-code · bundle=reliable-coding · policy=enforce

  PROBLEMS  what was measured, what was expected, what to do
    ✗ profile  [profile]
        measured: existing .hpp/profile.json differs in: policy_mode
        expected: the same answers as the recorded profile
        └ re-run with the recorded answers, or remove .hpp/profile.json to initialise again (nothing was overwritten)
```

### Prontidão por canal

A prontidão conta checagens que rodaram, cada uma com o comando que a reproduz. O que ela
consegue verificar depende de onde o `hpp` roda, e o agente diz qual canal usou. A partir de um
clone deste repositório — diretórios de módulo, `CHECKSUMS.txt` e `marketplace.json` ao lado do
manifesto — um plano contra um alvo vazio mostra:

```text
> detecting host...           ✓ greenfield · 0 existing item(s) preserved
> checking prerequisites...   ✓ python 3.14.3 · protocol 2.1
> mounting profile...         ✓ would-write · host=claude-code · bundle=reliable-coding · policy=audit · 3 default(s)
> loading modules...          ✓ 6 modules · reliable-coding · claude-code · 6/6 checksums verified
> wiring suggestions...       ✓ 7 commands to paste · 0 files written
> verifying evidence...       ✓ policy · graph · events · benchmark
> protocol online.

  READINESS  every line is a check that ran; the command below it reproduces it
  ████████████████░░░░  9/11 verified · 2 not verified · 0 failed
```

Os dois não verificados são o profile (só plano) e o wiring do host (um colar). A partir de uma
instalação por pip, que carrega o harness, o manifesto e a suíte de benchmark, mas nenhum
diretório de módulo e nenhum `marketplace.json`, o mesmo plano mostra `7/11 verified · 4 not verified`:
a integridade da distribuição e os checksums dos módulos são reportados como não verificados
porque não há contra o que medi-los, nunca como aprovados. O agente cita a linha que obteve, não
a linha que esperava.

### Flags

| Flag | Efeito |
|---|---|
| `--target <dir>` | o projeto a inicializar (default: diretório atual) |
| `--apply` | escreve `.hpp/profile.json`; sem ela, só plano |
| `--host`, `--bundle`, `--policy-mode audit\|enforce` | respondem às três perguntas; `--modules a,b` substitui o bundle por uma lista explícita |
| `--profile answers.json` | as mesmas respostas a partir de um arquivo (chaves `host`, `bundle`, `policy_mode`, `modules`; chave desconhecida é erro de uso) |
| `--yes`, `--non-interactive`, `--json`, ou `CI` no ambiente | nenhum prompt é alcançado; perguntas sem resposta tomam o default e o relatório diz isso |
| `--no-animation` | saída simples; `NO_COLOR` é respeitado; sem TTY a saída é completa e sem cor |
| `--no-benchmark` | pula o controle de benchmark no smoke; ele é reportado como não verificado, não descartado em silêncio |
| `--marketplace <slug>` | o slug usado no bloco de wiring do Claude Code, para forks |
| `--json` | o mesmo relatório em JSON (`schema: hpp.init-report/v1`), com `exit_code`, `readiness` e o detalhe de cada estágio — para CI e para agentes |

### Códigos de saída

| Código | Significado | Exemplo medido |
|---|---|---|
| `0` | plano ou apply concluído; todo controle que rodou passou | os planos citados acima |
| `1` | um aviso: um controle do smoke reprovou, ou o profile gravado conflita com as respostas dadas | `--policy-mode enforce` sobre um profile gravado com `audit` |
| `2` | uma recusa bloqueante: Python abaixo de 3.10, divergência manifesto/marketplace, módulo sem suporte no host, checksum divergente, id de módulo desconhecido | `--host codex --modules claude-dev-kit` → `loading modules... ✗ bundle custom requires claude-dev-kit, unsupported on codex` |
| `3` | um erro de uso na própria invocação | um arquivo `--profile` com chave desconhecida → `hpp init: profile file has unknown keys: colour (allowed: bundle, host, modules, policy_mode)` |

Com `--json`, o código que o processo vai devolver também está dentro do relatório (`exit_code`),
e um estágio que interrompeu a execução deixa os seguintes como `not run`.

### O que o agente diz (molde)

O texto que o agente cola na conversa ao apresentar um plano do `hpp init`. Placeholders em `{}`.
O molde está escrito em inglês; o agente fala na língua do humano e adapta as palavras, não a
estrutura.

```
I ran `hpp init` in plan mode against {target} -- nothing has been written. Summary:

**Project diagnosis:** {greenfield | in-progress, preserving: {list} | re-run, profile already recorded}.
**Answers:** host={host} ({flag|profile|default}) · bundle={bundle} ({source}) · policy={policy_mode} ({source}).
**Readiness:** {n}/11 verified · {m} not verified · {f} failed -- not verified: {items}.
  ({channel}: {clone of the repository | pip install}; the two extra items a pip install cannot measure are distribution integrity and module checksums.)
**What --apply would do:** write exactly one file, {target}/.hpp/profile.json.
**Wiring (settings/hooks/plugins):** never automatic. After the apply I bring you the wire block as printed and YOU paste it.

If this is fine, say "apply it" and I run the same command with --apply.
```

## Caminho 2 — o instalador de módulos (`kit_doctor.py`)

As linhas que o `hpp init` imprime no bloco de wiring para o Codex CLI, e para módulos
explicit-command no Claude Code, são este instalador. Ele copia um módulo por vez para dentro do
alvo e roda os smokes declarados do módulo; planeja primeiro e aplica só numa segunda invocação
explícita.

### A jornada em 5 passos (igual nos 4 cenários)

1. **Plano.** O agente roda `python installers/kit-forge-1.4.1/kit_doctor.py install --kit <dir-do-módulo> --host <host> --target <projeto> --human`
   (`--human` escolhe o relatório legível). Modo plano é o default: nenhuma escrita acontece,
   exit 0.
2. **Tradução.** O agente cola na conversa o bloco de confirmação (molde na seção "Bloco de
   confirmação" abaixo): o que o `detect` viu, o que o `--apply` faria, o que ficou pendente de
   decisão, e o resultado do smoke.
3. **Confirmação humana.** O humano responde em linguagem natural — "pode aplicar", "aplica",
   "sim". Qualquer coisa que não seja confirmação clara = não aplica.
   Se o humano quiser mudar uma resposta de pergunta (`questions:`), o agente escreve um arquivo
   `--answers` e roda o plano DE NOVO antes de pedir confirmação outra vez.
4. **Apply.** O agente re-invoca o MESMO comando com `--apply`. O instalador aplica o profile,
   roda o smoke de verdade e registra a instalação no registry.
5. **Relato + wiring manual.** O agente mostra a saída real do apply. Se o `wire-suggest`
   listou opções (plugin / bloco de settings), o agente apresenta o conteúdo exato e **o humano
   cola/aciona** — mutar `settings.local.json`/hooks é gate humano, sempre, mesmo depois do
   `--apply`.

### O que muda entre os 4 cenários

Tudo abaixo usa saída REAL do `kit_doctor.py`, que imprime em português. As saídas de
in-progress/re-run/falha foram capturadas contra uma fixture mínima (`demo-kit`) — mesma
estrutura de report, módulo de exemplo.

#### 1. `greenfield` — projeto novo

```
  ✓ detect
      classification=greenfield · new project — no previous config detected
```

O que o agente enfatiza: **não há nada a preservar**; o plano é o caminho feliz.
A decisão pedida ao humano é uma só: "o que o `--apply` faria está ok?".
Exemplo completo end-to-end na última seção deste caminho.

#### 2. `in-progress` — projeto com config existente

```
  ✓ detect
      classification=in-progress · project in progress — existing config detected (it will be preserved)
      já existe (não será tocado): .claude/settings.local.json: statusLine/hooks já configurados
```

O que muda na conversa: o agente lista **item por item o que já existe e será preservado** —
essa é a informação que tira o medo de instalar por cima. O profile nunca sobrescreve
(`skip-exists` é reportado, não silencioso). Se o humano QUISER substituir algo existente, isso é
uma ação manual dele, fora do instalador.

#### 3. `re-run` — mesmo par módulo+target já instalado antes

```
  ✓ detect
      classification=re-run · reinstall — this kit+target pair is already in the registry
      já existe (não será tocado): profile.yaml presente (customizado)
  ...
  ✓ profile
      já existe, preservado: profile.example.yaml -> profile.yaml
```

O que muda na conversa: o agente diz explicitamente que **rodar de novo é seguro e idempotente**
— nada duplica, customização é preservada. Re-run é o jeito normal de (a) verificar uma
instalação antiga e (b) atualizar após puxar uma versão nova do módulo.
A pergunta ao humano vira: "quer re-aplicar mesmo assim, ou só queria conferir?".

#### 4. Falha de smoke — o módulo reprovou no próprio self-test

```
  ⚠ smoke  [FAIL]
      self-tests: 1 ok · 0 sem suporte (ignorados)
      ⚠ FALHOU: scripts\bad_tool.py (exit 1)

RESULTADO: smoke FALHOU — não aplique este kit antes de corrigir os self-tests acima.
Depois de corrigir, rode o plano de novo para confirmar antes do --apply.
```

Exit code = 1. O que muda na conversa: **o agente NÃO oferece o `--apply`.** Ele reporta qual
script falhou, com exit code, e propõe o próximo passo (investigar o script, verificar
integridade com `kit_doctor.py verify <dir-do-módulo>`, ou baixar o módulo de novo). Só volta a
oferecer aplicação depois de um plano novo sair limpo. Um humano que insiste em aplicar com smoke
falhando está por conta própria — o agente registra que desaconselhou e por quê.

### Perguntas (`questions:`) na conversa

A maioria dos módulos não tem perguntas (por design). Quando tem, o plano mostra:

```
  ✓ configure
      sem resposta (default assumido): modo
      para responder de verdade: repetir com --answers <arquivo.json|yaml>
```

Fluxo do agente: (1) apresenta cada pergunta pendente com o default em destaque — "vou usar
`full`, a menos que você prefira `lite`"; (2) se o humano escolher algo diferente do default, o
agente escreve um `answers.json` e roda o plano de novo com `--answers answers.json`; (3) só
então pede confirmação. Instalar sem responder nada nunca trava — default sempre resolve.

### Bloco de confirmação (molde)

O texto que o agente cola na conversa ao apresentar um plano de módulo. Placeholders em `{}`. As
linhas marcadas `[cenário]` só entram no cenário correspondente. O molde está escrito em inglês;
o agente fala na língua do humano e adapta as palavras, não a estrutura.

```
I ran the {kit} installer in plan mode -- nothing has been written yet. Summary:

**Project diagnosis** ({target}):
[greenfield]   New project -- no previous config detected.
[in-progress]  Project in progress. The installer detected and will PRESERVE:
[in-progress]  {existing_config list, one per line}
[re-run]       This module was installed in this project before (it is in the registry).
[re-run]       Re-applying is safe: nothing is duplicated, your customisation is preserved.

**What --apply would do:**
- {profile actions: "copy profile.example.yaml -> profile.yaml" | "nothing to copy (already exists, preserved)"}
- record the installation in ~/.claude-kits/registry.json

**Module questions:** {"none" | "pending, using default: {id}={default} -- want to change it?"}

**Wiring (settings/hooks):** never automatic. After the apply I bring you the exact block
({paths suggested by wire-suggest}) and YOU decide whether to paste it.

**Smoke (module self-tests):** {N} ok, {N} ignored{" -- ALL passed" | see the failure block below}.

[if smoke ok]   If this is fine, say "apply it" and I run:
[if smoke ok]     python kit_doctor.py install {kit_dir} --target {target_dir} --apply
[if smoke fail] The smoke FAILED: {file} (exit {N}). I do NOT recommend applying.
[if smoke fail] Next step: {investigate the script | run kit_doctor.py verify {kit_dir}}.
[if smoke fail] Once that is fixed, I run the plan again and bring you the result.
```

### Exemplo end-to-end (greenfield, execução real)

Módulo: `operator-kit-1.5.0`. Comando que o agente rodou (saída real abaixo). Esta captura é
datada: ela é anterior ao caminho versionado do instalador. Na distribuição atual o módulo é o
`operator-kit-1.5.0` e o instalador vive em `installers/kit-forge-1.4.1/kit_doctor.py`; os
estágios, as flags (`--target`, `--host`, `--answers`, `--apply`, `--human`) e a forma da saída
são os mesmos.

```
$ python installers/kit-forge-1.4.1/kit_doctor.py install frameworks/operator-kit-1.5.0 \
    --target frameworks/operator-kit-1.5.0 --human

INSTALL PLAN — operator-kit-1.5.0  (dry run: nothing was written)
  target: frameworks\operator-kit-1.5.0
  host:   claude-code

  ✓ detect
      classification=greenfield · new project — no previous config detected
  ✓ prereqs
  ✓ profile
      would copy: profile.example.yaml -> operator-profile.yaml
  ✓ configure
  ✓ wire-suggest
      opção [plugin]: /plugin marketplace add . && /plugin install <nome>@<marketplace>
      opção [doc]: seguir SETTINGS-WIRE.md
      (nenhuma é executada automaticamente — mexer em settings/hooks é decisão humana)
  ✓ smoke
      self-tests: 27 ok · 0 sem suporte (ignorados)

Nada foi modificado. Se o plano está de acordo, aplique com:
  python kit_doctor.py install frameworks\operator-kit-1.5.0 --target frameworks\operator-kit-1.5.0 --apply
```

O que o agente diz ao humano (texto exato, seguindo o molde):

> Rodei o instalador do operator-kit-1.5.0 em modo plano — nada foi escrito ainda. Resumo:
>
> **Diagnóstico do projeto:** projeto novo (greenfield) — nenhuma config prévia detectada,
> nada a preservar.
>
> **O que o --apply faria:**
> - copiar `profile.example.yaml` -> `profile.yaml` (o profile que você vai customizar)
> - registrar a instalação em `~/.claude-kits/registry.json`
>
> **Perguntas do módulo:** nenhuma — este módulo não tem nada configurável na instalação.
>
> **Wiring (settings/hooks):** nunca é automático. Depois do apply, os caminhos são instalar
> como plugin (`/plugin marketplace add .` + `/plugin install`) ou seguir o `SETTINGS-WIRE.md` —
> eu te trago o passo a passo e você decide.
>
> **Smoke (self-tests do módulo):** 27 ok, 0 ignorados — todos passaram.
>
> Se estiver de acordo, me diga "pode aplicar" e eu rodo o mesmo comando com `--apply`.

Humano: **"pode aplicar"**

O agente roda o mesmo comando com `--apply`, cola a saída real (o cabeçalho vira
`INSTALL APPLIED — ... (--apply)`, a linha do profile vira `copied:`, o rodapé confirma
`Install applied and registered. Wiring of settings/hooks (if suggested above) stays manual.`) e fecha com o wiring:

> Aplicado e registrado. Falta só o wiring, que é seu: quer que eu te mostre o bloco do
> `SETTINGS-WIRE.md` para você colar no `settings.local.json`, ou prefere o caminho de plugin?
> Em qualquer um dos dois, quem executa o passo final é você.

## O que o agente NUNCA faz (checklist de conduta)

- [ ] NUNCA roda `--apply` — do `hpp init` ou do `kit_doctor.py` — sem confirmação explícita do humano NESTA conversa
- [ ] NUNCA edita `settings.local.json` / hooks / `AGENTS.md` — apresenta o bloco, o humano cola
- [ ] NUNCA reporta "instalado" sem colar a saída real do `--apply` (exit code incluso)
- [ ] NUNCA reporta uma linha de prontidão que não obteve — cita o canal e a contagem como impressos
- [ ] NUNCA oferece `--apply` quando o smoke falhou (exit 1) — corrige primeiro
- [ ] NUNCA responde as perguntas do módulo sozinho quando o humano expressou preferência —
      escreve `--answers` e re-planeja
- [ ] Em re-run, SEMPRE diz que é idempotente antes de pedir confirmação
