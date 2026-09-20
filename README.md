<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/hpp-banner-dark.svg">
    <img alt="House Party Protocol — dez kits para Claude Code" src="assets/hpp-banner-light.svg" width="100%">
  </picture>
</p>

<p align="center">
  <a href="LICENSE"><img alt="MIT" src="https://img.shields.io/badge/licen%C3%A7a-MIT-0000FF"></a>
  <a href="#os-dez-kits"><img alt="10 kits" src="https://img.shields.io/badge/kits-10-FF00FF"></a>
  <img alt="Claude Code plugin marketplace" src="https://img.shields.io/badge/Claude%20Code-plugin%20marketplace-0B0B12">
  <img alt="macOS · Linux · Windows" src="https://img.shields.io/badge/macOS%20%C2%B7%20Linux%20%C2%B7%20Windows-portável-59636E">
</p>

# House Party Protocol

**An agent harness where nothing ships without a second measurement.**

Dez kits instaláveis para Claude Code. Cada um resolve um problema que aparece quando você
para de conversar com um agente e passa a **operar** vários.

> O revisor roda em outro modelo e **não tem ferramenta de escrita**.
> Ou o checker tem `Write`, ou não tem — e isso é verificável.

```bash
/plugin marketplace add rushar-labs/house-party-protocol
/plugin install operator-kit@house-party-protocol
```

---

## A história

Este projeto nasceu dentro de uma agência operada por agentes de IA, onde várias sessões
trabalham em paralelo sobre o mesmo repositório, todos os dias. A velocidade veio rápido.
A confiança, não.

O que se acumulou foram as falhas silenciosas: o agente que disse "pronto" sobre um teste
que nunca rodou; o `grep` que devolveu zero porque abortou, não porque não havia nada; duas
sessões que editaram o mesmo arquivo com a melhor das intenções; o revisor que "consertou e
seguiu" — e com isso apagou a única evidência de que o processo estava furado.

Cada uma dessas falhas virou uma regra. Cada regra virou um gate. Cada gate nasceu com o
teste que o força a reprovar. Quando o conjunto ficou grande demais para caber num único
projeto, ele foi cortado em kits — cada um cobrindo um buraco que o outro não cobre, todos
passando pela mesma forja e pelo mesmo linter de publicação.

**O nome.** Em *Iron Man 3*, o House Party Protocol é a ordem que chama **todas** as armaduras
de uma vez — cada uma com um papel, nenhuma decorativa, e só quando o operador dá a palavra.
É o que este marketplace é: dez kits que chegam juntos, e nenhum deles decide sozinho o que
só o humano decide.

O que o projeto acredita está escrito no [`MANIFESTO.md`](MANIFESTO.md).

---

## Instalar

Pelo marketplace de plugins do Claude Code:

```bash
/plugin marketplace add rushar-labs/house-party-protocol
/plugin install operator-kit@house-party-protocol
```

Ou por cópia, sem plugin — cada kit traz `install/kit.install.yaml` e o instalador imprime
o plano antes de aplicar:

```bash
python instaladores/kit-forge-1.4.0/kit_doctor.py install --kit <caminho-do-kit>   # imprime o plano
python instaladores/kit-forge-1.4.0/kit_doctor.py install --kit <caminho-do-kit> --apply
```

**Portabilidade.** Os hooks de cada kit rodam via `hooks/pyrun.sh` (bash), que escolhe o
Python do projeto (`.venv`), depois `python3`, depois `python` — macOS, Linux e Windows
(Git Bash) sem alias nenhum. Nos comandos escritos nesta documentação, leia `python` como
"o seu Python 3" (`python3` no macOS).

---

## Os dez kits

| kit | versão | o que resolve |
|---|---|---|
| **operator-kit** | 1.3.0 | A camada portátil: verdade-antes-de-done, execução autônoma com guardrail, planejamento spec-driven, paralelismo com teto. Config-driven por um `profile.yaml` (autonomia × intensidade). Traz o loop `/ralph-gate`, o ledger de dívida técnica, 13 regras como doutrina instalável e o gerador de `CLAUDE.md` a partir do perfil (`claude-md-from-profile`). |
| **kit-forge** | 1.4.0 | A fábrica. Monta kits a partir de manifesto, com `ip_pii_linter` (gate de IP/PII), `guard_origins`, `skill_lint` e `kit_doctor` de 6 estágios. É também o gate que decide o que pode sair de casa. |
| **lane-kit** | 1.2.0 | N sessões sem colisão. Board com estado `CLAIMED → BUILDING → CHECKPOINT-READY → UNDER-REVIEW → VERIFIED/NEEDS-FIX → MERGED`, maker ≠ checker cross-model obrigatório, lock por diretório. Depende do `continuity-kit`. |
| **continuity-kit** | 1.2.1 | A sessão sobrevive a parada, `/clear` ou crash sem perder o próximo passo. Handoff com comando de re-derivação e de verificação-primeiro embutidos. |
| **claude-dev-kit** | 1.3.1 | Ferramentas de construir ferramentas: `skill-writer`, `hookify`, `plugin-dev`, `teaching`. Wiring idempotente com `--undo`. |
| **health-kit** | 1.3.1 | Sonda de serviço config-driven, com segmento de statusline cache-first. Doutrina embarcada: *health de SERVIÇO ≠ health de DADO*. |
| **dev-squad-kit** | 1.0.0 | 12 agentes de papel via slash-command, mais 3 skills de leitura e consolidação paralela token-safe. |
| **agent-framework-wizard** | 1.1.1 | Wizard de 6 passos para gerar o esqueleto de um agente ou skill novo. Modo não-interativo e `--demo`. |
| **supabase-pack** | 1.1.0 | Auditoria de RLS de verdade (via `pg_policies` + advisors) e scaffold de Edge Function. |
| **gotcha-memory** | 1.0.0 | A falha vira lição. Postflight registra cada comando que falha, classificado por família; recorrência vira um **gotcha**, e o preflight injeta a lição ANTES da próxima execução da mesma tarefa. Detecção conservadora — ambíguo não é falha. WARN-only. |

---

## Por que existe

A maior parte do ferramental de agente resolve *velocidade*. Este resolve *confiança* — e a
diferença aparece no dia em que o agente diz "pronto" e não está.

Quatro decisões de projeto atravessam os dez kits:

**1 · O revisor não tem caneta.** Quem constrói não aprova, e quem aprova roda em outro
modelo com `allowedTools` sem `Write` nem `Edit`. Não é uma instrução no prompt — é a
ausência da ferramenta. Se o checker pudesse editar, ele consertaria e seguiria, e o defeito
de processo nunca apareceria.

**2 · A régua ao lado do número.** Nenhum número é publicado sem o comando que o produziu.
Um relatório que diz "18 testes passando" sem o comando é uma afirmação sobre a memória de
alguém, não sobre o repositório.

**3 · O controle antes do veredito.** Antes de declarar algo morto, zero ou ausente, aponte
o mesmo instrumento para um caso que você sabe estar vivo. Se ele também disser "morto", o
instrumento não discrimina — e o veredito não vale.

**4 · O gate prova que sabe reprovar.** Todo gate nasce com um teste que o força a falhar
sobre o caso que ele existe para barrar. Um teste que só exercita o caminho feliz não
distingue "gate funcionando" de "gate ausente" — os dois passam igual.

---

## Os três contratos

O que separa um kit de uma pasta de scripts está escrito, e é verificável por lint:

| contrato | o que impõe | quem verifica |
|---|---|---|
| [`INSTALL-CONTRACT.md`](INSTALL-CONTRACT.md) | 6 estágios em ordem fixa (`detect → prereqs → profile → configure → wire-suggest → smoke`), fluxo plano→`--apply`, proibido `input()` bloqueante, `wire-suggest` nunca escreve em settings | `kit_doctor install` |
| [`SKILL-CONTRACT.md`](SKILL-CONTRACT.md) | 6 cláusulas: header, contrato de I/O, ≥3 exemplos **executados** com saída real colada (≥1 de falha, expirando em 90 dias), prova em <5s sem rede, portabilidade, corpo executável | `tools/skill_lint.py` |
| [`INSTALL-GUIDE-TEMPLATE.md`](INSTALL-GUIDE-TEMPLATE.md) | as 9 seções obrigatórias do README de cada kit, incluindo a seção 8 (prova com saída real, nunca inventada) e a 9 (desfazer) | revisão + lint futuro |

Contrato de saída, único em toda a família: **`0` ok/no-op · `1` warn · `2` block · `3` erro.**
Não existe `--skip-lint`.

---

## Documentação

- [`MANIFESTO.md`](MANIFESTO.md) — o que o projeto acredita, em oito princípios
- [`docs/MANUAL.html`](docs/MANUAL.html) — o manual da forja, com mini-curso de 6 módulos
- [`docs/CATALOGO.md`](docs/CATALOGO.md) — o que cada kit instala, recurso por recurso (skills, commands, hooks, rules, templates, scripts)
- [`docs/CATALOGO.html`](docs/CATALOGO.html) — o mesmo catálogo, navegável
- [`docs/UX-INSTALL-JOURNEY.md`](docs/UX-INSTALL-JOURNEY.md) — a jornada de instalação e os 3 papéis (instalador, agente, humano)
- [`CHANGELOG.md`](CHANGELOG.md) — as versões publicadas

---

## Verificar uma instalação

Cada kit traz `CHECKSUMS.txt` com sha256 por arquivo e um `SANITIZACAO.md` declarando o que
foi retirado antes de publicar.

```bash
cd <kit>
tr -d '\r' < CHECKSUMS.txt | sha256sum -c
```

> O `tr -d` não é enfeite: em checkout com CRLF o `sha256sum -c` anexa `\r` ao nome do
> arquivo, procura um arquivo que não existe, e devolve **FAILED com exit 0** — verificação
> nenhuma, com cara de verificação feita.

---

## Atribuição

Alguns kits adaptam trabalho de terceiros, sempre com licença compatível e origem declarada
no README do kit — notadamente material do [ECC](https://github.com/affaan-m/ECC) (MIT) no
`health-kit` (dashboard-builder) e no `claude-dev-kit` (architecture-decision-records,
skill-scout, search-first).

Código vendorizado dentro de um kit (`_lib/`) carrega a origem no cabeçalho do arquivo.

---

## Autor

House Party Protocol é feito por **Max Parisi** na **Rushar Labs** — o braço de engenharia de
agentes da [Rushar](https://rushar.com.br), Porto Alegre.

- Site: [rushar.com.br](https://rushar.com.br)
- GitHub: [rushar-labs](https://github.com/rushar-labs)
- Segurança: ver [`SECURITY.md`](SECURITY.md) · Contribuir: ver [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Citar: [`CITATION.cff`](CITATION.cff) (o GitHub mostra o botão *Cite this repository*)

Se este projeto lhe poupou uma noite, um link de volta já é o crédito que a licença pede.

## Licença

MIT — ver [`LICENSE`](LICENSE). Copyright © 2026 Max Parisi (Rushar Labs).
A licença MIT exige uma coisa só de quem redistribui: **manter o aviso de copyright**. É
assim que o crédito viaja com o código — ver [`NOTICE`](NOTICE).

<p align="center"><sub>Rushar Labs · Ideias · Sistemas · Pessoas · Impacto — <em>Construindo o que vem depois.</em></sub></p>
