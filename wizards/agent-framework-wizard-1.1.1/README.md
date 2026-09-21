[English](README.md) · [Português](README.pt-BR.md)

# Agent Framework Wizard

A 6-step wizard (`check_python → check_git → check_deps → configure → validate →
generate_and_summary`) that scaffolds a new agent/project: it generates
`operator-profile.yaml` (verification ladder R0-R4) + the chosen templates
(`00-LEIA-PRIMEIRO`, `00-STATE`, `00-VISION`, `00-PROCESSES`). It does not install the
`operator-kit` itself — it generates the initial skeleton a new project would use with it.

## Prerequisites + external APIs

| Requirement | Minimum version | Required? |
|---|---|---|
| Python | 3.9 | yes |
| git | any | yes — the wizard confirms `git --version` in step 2 |
| PyYAML | any | yes |

External services: **none — stdlib + PyYAML.**

## Install as a plugin

```bash
/plugin marketplace add .
/plugin install agent-framework-wizard@house-party-protocol
```

## Install by copy

```bash
cp -r agent-framework-wizard-1.0.0 <seu-projeto>/agent-framework-wizard
cd <seu-projeto>/agent-framework-wizard
```
This kit has no hooks/wiring — once copied, use it directly (next section).

## How to use (non-interactive — no mode blocks on stdin)

The real operator of this ecosystem is often an agent acting for the human — a terminal
`input()` hangs in exactly that context. This wizard's "Confirm" is `--interview` (prints
the question schema) followed by `--answers` (applies the answers):

```bash
# 1. Ver o schema de perguntas (JSON, exit 0, não gera nada)
python wizard.py --interview

# 2a. Scaffold rápido com defaults sensatos (sem perguntar nada)
python wizard.py --demo --out <dir>

# 2b. OU scaffold a partir de respostas prontas (o agente monta o JSON após ler --interview)
python wizard.py --answers respostas.json --out <dir>
```

Example `respostas.json`:
```json
{"project_name": "meu-agente", "templates": ["00-STATE", "00-VISION"]}
```

## What the installer detects / what the wizard detects

```
greenfield    → gera operator-profile.yaml + templates do zero em <out>/docs/plans/execucao/
em-andamento  → arquivo já existe com conteúdo DIFERENTE do que seria gerado -> skip
                (reportado em "files_skipped_customized", nunca sobrescrito)
re-run        → conteúdo idêntico ao que já existe -> no_op:true (nada muda, nada quebra)
```

## What is safe to run again

`generate_and_summary()` **never overwrites** a file that already exists with content
different from what would be generated (user customisation) — the
`files_skipped_customized` field in the returned JSON lists exactly what was preserved.
Running twice without editing anything gives `no_op: true`. To force regeneration on
purpose (discarding customisation), use `--force`.

## Manual wiring

None — this kit has no hooks and does not touch `settings.local.json`. It is a pure
command-line tool.

## Proof / acceptance (real output, executed)

```bash
python wizard.py --self-test
```
```
self-test OK — 6 passos rodam, 1a run gera, 2a run = no-op, placeholders substituídos, validate pega
config vazia, --interview/--answers sem NotImplementedError, skip-exists preserva edição, --force sobrescreve
```
<!-- executado: 2026-07-11 · exit=0 -->

Proof of `--interview` (real schema printed, not invented):
```bash
python wizard.py --interview
```
```json
{
  "questions": [
    {
      "id": "project_name",
      "prompt": "Qual o nome do projeto/agente?",
      "type": "string",
      "default": "agente-teste"
    },
    {
      "id": "templates",
      "prompt": "Quais templates instanciar? (lista dentre os disponíveis)",
      "type": "choice",
      "options": ["00-LEIA-PRIMEIRO", "00-PROCESSES", "00-STATE", "00-VISION"],
      "default": ["00-LEIA-PRIMEIRO", "00-STATE", "00-VISION", "00-PROCESSES"]
    }
  ]
}
```
<!-- executado: 2026-07-11 · exit=0 -->

## Undo

```
- Plugin: /plugin uninstall agent-framework-wizard@house-party-protocol
- Cópia: remover a pasta agent-framework-wizard/ do projeto
- Scaffold gerado: remover manualmente operator-profile.yaml + docs/plans/execucao/*.md
  do projeto onde o wizard rodou (não há wiring/settings para desfazer)
```
