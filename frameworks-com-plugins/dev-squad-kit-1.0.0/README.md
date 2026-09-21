[English](README.md) · [Português](README.pt-BR.md)

# Dev Squad Kit

## 1. What it is

A squad of 12 role agents via slash-command (`*master`, `*analyst`, `*architect`,
`*data-engineer`, `*dev`, `*devops`, `*pm`, `*po`, `*qa`, `*sm`, `*squad-creator`,
`*ux-design-expert`) — each with its own persona, numbered commands and a collaboration
checklist with the others — plus 3 token-safe parallel reading/consolidation skills
(`pp-discovery`, `pp-raiox`, `pp-consolidate`).

**What this kit does NOT do:** it does not include the proprietary tree of
tasks/templates/checklists that the `*create`, `*task`, `*workflow`, `*execute-checklist`
commands expect to find in `.devsquad-core/{tasks,templates,checklists,data,utils,workflows}/`.
Without that tree, those specific commands will fail or improvise. Use the 12 agents for
persona, `*help`, `*guide` and delegation of reasoning between roles — or build/bring your
own task tree if you want the complete document-creation commands. Each of the 12 commands
carries this same notice at the top (the **Dependências fora deste kit:** block), before
the activation instructions, so the agent knows what to skip when the path does not exist.

## 2. Prerequisites + external APIs

| Requirement | Minimum version | Required? |
|---|---|---|
| Python | 3.9 | only for the installer's `skill_lint.py`/`kit_doctor.py` |

External services: **none — stdlib only.** The 12 agents are persona `.md` files (prompt),
not executable code, and call no API.

## 3. Install as a plugin

```bash
/plugin marketplace add .
/plugin install dev-squad-kit@house-party-protocol
```

## 4. Install by copy

```bash
cp -r dev-squad-kit <seu-projeto>/dev-squad-kit
cd <seu-projeto>
python dev-squad-kit/../instaladores/kit-forge/kit_doctor.py install dev-squad-kit --target . --human
python dev-squad-kit/../instaladores/kit-forge/kit_doctor.py install dev-squad-kit --target . --apply
```

## 5. What the installer detects

```
greenfield    → copia os 12 comandos + 3 skills, nada mais a gerar (não há profile.yaml)
em-andamento  → se já existir commands/<nome>.md com o mesmo nome, reporta conflito, não sobrescreve
re-run        → cópia idempotente; nenhum estado externo pra perder
```

## 6. What is safe to run again

Everything. There is no customisable profile and no generated state — the commands and
skills are static. Running the installation again only re-copies the same files.

## 7. Manual wiring

None. This kit has no hooks — only `commands/` and `skills/`, both auto-discovered by
Claude Code through `.claude-plugin/plugin.json`.

## 8. Proof (real output, executed)

```
$ python ../instaladores/kit-forge/tools/skill_lint.py --all skills --run-proofs

[FAIL] skills\pp-consolidate\SKILL.md
    FAIL L1d.quando_nao_ativar        seção '## Quando NÃO Ativar' ausente
    FAIL L2a.contrato_ausente         seção '## Contrato' ausente
    FAIL L3a.exemplos_min3            0 exemplo(s) executado(s) < 3
    FAIL L4a.prova_ausente            seção '## Prova' ausente
[FAIL] skills\pp-discovery\SKILL.md   (mesmos 4 achados)
[FAIL] skills\pp-raiox\SKILL.md       (mesmos 4 achados)
skill_lint: 0 pass · 0 warn · 3 fail (de 3)
```

**Product honesty:** the 3 `pp-*` skills are investigation methodology (prose guiding how
to inventory/read a repo before diving in), not scripts with deterministic output — which
is why they have no `--self-test` and no `## Prova` section in the format that this
marketplace's `SKILL-CONTRACT.md` requires for tool-skills. They have not yet been updated
to the formal v1.0 contract (`## Contrato` section, 3 executed examples). They work as a
reasoning guide; they have no mechanical proof of execution. Documented here rather than
hidden — decide whether that serves your case before installing.

The 12 persona agents have no self-test mechanism (they are prompt, not code) — the
possible proof is reading the `.md` itself, which deterministically and explicitly defines
commands, personas and collaboration rules.

## 9. Undo

```
- Plugin: /plugin uninstall dev-squad-kit@house-party-protocol
- Cópia: remover a pasta dev-squad-kit/ do projeto (nenhum outro arquivo foi tocado)
```
