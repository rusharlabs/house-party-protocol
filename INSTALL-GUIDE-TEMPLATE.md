[English](INSTALL-GUIDE-TEMPLATE.md) · [Português](INSTALL-GUIDE-TEMPLATE.pt-BR.md)

# INSTALL-GUIDE-TEMPLATE — the mould of the installation README of every kit

> **Version:** 1.0.0 · **Sibling of:** `SKILL-CONTRACT.md` (the SKILL.md contract) and
> `INSTALL-CONTRACT.md` (the installer contract). This one is the contract of the **README**
> that documents the installation for a human/agent reading it for the first time.
> **Enforcement:** manual review in this round; a candidate for a future lint if the
> marketplace grows (same pattern as `skill_lint.py`).

## Principle

```
UM ESTRANHO, NUM REPO VIRGEM, LENDO SÓ ESTE README, CONSEGUE:
(1) saber SE precisa de alguma API/serviço externo antes de instalar,
(2) escolher entre plugin e cópia sem adivinhar,
(3) saber O QUE o instalador vai detectar no projeto dele,
(4) rodar de novo sem medo de perder customização,
(5) provar com saída REAL que a instalação funcionou,
(6) desfazer, se precisar.

Prosa sem comando literal para cada um destes 6 pontos não é guia — é resumo de marketing.
```

(A stranger, in a pristine repo, reading only this README, can: (1) know WHETHER any external
API/service is needed before installing, (2) choose between plugin and copy without guessing,
(3) know WHAT the installer will detect in their project, (4) run it again without fear of losing
customisation, (5) prove with REAL output that the installation worked, (6) undo it, if needed.
Prose without a literal command for each of these 6 points is not a guide — it is marketing
copy.)

## The 9 mandatory sections (in this order)

### 1. What it is (1 paragraph)
What the kit solves, in problem language — not a feature list. No "revolutionary", no empty
adjective. A sentence of negative scope is welcome ("it does not do X — for X, see `<sibling
kit>`").

### 2. Prerequisites + external APIs
```
| Requisito | Versão mínima | Obrigatório? |
|---|---|---|
| Python | 3.9 | sim |
| PyYAML | qualquer | sim/não |

Serviços externos: <NENHUM — stdlib only> OU <lista: nome, via (MCP/API direta), credencial>
```
(Table columns: requirement · minimum version · mandatory? — `sim` = yes, `não` = no,
`qualquer` = any. Last line: external services: `<NENHUM — stdlib only>` (none) OR the list —
name, via (MCP/direct API), credential.)

**Hard rule:** the default is **"none — stdlib only"**. If the kit needs something external, name
it exactly (e.g. Supabase via MCP, URL + anon key). **NEVER** `ANTHROPIC_API_KEY` — this
ecosystem's regime is subscription/quota, not pay-per-use (see `partial-autonomy-slider` in the
operator-kit and the subscription-only doctrine).

### 3. Install via plugin (the recommended path when `.claude-plugin/plugin.json` exists)
```bash
/plugin marketplace add .
/plugin install <nome-do-kit>@house-party-protocol
```
If the kit does not have a `plugin.json` yet, this section says so explicitly and points at
section 4 as the only path.

### 4. Install by copy (always works, even without plugin support)
```bash
cp -r <kit-dir> <seu-projeto>/<nome-do-kit>
cd <seu-projeto>
python <nome-do-kit>/instaladores/kit-forge/kit_doctor.py install <nome-do-kit> --target . --human
#                                                                                   ^ mostra o PLANO, zero escrita
python <nome-do-kit>/instaladores/kit-forge/kit_doctor.py install <nome-do-kit> --target . --apply
#                                                                                   ^ aplica de verdade
```
(`<seu-projeto>` = your project, `<nome-do-kit>` = the kit name; the first `install` shows the
PLAN with zero writes, the second, with `--apply`, applies for real.) Adjust the path of
`kit_doctor.py` to wherever the kit-forge was copied/installed — it is the single installation
engine of the whole marketplace, see `INSTALL-CONTRACT.md`.

### 5. What the installer detects (greenfield / in-progress / re-run)
One sentence per classification, specific to this kit:
```
greenfield    → <o que acontece: gera tudo do zero>
em-andamento  → <o que é detectado: ex. "settings.local.json já tem hooks — reportado, não sobrescrito">
re-run        → <o que é idempotente: ex. "profile já existe — skip-exists">
```
(`greenfield` → what happens: generates everything from scratch; `em-andamento` (in-progress) →
what is detected, e.g. "settings.local.json already has hooks — reported, not overwritten";
`re-run` → what is idempotent, e.g. "profile already exists — skip-exists".)

### 6. What is safe to run again
An explicit list of what the installer NEVER overwrites without `--force`/a human gate, and of
what IS regenerated every time (e.g. derived docs vs. customisable config). If the kit has a
script like `generate_and_summary` with skip-exists, cite the field of the returned JSON that
proves it (`files_skipped_customized`, `no_op`).

### 7. Manual wiring (human gate — never automatic)
```
⚠️ Editar .claude/settings.local.json é gate humano nesta doutrina — sessões automatizadas
têm trava explícita contra auto-editar arquivo de settings/hooks. Cole você mesmo o bloco
abaixo (ou rode o comando programático, se o kit tiver um) — tudo WARN-only + timeout: 30.
```
(The notice reads: editing `.claude/settings.local.json` is a human gate in this doctrine —
automated sessions have an explicit lock against auto-editing settings/hooks files. Paste the
block below yourself (or run the programmatic command, if the kit has one) — all WARN-only +
`timeout: 30`.) Paste here the real block from `install/wiring.settings.jsonc` (or the command of
`scripts/wire_settings.py --spec ...`, if that is this kit's programmatic format) — **never**
summarise; paste the whole block exactly as it is in the source file.

### 8. Proof / acceptance (real output, executed — never invented)
```bash
python <kit>/scripts/<algo>.py --self-test
```
```
<colar a saída REAL, literal, do comando acima — com marcador de data se o kit seguir o
padrão SKILL-CONTRACT C3>
```
(Paste the REAL, literal output of the command above — with a date marker if the kit follows the
SKILL-CONTRACT C3 pattern.) At least 1 proof command per README. Invented output violates
`agent-integrity.md`.

### 9. Undo
```
- Plugin: /plugin uninstall <nome>@house-party-protocol
- Cópia: remover a pasta <nome-do-kit>/ do projeto + reverter o bloco colado em
  settings.local.json manualmente (gate humano também na remoção)
- wire_settings.py (se aplicável): python scripts/wire_settings.py --spec ... --undo
```
(Plugin: `/plugin uninstall <nome>@house-party-protocol`. Copy: remove the `<nome-do-kit>/`
folder from the project + revert the block pasted into `settings.local.json` by hand — a human
gate on removal too. `wire_settings.py` (if applicable): `python scripts/wire_settings.py --spec ... --undo`.)

## Checklist before considering a README "compliant"

```
[ ] Seção 1 diz o que o kit NÃO faz (escopo negativo), não só o que faz
[ ] Seção 2 declara "nenhum" ou nomeia o serviço externo exato — nunca omite a seção
[ ] Seção 2 NUNCA menciona ANTHROPIC_API_KEY como pré-requisito
[ ] Seção 3 existe SE plugin.json existe; senão diz explicitamente que não existe ainda
[ ] Seção 4 tem os 2 comandos reais (plano, depois --apply) do kit_doctor.py
[ ] Seção 5 tem as 3 classificações (greenfield/em-andamento/re-run) especificas do kit
[ ] Seção 6 nomeia o campo do JSON que prova skip-exists (se o kit tiver generate/profile)
[ ] Seção 7 cola o bloco de wiring INTEIRO (não resume) e marca gate humano
[ ] Seção 8 tem saída REAL executada, não inventada
[ ] Seção 9 explica como desfazer plugin E cópia
```

The ten boxes, in order: section 1 says what the kit does NOT do (negative scope), not only what
it does; section 2 declares "none" or names the exact external service — never omits the
section; section 2 NEVER mentions `ANTHROPIC_API_KEY` as a prerequisite; section 3 exists IF
`plugin.json` exists, otherwise says explicitly that it does not exist yet; section 4 has the 2
real `kit_doctor.py` commands (plan, then `--apply`); section 5 has the 3 classifications
(greenfield/in-progress/re-run) specific to the kit; section 6 names the JSON field that proves
skip-exists (if the kit has generate/profile); section 7 pastes the WHOLE wiring block (no
summary) and marks the human gate; section 8 has REAL executed output, not invented; section 9
explains how to undo both plugin AND copy.

---

*Sibling of `SKILL-CONTRACT.md` — same principle (stranger + pristine repo + real proof), applied
to the installation README instead of to the body of a skill.*
