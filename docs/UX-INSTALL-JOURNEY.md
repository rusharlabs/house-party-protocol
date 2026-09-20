# UX-INSTALL-JOURNEY — a jornada canônica de instalação de um kit, contada na conversa

> **Versão:** 1.0.0 — camada de apresentação sobre contrato congelado.
> **Irmão de:** `INSTALL-CONTRACT.md` (a mecânica dos 6 estágios) e `INSTALL-GUIDE-TEMPLATE.md`
> (o molde do README por-kit). Este documento descreve a EXPERIÊNCIA: como um AGENTE
> (Claude Code) guia um HUMANO pela instalação, numa conversa.
> Nada aqui muda a mecânica — se este doc contradisser `INSTALL-CONTRACT.md`, o contrato vence.

## Princípio

```
O HUMANO NUNCA VÊ UM PROMPT DE TERMINAL. ELE VÊ UMA CONVERSA.
O agente roda o plano, traduz o plano em português, e espera o humano dizer
"pode aplicar" em linguagem natural. Só então re-invoca com --apply.
Não existe input() em lugar nenhum — o "Confirm" é a dupla invocação.
```

Três papéis, sem sobreposição:

| Papel | Faz | Nunca faz |
|---|---|---|
| **kit_doctor.py** | executa os 6 estágios; em modo plano, zero escrita | pergunta em stdin; escreve settings/hooks |
| **agente** | roda comandos, traduz o plano, pede confirmação, reporta com saída real | aplica sem confirmação; edita `settings.local.json`/hooks por conta própria |
| **humano** | lê o plano na conversa, decide, confirma em linguagem natural | precisa decorar flags — o agente carrega o comando |

## A jornada em 5 passos (igual nos 4 cenários)

1. **Plano.** O agente roda `python kit_doctor.py install <kit> --target <projeto> --human`.
   Modo plano é o default: nenhuma escrita acontece, exit 0.
2. **Tradução.** O agente cola na conversa o bloco de confirmação (template na seção
   "Bloco de confirmação" abaixo): o que o `detect` viu, o que o `--apply` faria, o que
   ficou pendente de decisão, e o resultado do smoke.
3. **Confirmação humana.** O humano responde em linguagem natural — "pode aplicar",
   "aplica", "sim". Qualquer coisa que não seja confirmação clara = não aplica.
   Se o humano quiser mudar uma resposta de pergunta (`questions:`), o agente escreve
   um arquivo `--answers` e roda o plano DE NOVO antes de pedir confirmação outra vez.
4. **Apply.** O agente re-invoca o MESMO comando com `--apply`. O instalador aplica
   profile, roda smoke de verdade e registra a instalação no registry.
5. **Relato + wiring manual.** O agente mostra a saída real do apply. Se o
   `wire-sugerido` listou opções (plugin / bloco de settings), o agente apresenta o
   conteúdo exato e **o humano cola/aciona** — mutar `settings.local.json`/hooks é
   gate humano, sempre, mesmo depois do `--apply`.

## O que muda entre os 4 cenários

Tudo abaixo usa saída REAL do `kit_doctor.py`. As saídas de
in-progress/re-run/falha foram capturadas contra uma fixture mínima (`demo-kit`) —
mesma estrutura de report, kit de exemplo.

### 1. `greenfield` — projeto novo

```
  ✓ detect
      classificacao=greenfield · projeto novo — nenhuma config prévia detectada
```

O que o agente enfatiza: **não há nada a preservar**; o plano é o caminho feliz.
A decisão pedida ao humano é uma só: "o que o --apply faria está ok?".
Exemplo completo end-to-end na última seção.

### 2. `in-progress` — projeto com config existente

```
  ✓ detect
      classificacao=in-progress · projeto em andamento — config existente detectada (será preservada)
      já existe (não será tocado): .claude/settings.local.json: statusLine/hooks já configurados
```

O que muda na conversa: o agente lista **item por item o que já existe e será
preservado** — essa é a informação que tira o medo de instalar por cima. O profile
nunca sobrescreve (`skip-exists` é reportado, não silencioso). Se o humano QUISER
substituir algo existente, isso é uma ação manual dele, fora do instalador.

### 3. `re-run` — mesmo par kit+target já instalado antes

```
  ✓ detect
      classificacao=re-run · reinstalação — este par kit+target já consta no registry
      já existe (não será tocado): profile.yaml presente (customizado)
  ...
  ✓ profile
      já existe, preservado: profile.example.yaml -> profile.yaml
```

O que muda na conversa: o agente diz explicitamente que **rodar de novo é seguro e
idempotente** — nada duplica, customização é preservada. Re-run é o jeito normal de
(a) verificar uma instalação antiga e (b) atualizar após puxar uma versão nova do kit.
A pergunta ao humano vira: "quer re-aplicar mesmo assim, ou só queria conferir?".

### 4. Falha de smoke — o kit reprovou no próprio self-test

```
  ⚠ smoke  [FAIL]
      self-tests: 1 ok · 0 sem suporte (ignorados)
      ⚠ FALHOU: scripts\bad_tool.py (exit 1)

RESULTADO: smoke FALHOU — não aplique este kit antes de corrigir os self-tests acima.
Depois de corrigir, rode o plano de novo para confirmar antes do --apply.
```

Exit code = 1. O que muda na conversa: **o agente NÃO oferece o --apply.** Ele
reporta qual script falhou, com exit code, e propõe o próximo passo (investigar o
script, verificar integridade com `kit_doctor.py verify <kit>`, ou baixar o kit de
novo). Só volta a oferecer aplicação depois de um plano novo sair limpo. Um humano
que insiste em aplicar com smoke falhando está por conta própria — o agente registra
que desaconselhou e por quê.

## Perguntas (`questions:`) na conversa

A maioria dos kits não tem perguntas (por design). Quando tem, o plano mostra:

```
  ✓ configure
      sem resposta (default assumido): modo
      para responder de verdade: repetir com --answers <arquivo.json|yaml>
```

Fluxo do agente: (1) apresenta cada pergunta pendente com o default em destaque —
"vou usar `full`, a menos que você prefira `lite`"; (2) se o humano escolher algo
diferente do default, o agente escreve um `answers.json` e roda o plano de novo com
`--answers answers.json`; (3) só então pede confirmação. Instalar sem responder nada
nunca trava — default sempre resolve.

## Bloco de confirmação (template)

O texto que o agente cola na conversa ao apresentar um plano. Placeholders em `{}`.
As linhas marcadas `[cenário]` só entram no cenário correspondente.

```
Rodei o instalador do {kit} em modo plano — nada foi escrito ainda. Resumo:

**Diagnóstico do projeto** ({target}):
[greenfield]   Projeto novo — nenhuma config prévia detectada.
[in-progress]  Projeto em andamento. O instalador detectou e vai PRESERVAR:
[in-progress]  {lista de existing_config, um por linha}
[re-run]       Este kit já foi instalado neste projeto antes (consta no registry).
[re-run]       Re-aplicar é seguro: nada duplica, sua customização é preservada.

**O que o --apply faria:**
- {ações do profile: "copiar profile.example.yaml -> profile.yaml" | "nada a copiar (já existe, preservado)"}
- registrar a instalação em ~/.claude-kits/registry.json

**Perguntas do kit:** {"nenhuma" | "pendentes, usando default: {id}={default} — quer mudar?"}

**Wiring (settings/hooks):** nunca é automático. Depois do apply eu te trago o bloco
exato ({caminhos sugeridos pelo wire-sugerido}) e VOCÊ decide colar.

**Smoke (self-tests do kit):** {N} ok, {N} ignorados{" — TODOS passaram" | ver bloco de falha abaixo}.

[se smoke ok]   Se estiver de acordo, me diga "pode aplicar" e eu rodo:
[se smoke ok]     python kit_doctor.py install {kit_dir} --target {target_dir} --apply
[se smoke fail] ⚠ O smoke FALHOU: {arquivo} (exit {N}). NÃO recomendo aplicar.
[se smoke fail] Próximo passo: {investigar o script | rodar kit_doctor.py verify {kit_dir}}.
[se smoke fail] Corrigido isso, eu rodo o plano de novo e te trago o resultado.
```

## Exemplo end-to-end (greenfield, execução real)

Kit: `operator-kit-1.1.0`. Comando que o agente rodou (saída real abaixo):

```
$ python instaladores/kit-forge/kit_doctor.py install frameworks-com-plugins/operator-kit-1.1.0 \
    --target frameworks-com-plugins/operator-kit-1.1.0 --human

PLANO DE INSTALACAO — operator-kit-1.1.0  (simulação: nada foi escrito)
  target: frameworks-com-plugins\operator-kit-1.1.0
  host:   claude-code

  ✓ detect
      classificacao=greenfield · projeto novo — nenhuma config prévia detectada
  ✓ prereqs
  ✓ profile
      copiaria: profile.example.yaml -> profile.yaml
  ✓ configure
  ✓ wire-sugerido
      opção [plugin]: /plugin marketplace add . && /plugin install <nome>@<marketplace>
      opção [doc]: seguir SETTINGS-WIRE.md
      (nenhuma é executada automaticamente — mexer em settings/hooks é decisão humana)
  ✓ smoke
      self-tests: 27 ok · 0 sem suporte (ignorados)

Nada foi modificado. Se o plano está de acordo, aplique com:
  python kit_doctor.py install frameworks-com-plugins\operator-kit-1.1.0 --target frameworks-com-plugins\operator-kit-1.1.0 --apply
```

O que o agente diz ao humano (texto exato, seguindo o template):

> Rodei o instalador do operator-kit-1.1.0 em modo plano — nada foi escrito ainda. Resumo:
>
> **Diagnóstico do projeto:** projeto novo (greenfield) — nenhuma config prévia detectada,
> nada a preservar.
>
> **O que o --apply faria:**
> - copiar `profile.example.yaml` -> `profile.yaml` (o profile que você vai customizar)
> - registrar a instalação em `~/.claude-kits/registry.json`
>
> **Perguntas do kit:** nenhuma — este kit não tem nada configurável na instalação.
>
> **Wiring (settings/hooks):** nunca é automático. Depois do apply, os caminhos são
> instalar como plugin (`/plugin marketplace add .` + `/plugin install`) ou seguir o
> `SETTINGS-WIRE.md` — eu te trago o passo a passo e você decide.
>
> **Smoke (self-tests do kit):** 27 ok, 0 ignorados — todos passaram.
>
> Se estiver de acordo, me diga "pode aplicar" e eu rodo o mesmo comando com `--apply`.

Humano: **"pode aplicar"**

O agente roda o mesmo comando com `--apply`, cola a saída real (header vira
`INSTALACAO APLICADA — ... (--apply)`, profile vira `copiado:`, rodapé confirma
`Instalação aplicada e registrada.`) e fecha com o wiring:

> Aplicado e registrado. Falta só o wiring, que é seu: quer que eu te mostre o bloco
> do `SETTINGS-WIRE.md` para você colar no `settings.local.json`, ou prefere o caminho
> de plugin? Em qualquer um dos dois, quem executa o passo final é você.

## O que o agente NUNCA faz (checklist de conduta)

```
[ ] NUNCA roda --apply sem confirmação explícita do humano NESTA conversa
[ ] NUNCA edita settings.local.json / hooks — apresenta o bloco, humano cola
[ ] NUNCA reporta "instalado" sem colar a saída real do --apply (exit code incluso)
[ ] NUNCA oferece --apply quando o smoke falhou (exit 1) — corrige primeiro
[ ] NUNCA responde perguntas do kit sozinho quando o humano expressou preferência —
    escreve --answers e re-planeja
[ ] Em re-run, SEMPRE diz que é idempotente antes de pedir confirmação
```
