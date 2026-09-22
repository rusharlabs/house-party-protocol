[English](CATALOG.md) · [Português](CATALOG.pt-BR.md)

# Catalogue — house-party-protocol

Derived from the emitted tree: what each kit installs, resource by resource. Regenerate with
`python installers/kit-forge-*/tools/catalogo_md.py . --write`.

## Shared resources

Documents that apply to every kit: [`ARCHITECTURE.md`](ARCHITECTURE.md) · [`ARCHITECTURE.pt-BR.md`](ARCHITECTURE.pt-BR.md) · [`BENCHMARK.md`](BENCHMARK.md) · [`BENCHMARK.pt-BR.md`](BENCHMARK.pt-BR.md) · [`BRAND.md`](BRAND.md) · [`BRAND.pt-BR.md`](BRAND.pt-BR.md) · [`CONCEPTS.md`](CONCEPTS.md) · [`CONCEPTS.pt-BR.md`](CONCEPTS.pt-BR.md) · [`GITHUB-DESCRIPTION.txt`](GITHUB-DESCRIPTION.txt) · [`GRAPH-MODEL.md`](GRAPH-MODEL.md) · [`GRAPH-MODEL.pt-BR.md`](GRAPH-MODEL.pt-BR.md) · [`LOOPS.md`](LOOPS.md) · [`LOOPS.pt-BR.md`](LOOPS.pt-BR.md) · [`MANUAL.html`](MANUAL.html) · [`MANUAL.pt-BR.html`](MANUAL.pt-BR.html) · [`METHOD.md`](METHOD.md) · [`METHOD.pt-BR.md`](METHOD.pt-BR.md) · [`PROOF.md`](PROOF.md) · [`PROOF.pt-BR.md`](PROOF.pt-BR.md) · [`TIPS.md`](TIPS.md) · [`TIPS.pt-BR.md`](TIPS.pt-BR.md) · [`UX-INSTALL-JOURNEY.md`](UX-INSTALL-JOURNEY.md) · [`UX-INSTALL-JOURNEY.pt-BR.md`](UX-INSTALL-JOURNEY.pt-BR.md)

| kit | version | skills | commands | agents | hooks | rules | templates | scripts |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| [kit-forge](#kit-forge) | 1.4.1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| [operator-kit](#operator-kit) | 1.5.0 | 13 | 2 | 2 | 10 | 13 | 1 | 17 |
| [continuity-kit](#continuity-kit) | 1.3.0 | 2 | 0 | 0 | 3 | 0 | 12 | 2 |
| [lane-kit](#lane-kit) | 1.3.0 | 1 | 0 | 0 | 4 | 0 | 4 | 4 |
| [health-kit](#health-kit) | 1.3.2 | 2 | 0 | 0 | 1 | 0 | 0 | 3 |
| [claude-dev-kit](#claude-dev-kit) | 1.3.2 | 8 | 0 | 0 | 1 | 0 | 0 | 2 |
| [supabase-pack](#supabase-pack) | 1.1.1 | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| [agent-framework-wizard](#agent-framework-wizard) | 1.2.0 | 1 | 0 | 0 | 0 | 0 | 5 | 0 |
| [dev-squad-kit](#dev-squad-kit) | 1.0.1 | 3 | 12 | 12 | 0 | 0 | 0 | 0 |
| [gotcha-memory](#gotcha-memory) | 1.0.1 | 1 | 0 | 0 | 3 | 0 | 0 | 0 |
| **total** | | **33** | **14** | **14** | **23** | **13** | **22** | **28** |

## kit-forge

The IP/PII gate plus the kit assembler. ip_pii_linter + kit_assembler (with guard_origins built in) + kit_doctor (verify/install/registry, 6 stages: detect/prereqs/profile/configure/wire-suggest/smoke) + guard_origins + wire_settings + install_git_hook + skill_lint + tools/browse.py (interactive marketplace menu), single exit contract (0 ok/no-op, 1 warn, 2 block, 3 error). No --skip-lint.

**Hooks**

| event | script |
|---|---|
| (wired by the installer) | `guard_origins.py` |

## operator-kit

The harness's operational module: executable gates, governed loops, standalone pass@k/pass^k, audit/enforce policy, preflight, spec-driven planning and two read-only checkers.

**Skills**

| skill | what it does |
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

| event | script |
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

**Documents and records** — `docs/ANTHROPIC-STANDARDS.md` · `docs/ANTHROPIC-STANDARDS.pt-BR.md` · `docs/MCP-RUNBOOK.md` · `docs/MCP-RUNBOOK.pt-BR.md` · `docs/RULES-EAGER-BUDGET.md` · `docs/RULES-EAGER-BUDGET.pt-BR.md`

## continuity-kit

Handoff-v1.1: a session survives a stop/clear/crash without losing its next step. Schema with git-block + re_derive_cmd (LC-1) + verify_first_cmd (LC-4), Stop/PreCompact/SessionStart hooks. Includes doc-rollup (history/evolution with built-in degradation) + pre-clear (long-term + short-term).

**Skills**

| skill | what it does |
|---|---|
| `doc-rollup` | Keeps the project's history/evolution docs (changelog, narrative timeline, state snapshot, lessons, session wrapup) up to date after a significant session — with built-in degradation (a stamp instead of endless narrative) from day 1. |
| `pre-clear` | Before a /clear, consolidates the LONG TERM (conditional doc-rollup — how we got here) and the SHORT TERM (handoff — what comes next), then renders the BOOT BUNDLE. |

**Hooks**

| event | script |
|---|---|
| SessionStart · `*` | `handoff_inject.py` |
| Stop · `*` | `handoff_guard.py` |
| PreCompact · `*` | `handoff_guard.py` |

**Templates** — `00-DEPLOY.template.md` · `00-ISOLATION-AND-RECOVERY.template.md` · `00-PROCESSES.template.md` · `00-READ-FIRST.template.md` · `00-ROLLBACK.template.md` · `00-STATE.template.md` · `00-VISION.template.md` · `LEARNINGS.template.md` · `loop-charter.template.md` · `settings-continuidade.template.json` · `wave-prd.template.md` · `wave-review.template.md`

**Scripts** — `doc_rollup.py` · `state_mirror.py`

## lane-kit

N sessions without collisions. Lane board, cross-model maker!=checker, per-directory lock, git-guard and territory-guard. The checker_router detects Codex, Cursor and Gemini and picks a provider different from the maker's.

**Skills**

| skill | what it does |
|---|---|
| `lane-coordinator` | Coordinates N concurrent sessions (lanes) over the same repo through a whiteboard with a state machine (lane_board.py) — from CLAIMED to MERGED, with cross-model maker≠checker enforced in code, not by textual discipline. |

**Hooks**

| event | script |
|---|---|
| SessionStart · `*` | `lane_register.py` |
| PreToolUse · `Bash` | `lane_git_guard.py` |
| PreToolUse · `Edit|Write` | `lane_territory_guard.py` |
| PostToolUse · `*` | `lane_register.py --heartbeat` |

**Templates** — `lane-registry.example.json` · `lanes.example.yaml` · `REORIENT-MAILBOX.template.md` · `status-stakeholder.template.html`

**Scripts** — `checker_router.py` · `lane_board.py` · `lane_effects.py` · `lane_rescue.py`

## health-kit

Service health probe (http/cmd) driven by profile.yaml + a statusline segment with per-service detail (api:OK db:DOWN), cache-first (the statusline never touches the network). Embedded doctrine: SERVICE health != DATA health. +dashboard-builder (Grafana/SigNoz, adapted from ECC, MIT).

**Skills**

| skill | what it does |
|---|---|
| `dashboard-builder` | Builds monitoring dashboards (Grafana, SigNoz and similar) that answer real operator questions, not "show every metric that exists". Use when turning a list of metrics into a genuinely operable dashboard. |
| `health-check` | Probes a config-driven list of services (HTTP or local command) and writes a JSON cache that another tool (e.g. the statusline) can read without touching the network — never on the hot path itself, it only generates the cache. |

**Hooks**

| event | script |
|---|---|
| SessionStart · `*` | `pyrun.sh "${CLAUDE_PLUGIN_ROOT}/scripts/health_probe.py" --quiet` |

**Scripts** — `gate_sheet_panel.py` · `health_probe.py` · `wire_statusline.py`

## claude-dev-kit

Tools for building tools: skill-writer, hookify, plugin-dev, teaching, reversible wiring, secret scan, three skills adapted from ECC (MIT) and an auditable registry of candidate external skills.

**Skills**

| skill | what it does |
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

| event | script |
|---|---|
| PreToolUse · `Edit|Write|MultiEdit` | `secret_scan_on_write.py` |

**Scripts** — `install_git_hook.py` · `wire_settings.py`

**Documents and records** — `docs/hook-template.py` · `docs/SKILL-CANDIDATES.json` · `docs/SKILL-CONTRACT.md` · `docs/SKILL-CONTRACT.pt-BR.md` · `docs/skill-template.md` · `docs/skill-template.pt-BR.md`

## supabase-pack

rls-audit (real RLS via pg_policies + get_advisors) + supabase-edge-scaffold (TypeScript Edge Function with deno check).

**Skills**

| skill | what it does |
|---|---|
| `rls-audit` | Audits a Supabase project's RLS for real — pg_policies per permissive anon policy + get_advisors, not only the relrowsecurity flag |
| `supabase-edge-scaffold` | Scaffold of a Supabase Edge Function with correct CORS + service-role + error handling, instead of copying boilerplate by hand |

## agent-framework-wizard

6-step wizard (check_python->check_git->check_deps->configure->validate->generate_and_summary) that scaffolds a new agent/skill. Non-interactive --interview/--answers + --demo; skip-exists with --force.

**Skills**

| skill | what it does |
|---|---|
| `agent-framework-scaffold` | Runs the 6-step wizard that generates the skeleton of a new project (operator-profile.yaml + the chosen TEMPLATE-SET templates) — generic method (check environment → configure → validate → generate), rewritten from scratch. |

**Templates** — `00-PROCESSES.template.md` · `00-READ-FIRST.template.md` · `00-STATE.template.md` · `00-VISION.template.md` · `agents`

## dev-squad-kit

A squad of 12 roles available as slash commands and real subagents, with explicit tools and read-only QA, plus 3 token-safe parallel reading/consolidation skills. Does not include the proprietary tasks/templates tree.

**Skills**

| skill | what it does |
|---|---|
| `pp-consolidate` | Parallel Process Consolidate - consolidates the outputs of parallel sessions/agents into a single, deduplicated, verifiable verdict |
| `pp-discovery` | Parallel Process Discovery - token-safe inventory of repositories, folders and large artifacts before deep analysis |
| `pp-xray` | Parallel Process X-Ray - line-by-line reading of an external module/repo with evidence, risks and calls for the next investigation |

**Commands** — `/analyst` · `/architect` · `/data-engineer` · `/dev` · `/devops` · `/master` · `/pm` · `/po` · `/qa` · `/sm` · `/squad-creator` · `/ux-design-expert`

**Agents** — `analyst` · `architect` · `data-engineer` · `dev` · `devops` · `master` · `pm` · `po` · `qa` · `sm` · `squad-creator` · `ux-design-expert`

## gotcha-memory

Standalone operational learning loop: a failure becomes knowledge. After every Bash command that fails, the postflight records the event classified by error family; when the same type recurs N times within a window it becomes a GOTCHA -- an actionable lesson the preflight injects BEFORE the next run of the same task. Curated gotchas (your rules) are always-on. Conservative detection: only a clear error signal counts, ambiguous is not a failure. Two WARN-only hooks (always exit 0) -- the learning loop never blocks the flow. stdlib only.

**Skills**

| skill | what it does |
|---|---|
| `gotcha-memory` | Operational learning loop — records command failures, detects recurrence and injects the lesson as a preamble before the next execution of the same task. Use to query/seed/debug the project's gotcha memory. |

**Hooks**

| event | script |
|---|---|
| PreToolUse · `Bash` | `gotcha_preflight.py` |
| PostToolUse · `Bash` | `gotcha_postflight.py` |
| PostToolUseFailure · `Bash` | `gotcha_postflight.py` |
