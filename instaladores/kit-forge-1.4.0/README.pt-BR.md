[English](README.md) · [Português](README.pt-BR.md)

# Kit Forge

O gate de IP/PII + o montador de kits deste marketplace. Não é um kit para instalar num
projeto de terceiro — é a ferramenta que **constrói e verifica** os outros kits
(incluindo a si mesma). `ip_pii_linter.py` (varre nomes de cliente/infra internos antes
de qualquer coisa virar público), `kit_assembler.py` (monta um kit a partir de um
manifesto declarativo + a fonte, com `guard_origins` integrado — aborta se a fonte mudar
no meio da montagem), `kit_doctor.py` (verify/install/registry — o motor único de
instalação de todo o marketplace, 6 estágios), `wire_settings.py` (merge idempotente em
`settings.local.json`), `install_git_hook.py` (encadeia com `pre-commit` alheio), e
`tools/skill_lint.py` (o linter que cobra o SKILL-CONTRACT das skills de outros kits).
Contrato único de exit em tudo: `0 ok/no-op`, `1 warn`, `2 block`, `3 erro`. Sem
`--skip-lint` em nenhuma ferramenta — o gate de IP/PII é sempre obrigatório.

## Pré-requisitos + APIs externas

| Requisito | Versão mínima | Obrigatório? |
|---|---|---|
| Python | 3.8 | sim |
| PyYAML | qualquer | sim — `kit_assembler.py`/`ip_pii_linter.py`/`wire_settings.py` parseiam manifesto/ruleset/spec com ela; a função central dessas 3 ferramentas depende dela |

Serviços externos: **nenhum — stdlib + PyYAML, só toca filesystem local.**

## Instalar via plugin

Este kit não tem `.claude-plugin/plugin.json` (não é consumido como plugin — é a
ferramenta que constrói/verifica os OUTROS kits do marketplace). Use por cópia.

## Instalar por cópia

```bash
cp -r kit-forge-1.2.0 <seu-projeto>/kit-forge
cd <seu-projeto>
python kit-forge/kit_doctor.py install kit-forge --target . --human
#                                                     ^ plano, zero escrita
python kit-forge/kit_doctor.py install kit-forge --target . --apply
#                                                     ^ aplica de verdade
```

## O que o instalador detecta

```
greenfield    → nenhum arquivo de config próprio (ip-ruleset.yaml é do NEGÓCIO que usa
                 o kit-forge, não deste kit — copie ip-ruleset.example.yaml e preencha)
em-andamento  → ip-ruleset.yaml customizado já presente (skip-exists, nunca sobrescrito)
re-run        → registry (~/.claude-kits/registry.json) marca re-run
```

## O que é seguro rodar de novo

`wire_settings.py` é idempotente e byte-estável (rodar duas vezes não duplica). O
`ip-ruleset.yaml` real (com nomes de cliente/porta/domínio do SEU negócio) nunca é
sobrescrito automaticamente por nenhuma ferramenta aqui — só você edita.
`kit_assembler.py` sempre monta num diretório de saída novo (nunca escreve por cima do
kit já emitido em produção sem você apontar `--out` explicitamente).

## Wiring manual

Nenhum — este kit não tem hooks/plugin. É uma coleção de ferramentas de linha de
comando invocadas sob demanda (ex.: por um cron de CI, ou manualmente antes de publicar
um kit novo).

## Configurar o ruleset de IP/PII (o passo real antes de montar qualquer kit)

```bash
cp ip-ruleset.example.yaml ip-ruleset.yaml
# editar ip-ruleset.yaml com os nomes de cliente/infra REAIS do seu negócio
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
self-test OK — verify (ok/warn/corrupt/error) + compat posicional + install (6 estágios:
detect/prereqs/profile/configure/wire/smoke, plan-first/--apply, --answers, re-run) +
registry (kit+target, sem duplicar) + render_plan
```
<!-- executado: 2026-07-11 · exit=0 -->

```bash
python ip_pii_linter.py --self-test
```
```
self-test OK — 17 findings em 16 regras distintas
```
<!-- executado: 2026-07-11 · exit=0 -->

```bash
python wire_settings.py --self-test
```
```
self-test OK — wire idempotente, conflito sem --force preservado, --force sobrescreve, --undo byte-idêntico
```
<!-- executado: 2026-07-11 · exit=0 -->

## Desfazer

```
- Cópia: remover a pasta kit-forge/ do projeto (nada mais para reverter — sem
  wiring/settings tocados por este kit em si)
- ip-ruleset.yaml: apagar manualmente se não quiser mais rodar o lint neste negócio
```

## Documentação estendida

- `INSTALL-CONTRACT.md` (raiz do marketplace) — o contrato completo dos 6 estágios de
  `kit_doctor.py install`, schema de `kit.install.yaml`, seam de cross-host.
- `../../SKILL-CONTRACT.md` (raiz do marketplace) — o contrato de `SKILL.md` cobrado
  por `tools/skill_lint.py`.
- `../../docs/UX-INSTALL-JOURNEY.md` — a jornada de instalação contada na conversa
  (greenfield/em-andamento/re-run/falha), do ponto de vista do agente guiando o humano.
