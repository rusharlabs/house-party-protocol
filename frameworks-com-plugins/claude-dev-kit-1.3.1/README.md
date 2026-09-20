# Claude Dev Kit

Ferramentas de **construir ferramentas** para Claude Code. 4 meta-skills (`skill-writer`,
`hookify`, `plugin-dev`, `teaching`) com `SKILL-CONTRACT.md` vendorizado — não descrevem em
prosa como criar uma skill/hook/plugin, cobram o mesmo contrato (header + I/O + ≥3 exemplos
reais + prova) de quem o usa para criar as próprias. Mais 2 ferramentas de instalação:
`wire_settings.py` (merge idempotente e byte-estável em `settings.local.json`, com `--undo`)
e `install_git_hook.py` (encadeia com um `pre-commit` alheio já existente — nunca substitui).
Não gera código de produto — gera a ferramenta que gera/audita outras ferramentas.

## Pré-requisitos + APIs externas

| Requisito | Versão mínima | Obrigatório? |
|---|---|---|
| Python | 3.8 | sim |
| PyYAML | qualquer | sim |

Serviços externos: **nenhum — stdlib + PyYAML, só toca filesystem local + git do projeto-alvo.**

## Instalar via plugin (auto-wire de 1 clique)

```bash
/plugin marketplace add .
/plugin install claude-dev-kit@house-party-protocol
```
O `hooks/hooks.json` já arma `secret_scan_on_write.py` automaticamente (via
`${CLAUDE_PLUGIN_ROOT}`, matcher `Edit|Write|MultiEdit`).

## Instalar por cópia

```bash
cp -r claude-dev-kit-1.1.0 <seu-projeto>/claude-dev-kit
cd <seu-projeto>
python claude-dev-kit/instaladores/kit-forge/kit_doctor.py install claude-dev-kit --target . --human
#                                                                                       ^ plano, zero escrita
python claude-dev-kit/instaladores/kit-forge/kit_doctor.py install claude-dev-kit --target . --apply
#                                                                                       ^ aplica de verdade
```

## O que o instalador detecta

```
greenfield    → nenhum profile.example.* neste kit (sem config configurável — YAGNI); nada a copiar
em-andamento  → .claude/settings.local.json já com o hook secret_scan_on_write (reportado, não sobrescrito)
re-run        → registry (~/.claude-kits/registry.json) marca re-run; wire_settings.py idempotente detecta merge já aplicado
```

## O que é seguro rodar de novo

`wire_settings.py` é **idempotente e byte-estável**: rodar duas vezes produz o mesmo
`settings.local.json` (não duplica a entrada). Em conflito (uma entrada diferente já
existe no mesmo path), preserva o que já está lá **sem `--force`** — só sobrescreve com
`--force` explícito. `install_git_hook.py` é **chain-preserving**: se já existir um
`pre-commit` de outra ferramenta, encadeia (nunca substitui).

## Wiring manual (gate humano — nunca automático)

> ⚠️ Editar `.claude/settings.local.json` é gate humano. O `wire_settings.py` é
> **programático** (formato diferente do `wiring.settings.jsonc` colar-humano dos outros
> kits) — mas mesmo assim NUNCA roda sozinho: o gate humano é quem invoca o comando.

```bash
python scripts/wire_settings.py --spec hooks/wiring-spec.yaml --settings .claude/settings.local.json
#                                                                          ^ merge idempotente; --undo reverte
```

Conteúdo de `hooks/wiring-spec.yaml` (o que será mesclado):
```yaml
# wiring-spec.yaml — consumido por scripts/wire_settings.py --spec (claude-dev-kit)
hooks:
  PreToolUse:
    matcher: "Edit|Write|MultiEdit"
    match_substring: "secret_scan_on_write"
    value:
      type: command
      command: "python \"${CLAUDE_PLUGIN_ROOT}/hooks/secret_scan_on_write.py\""
      timeout: 30
```

Git hook (encadeia com `pre-commit` alheio, nunca substitui):
```bash
python scripts/install_git_hook.py --repo . --hook-name pre-commit --payload <payload.sh>
```

## Prova / aceite (saída real, executada)

```bash
python scripts/wire_settings.py --self-test
```
```
self-test OK — wire idempotente, conflito sem --force preservado, --force sobrescreve, --undo byte-idêntico
```
<!-- executado: 2026-07-11 · exit=0 -->

## Desfazer

```
- Plugin: /plugin uninstall claude-dev-kit@house-party-protocol
- Cópia: remover a pasta claude-dev-kit/ do projeto
- wire_settings.py: python scripts/wire_settings.py --spec hooks/wiring-spec.yaml --settings .claude/settings.local.json --undo
- install_git_hook.py: remover manualmente o bloco encadeado do .git/hooks/pre-commit
  (o script preserva o pre-commit alheio original abaixo do bloco inserido)
```
