[English](README.md) · [Português](README.pt-BR.md)

# Kit Forge

O gate de IP/PII + o montador de kits deste marketplace, e o **instalador de todos os
outros módulos**. `ip_pii_linter.py` (varre nomes de cliente/infra internos antes de
qualquer coisa virar público), `kit_assembler.py` (monta um kit a partir de um manifesto
declarativo + a fonte, com `guard_origins` integrado — aborta se a fonte mudar no meio da
montagem), `kit_doctor.py` (verify/install/registry/marketplace — o motor único de
instalação de todo o marketplace, 6 estágios), `wire_settings.py` (merge idempotente em
`settings.local.json`), `install_git_hook.py` (encadeia com `pre-commit` alheio),
`tools/skill_lint.py` (o linter que cobra o SKILL-CONTRACT das skills de outros kits),
`tools/browse.py` (menu interativo do marketplace), `tools/catalog_md.py` (catálogo
bilíngue de módulos derivado da árvore emitida) e `tools/codex_skills.py` (instala um kit
no layout que o Codex CLI descobre). Contrato único de exit em tudo: `0 ok/no-op`,
`1 warn`, `2 block`, `3 erro`. Sem `--skip-lint` em nenhuma ferramenta — o gate de IP/PII
é sempre obrigatório.

## Pré-requisitos + APIs externas

| Requisito | Versão mínima | Obrigatório? |
|---|---|---|
| Python | 3.8 | sim |
| PyYAML | qualquer | sim — `kit_assembler.py`/`ip_pii_linter.py`/`wire_settings.py` parseiam manifesto/ruleset/spec com ela; a função central dessas 3 ferramentas depende dela |

Serviços externos: **nenhum — stdlib + PyYAML, só toca filesystem local.**

## Instalar via plugin

O Kit Forge **é** um plugin: o `.claude-plugin/plugin.json` viaja no módulo emitido
declara nome, versão, descrição e keywords, e o `marketplace.json` da raiz da distribuição
o lista em `installers`.

```bash
/plugin marketplace add rusharlabs/house-party-protocol
/plugin install kit-forge@house-party-protocol
```

O que o plugin entrega são as **ferramentas, num caminho estável**: `${CLAUDE_PLUGIN_ROOT}`
resolve para o módulo instalado, então o agente roda
`python "${CLAUDE_PLUGIN_ROOT}/kit_doctor.py" ...` ou
`python "${CLAUDE_PLUGIN_ROOT}/tools/skill_lint.py" ...` sem saber onde o marketplace foi
clonado. Ele **não traz skills, commands nem hooks auto-armados** — o manifesto não tem as
chaves `skills`/`commands`/`hooks`, e não existe `hooks/hooks.json`. O
`hooks/guard_origins.py --hook` é um guard `PreToolUse` opcional (bloqueia escrita nos
caminhos de origem que você listar) que você arma manualmente, se quiser.

## Instalar por cópia

Na distribuição emitida este módulo vive em `installers/kit-forge-1.4.2/` (o diretório
carrega a versão — declare-a uma vez, em `KIT`). Ele se instala com o próprio
`kit_doctor.py`, rodado da raiz da distribuição; planeja primeiro, só escreve com `--apply`:

```bash
KIT=installers/kit-forge-1.4.2
cp -r "$KIT" ../your-repo/kit-forge             # the copy itself (kit_doctor does not copy on claude-code)
python installers/kit-forge-1.4.2/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo
python installers/kit-forge-1.4.2/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo --apply
# Codex CLI: --host codex — the installer copies the module into .agents/hpp/kit-forge; no cp -r needed
```

## O que o instalador detecta

O estágio `detect` classifica o alvo (só leitura) com exatamente estes três rótulos:

```
greenfield    -> no prior config in the target; profile stage would copy ip-ruleset.example.yaml -> ip-ruleset.yaml
                 (the real ruleset belongs to the BUSINESS that uses kit-forge, not to this kit — fill it in)
in-progress   -> .claude/ exists, or settings(.local).json already has hooks/statusLine, or ip-ruleset.yaml
                 is already present, or the repo has more than 3 commits: reported, never overwritten (skip-exists)
re-run        -> this kit+target pair is already in the registry (~/.claude-kits/registry.json)
```

## O que é seguro rodar de novo

`wire_settings.py` é idempotente e byte-estável (rodar duas vezes não duplica). O
`ip-ruleset.yaml` real (com nomes de cliente/porta/domínio do SEU negócio) nunca é
sobrescrito automaticamente por nenhuma ferramenta aqui — só você edita.
`kit_assembler.py` sempre monta num diretório de saída novo (nunca escreve por cima do
kit já emitido em produção sem você apontar `--out` explicitamente).

## Wiring manual

Nenhum obrigatório — o kit não tem `hooks/hooks.json`. É uma coleção de ferramentas de
linha de comando invocadas sob demanda (ex.: por um cron de CI, ou manualmente antes de
publicar um kit novo). O único wiring opcional é o `hooks/guard_origins.py --hook` como
guard `PreToolUse`, e esse é um colar humano no `settings.local.json`.

## Configurar o ruleset de IP/PII (o passo real antes de montar qualquer kit)

```bash
cp ip-ruleset.example.yaml ip-ruleset.yaml
# edit ip-ruleset.yaml with the REAL client/infra names of your business
python ip_pii_linter.py --self-test
```
`ip-ruleset.example.yaml` é neutro (pode compor um kit distribuído); `ip-ruleset.yaml`
real (com nomes reais) **nunca** sai num kit montado — fica fora do manifesto de
qualquer `kit_assembler.py`.

## Prova / aceite (saída real, executada)

```bash
python kit_doctor.py --self-test
```
```
self-test OK — verify (ok/warn/corrupt/error) + positional compat + install (6 stages: detect/prereqs/profile/configure/wire/smoke, plan-first/--apply, --answers, re-run) + registry (kit+target, no duplicates) + render_plan + marketplace (out-of-place/version-mismatch + control)
```
<!-- executado: 2026-09-21 · exit=0 -->

```bash
python ip_pii_linter.py --self-test
```
```
self-test OK — 17 findings across 16 distinct rules
```
<!-- executado: 2026-09-21 · exit=0 -->

```bash
python wire_settings.py --self-test
```
```
self-test OK — wire idempotent, conflict without --force preserved, --force overwrites, --undo byte-identical, a crash mid-write does not truncate, a concurrent write is refused (exit 2)
```
<!-- executado: 2026-09-21 · exit=0 -->

## Desfazer

```
- Plugin:  /plugin uninstall kit-forge@house-party-protocol
- Copy:    remove the kit-forge/ folder from the project (nothing else to revert — this kit
           touches no wiring/settings by itself)
- ip-ruleset.yaml: delete it by hand if you no longer want to lint this business
```

## Documentação estendida

- `INSTALL-CONTRACT.md` (raiz da distribuição) — o contrato completo dos 6 estágios de
  `kit_doctor.py install`, schema de `kit.install.yaml`, seam de cross-host.
- `SKILL-CONTRACT.md` (raiz da distribuição) — o contrato de `SKILL.md` cobrado por
  `tools/skill_lint.py`.
- `docs/UX-INSTALL-JOURNEY.md` (raiz da distribuição) — a jornada de instalação contada
  na conversa (greenfield/in-progress/re-run/falha), do ponto de vista do agente guiando o
  humano.
