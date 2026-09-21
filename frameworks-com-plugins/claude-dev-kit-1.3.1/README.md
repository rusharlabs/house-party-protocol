[English](README.md) · [Português](README.pt-BR.md)

# Claude Dev Kit

Tools for **building tools** for Claude Code. 4 meta-skills (`skill-writer`, `hookify`,
`plugin-dev`, `teaching`) with a vendored `SKILL-CONTRACT.md` — they do not describe in
prose how to create a skill/hook/plugin, they enforce the same contract (header + I/O + at
least 3 real examples + proof) on whoever uses them to create their own. Plus 2 installation
tools: `wire_settings.py` (idempotent, byte-stable merge into `settings.local.json`, with
`--undo`) and `install_git_hook.py` (chains with an existing `pre-commit` from someone
else — never replaces it). It does not generate product code — it generates the tool that
generates/audits other tools.

## Prerequisites + external APIs

| Requirement | Minimum version | Required? |
|---|---|---|
| Python | 3.8 | yes |
| PyYAML | any | yes |

External services: **none — stdlib + PyYAML, touches only the local filesystem + the target project's git.**

## Install as a plugin (1-click auto-wire)

```bash
/plugin marketplace add .
/plugin install claude-dev-kit@house-party-protocol
```
The `hooks/hooks.json` already wires `secret_scan_on_write.py` automatically (through
`${CLAUDE_PLUGIN_ROOT}`, matcher `Edit|Write|MultiEdit`).

## Install by copy

```bash
cp -r claude-dev-kit-1.1.0 <seu-projeto>/claude-dev-kit
cd <seu-projeto>
python claude-dev-kit/instaladores/kit-forge/kit_doctor.py install claude-dev-kit --target . --human
#                                                                                       ^ plano, zero escrita
python claude-dev-kit/instaladores/kit-forge/kit_doctor.py install claude-dev-kit --target . --apply
#                                                                                       ^ aplica de verdade
```

## What the installer detects

```
greenfield    → nenhum profile.example.* neste kit (sem config configurável — YAGNI); nada a copiar
em-andamento  → .claude/settings.local.json já com o hook secret_scan_on_write (reportado, não sobrescrito)
re-run        → registry (~/.claude-kits/registry.json) marca re-run; wire_settings.py idempotente detecta merge já aplicado
```

## What is safe to run again

`wire_settings.py` is **idempotent and byte-stable**: running it twice produces the same
`settings.local.json` (it does not duplicate the entry). On conflict (a different entry
already exists at the same path), it preserves what is there **without `--force`** — it
only overwrites with an explicit `--force`. `install_git_hook.py` is **chain-preserving**:
if a `pre-commit` from another tool already exists, it chains (never replaces).

## Manual wiring (human gate — never automatic)

> Editing `.claude/settings.local.json` is a human gate. `wire_settings.py` is
> **programmatic** (a different format from the human-paste `wiring.settings.jsonc` of the
> other kits) — but it still NEVER runs on its own: the human gate is who invokes the command.

```bash
python scripts/wire_settings.py --spec hooks/wiring-spec.yaml --settings .claude/settings.local.json
#                                                                          ^ merge idempotente; --undo reverte
```

Content of `hooks/wiring-spec.yaml` (what will be merged):
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

Git hook (chains with someone else's `pre-commit`, never replaces it):
```bash
python scripts/install_git_hook.py --repo . --hook-name pre-commit --payload <payload.sh>
```

## Proof / acceptance (real output, executed)

```bash
python scripts/wire_settings.py --self-test
```
```
self-test OK — wire idempotente, conflito sem --force preservado, --force sobrescreve, --undo byte-idêntico
```
<!-- executado: 2026-07-11 · exit=0 -->

## Undo

```
- Plugin: /plugin uninstall claude-dev-kit@house-party-protocol
- Cópia: remover a pasta claude-dev-kit/ do projeto
- wire_settings.py: python scripts/wire_settings.py --spec hooks/wiring-spec.yaml --settings .claude/settings.local.json --undo
- install_git_hook.py: remover manualmente o bloco encadeado do .git/hooks/pre-commit
  (o script preserva o pre-commit alheio original abaixo do bloco inserido)
```
