[English](UX-INSTALL-JOURNEY.md) · [Português](UX-INSTALL-JOURNEY.pt-BR.md)

# UX-INSTALL-JOURNEY — the canonical installation journey of a module, told in the conversation

> **Version:** 1.0.0 — a presentation layer over a frozen contract.
> **Sibling of:** `INSTALL-CONTRACT.md` (the mechanics of the 6 stages) and
> `INSTALL-GUIDE-TEMPLATE.md` (the mould of the per-module README); both ship at the root of the
> emitted distribution. This document describes the EXPERIENCE: how an AGENT (Claude Code) guides
> a HUMAN through the installation, in a conversation.
> Nothing here changes the mechanics — if this document contradicts `INSTALL-CONTRACT.md`, the
> contract wins.

## Principle

**The human never sees a terminal prompt. The human sees a conversation.** The agent runs the
plan, translates the plan into the human's language, and waits for the human to say "apply it"
in natural language. Only then does it re-invoke with `--apply`. There is no `input()` anywhere —
the "Confirm" is the double invocation.

Three roles, with no overlap:

| Role | Does | Never does |
|---|---|---|
| **kit_doctor.py** | runs the 6 stages; in plan mode, zero writes | asks on stdin; writes settings/hooks |
| **agent** | runs commands, translates the plan, asks for confirmation, reports with real output | applies without confirmation; edits `settings.local.json`/hooks on its own |
| **human** | reads the plan in the conversation, decides, confirms in natural language | needs to memorise flags — the agent carries the command |

## The journey in 5 steps (the same in the 4 scenarios)

1. **Plan.** The agent runs `python kit_doctor.py install <kit> --target <project> --human`.
   Plan mode is the default: nothing is written, exit 0.
2. **Translation.** The agent pastes the confirmation block into the conversation (template in
   the "Confirmation block" section below): what `detect` saw, what `--apply` would do, what is
   still pending a decision, and the smoke result.
3. **Human confirmation.** The human answers in natural language — "apply it", "go ahead",
   "yes". Anything that is not a clear confirmation = do not apply.
   If the human wants to change an answer to a question (`questions:`), the agent writes an
   `--answers` file and runs the plan AGAIN before asking for confirmation once more.
4. **Apply.** The agent re-invokes the SAME command with `--apply`. The installer applies the
   profile, runs the smoke for real and records the installation in the registry.
5. **Report + manual wiring.** The agent shows the real output of the apply. If `wire-sugerido`
   listed options (plugin / settings block), the agent presents the exact content and **the human
   pastes/triggers it** — mutating `settings.local.json`/hooks is a human gate, always, even after
   `--apply`.

## What changes between the 4 scenarios

Everything below uses REAL output of `kit_doctor.py`, which prints in Portuguese. The
in-progress/re-run/failure outputs were captured against a minimal fixture (`demo-kit`) — same
report structure, example module.

### 1. `greenfield` — new project

```
  ✓ detect
      classificacao=greenfield · projeto novo — nenhuma config prévia detectada
```

What the agent emphasises: **there is nothing to preserve**; the plan is the happy path.
The human is asked one decision only: "is what `--apply` would do fine?".
Complete end-to-end example in the last section.

### 2. `in-progress` — project with existing config

```
  ✓ detect
      classificacao=in-progress · projeto em andamento — config existente detectada (será preservada)
      já existe (não será tocado): .claude/settings.local.json: statusLine/hooks já configurados
```

What changes in the conversation: the agent lists **item by item what already exists and will be
preserved** — that is the information that removes the fear of installing on top. The profile
never overwrites (`skip-exists` is reported, not silent). If the human WANTS to replace something
that exists, that is a manual action of theirs, outside the installer.

### 3. `re-run` — the same module+target pair was installed before

```
  ✓ detect
      classificacao=re-run · reinstalação — este par kit+target já consta no registry
      já existe (não será tocado): profile.yaml presente (customizado)
  ...
  ✓ profile
      já existe, preservado: profile.example.yaml -> profile.yaml
```

What changes in the conversation: the agent says explicitly that **running again is safe and
idempotent** — nothing is duplicated, customisation is preserved. Re-run is the normal way to
(a) check an old installation and (b) update after pulling a new version of the module.
The question to the human becomes: "do you want to re-apply anyway, or did you only want to check?".

### 4. Smoke failure — the module failed its own self-test

```
  ⚠ smoke  [FAIL]
      self-tests: 1 ok · 0 sem suporte (ignorados)
      ⚠ FALHOU: scripts\bad_tool.py (exit 1)

RESULTADO: smoke FALHOU — não aplique este kit antes de corrigir os self-tests acima.
Depois de corrigir, rode o plano de novo para confirmar antes do --apply.
```

Exit code = 1. What changes in the conversation: **the agent does NOT offer `--apply`.** It
reports which script failed, with its exit code, and proposes the next step (investigate the
script, check integrity with `kit_doctor.py verify <kit>`, or download the module again). It only
offers to apply again after a new plan comes out clean. A human who insists on applying with a
failing smoke is on their own — the agent records that it advised against it, and why.

## Questions (`questions:`) in the conversation

Most modules have no questions (by design). When one does, the plan shows:

```
  ✓ configure
      sem resposta (default assumido): modo
      para responder de verdade: repetir com --answers <arquivo.json|yaml>
```

Agent flow: (1) present each pending question with the default highlighted — "I will use
`full`, unless you prefer `lite`"; (2) if the human picks something other than the default, the
agent writes an `answers.json` and runs the plan again with `--answers answers.json`; (3) only
then ask for confirmation. Installing without answering anything never blocks — the default
always resolves.

## Confirmation block (template)

The text the agent pastes into the conversation when presenting a plan. Placeholders in `{}`.
Lines marked `[scenario]` only enter in the matching scenario. The template is written in
English; the agent speaks in the human's language and adapts the wording, not the structure.

```
I ran the {kit} installer in plan mode -- nothing has been written yet. Summary:

**Project diagnosis** ({target}):
[greenfield]   New project -- no previous config detected.
[in-progress]  Project in progress. The installer detected and will PRESERVE:
[in-progress]  {existing_config list, one per line}
[re-run]       This module was installed in this project before (it is in the registry).
[re-run]       Re-applying is safe: nothing is duplicated, your customisation is preserved.

**What --apply would do:**
- {profile actions: "copy profile.example.yaml -> profile.yaml" | "nothing to copy (already exists, preserved)"}
- record the installation in ~/.claude-kits/registry.json

**Module questions:** {"none" | "pending, using default: {id}={default} -- want to change it?"}

**Wiring (settings/hooks):** never automatic. After the apply I bring you the exact block
({paths suggested by wire-sugerido}) and YOU decide whether to paste it.

**Smoke (module self-tests):** {N} ok, {N} ignored{" -- ALL passed" | see the failure block below}.

[if smoke ok]   If this is fine, say "apply it" and I run:
[if smoke ok]     python kit_doctor.py install {kit_dir} --target {target_dir} --apply
[if smoke fail] The smoke FAILED: {file} (exit {N}). I do NOT recommend applying.
[if smoke fail] Next step: {investigate the script | run kit_doctor.py verify {kit_dir}}.
[if smoke fail] Once that is fixed, I run the plan again and bring you the result.
```

## End-to-end example (greenfield, real run)

Module: `operator-kit-1.1.0`. Command the agent ran (real output below). This capture is dated:
it predates the versioned installer path. In the current distribution the module is
`operator-kit-1.4.0` and the installer lives at `instaladores/kit-forge-1.4.0/kit_doctor.py`;
the stages, the flags (`--target`, `--host`, `--answers`, `--apply`, `--human`) and the shape of
the output are the same.

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

What the agent says to the human (exact text, following the template):

> I ran the operator-kit-1.1.0 installer in plan mode — nothing has been written yet. Summary:
>
> **Project diagnosis:** new project (greenfield) — no previous config detected, nothing to
> preserve.
>
> **What --apply would do:**
> - copy `profile.example.yaml` -> `profile.yaml` (the profile you will customise)
> - record the installation in `~/.claude-kits/registry.json`
>
> **Module questions:** none — this module has nothing configurable at install time.
>
> **Wiring (settings/hooks):** never automatic. After the apply, the paths are installing as a
> plugin (`/plugin marketplace add .` + `/plugin install`) or following `SETTINGS-WIRE.md` — I
> bring you the step by step and you decide.
>
> **Smoke (module self-tests):** 27 ok, 0 ignored — all passed.
>
> If this is fine, say "apply it" and I run the same command with `--apply`.

Human: **"apply it"**

The agent runs the same command with `--apply`, pastes the real output (the header becomes
`INSTALACAO APLICADA — ... (--apply)`, the profile line becomes `copiado:`, the footer confirms
`Instalação aplicada e registrada.`) and closes with the wiring:

> Applied and recorded. Only the wiring is left, and it is yours: do you want me to show you the
> block from `SETTINGS-WIRE.md` to paste into `settings.local.json`, or do you prefer the plugin
> path? In either one, the person who runs the final step is you.

## What the agent NEVER does (conduct checklist)

- [ ] NEVER runs `--apply` without explicit confirmation from the human IN THIS conversation
- [ ] NEVER edits `settings.local.json` / hooks — presents the block, the human pastes it
- [ ] NEVER reports "installed" without pasting the real output of `--apply` (exit code included)
- [ ] NEVER offers `--apply` when the smoke failed (exit 1) — fix first
- [ ] NEVER answers the module's questions alone when the human expressed a preference —
      writes `--answers` and re-plans
- [ ] On re-run, ALWAYS says it is idempotent before asking for confirmation
