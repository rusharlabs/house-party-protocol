[English](README.md) · [Português](README.pt-BR.md)

# Claude Dev Kit

Ferramentas de **construir ferramentas** para Claude Code. 8 meta-skills
(`ls skills | wc -l` = 8 no módulo emitido) com `docs/SKILL-CONTRACT.md` vendorizado —
não descrevem em prosa como criar uma skill/hook/plugin, cobram o mesmo contrato (header +
I/O + ≥3 exemplos reais + prova) de quem as usa para criar as próprias:

| Skill | O que faz |
|---|---|
| `skill-writer` | guia a criação de uma skill — estrutura, frontmatter, descrições eficazes, validação contra o SKILL-CONTRACT |
| `skill-scout` | busca skills locais, no marketplace, no GitHub e na web ANTES de escrever uma skill nova |
| `search-first` | busca biblioteca/ferramenta/padrão existente (npm/PyPI, MCP, GitHub) ANTES de escrever código novo |
| `hookify` | cria hooks REAIS — scripts executáveis (stdin JSON, exit 0/1/2), registrados via `hooks.json` de plugin ou colados em settings |
| `plugin-dev` | empacota skills/hooks/commands num plugin instalável (`.claude-plugin/plugin.json` + `hooks/hooks.json` + `${CLAUDE_PLUGIN_ROOT}`) |
| `claude-dev-setup` | instala os hooks base num projeto novo — wiring de settings idempotente e reversível |
| `architecture-decision-records` | captura as decisões arquiteturais da sessão como ADRs estruturados em `docs/adr/` |
| `teaching` | transforma qualquer output técnico numa oportunidade de aprendizado (onde mora, com o que conecta, por quê) |

Mais o ferramental: `scripts/wire_settings.py` (merge idempotente e byte-estável em
`settings.local.json`, com `--undo`), `scripts/install_git_hook.py` (encadeia com um
`pre-commit` alheio já existente — nunca substitui) e `tools/skill_lint.py`, cópia
vendorizada do linter do marketplace para o kit conferir as próprias skills sem o
instalador por perto. Não gera código de produto — gera a ferramenta que gera/audita
outras ferramentas.

## Pré-requisitos + APIs externas

| Requisito | Versão mínima | Obrigatório? |
|---|---|---|
| Python | 3.8 | sim |
| PyYAML | qualquer | sim |

Serviços externos: **nenhum — stdlib + PyYAML, só toca filesystem local + git do projeto-alvo.**

## Instalar via plugin (auto-wire de 1 clique)

```bash
/plugin marketplace add rusharlabs/house-party-protocol
/plugin install claude-dev-kit@house-party-protocol
```
O `.claude-plugin/plugin.json` declara `hooks/hooks.json`, que arma
`secret_scan_on_write.py` automaticamente (via `${CLAUDE_PLUGIN_ROOT}`, matcher
`Edit|Write|MultiEdit`). As 8 skills são auto-descobertas.

## Instalar por cópia

Na distribuição emitida este módulo vive em
`frameworks/claude-dev-kit-1.3.2/` (o diretório carrega a versão — declare-a
uma vez, em `KIT`). O instalador é `installers/kit-forge-1.4.1/kit_doctor.py`; rode-o da
raiz da distribuição. Ele planeja primeiro e só escreve numa segunda invocação explícita
com `--apply`:

```bash
KIT=frameworks/claude-dev-kit-1.3.2
cp -r "$KIT" ../your-repo/claude-dev-kit      # the copy itself (kit_doctor does not copy on claude-code)
python installers/kit-forge-1.4.1/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo
python installers/kit-forge-1.4.1/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo --apply
# Codex CLI: --host codex — the installer copies the module into .agents/hpp/claude-dev-kit
#            and each skill into .agents/skills/hpp-claude-dev-kit-<skill>; no cp -r needed
```

## O que o instalador detecta

O estágio `detect` classifica o alvo (só leitura) com exatamente estes três rótulos:

```
greenfield    -> no prior config in the target; nothing to copy (this kit has no *.example.* file — YAGNI)
in-progress   -> .claude/ exists, or settings(.local).json already has hooks/statusLine, or the repo has
                 more than 3 commits: reported, never overwritten
re-run        -> this kit+target pair is already in the registry (~/.claude-kits/registry.json);
                 wire_settings.py is idempotent and reports an already-applied merge as no-op
```

## O que é seguro rodar de novo

`wire_settings.py` é **idempotente e byte-estável**: rodar duas vezes produz o mesmo
`settings.local.json` (não duplica a entrada). Em conflito (uma entrada diferente já
existe no mesmo path), preserva o que já está lá **sem `--force`** — só sobrescreve com
`--force` explícito. `install_git_hook.py` é **chain-preserving**: se já existir um
`pre-commit` de outra ferramenta, encadeia (nunca substitui).

## Wiring manual (gate humano — nunca automático)

> Editar `.claude/settings.local.json` é gate humano. O `wire_settings.py` é
> **programático** (formato diferente do `wiring.settings.jsonc` colar-humano dos outros
> kits) — mas mesmo assim NUNCA roda sozinho: o gate humano é quem invoca o comando. O
> arquivo-alvo precisa existir (`{}` basta).

```bash
python scripts/wire_settings.py --spec hooks/wiring-spec.yaml --target .claude/settings.local.json
#                                                                          ^ idempotent merge; --undo reverts
```

O `hooks/wiring-spec.yaml` declara o que será mesclado: uma entrada `PreToolUse`, matcher
`Edit|Write|MultiEdit`, casada pela substring `secret_scan_on_write`, rodando
`python "${CLAUDE_PLUGIN_ROOT}/hooks/secret_scan_on_write.py"` com `timeout: 30`.

Git hook (encadeia com `pre-commit` alheio, nunca substitui):
```bash
python scripts/install_git_hook.py --repo . --hook-name pre-commit --payload <payload.sh>
```

## Prova / aceite (saída real, executada)

```bash
python scripts/wire_settings.py --self-test
```
```
self-test OK — wire idempotent, conflict without --force preserved, --force overwrites, --undo byte-identical
```
<!-- executado: 2026-09-21 · exit=0 -->

```bash
python tools/skill_lint.py --all skills --run-proofs
```
Última linha da saída (as 8 linhas `[PASS]` acima dela carregam separadores de caminho do SO):
```
skill_lint: 8 pass · 0 warn · 0 fail (of 8)
```
<!-- executado: 2026-09-21 · exit=0 -->

## Desfazer

```
- Plugin:  /plugin uninstall claude-dev-kit@house-party-protocol
- Copy:    remove the claude-dev-kit/ folder from the project
- wire_settings.py: python scripts/wire_settings.py --spec hooks/wiring-spec.yaml --target .claude/settings.local.json --undo
- install_git_hook.py: remove the chained block from .git/hooks/pre-commit by hand
           (the script keeps the original third-party pre-commit below the inserted block)
```
