[English](CATALOG.md) · [Português](CATALOG.pt-BR.md)

# Catálogo — house-party-protocol

Derivado da árvore emitida: o que cada kit instala, recurso por recurso. Regenerar com
`python installers/kit-forge-*/tools/catalog_md.py . --write`.

## Recursos transversais

Documentos válidos para todos os kits: [`ARCHITECTURE.md`](ARCHITECTURE.md) · [`ARCHITECTURE.pt-BR.md`](ARCHITECTURE.pt-BR.md) · [`BENCHMARK.md`](BENCHMARK.md) · [`BENCHMARK.pt-BR.md`](BENCHMARK.pt-BR.md) · [`BRAND.md`](BRAND.md) · [`BRAND.pt-BR.md`](BRAND.pt-BR.md) · [`CONCEPTS.md`](CONCEPTS.md) · [`CONCEPTS.pt-BR.md`](CONCEPTS.pt-BR.md) · [`DESIGN.md`](DESIGN.md) · [`DESIGN.pt-BR.md`](DESIGN.pt-BR.md) · [`GITHUB-DESCRIPTION.txt`](GITHUB-DESCRIPTION.txt) · [`GRAPH-MODEL.md`](GRAPH-MODEL.md) · [`GRAPH-MODEL.pt-BR.md`](GRAPH-MODEL.pt-BR.md) · [`LOOPS.md`](LOOPS.md) · [`LOOPS.pt-BR.md`](LOOPS.pt-BR.md) · [`MANUAL.html`](MANUAL.html) · [`MANUAL.pt-BR.html`](MANUAL.pt-BR.html) · [`METHOD.md`](METHOD.md) · [`METHOD.pt-BR.md`](METHOD.pt-BR.md) · [`PROOF.md`](PROOF.md) · [`PROOF.pt-BR.md`](PROOF.pt-BR.md) · [`TIPS.md`](TIPS.md) · [`TIPS.pt-BR.md`](TIPS.pt-BR.md) · [`UX-INSTALL-JOURNEY.md`](UX-INSTALL-JOURNEY.md) · [`UX-INSTALL-JOURNEY.pt-BR.md`](UX-INSTALL-JOURNEY.pt-BR.md)

| kit | versão | skills | commands | agents | hooks | rules | templates | scripts |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| [kit-forge](#kit-forge) | 1.4.2 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| [operator-kit](#operator-kit) | 1.6.0 | 13 | 2 | 2 | 10 | 13 | 1 | 17 |
| [continuity-kit](#continuity-kit) | 1.4.0 | 2 | 0 | 0 | 3 | 0 | 12 | 2 |
| [lane-kit](#lane-kit) | 1.4.0 | 1 | 0 | 0 | 4 | 0 | 4 | 4 |
| [health-kit](#health-kit) | 1.3.3 | 2 | 0 | 0 | 1 | 0 | 0 | 3 |
| [claude-dev-kit](#claude-dev-kit) | 1.3.3 | 8 | 0 | 0 | 1 | 0 | 0 | 2 |
| [supabase-pack](#supabase-pack) | 1.1.2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| [agent-framework-wizard](#agent-framework-wizard) | 1.2.1 | 1 | 0 | 0 | 0 | 0 | 5 | 0 |
| [dev-squad-kit](#dev-squad-kit) | 1.1.0 | 3 | 12 | 12 | 0 | 0 | 0 | 0 |
| [gotcha-memory](#gotcha-memory) | 1.0.2 | 1 | 0 | 0 | 3 | 0 | 0 | 0 |
| **total** | | **33** | **14** | **14** | **23** | **13** | **22** | **28** |

## kit-forge

O gate de IP/PII + o montador de kits. ip_pii_linter + kit_assembler (com guard_origins integrado) + kit_doctor (verify/install/registry, 6 estagios: detect/prereqs/profile/configure/wire-suggest/smoke) + guard_origins + wire_settings + install_git_hook + skill_lint + tools/browse.py (menu interativo do marketplace), contrato unico de exit (0 ok/no-op, 1 warn, 2 block, 3 erro). Sem --skip-lint.

**Hooks**

| evento | script |
|---|---|
| (wiring pelo instalador) | `guard_origins.py` |

## operator-kit

Módulo operacional do harness: gates executáveis, loops governados, pass@k/pass^k standalone, política audit/enforce, preflight, planejamento spec-driven e dois checkers read-only.

**Skills**

| skill | o que faz |
|---|---|
| `adversarial-refuter` | Before accepting "done/ready", dispatches read-only refuters that try to KNOCK DOWN the claim against the disk/live source |
| `claude-md-from-profile` | Generates the project's CLAUDE.md block FROM operator-profile.yaml - floor first (what the AI does not decide), then where things live, the rules of done and the flow. Idempotent, signed; refuses to overwrite a hand-edited block |
| `delegate-with-handback` | Delegates a long/independent task to a 2nd agent with explicit context and a verification gate on the return |
| `doc-consolidator-dedup` | Merges N overlapping docs/plans into a single deduplicated work-list, archives the superseded ones with a stub-redirect — grep/ls before creating/classifying (LC-3) |
| `dual-report-builder` | Generates TWO versions of the same analysis/report — INTERNAL (raw, failures exposed, dark) and EXTERNAL (premium, positive, no failures exposed, light) — as self-contained HTML with pure-CSS charts, print-friendly. The external version goes through a sober-register gate (banned phrases from the profile). Use when producing a report/dashboard with a dual audience (internal team + client/stakeholder). |
| `gate-sheet-collector` | Drains everything that depends on the human into ONE form (exact command + what-it-unblocks), without ever blocking the loop |
| `gated-improvement-proposal` | Every self-edit of the harness (rule/CLAUDE.md/prompt/hook) becomes a PROPOSAL that passes a gate before being applied — never a sensitive auto-merge |
| `live-source-prover` | Before citing ANY number/status/metric, re-derives it at the live source and labels it "live @ HH:MM + source" — never repeats stale data |
| `parallel-dispatch` | Fires independent tasks in waves with a concurrency ceiling + sequential fallback on rate limit |
| `pre-clear-boot-block` | Before a /clear, emits the DONE / MISSING / read-in-this-order block so the fresh session resumes with zero loss |
| `ralph-loop-driver` | Turns the agent into an autonomous lead engineer — reads charter+work-list, executes until exhausted, self-prompts, stops at the stop-conditions |
| `rls-audit` | Really audits the RLS of a Supabase project — pg_policies per permissive anon policy + get_advisors, not just the relrowsecurity flag |
| `supabase-edge-scaffold` | Scaffolds a Supabase Edge Function with correct CORS + service-role + error handling, instead of copying boilerplate by hand |

**Commands** — `/cancel-ralph-gate` · `/ralph-gate`

**Agents** — `refutador` · `silent-failure-hunter`

**Hooks**

| evento | script |
|---|---|
| PreToolUse · `Bash` | `operation_guard_portable.py` |
| PreToolUse · `Bash` | `snapshot_rollback_gate.py` |
| PreToolUse · `Bash` | `external_send_draft_gate.py` |
| PreToolUse · `Bash` | `fact_force_gate.py` |
| PreToolUse · `Edit|Write|MultiEdit|NotebookEdit` | `secret_scan_on_write.py` |
| PreToolUse · `Edit|Write|MultiEdit|NotebookEdit` | `project_root_confirm.py` |
| PreToolUse · `Edit|Write|MultiEdit|NotebookEdit` | `fact_force_gate.py` |
| UserPromptSubmit · `*` | `rule_capture.py` |
| Stop · `*` | `ralph_gate.py` |
| Stop · `*` | `autoprompt_resume.py` |

**Rules** — `agent-cognition` · `agent-integrity` · `epistemic-standards` · `gateguard` · `learned-corrections` · `loop-cost-budget` · `loop-maker-checker` · `loop-operator` · `loop-passk` · `loop-patterns-catalog` · `no-secrets-in-memory` · `partial-autonomy-slider` · `stale-replay-guard`

**Templates** — `loop-charter-template.md`

**Scripts** — `audit_plan.py` · `claude_md_from_profile.py` · `debt_ledger.py` · `delta_inventory.py` · `determinism_harness.py` · `distill_corrections.py` · `done_gate.py` · `drift_check.py` · `gate_sheet_panel.py` · `goal_ledger.py` · `goal_review.py` · `health_probe.py` · `live_count.py` · `passk_eval.py` · `preflight.py` · `status_now.py` · `verify_ladder.py`

**Documentos e registros** — `docs/HOOK-SKILL-STANDARDS.md` · `docs/HOOK-SKILL-STANDARDS.pt-BR.md` · `docs/MCP-RUNBOOK.md` · `docs/MCP-RUNBOOK.pt-BR.md` · `docs/RULES-EAGER-BUDGET.md` · `docs/RULES-EAGER-BUDGET.pt-BR.md`

## continuity-kit

Handoff-v1.1: uma sessao sobrevive a parada/clear/crash sem perder o proximo passo. Schema com git-block + re_derive_cmd (todo numero carrega o comando que o re-deriva ao vivo) + verify_first_cmd (conferir ao vivo antes de repetir qualquer acao que o handoff descreve), hooks Stop/PreCompact/SessionStart. Inclui doc-rollup (historico/evolucao com degradacao embutida) + pre-clear (longo-prazo + curto-prazo).

**Skills**

| skill | o que faz |
|---|---|
| `doc-rollup` | Keeps the project's history/evolution docs (changelog, narrative timeline, state snapshot, lessons, session wrapup) up to date after a significant session — with built-in degradation (a stamp instead of endless narrative) from day 1. |
| `pre-clear` | Before a /clear, consolidates the LONG TERM (conditional doc-rollup — how we got here) and the SHORT TERM (handoff — what comes next), then renders the BOOT BUNDLE. |

**Hooks**

| evento | script |
|---|---|
| SessionStart · `*` | `handoff_inject.py` |
| Stop · `*` | `handoff_guard.py` |
| PreCompact · `*` | `handoff_guard.py` |

**Templates** — `00-DEPLOY.template.md` · `00-ISOLATION-AND-RECOVERY.template.md` · `00-PROCESSES.template.md` · `00-READ-FIRST.template.md` · `00-ROLLBACK.template.md` · `00-STATE.template.md` · `00-VISION.template.md` · `LEARNINGS.template.md` · `loop-charter.template.md` · `settings-continuidade.template.json` · `wave-prd.template.md` · `wave-review.template.md`

**Scripts** — `doc_rollup.py` · `state_mirror.py`

## lane-kit

N sessoes sem colisao. Lane board, maker!=checker cross-model, lock por diretorio, git-guard e territory-guard. O checker_router detecta Codex, Cursor e Gemini e escolhe um provider diferente do maker. Best-of-N: compete/select registram qual de N tentativas concorrentes venceu.

**Skills**

| skill | o que faz |
|---|---|
| `lane-coordinator` | Coordinates N concurrent sessions (lanes) over the same repo through a whiteboard with a state machine (lane_board.py) — from CLAIMED to MERGED, with cross-model maker≠checker enforced in code, not by textual discipline. |

**Hooks**

| evento | script |
|---|---|
| SessionStart · `*` | `lane_register.py` |
| PreToolUse · `Bash` | `lane_git_guard.py` |
| PreToolUse · `Edit|Write` | `lane_territory_guard.py` |
| PostToolUse · `*` | `lane_register.py --heartbeat` |

**Templates** — `lane-registry.example.json` · `lanes.example.yaml` · `REORIENT-MAILBOX.template.md` · `status-stakeholder.template.html`

**Scripts** — `checker_router.py` · `lane_board.py` · `lane_effects.py` · `lane_rescue.py`

## health-kit

Sonda de saude de servicos (http/cmd) config-driven por profile.yaml + segmento de statusline com detalhe por-servico (api:OK db:DOWN), cache-first (statusline nunca toca rede). Doutrina embarcada: health de SERVICO != health de DADO. +dashboard-builder (Grafana/SigNoz).

**Skills**

| skill | o que faz |
|---|---|
| `dashboard-builder` | Builds monitoring dashboards (Grafana, SigNoz and similar) that answer real operator questions, not "show every metric that exists". Use when turning a list of metrics into a genuinely operable dashboard. |
| `health-check` | Probes a config-driven list of services (HTTP or local command) and writes a JSON cache that another tool (e.g. the statusline) can read without touching the network — never on the hot path itself, it only generates the cache. |

**Hooks**

| evento | script |
|---|---|
| SessionStart · `*` | `pyrun.sh "${CLAUDE_PLUGIN_ROOT}/scripts/health_probe.py" --quiet` |

**Scripts** — `gate_sheet_panel.py` · `health_probe.py` · `wire_statusline.py`

## claude-dev-kit

Ferramentas de construir ferramentas: skill-writer, hookify, plugin-dev, teaching, wiring reversivel, secret scan, architecture-decision-records, search-first e skill-scout.

**Skills**

| skill | o que faz |
|---|---|
| `architecture-decision-records` | Captures architectural decisions made during the session as structured ADRs (context, alternatives considered, consequences) in docs/adr/. Use when the user decides between significant alternatives (framework, database, pattern) or asks "why did we choose X?". |
| `claude-dev-setup` | Installs the base Claude Code hooks in a new project - idempotent and reversible settings wiring (never overwrites someone else's config without --force) + chain-preserving git hook (never replaces an existing pre-commit hook). |
| `hookify` | Creates REAL hooks for Claude Code — executable scripts (stdin JSON, exit 0/1/2), registered via a plugin's hooks.json or pasted into settings.json. Use when the user wants to create a hook, a safety rule, a custom validation, a lifecycle hook. |
| `plugin-dev` | Packages skills/hooks/commands into an installable Claude Code plugin — the real anatomy (.claude-plugin/plugin.json + hooks/hooks.json + ${CLAUDE_PLUGIN_ROOT}), no framework/build step. Use when the user wants to create a plugin, package an extension, or distribute a set of skills/hooks. |
| `search-first` | Searches for an existing library/tool/pattern BEFORE writing new code - covers package registries (npm/PyPI), MCP and GitHub, in addition to the local grep. Use before creating a utility, helper, or new integration. |
| `skill-scout` | Searches for skills locally, in the marketplace, on GitHub and on the web BEFORE creating a new skill — avoids duplicating work that already exists. Use when the user says "create a skill", "is there a skill for X?", or you are about to suggest creating a new skill. |
| `skill-writer` | Guides the creation of Agent Skills for Claude Code — structure, frontmatter, effective descriptions, and validation against the SKILL-CONTRACT. Use when the user wants to create, write or structure a new skill. |
| `teaching` | Turns any technical output (creation, structure, architectural decision) into a learning opportunity - a tree of where the element lives, an x-ray of what-it-is/where-it-sits/what-it-is-for, a connection map, a business analogy, and explained decisions. Always use in technical output for a non-programmer reader. |

**Hooks**

| evento | script |
|---|---|
| PreToolUse · `Edit|Write|MultiEdit` | `secret_scan_on_write.py` |

**Scripts** — `install_git_hook.py` · `wire_settings.py`

**Documentos e registros** — `docs/hook-template.py` · `docs/SKILL-CONTRACT.md` · `docs/SKILL-CONTRACT.pt-BR.md` · `docs/skill-template.md` · `docs/skill-template.pt-BR.md`

## supabase-pack

rls-audit (RLS de verdade via pg_policies + get_advisors) + supabase-edge-scaffold (Edge Function TS com deno check).

**Skills**

| skill | o que faz |
|---|---|
| `rls-audit` | Audits a Supabase project's RLS for real — pg_policies per permissive anon policy + get_advisors, not only the relrowsecurity flag |
| `supabase-edge-scaffold` | Scaffold of a Supabase Edge Function with correct CORS + service-role + error handling, instead of copying boilerplate by hand |

## agent-framework-wizard

Wizard de 6 passos (check_python->check_git->check_deps->configure->validate->generate_and_summary) para gerar o esqueleto de um agente/skill novo. --interview/--answers nao-interativos + --demo; skip-exists com --force.

**Skills**

| skill | o que faz |
|---|---|
| `agent-framework-scaffold` | Runs the 6-step wizard that generates the skeleton of a new project (operator-profile.yaml + the chosen templates) — check environment → configure → validate → generate. |

**Templates** — `00-PROCESSES.template.md` · `00-READ-FIRST.template.md` · `00-STATE.template.md` · `00-VISION.template.md` · `agents`

## dev-squad-kit

Squad com 12 papéis disponíveis como slash commands e subagents reais, tools explícitos e QA read-only, mais 3 skills de leitura/consolidação paralela token-safe. Não traz árvore de tasks/templates: os comandos de papel que a esperam (*create, *task, *workflow) precisam da sua.

**Skills**

| skill | o que faz |
|---|---|
| `pp-consolidate` | Parallel Process Consolidate - consolidates the outputs of parallel sessions/agents into a single, deduplicated, verifiable verdict |
| `pp-discovery` | Parallel Process Discovery - token-safe inventory of repositories, folders and large artifacts before deep analysis |
| `pp-xray` | Parallel Process X-Ray - line-by-line reading of an external module/repo with evidence, risks and calls for the next investigation |

**Commands** — `/analyst` · `/architect` · `/data-engineer` · `/dev` · `/devops` · `/master` · `/pm` · `/po` · `/qa` · `/sm` · `/squad-creator` · `/ux-design-expert`

**Agents** — `analyst` · `architect` · `data-engineer` · `dev` · `devops` · `master` · `pm` · `po` · `qa` · `sm` · `squad-creator` · `ux-design-expert`

## gotcha-memory

Loop de aprendizado operacional standalone: a falha vira conhecimento. Depois de cada comando Bash que falha, o postflight registra o evento classificado por familia de erro; quando o mesmo tipo recorre N vezes numa janela, vira um GOTCHA -- uma licao acionavel que o preflight injeta ANTES da proxima execucao da mesma tarefa. Gotchas curated (suas regras) sao always-on. Deteccao conservadora: so sinal claro de erro conta, ambiguo nao e falha. Dois hooks WARN-only (exit 0 sempre) -- o loop de aprendizado jamais bloqueia o fluxo. stdlib only.

**Skills**

| skill | o que faz |
|---|---|
| `gotcha-memory` | Operational learning loop — records command failures, detects recurrence and injects the lesson as a preamble before the next execution of the same task. Use to query/seed/debug the project's gotcha memory. |

**Hooks**

| evento | script |
|---|---|
| PreToolUse · `Bash` | `gotcha_preflight.py` |
| PostToolUse · `Bash` | `gotcha_postflight.py` |
| PostToolUseFailure · `Bash` | `gotcha_postflight.py` |
