[English](README.md) · [Português](README.pt-BR.md)

# Operator Kit

Portable layer for **disciplined operation with AI/Claude** — truth-before-done,
autonomous execution with guardrails, spec-driven planning, parallelism with a ceiling,
self-healing memory, direct communication. **It is not about any specific ecosystem**:
it drops into **any project** and is re-tuned through **a single config file**
(`operator-profile.yaml`). The mechanisms (scripts/hooks/skills/output-styles) are
**inert and generic** — all customisation lives in the profile. Swap the profile → same
kit, opposite behaviour (conservative for a client, aggressive for hacking), zero code
edits. It does not do multi-session (`lane-kit`) nor session handoff (`continuity-kit`) —
this kit is the execution-discipline layer, not the continuity layer.

## Prerequisites + external APIs

| Requirement | Minimum version | Required? |
|---|---|---|
| Python | 3.9 | yes |
| PyYAML | any | yes — the central config mechanism only really works with it |

External services: **none fixed.** `urllib.request` in `health_probe.py`/`drift_check.py`
points at targets that YOUR `operator-profile.yaml` declares (`health.probes`, default
`[]`) — generic, not a service embedded in the kit. **Never `ANTHROPIC_API_KEY`** — the
regime is subscription/quota, not pay-per-use.

## What is in this folder

Counts below were taken with `ls scripts | wc -l` (17) and `ls skills | wc -l` (13) on the
emitted module.

```
operator-kit/
├── README.md · README.pt-BR.md   ← this file (and its Portuguese twin)
├── profile.example.yaml          ← commented template to copy into a new project
├── (create operator-profile.yaml from profile.example.yaml — not versioned)
├── install/
│   └── kit.install.yaml          ← manifest read by kit_doctor.py install (6 stages)
├── _lib/
│   ├── profile_loader.py         ← finds + reads the profile (stdlib + PyYAML). EVERY mechanism imports from here.
│   ├── concurrency.py            ← ceiling of simultaneous agents (concorrencia.teto)
│   └── launcher.py               ← resolves the right Python launcher (never hardcodes "py")
├── scripts/                      ← 17 scripts: done_gate, verify_ladder, preflight, debt_ledger,
│                                    goal_ledger/goal_review, passk_eval, audit_plan,
│                                    determinism_harness, distill_corrections, drift_check,
│                                    health_probe, live_count, status_now, delta_inventory,
│                                    gate_sheet_panel, claude_md_from_profile
├── hooks/                        ← 8 hooks (hooks.json wires all of them, WARN-only): operation_guard_
│                                    portable, snapshot_rollback_gate, external_send_draft_gate,
│                                    secret_scan_on_write, project_root_confirm, rule_capture,
│                                    ralph_gate, autoprompt_resume — plus pyrun.sh (resolves the
│                                    project's Python interpreter for every hook)
├── skills/                       ← 13 skills: delegate-with-handback, parallel-dispatch,
│                                    adversarial-refuter, gated-improvement-proposal,
│                                    ralph-loop-driver, pre-clear-boot-block, live-source-prover,
│                                    gate-sheet-collector, doc-consolidator-dedup,
│                                    dual-report-builder, rls-audit, supabase-edge-scaffold,
│                                    claude-md-from-profile
├── agents/                       ← 2 read-only sub-agents: refutador, silent-failure-hunter (+ NOTICE-ECC.md)
├── commands/                     ← /ralph-gate, /cancel-ralph-gate
├── evals/                        ← ralph-gate-T1-T4.sh (proof of the loop)
├── evolve/                       ← instinct_promote.py + NOTICE-ECC.md (credit of origin)
├── statusline/
│   └── statusline.py             ← composable status bar (segments configured in the profile)
├── templates/
│   └── loop-charter-template.md  ← fill-in anatomy of an autonomous loop
├── rules/                        ← 13 universal rules (.claude/rules/*.md) — see the table below
├── docs/
│   ├── ANTHROPIC-STANDARDS.md    ← hook/skill/sub-agent conventions
│   └── MCP-RUNBOOK.md            ← how to discover, test and diagnose MCP servers
├── output-styles/
│   ├── direct-register.md        ← tone: direct, plain error reporting, banned phrases
│   └── execute-100pct.md         ← LC-2: authorised → executes the whole scope in batch
├── RALPH-GATE.md                 ← doctrine of the /ralph-gate loop
├── SETTINGS-WIRE.md              ← ready-to-paste blocks for settings.local.json — HUMAN gate
├── AGENTS.md                     ← Codex CLI entry point (what Codex reads on --host codex)
└── LICENSE · CHECKSUMS.txt · SANITIZATION.md   ← added by the forge at emission
```

## Install as a plugin (1 click)

```bash
/plugin marketplace add rushar-labs/house-party-protocol
/plugin install operator-kit@house-party-protocol
```
`.claude-plugin/plugin.json` declares `hooks/hooks.json` and `commands/`: the 8 hooks are
wired automatically (through `${CLAUDE_PLUGIN_ROOT}`), and skills, commands, agents and
output-styles are auto-discovered. **statusLine** remains manual (a Claude Code limit: a
plugin cannot embed `statusLine`) — see `SETTINGS-WIRE.md` §3.

## Install by copy

In the emitted distribution this module lives in `frameworks-com-plugins/operator-kit-1.4.0/`
(the directory carries the version — state it once, in `KIT`). The installer is
`instaladores/kit-forge-1.4.0/kit_doctor.py`; run it from the distribution root. It plans
first and writes only on a second, explicit `--apply`:

```bash
KIT=frameworks-com-plugins/operator-kit-1.4.0
cp -r "$KIT" ../your-repo/operator-kit        # the copy itself (kit_doctor does not copy on claude-code)
python instaladores/kit-forge-1.4.0/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo
python instaladores/kit-forge-1.4.0/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo --apply
# Codex CLI: --host codex — the installer copies the module into .agents/hpp/operator-kit
#            and each skill into .agents/skills/hpp-operator-kit-<skill>; no cp -r needed
```
The `profile` stage copies every `*.example.*` at the module root into the target, dropping
`.example` — so `profile.example.yaml` lands as `profile.yaml` (never overwritten if it
exists). The loaders read **`operator-profile.yaml`**: rename the copy (or point
`OPERATOR_PROFILE` at it), then adjust by hand: `idioma`, `paths.*`, `autonomia.default`,
`intensidade.default`, `concorrencia.teto`, `guardrails.protected_paths`/`protected_branches`,
`verificacao.done_criterios` with the real commands of your stack. Smoke test:
```bash
python operator-kit/_lib/profile_loader.py             # prints the resolved profile
python operator-kit/scripts/done_gate.py --self-test   # self-test OK
python operator-kit/scripts/done_gate.py --profile py  # runs the 'py' criteria of the profile
```
gitignore the `paths.resume_pointer` (e.g. `.claude/RESUME-NEXT.md`). Output-styles:
copy `output-styles/*.md` into the project's `.claude/output-styles/` and activate with
`/output-style`.

## What the installer detects

The `detect` stage classifies the target (read-only) with exactly these three labels:

```
greenfield    -> no prior config in the target; profile stage would copy profile.example.yaml -> profile.yaml
in-progress   -> .claude/ exists, or settings(.local).json already has hooks/statusLine, or a real
                 profile is present, or the repo has more than 3 commits: reported, never overwritten (skip-exists)
re-run        -> this kit+target pair is already in the registry (~/.claude-kits/registry.json)
```

This kit **has no `questions:`** in `kit.install.yaml` (deliberate, YAGNI) —
`operator-profile.yaml` has ~15 blocks of real config, too many to fit in discrete
installer questions; the right path is to copy the example and adjust by hand (the
`profile` stage already does the copy; anything beyond that would not be honest).

## What is safe to run again

The `profile` stage **never overwrites** a profile that already exists. All 8 hooks and
the 17 scripts degrade to safe defaults if the profile is missing or malformed (they never
break the caller). Running `kit_doctor.py install --apply` again is safe: customisation in
the profile survives.

## Manual wiring (human gate — never automatic)

> Editing `.claude/settings.local.json` is a human gate in this doctrine — automated
> sessions have an explicit lock against self-editing settings/hooks files. See
> `SETTINGS-WIRE.md` for the complete paste blocks (the 8 hooks + the statusLine).

Post-wire smoke test:
```bash
python operator-kit/hooks/autoprompt_resume.py --self-test
python operator-kit/scripts/done_gate.py --self-test
```

## Construction principle

**Reuse / generalise / activate — never duplicate (LC-3).** Most of the kit generalises
skills/hooks that already existed in the origin repo; the loop/verification mechanisms
(`ralph_gate`, `determinism_harness`, `passk_eval`, `debt_ledger`) were built from the
doctrine already codified in `rules/` (see `evolve/NOTICE-ECC.md` for credit of patterns
adopted from external sources — always a clean-room reimplementation, never a literal copy).

## `rules/` — installable doctrine (13 rules + 1 doc)

Beyond the mechanisms (scripts/hooks/skills), the kit brings the **doctrine in text**
behind them: 13 `.claude/rules/*.md` files + `docs/ANTHROPIC-STANDARDS.md`, generalised
and ready to install in any project.

**How to install:** copy `rules/*.md` into the target project's `.claude/rules/` (each one
already carries its own `Auto-Trigger`/`Keywords`/`Prioridade` header for auto-routing),
OR reference the files directly from the project's `CLAUDE.md` if you prefer central
doctrine over lazy-loading by keyword.

| Rule | Doctrine (1 line) | Mechanised by (from this kit) |
|-------|---------------------|------------------------------|
| `learned-corrections.md` (LC-1/2/3) | Audit the source live before citing a number; execute 100% when authorised; grep before creating/classifying | `scripts/live_count.py`, `scripts/audit_plan.py`, `scripts/drift_check.py`, `scripts/distill_corrections.py` |
| `stale-replay-guard.md` (LC-4) | Restored context is historical reference, not an execution queue — never re-fire what already ran | `hooks/autoprompt_resume.py`, `skills/pre-clear-boot-block` |
| `epistemic-standards.md` | Separate FACT (with source) from RECOMMENDATION; declare confidence; never invent | `skills/live-source-prover`, `scripts/live_count.py` |
| `agent-integrity.md` | Every content generated about an agent/persona must be traceable to a source, never invented | reference doctrine (no dedicated mechanism in this kit) |
| `no-secrets-in-memory.md` | Never a plaintext credential in a file that persists (memory/doc/rule) | `hooks/secret_scan_on_write.py` |
| `gateguard.md` | Facts (importers/schema/rollback) before the first Edit; rollback+authorisation+verify before destructive Bash | `hooks/snapshot_rollback_gate.py`, `hooks/project_root_confirm.py` |
| `loop-operator.md` | Pre-flight (baseline+rollback+branch) + 4 stop-conditions + triple action (pause+notice+demote) | `hooks/ralph_gate.py`, `templates/loop-charter-template.md` |
| `loop-cost-budget.md` (LC-5) | Token/cost budget is a first-class stop condition, declared BEFORE the loop runs | `hooks/ralph_gate.py` (kill-switch), `operator-profile.yaml` (`concorrencia.teto`) |
| `loop-maker-checker.md` | Whoever builds is not whoever approves; the checker runs on a different model, read-only | `skills/adversarial-refuter`, `skills/gated-improvement-proposal` |
| `loop-passk.md` | pass@k measures capability, pass^k measures regression — 1 green run proves nothing | `scripts/passk_eval.py`, `scripts/determinism_harness.py` |
| `loop-patterns-catalog.md` | Catalogue of 6 autonomous-loop architectures (which shape to use before arming one) | `templates/loop-charter-template.md` (reference when choosing the shape) |
| `agent-cognition.md` | Protocol for how an agent/persona should load identity and reason in cascade | reference doctrine (applies to projects with agents/personas) |
| `partial-autonomy-slider.md` | Autonomy as a slider (0-5) + intensity (lite/full/ultra/off) — orthogonal dimensions; promotion requires a real eval, demotion is automatic on incident | `operator-profile.yaml` (`autonomia.default`, `intensidade.default`), `hooks/operation_guard_portable.py` |
| `docs/ANTHROPIC-STANDARDS.md` | Hook/skill/sub-agent conventions (timeout, exit codes, explicit allowedTools) | applies to every hook/skill of this very kit |

## Proof / acceptance (real output, executed)

```bash
python scripts/done_gate.py --self-test
```
```
self-test OK
```
<!-- executado: 2026-09-21 · exit=0 -->

## Undo

```
- Plugin:  /plugin uninstall operator-kit@house-party-protocol
- Copy:    remove the operator-kit/ folder from the project + revert the blocks pasted into
           settings.local.json by hand (removal is a human gate too)
- Resume pointer: rm .claude/RESUME-NEXT.md (ephemeral, regenerated at the next Stop)
```

## Honest portability

- The scripts/output-styles/templates here are **100% portable** (they depend only on
  Python stdlib + PyYAML + git).
- All 8 hooks degrade to safe defaults without a profile — none breaks the caller.
- A small subset of analysis mechanisms (`drift_check.py`, `live_count.py`) produces
  richer results when the target project has its own `docs/plans/` structure — they work
  in any project, but the value grows with the convention.
