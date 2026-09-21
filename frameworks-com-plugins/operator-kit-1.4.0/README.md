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

```
operator-kit/
├── README.md                     ← este arquivo
├── (crie operator-profile.yaml a partir de profile.example.yaml — não versionado)
├── profile.example.yaml          ← template comentado p/ copiar em projeto novo
├── install/
│   └── kit.install.yaml          ← manifesto lido por kit_doctor.py install (6 estágios)
├── _lib/
│   ├── profile_loader.py         ← acha+lê o profile (stdlib + PyYAML). TODO mecanismo importa daqui.
│   ├── concurrency.py            ← teto de agentes simultâneos (concorrencia.teto)
│   └── launcher.py               ← resolve o launcher Python correto (nunca fixa "py")
├── scripts/                      ← 16 scripts (done_gate, verify_ladder, debt_ledger,
│                                    goal_ledger/goal_review, passk_eval, audit_plan,
│                                    determinism_harness, distill_corrections, drift_check,
│                                    health_probe, live_count, status_now, delta_inventory,
│                                    gate_sheet_panel)
├── hooks/                        ← 8 hooks (hooks.json arma todos, WARN-only): operation_guard_
│                                    portable, snapshot_rollback_gate, external_send_draft_gate,
│                                    secret_scan_on_write, project_root_confirm, rule_capture,
│                                    ralph_gate, autoprompt_resume
├── skills/                       ← 12 skills (delegate-with-handback, parallel-dispatch,
│                                    adversarial-refuter, gated-improvement-proposal,
│                                    ralph-loop-driver, pre-clear-boot-block, live-source-prover,
│                                    gate-sheet-collector, doc-consolidator-dedup,
│                                    dual-report-builder, rls-audit, supabase-edge-scaffold)
├── commands/                     ← /ralph-gate, /cancel-ralph-gate
├── evals/                        ← ralph-gate-T1-T4.sh (prova do loop)
├── evolve/                       ← instinct_promote.py + NOTICE-ECC.md (crédito de origem)
├── templates/
│   └── loop-charter-template.md  ← anatomia preenchível de um loop autônomo
├── rules/                        ← 13 regras universais (.claude/rules/*.md) — ver tabela abaixo
├── docs/
│   └── ANTHROPIC-STANDARDS.md    ← convenções de hook/skill/sub-agent
├── output-styles/
│   ├── direct-register.md        ← tom: direto, pt-BR, erro plano, frases-banidas
│   └── execute-100pct.md         ← LC-2: autorizado → executa todo o escopo em batch
├── RALPH-GATE.md                 ← doutrina do loop /ralph-gate
└── SETTINGS-WIRE.md              ← blocos prontos p/ colar em settings.local.json — GATE humano
```

## Install as a plugin (1 click)

```bash
/plugin marketplace add .                            # registra o marketplace
/plugin install operator-kit@house-party-protocol             # instala + arma os 8 hooks WARN-only
```
Wires the hooks automatically (through `${CLAUDE_PLUGIN_ROOT}`); skills, commands and
output-styles are auto-discovered. **statusLine** remains manual (a Claude Code limit: a
plugin cannot embed `statusLine`) — see `SETTINGS-WIRE.md` §3.

## Install by copy

```bash
cp -r operator-kit-1.1.0 <seu-projeto>/operator-kit
cd <seu-projeto>
python operator-kit/instaladores/kit-forge/kit_doctor.py install operator-kit --target . --human
#                                                                                  ^ plano, zero escrita
python operator-kit/instaladores/kit-forge/kit_doctor.py install operator-kit --target . --apply
#                                                                                  ^ aplica de verdade
```
The `profile` stage copies `profile.example.yaml → operator-profile.yaml` if it does not
exist (never overwrites). Then adjust by hand: `idioma`, `paths.*`,
`autonomia.default`, `intensidade.default`, `concorrencia.teto`,
`guardrails.protected_paths`/`protected_branches`, `verificacao.done_criterios` with the
real commands of your stack. Smoke test:
```bash
python operator-kit/_lib/profile_loader.py             # imprime o profile resolvido
python operator-kit/scripts/done_gate.py --self-test   # self-test OK
python operator-kit/scripts/done_gate.py --profile py  # roda os critérios 'py' do perfil
```
gitignore the `paths.resume_pointer` (e.g. `.claude/RESUME-NEXT.md`). Output-styles:
copy `output-styles/*.md` into the project's `.claude/output-styles/` and activate with
`/output-style`.

## What the installer detects

```
greenfield    → copia profile.example.yaml -> operator-profile.yaml (estágio profile)
em-andamento  → .claude/settings.local.json já tem hooks/statusLine configurados (reportado, não sobrescrito)
re-run        → registry (~/.claude-kits/registry.json) marca re-run; operator-profile.yaml existente = skip-exists
```

This kit **has no `questions:`** in `kit.install.yaml` (deliberate, YAGNI) —
`operator-profile.yaml` has ~15 blocks of real config, too many to fit in discrete
installer questions; the right path is to copy the example and adjust by hand (the
`profile` stage already does the copy; anything beyond that would not be honest).

## What is safe to run again

The `profile` stage **never overwrites** `operator-profile.yaml` if it already exists.
All 8 hooks and the 16 scripts degrade to safe defaults if the profile is missing or
malformed (they never break the caller). Running `kit_doctor.py install --apply` again is
safe: customisation in the profile survives.

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
skills/hooks that already existed in this repo; the loop/verification mechanisms
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
<!-- executado: 2026-07-11 · exit=0 -->

## Undo

```
- Plugin: /plugin uninstall operator-kit@house-party-protocol
- Cópia: remover a pasta operator-kit/ do projeto + reverter os blocos colados em
  settings.local.json manualmente (gate humano também na remoção)
- Ponteiro de retomada: rm .claude/RESUME-NEXT.md (efêmero, regenerado no próximo Stop)
```

## Honest portability

- The scripts/output-styles/templates here are **100% portable** (they depend only on
  Python stdlib + PyYAML + git).
- All 8 hooks degrade to safe defaults without a profile — none breaks the caller.
- A small subset of analysis mechanisms (`drift_check.py`, `live_count.py`) produces
  richer results when the target project has its own `docs/plans/` structure — they work
  in any project, but the value grows with the convention.
