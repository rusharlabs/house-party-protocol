# Catálogo — house-party-protocol

Derivado da árvore emitida: o que cada kit instala, recurso por recurso. Regenerar com
`python instaladores/kit-forge-*/tools/catalogo_md.py . --write`.

## Recursos transversais

Documentos válidos para todos os kits: [`ARCHITECTURE.md`](ARCHITECTURE.md) · [`BENCHMARK.md`](BENCHMARK.md) · [`BRAND.md`](BRAND.md) · [`CATALOGO.html`](CATALOGO.html) · [`GITHUB-DESCRIPTION.txt`](GITHUB-DESCRIPTION.txt) · [`GRAPH-MODEL.md`](GRAPH-MODEL.md) · [`LOOPS.md`](LOOPS.md) · [`MANUAL.html`](MANUAL.html) · [`PROOF.md`](PROOF.md) · [`TIPS.md`](TIPS.md) · [`UX-INSTALL-JOURNEY.md`](UX-INSTALL-JOURNEY.md)

| kit | versão | skills | commands | agents | hooks | rules | templates | scripts |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| [kit-forge](#kit-forge) | 1.4.0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| [operator-kit](#operator-kit) | 1.4.0 | 13 | 2 | 2 | 8 | 13 | 1 | 17 |
| [continuity-kit](#continuity-kit) | 1.2.1 | 2 | 0 | 0 | 3 | 0 | 12 | 2 |
| [lane-kit](#lane-kit) | 1.2.0 | 1 | 0 | 0 | 3 | 0 | 4 | 2 |
| [health-kit](#health-kit) | 1.3.1 | 2 | 0 | 0 | 1 | 0 | 0 | 3 |
| [claude-dev-kit](#claude-dev-kit) | 1.3.1 | 8 | 0 | 0 | 1 | 0 | 0 | 2 |
| [supabase-pack](#supabase-pack) | 1.1.0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| [agent-framework-wizard](#agent-framework-wizard) | 1.1.1 | 1 | 0 | 0 | 0 | 0 | 4 | 0 |
| [dev-squad-kit](#dev-squad-kit) | 1.0.0 | 3 | 12 | 12 | 0 | 0 | 0 | 0 |
| [gotcha-memory](#gotcha-memory) | 1.0.0 | 1 | 0 | 0 | 2 | 0 | 0 | 0 |
| **total** | | **33** | **14** | **14** | **19** | **13** | **21** | **26** |

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
| `adversarial-refuter` | Antes de aceitar "feito/pronto", despacha refutadores read-only que tentam DERRUBAR a claim no disco/fonte viva |
| `claude-md-from-profile` | Gera o bloco de CLAUDE.md do projeto A PARTIR do operator-profile.yaml — piso primeiro (o que a IA nao decide), depois onde as coisas moram, as regras do pronto e o fluxo. Idempotente, com assinatura; recusa sobrescrever bloco editado a mao |
| `delegate-with-handback` | Delega tarefa longa/independente a um 2º agente com contexto explícito e gate de verificação no retorno |
| `doc-consolidator-dedup` | Funde N docs/planos sobrepostos num work-list único deduplicado, arquiva os superseded com stub-redirect — grep/ls antes de criar/classificar (LC-3) |
| `dual-report-builder` | Gera DUAS versoes da mesma analise/relatorio — INTERNA (crua, falhas expostas, dark) e EXTERNA (premium, positiva, sem expor falhas, light) — em HTML self-contained com charts CSS-puro e print-friendly. A versao externa passa por gate de registro sobrio (frases banidas do profile). Use ao produzir relatorio/dashboard que tem audiencia dupla (time interno + cliente/stakeholder). |
| `gate-sheet-collector` | Drena tudo que depende do humano para UM formulário (comando exato + o-que-destrava), sem nunca bloquear o loop |
| `gated-improvement-proposal` | Toda auto-edição do harness (regra/CLAUDE.md/prompt/hook) vira PROPOSTA que passa por gate antes de aplicar — nunca auto-merge sensível |
| `live-source-prover` | Antes de citar QUALQUER número/status/métrica, re-deriva na fonte viva e rotula "live @ HH:MM + fonte" — nunca repete dado stale |
| `parallel-dispatch` | Dispara tarefas independentes em ondas com teto de concorrência + fallback sequencial em rate-limit |
| `pre-clear-boot-block` | Antes de um /clear, emite o bloco DONE / FALTA / leia-nesta-ordem para a sessão fresca retomar com zero perda |
| `ralph-loop-driver` | Vira o agente em engenheiro-líder autônomo — lê charter+work-list, executa até esgotar, self-prompta, para nas stop-conditions |
| `rls-audit` | Audita RLS de um projeto Supabase de verdade — pg_policies por policy anon permissiva + get_advisors, não só a flag relrowsecurity |
| `supabase-edge-scaffold` | Scaffold de uma Supabase Edge Function com CORS + service-role + tratamento de erro corretos, em vez de copiar boilerplate à mão |

**Commands** — `/cancel-ralph-gate` · `/ralph-gate`

**Agents** — `refutador` · `silent-failure-hunter`

**Hooks**

| evento | script |
|---|---|
| PreToolUse · `Bash` | `operation_guard_portable.py` |
| PreToolUse · `Bash` | `snapshot_rollback_gate.py` |
| PreToolUse · `Bash` | `external_send_draft_gate.py` |
| PreToolUse · `Edit|Write|MultiEdit` | `secret_scan_on_write.py` |
| PreToolUse · `Edit|Write|MultiEdit` | `project_root_confirm.py` |
| UserPromptSubmit · `*` | `rule_capture.py` |
| Stop · `*` | `ralph_gate.py` |
| Stop · `*` | `autoprompt_resume.py` |

**Rules** — `agent-cognition` · `agent-integrity` · `epistemic-standards` · `gateguard` · `learned-corrections` · `loop-cost-budget` · `loop-maker-checker` · `loop-operator` · `loop-passk` · `loop-patterns-catalog` · `no-secrets-in-memory` · `partial-autonomy-slider` · `stale-replay-guard`

**Templates** — `loop-charter-template.md`

**Scripts** — `audit_plan.py` · `claude_md_from_profile.py` · `debt_ledger.py` · `delta_inventory.py` · `determinism_harness.py` · `distill_corrections.py` · `done_gate.py` · `drift_check.py` · `gate_sheet_panel.py` · `goal_ledger.py` · `goal_review.py` · `health_probe.py` · `live_count.py` · `passk_eval.py` · `preflight.py` · `status_now.py` · `verify_ladder.py`

**Documentos e registros** — `docs/ANTHROPIC-STANDARDS.md` · `docs/MCP-RUNBOOK.md`

## continuity-kit

Handoff-v1.1: uma sessao sobrevive a parada/clear/crash sem perder o proximo passo. Schema com git-block + re_derive_cmd (LC-1) + verify_first_cmd (LC-4), hooks Stop/PreCompact/SessionStart. Inclui doc-rollup (historico/evolucao com degradacao embutida) + pre-clear (longo-prazo + curto-prazo).

**Skills**

| skill | o que faz |
|---|---|
| `doc-rollup` | Mantém os docs de historico/evolucao do projeto (changelog, timeline narrativa, snapshot de estado, licoes, wrapup de sessao) atualizados apos uma sessao significativa — com degradacao embutida (carimbo em vez de narrativa infinita) desde o dia 1. |
| `pre-clear` | Antes de um /clear, consolida o LONGO PRAZO (doc-rollup condicional — como chegamos até aqui) e o CURTO PRAZO (handoff — o que vem depois), depois renderiza o BOOT BUNDLE. |

**Hooks**

| evento | script |
|---|---|
| (wiring pelo instalador) | `handoff_guard.py` |
| (wiring pelo instalador) | `handoff_inject.py` |
| (wiring pelo instalador) | `session_boot.py` |

**Templates** — `00-DEPLOY.template.md` · `00-ISOLAMENTO-E-RECUPERACAO.template.md` · `00-LEIA-PRIMEIRO.template.md` · `00-PROCESSES.template.md` · `00-ROLLBACK.template.md` · `00-STATE.template.md` · `00-VISION.template.md` · `LEARNINGS.template.md` · `loop-charter.template.md` · `prd-onda.template.md` · `review-onda.template.md` · `settings-continuidade.template.json`

**Scripts** — `doc_rollup.py` · `state_mirror.py`

## lane-kit

N sessoes sem colisao. Lane board, maker!=checker cross-model, lock por diretorio, git-guard e territory-guard. O checker_router detecta Codex, Cursor e Gemini e escolhe um provider diferente do maker.

**Skills**

| skill | o que faz |
|---|---|
| `lane-coordinator` | Coordena N sessões (lanes) concorrentes sobre o mesmo repo via um quadro-branco com máquina de estados (lane_board.py) — CLAIMED até MERGED, com maker≠checker cross-model enforçado em código, não em disciplina textual. |

**Hooks**

| evento | script |
|---|---|
| (wiring pelo instalador) | `lane_git_guard.py` |
| (wiring pelo instalador) | `lane_register.py` |
| (wiring pelo instalador) | `lane_territory_guard.py` |

**Templates** — `lane-registry.example.json` · `lanes.example.yaml` · `REORIENT-MAILBOX.template.md` · `status-stakeholder.template.html`

**Scripts** — `checker_router.py` · `lane_board.py`

## health-kit

Sonda de saude de servicos (http/cmd) config-driven por profile.yaml + segmento de statusline com detalhe por-servico (api:OK db:DOWN), cache-first (statusline nunca toca rede). Doutrina embarcada: health de SERVICO != health de DADO. +dashboard-builder (Grafana/SigNoz, adaptado do ECC MIT).

**Skills**

| skill | o que faz |
|---|---|
| `dashboard-builder` | Constrói dashboards de monitoramento (Grafana, SigNoz e similares) que respondem perguntas reais de operador, não "mostra toda métrica que existe". Use ao transformar uma lista de métricas em dashboard operável de verdade. |
| `health-check` | Sonda uma lista config-driven de serviços (HTTP ou comando local) e grava um cache JSON que outra ferramenta (ex.: statusline) pode ler sem tocar rede — nunca no próprio caminho quente, só gera o cache. |

**Hooks**

| evento | script |
|---|---|
| SessionStart · `*` | `bash "${CLAUDE_PLUGIN_ROOT}/hooks/pyrun.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/health_probe.py" --quiet` |

**Scripts** — `gate_sheet_panel.py` · `health_probe.py` · `wire_statusline.py`

## claude-dev-kit

Ferramentas de construir ferramentas: skill-writer, hookify, plugin-dev, teaching, wiring reversivel, secret scan, tres skills adaptadas do ECC MIT e um registro auditavel de skills externas candidatas.

**Skills**

| skill | o que faz |
|---|---|
| `architecture-decision-records` | Captura decisões arquiteturais tomadas durante a sessão como ADRs estruturados (contexto, alternativas consideradas, consequências) em docs/adr/. Use quando o usuário decide entre alternativas significativas (framework, banco, padrão) ou pergunta "por que escolhemos X?". |
| `claude-dev-setup` | Instala hooks base do Claude Code num projeto novo — wiring de settings idempotente e reversível (nunca sobrescreve config alheia sem --force) + git hook chain-preserving (nunca substitui um hook pre-commit já existente). |
| `hookify` | Cria hooks REAIS para Claude Code — scripts executáveis (stdin JSON, exit 0/1/2), registrados via hooks.json de plugin ou colados em settings.json. Use quando o usuário quer criar hook, regra de segurança, validação customizada, lifecycle hook. |
| `plugin-dev` | Empacota skills/hooks/commands num plugin Claude Code instalável — anatomia real (.claude-plugin/plugin.json + hooks/hooks.json + ${CLAUDE_PLUGIN_ROOT}), sem framework/build-step. Use quando o usuário quer criar plugin, empacotar uma extensão, ou distribuir um conjunto de skills/hooks. |
| `search-first` | Busca por biblioteca/ferramenta/padrão existente ANTES de escrever código novo — cobre registro de pacotes (npm/PyPI), MCP e GitHub, além do grep local. Use antes de criar utilitário, helper, ou integração nova. |
| `skill-scout` | Busca skills locais, no marketplace, no GitHub e na web ANTES de criar uma skill nova — evita duplicar trabalho já existente. Use quando o usuário disser "criar uma skill", "existe skill pra X?", ou você estiver prestes a sugerir criar uma skill nova. |
| `skill-writer` | Guia a criação de Agent Skills para Claude Code — estrutura, frontmatter, descrições eficazes, e validação contra o SKILL-CONTRACT. Use quando o usuário quer criar, escrever ou estruturar uma nova skill. |
| `teaching` | Transforma qualquer output técnico (criação, estrutura, decisão arquitetural) numa oportunidade de aprendizado — árvore de onde o elemento mora, raio-x de o-que-é/onde-fica/pra-que-serve, mapa de conexões, analogia de negócio, e decisões explicadas. Use sempre em output técnico para um leitor não-programador. |

**Hooks**

| evento | script |
|---|---|
| PreToolUse · `Edit|Write|MultiEdit` | `secret_scan_on_write.py` |

**Scripts** — `install_git_hook.py` · `wire_settings.py`

**Documentos e registros** — `docs/hook-template.py` · `docs/SKILL-CANDIDATES.json` · `docs/SKILL-CONTRACT.md` · `docs/skill-template.md`

## supabase-pack

rls-audit (RLS de verdade via pg_policies + get_advisors) + supabase-edge-scaffold (Edge Function TS com deno check).

**Skills**

| skill | o que faz |
|---|---|
| `rls-audit` | Audita RLS de um projeto Supabase de verdade — pg_policies por policy anon permissiva + get_advisors, não só a flag relrowsecurity |
| `supabase-edge-scaffold` | Scaffold de uma Supabase Edge Function com CORS + service-role + tratamento de erro corretos, em vez de copiar boilerplate à mão |

## agent-framework-wizard

Wizard de 6 passos (check_python->check_git->check_deps->configure->validate->generate_and_summary) para gerar o esqueleto de um agente/skill novo. --interview/--answers nao-interativos + --demo; skip-exists com --force.

**Skills**

| skill | o que faz |
|---|---|
| `agent-framework-scaffold` | Roda o wizard de 6 passos que gera o esqueleto de um projeto novo (operator-profile.yaml + templates do TEMPLATE-SET escolhidos) — método genérico (check ambiente → configurar → validar → gerar), reescrito do zero. |

**Templates** — `00-LEIA-PRIMEIRO.template.md` · `00-PROCESSES.template.md` · `00-STATE.template.md` · `00-VISION.template.md`

## dev-squad-kit

Squad com 12 papéis disponíveis como slash commands e subagents reais, tools explícitos e QA read-only, mais 3 skills de leitura/consolidação paralela token-safe. Não inclui árvore proprietária de tasks/templates.

**Skills**

| skill | o que faz |
|---|---|
| `pp-consolidate` | Parallel Process Consolidate - consolida outputs de sessoes/agentes paralelos em um veredito unico, deduplicado e verificavel |
| `pp-discovery` | Parallel Process Discovery - inventario token-safe de repositorios, pastas e artefatos grandes antes de analise profunda |
| `pp-raiox` | Parallel Process Raio-X - leitura linha-a-linha de um modulo/repo externo com evidencias, riscos e chamadas de proxima investigacao |

**Commands** — `/analyst` · `/architect` · `/data-engineer` · `/dev` · `/devops` · `/master` · `/pm` · `/po` · `/qa` · `/sm` · `/squad-creator` · `/ux-design-expert`

**Agents** — `analyst` · `architect` · `data-engineer` · `dev` · `devops` · `master` · `pm` · `po` · `qa` · `sm` · `squad-creator` · `ux-design-expert`

## gotcha-memory

Loop de aprendizado operacional standalone: a falha vira conhecimento. Depois de cada comando Bash que falha, o postflight registra o evento classificado por familia de erro; quando o mesmo tipo recorre N vezes numa janela, vira um GOTCHA -- uma licao acionavel que o preflight injeta ANTES da proxima execucao da mesma tarefa. Gotchas curated (suas regras) sao always-on. Deteccao conservadora: so sinal claro de erro conta, ambiguo nao e falha. Dois hooks WARN-only (exit 0 sempre) -- o loop de aprendizado jamais bloqueia o fluxo. stdlib only.

**Skills**

| skill | o que faz |
|---|---|
| `gotcha-memory` | Loop de aprendizado operacional — registra falhas de comandos, detecta recorrência e injeta a lição como preâmbulo antes da próxima execução da mesma tarefa. Use para consultar/seedar/depurar a memória de gotchas do projeto. |

**Hooks**

| evento | script |
|---|---|
| PreToolUse · `Bash` | `gotcha_preflight.py` |
| PostToolUse · `Bash` | `gotcha_postflight.py` |
