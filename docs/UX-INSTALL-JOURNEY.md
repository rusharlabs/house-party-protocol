[English](UX-INSTALL-JOURNEY.md) · [Português](UX-INSTALL-JOURNEY.pt-BR.md)

# UX-INSTALL-JOURNEY — the installation journey, told in the conversation

> **Version:** 2.0.0 — a presentation layer over two frozen contracts.
> **Path 1** is `hpp init`, the harness installer (`hpp/wizard.py`, six stages, plan then
> `--apply`). **Path 2** is the module installer, `installers/kit-forge-1.4.2/kit_doctor.py`,
> whose mechanics live in `INSTALL-CONTRACT.md` and whose per-module README follows
> `INSTALL-GUIDE-TEMPLATE.md`; both ship at the root of this repository. This document describes
> the EXPERIENCE: how an AGENT (Claude Code or Codex CLI) guides a HUMAN through the installation,
> in a conversation. Nothing here changes the mechanics — if this document contradicts the code or
> `INSTALL-CONTRACT.md`, they win. Every `hpp init` output quoted in Path 1 was measured on
> 2026-09-23 against version 2.5.8, from a clone of this repository at the `v2.5.8` tag unless the
> text says "pip install"; the `kit_doctor.py` outputs in Path 2 were captured on 2026-09-21 against
> version 2.4.1, and the end-to-end example says what has changed since. What is marked
> *new in 2.6.0* arrived after the version measured here.

## Principle

**The human never sees a terminal prompt. The human sees a conversation.** The agent runs the
plan, translates the plan into the human's language, and waits for the human to say "apply it"
in natural language. Only then does it re-invoke with `--apply`. There is no `input()` reached in
an agent session — `hpp init` only prompts on a TTY, and `--non-interactive`, `--yes`, `--json`
or `CI` in the environment take that path away; the "Confirm" is the double invocation.

Three roles, with no overlap:

| Role | Does | Never does |
|---|---|---|
| **installer** (`hpp init` · `kit_doctor.py`) | runs its stages; in plan mode, zero writes | asks on stdin in an agent session; writes settings/hooks |
| **agent** | runs commands, translates the plan, asks for confirmation, reports with real output | applies without confirmation; edits `settings.local.json`/hooks on its own |
| **human** | reads the plan in the conversation, decides, confirms in natural language | needs to memorise flags — the agent carries the command |

## Path 1 — `hpp init`, the harness journey (primary)

`hpp init` is the front door: it plans the whole installation for a host, verifies what it can,
writes at most one file, and prints the module-installer lines of Path 2 in its wire block. The
agent starts here, always.

### The six stages

The stages are fixed and run in this order; each boot line completes only when its stage has
finished.

| Stage | Boot line | What it measures | What can stop it |
|---|---|---|---|
| `detect` | `detecting host...` | `greenfield`, `in-progress` or `re-run`, from `.claude/settings*.json`, `AGENTS.md`, `.agents/`, `.hpp/events.jsonl`, a previous `.hpp/profile.json` and the git commit count; lists what exists and is kept | a corrupt event log or profile is a warning with the file to inspect |
| `prereqs` | `checking prerequisites...` | Python at or above 3.10; the manifest contract; the distribution when `marketplace.json` sits beside the manifest; `git` on `PATH` | Python below the floor or a manifest/marketplace divergence halts (exit 2) |
| `profile` | `mounting profile...` | four answers — host, bundle, policy mode and an optional decision advisor (new in 2.6.0; default `off`, never counted as a pending default) — from flags, `--profile`, the prompt (TTY only) or the default, with the source of each recorded | a recorded profile with different answers is a `conflict`; nothing is overwritten |
| `configure` | `loading modules...` | the module plan for the host, `native` or `explicit-command` per module, and `CHECKSUMS.txt` for every module directory present | a module unsupported on the host, or a checksum mismatch, halts (exit 2) |
| `wire-suggest` | `wiring suggestions...` | the block to paste: plugin lines for Claude Code, module-installer lines for Codex CLI and for explicit-command modules, the policy command as configured; before the block, a HOOK CAPABILITIES table — each hook the chosen modules declare, with its events, its exit policy (`observe`, `warn`, `block`) and its capability groups — counted on the boot line (`17 hooks declaring capabilities` for `reliable-coding`) | nothing; it never writes |
| `smoke` | `verifying evidence...` | four controls: policy classifier, capability graph, event log, benchmark at `k=1` | a failed control sets exit 1 and names itself |

### Plan, then `--apply`

1. **Plan.** The agent runs `python -m hpp init --target <project> --non-interactive --no-animation`
   (from a clone of this repository) or `hpp init --target <project> --non-interactive --no-animation`
   (from a pip install). Plan mode is the default: nothing is written, the target holds the same
   files afterwards, exit 0.
2. **Translation.** The agent pastes the confirmation block (template below) into the
   conversation: what `detect` saw, the four answers (the fourth, the decision advisor, is
   optional) and where each came from, the readiness line with what was and was not verified, the
   HOOK CAPABILITIES table read aloud, the wire block, and the pages the DOCUMENTATION section
   named.
3. **Human confirmation.** The human answers in natural language — "apply it", "go ahead",
   "yes". Anything that is not a clear confirmation = do not apply. If the human wants a
   different answer (another host, `enforce` instead of `audit`, an explicit module list), the
   agent re-runs the plan with `--host`, `--bundle`, `--policy-mode` or `--modules` and asks again.
4. **Apply.** The agent re-invokes the SAME command with `--apply`. Exactly one file is written,
   `.hpp/profile.json` inside the target; the boot line reads `written` and the readiness line
   gains one verified item:

```text
> mounting profile...         ✓ written · host=claude-code · bundle=reliable-coding · policy=audit · 3 default(s)

  ██████████████████░░  10/11 verified · 1 not verified · 0 failed
    ✓ profile recorded        .hpp/profile.json written
    · host wiring             not verified — manual gate — paste the block, then run doctor

  APPLIED  1 file(s) written inside the target
    .hpp/profile.json    written      host=claude-code · bundle=reliable-coding · policy=audit
```

5. **Wiring, by the human.** The agent shows the wire block as printed and **the human pastes
   it**: `/plugin marketplace add` and `/plugin install` lines on Claude Code, module-installer
   lines on Codex CLI and for explicit-command modules. `hpp init` never edits `settings.json`,
   hooks or `AGENTS.md`; host wiring stays `not verified` until the human has done it.

Running the same command again is safe: `detect` reports `re-run · 1 existing item(s) preserved`
and `profile` reports `unchanged`. Different answers against a recorded profile are a `conflict`:
the differing keys are named, nothing is overwritten, exit 1.

```text
> mounting profile...         ! conflict · host=claude-code · bundle=reliable-coding · policy=enforce · 2 default(s)

  PROBLEMS  what was measured, what was expected, what to do
    ✗ profile  [profile]
        measured: existing .hpp/profile.json differs in: policy_mode
        expected: the same answers as the recorded profile
        └ re-run with the recorded answers, or remove .hpp/profile.json to initialise again (nothing was overwritten)
```

### Readiness per channel

Readiness counts checks that ran, each with the command that reproduces it. What it can verify
depends on where `hpp` runs, and the agent says which channel it used. From a clone of this
repository — module directories, `CHECKSUMS.txt` and `marketplace.json` beside the manifest — a
plan against an empty target reads:

```text
> detecting host...           ✓ greenfield · 0 existing item(s) preserved
> checking prerequisites...   ✓ python 3.14.3 · protocol 2.1
> mounting profile...         ✓ would-write · host=claude-code · bundle=reliable-coding · policy=audit · 3 default(s)
> loading modules...          ✓ 6 modules · reliable-coding · claude-code · 6/6 checksums verified
> wiring suggestions...       ✓ 7 commands to paste · 0 files written · 17 hooks declaring capabilities
> verifying evidence...       ✓ policy · graph · events · benchmark
> protocol online.

  READINESS  every line is a check that ran; the command below it reproduces it
  ████████████████░░░░  9/11 verified · 2 not verified · 0 failed
```

The two not verified are the profile (plan only) and the host wiring (a paste). From a pip
install, which carries the harness, the manifest and the benchmark suite but no module
directories and no `marketplace.json`, the same plan reads `7/11 verified · 4 not verified`:
distribution integrity and module checksums are reported as not verified because there is
nothing to measure them against, never as passed. The agent quotes the line it got, not the
line it expected.

After NEXT, the report prints a DOCUMENTATION section that names only pages found on disk. From a clone it
lists `INSTALL_FOR_AGENTS.md`, `docs/CATALOG.md` and `docs/MANUAL.html`; a pip install carries no
documentation pages, and the section is then absent rather than pointing at files that are not
there. The agent passes on the paths it was given and invents none.

### Flags

| Flag | Effect |
|---|---|
| `--target <dir>` | the project to initialise (default: current directory) |
| `--apply` | write `.hpp/profile.json`; without it, plan only |
| `--host`, `--bundle`, `--policy-mode audit\|enforce` | answer the three required questions; `--modules a,b` replaces the bundle with an explicit list |
| `--decision-advisor off\|typesafe\|openrouter\|compatible` | new in 2.6.0. The optional fourth question (default `off`): records a typed-decision advisor you declare and prints how to integrate it; hpp never calls it and stores no key |
| `--profile answers.json` | the same answers from a file (keys `host`, `bundle`, `policy_mode`, `modules` and, new in 2.6.0, `decision_advisor`; an unknown key is a usage error) |
| `--yes`, `--non-interactive`, `--json`, or `CI` in the environment | no prompt is reached; unanswered questions take their defaults and the report says so |
| `--no-animation` | plain output; `NO_COLOR` is honoured; without a TTY the output is complete and uncoloured |
| `--no-benchmark` | skip the benchmark control in smoke; it is reported as not verified, not silently dropped |
| `--marketplace <slug>` | the slug used in the Claude Code wire block, for forks |
| `--json` | the same report as JSON (`schema: hpp.init-report/v1`), with `exit_code`, `readiness` and every stage's detail — for CI and for agents |

### Exit codes

| Code | Meaning | Measured example |
|---|---|---|
| `0` | plan or apply completed; every control that ran passed | the plans quoted above |
| `1` | a warning: a smoke control failed, or the recorded profile conflicts with the answers given | `--policy-mode enforce` over a profile recorded with `audit` |
| `2` | a blocking refusal: Python below 3.10, manifest/marketplace divergence, a module unsupported on the host, a checksum mismatch, an unknown module id | `--host codex --modules claude-dev-kit` → `loading modules... ✗ bundle custom requires claude-dev-kit, unsupported on codex` |
| `3` | a usage error in the invocation itself | a `--profile` file with an unknown key → `hpp init: profile file has unknown keys: colour (allowed: bundle, host, modules, policy_mode)` (2.6.0 also lists `decision_advisor`) |

With `--json`, the code the process will return is also inside the report (`exit_code`), and a
stage that halted the run leaves the later ones as `not run`.

### What the agent says (template)

The text the agent pastes into the conversation when presenting an `hpp init` plan. Placeholders
in `{}`; a part in `[]` enters only when it applies — the decision advisor only when it is not
`off` (new in 2.6.0). The template is written in English; the agent speaks in the human's language
and adapts the wording, not the structure.

```
I ran `hpp init` in plan mode against {target} -- nothing has been written. Summary:

**Project diagnosis:** {greenfield | in-progress, preserving: {list} | re-run, profile already recorded}.
**Answers:** host={host} ({flag|profile|default}) · bundle={bundle} ({source}) · policy={policy_mode} ({source})[ · decision-advisor={value} ({source})].
**Readiness:** {n}/11 verified · {m} not verified · {f} failed -- not verified: {items}.
  ({channel}: {clone of the repository | pip install}; the two extra items a pip install cannot measure are distribution integrity and module checksums.)
**What --apply would do:** write exactly one file, {target}/.hpp/profile.json.
**Hook capabilities:** {n} hooks declaring capabilities -- for each: {id}, {events}, {exit policy}, {capability groups}, as the HOOK CAPABILITIES table prints them[; on Codex CLI none of them is activated].
**Wiring (settings/hooks/plugins):** never automatic. After the apply I bring you the wire block as printed and YOU paste it.
**Documentation:** {the pages the DOCUMENTATION section named | none -- this copy ships no documentation pages}.

If this is fine, say "apply it" and I run the same command with --apply.
```

## Path 2 — the module installer (`kit_doctor.py`)

The lines `hpp init` prints in its wire block for Codex CLI, and for explicit-command modules on
Claude Code, are this installer. It copies one module at a time into the target and runs the
module's declared smokes; it plans first and applies only on a second, explicit invocation.

### The journey in 5 steps (the same in the 4 scenarios)

1. **Plan.** The agent runs `python installers/kit-forge-1.4.2/kit_doctor.py install --kit <module-dir> --host <host> --target <project> --human`
   (`--human` selects the human-readable report). Plan mode is the default: nothing is written,
   exit 0.
2. **Translation.** The agent pastes the confirmation block into the conversation (template in
   the "Confirmation block" section below): what `detect` saw, what `--apply` would do, what is
   still pending a decision, and the smoke result.
3. **Human confirmation.** The human answers in natural language — "apply it", "go ahead",
   "yes". Anything that is not a clear confirmation = do not apply.
   If the human wants to change an answer to a question (`questions:`), the agent writes an
   `--answers` file and runs the plan AGAIN before asking for confirmation once more.
4. **Apply.** The agent re-invokes the SAME command with `--apply`. The installer applies the
   profile, runs the smoke for real and records the installation in the registry.
5. **Report + manual wiring.** The agent shows the real output of the apply. If `wire-suggest`
   listed options (plugin / settings block), the agent presents the exact content and **the human
   pastes/triggers it** — mutating `settings.local.json`/hooks is a human gate, always, even after
   `--apply`.

### What changes between the 4 scenarios

Everything below uses REAL output of `kit_doctor.py`, which prints in Portuguese. The
in-progress/re-run/failure outputs were captured against a minimal fixture (`demo-kit`) — same
report structure, example module.

#### 1. `greenfield` — new project

```
  ✓ detect
      classification=greenfield · new project — no previous config detected
```

What the agent emphasises: **there is nothing to preserve**; the plan is the happy path.
The human is asked one decision only: "is what `--apply` would do fine?".
Complete end-to-end example in the last section of this path.

#### 2. `in-progress` — project with existing config

```
  ✓ detect
      classification=in-progress · project in progress — existing config detected (it will be preserved)
      já existe (não será tocado): .claude/settings.local.json: statusLine/hooks já configurados
```

What changes in the conversation: the agent lists **item by item what already exists and will be
preserved** — that is the information that removes the fear of installing on top. The profile
never overwrites (`skip-exists` is reported, not silent). If the human WANTS to replace something
that exists, that is a manual action of theirs, outside the installer.

#### 3. `re-run` — the same module+target pair was installed before

```
  ✓ detect
      classification=re-run · reinstall — this kit+target pair is already in the registry
      já existe (não será tocado): profile.yaml presente (customizado)
  ...
  ✓ profile
      já existe, preservado: profile.example.yaml -> profile.yaml
```

What changes in the conversation: the agent says explicitly that **running again is safe and
idempotent** — nothing is duplicated, customisation is preserved. Re-run is the normal way to
(a) check an old installation and (b) update after pulling a new version of the module.
The question to the human becomes: "do you want to re-apply anyway, or did you only want to check?".

#### 4. Smoke failure — the module failed its own self-test

```
  ⚠ smoke  [FAIL]
      self-tests: 1 ok · 0 sem suporte (ignorados)
      ⚠ FALHOU: scripts\bad_tool.py (exit 1)

RESULTADO: smoke FALHOU — não aplique este kit before de corrigir os self-tests acima.
Depois de corrigir, rode o plano de novo para confirmar before do --apply.
```

Exit code = 1. What changes in the conversation: **the agent does NOT offer `--apply`.** It
reports which script failed, with its exit code, and proposes the next step (investigate the
script, check integrity with `kit_doctor.py verify <module-dir>`, or download the module again).
It only offers to apply again after a new plan comes out clean. A human who insists on applying
with a failing smoke is on their own — the agent records that it advised against it, and why.

### Questions (`questions:`) in the conversation

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

### Confirmation block (template)

The text the agent pastes into the conversation when presenting a module plan. Placeholders in
`{}`. Lines marked `[scenario]` only enter in the matching scenario. The template is written in
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
({paths suggested by wire-suggest}) and YOU decide whether to paste it.

**Smoke (module self-tests):** {N} ok, {N} ignored{" -- ALL passed" | see the failure block below}.

[if smoke ok]   If this is fine, say "apply it" and I run:
[if smoke ok]     python kit_doctor.py install {kit_dir} --target {target_dir} --apply
[if smoke fail] The smoke FAILED: {file} (exit {N}). I do NOT recommend applying.
[if smoke fail] Next step: {investigate the script | run kit_doctor.py verify {kit_dir}}.
[if smoke fail] Once that is fixed, I run the plan again and bring you the result.
```

### End-to-end example (greenfield, real run)

Module: `operator-kit-1.5.0`. Command the agent ran (real output below). This capture is dated:
it predates the versioned installer path. In the current distribution the module is
`operator-kit-1.5.0` and the installer lives at `installers/kit-forge-1.4.1/kit_doctor.py`;
the stages, the flags (`--target`, `--host`, `--answers`, `--apply`, `--human`) and the shape of
the output are the same.

```
$ python installers/kit-forge-1.4.1/kit_doctor.py install frameworks/operator-kit-1.5.0 \
    --target frameworks/operator-kit-1.5.0 --human

INSTALL PLAN — operator-kit-1.5.0  (dry run: nothing was written)
  target: frameworks\operator-kit-1.5.0
  host:   claude-code

  ✓ detect
      classification=greenfield · new project — no previous config detected
  ✓ prereqs
  ✓ profile
      would copy: profile.example.yaml -> operator-profile.yaml
  ✓ configure
  ✓ wire-suggest
      opção [plugin]: /plugin marketplace add . && /plugin install <name>@<marketplace>
      opção [doc]: seguir SETTINGS-WIRE.md
      (nenhuma é executada automaticamente — mexer em settings/hooks é decisão humana)
  ✓ smoke
      self-tests: 27 ok · 0 sem suporte (ignorados)

Nada foi modificado. Se o plano está de acordo, aplique com:
  python kit_doctor.py install frameworks\operator-kit-1.5.0 --target frameworks\operator-kit-1.5.0 --apply
```

What the agent says to the human (exact text, following the template):

> I ran the operator-kit-1.5.0 installer in plan mode — nothing has been written yet. Summary:
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
`INSTALL APPLIED — ... (--apply)`, the profile line becomes `copied:`, the footer confirms
`Install applied and registered. Wiring of settings/hooks (if suggested above) stays manual.`) and closes with the wiring:

> Applied and recorded. Only the wiring is left, and it is yours: do you want me to show you the
> block from `SETTINGS-WIRE.md` to paste into `settings.local.json`, or do you prefer the plugin
> path? In either one, the person who runs the final step is you.

## What the agent NEVER does (conduct checklist)

- [ ] NEVER runs `--apply` — of `hpp init` or of `kit_doctor.py` — without explicit confirmation from the human IN THIS conversation
- [ ] NEVER edits `settings.local.json` / hooks / `AGENTS.md` — presents the block, the human pastes it
- [ ] NEVER reports "installed" without pasting the real output of `--apply` (exit code included)
- [ ] NEVER reports a readiness line it did not get — quotes the channel and the count as printed
- [ ] NEVER offers `--apply` when the smoke failed (exit 1) — fix first
- [ ] NEVER answers the module's questions alone when the human expressed a preference —
      writes `--answers` and re-plans
- [ ] On re-run, ALWAYS says it is idempotent before asking for confirmation
