[English](README.md) · [Português](README.pt-BR.md)

# Operator Kit

Camada portátil de **operação disciplinada com IA/Claude** — verdade-antes-de-done,
execução autônoma com guardrails, planejamento spec-driven, paralelismo com teto,
memória que se cura, comunicação direta. **Não é sobre nenhum ecossistema específico**:
cai em **qualquer projeto** e é re-tunado por **um único arquivo de config**
(`operator-profile.yaml`). Os mecanismos (scripts/hooks/skills/output-styles) são
**inertes e genéricos** — toda a personalização vive no profile. Trocar o perfil → mesmo
kit, comportamento oposto (conservador p/ cliente, agressivo p/ hacking), zero edição de
código. Não faz multi-sessão (`lane-kit`) nem handoff de sessão (`continuity-kit`) — este
kit é a camada de disciplina de execução, não de continuidade.

## Pré-requisitos + APIs externas

| Requisito | Versão mínima | Obrigatório? |
|---|---|---|
| Python | 3.9 | sim |
| PyYAML | qualquer | sim — mecanismo central de config só funciona de verdade com ela |

Serviços externos: **nenhum fixo.** `urllib.request` em `health_probe.py`/`drift_check.py`
aponta para alvos que o SEU `operator-profile.yaml` declara (`health.probes`, default
`[]`) — genérico, não um serviço embutido no kit. **Nunca `ANTHROPIC_API_KEY`** — regime
é assinatura/quota, não pay-per-use.

## O que tem nesta pasta

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

## Instalar via plugin (1 clique)

```bash
/plugin marketplace add .                            # registra o marketplace
/plugin install operator-kit@house-party-protocol             # instala + arma os 8 hooks WARN-only
```
Arma os hooks automaticamente (via `${CLAUDE_PLUGIN_ROOT}`); skills, commands e
output-styles são auto-descobertos. **statusLine** continua manual (limite do Claude
Code: plugin não embute `statusLine`) — ver `SETTINGS-WIRE.md` §3.

## Instalar por cópia

```bash
cp -r operator-kit-1.1.0 <seu-projeto>/operator-kit
cd <seu-projeto>
python operator-kit/instaladores/kit-forge/kit_doctor.py install operator-kit --target . --human
#                                                                                  ^ plano, zero escrita
python operator-kit/instaladores/kit-forge/kit_doctor.py install operator-kit --target . --apply
#                                                                                  ^ aplica de verdade
```
O estágio `profile` copia `profile.example.yaml → operator-profile.yaml` se não existir
(nunca sobrescreve). Depois, ajuste manualmente: `idioma`, `paths.*`,
`autonomia.default`, `intensidade.default`, `concorrencia.teto`,
`guardrails.protected_paths`/`protected_branches`, `verificacao.done_criterios` com os
comandos reais do seu stack. Smoke test:
```bash
python operator-kit/_lib/profile_loader.py             # imprime o profile resolvido
python operator-kit/scripts/done_gate.py --self-test   # self-test OK
python operator-kit/scripts/done_gate.py --profile py  # roda os critérios 'py' do perfil
```
gitignore do `paths.resume_pointer` (ex.: `.claude/RESUME-NEXT.md`). Output-styles:
copiar `output-styles/*.md` p/ `.claude/output-styles/` do projeto e ativar com
`/output-style`.

## O que o instalador detecta

```
greenfield    → copia profile.example.yaml -> operator-profile.yaml (estágio profile)
em-andamento  → .claude/settings.local.json já tem hooks/statusLine configurados (reportado, não sobrescrito)
re-run        → registry (~/.claude-kits/registry.json) marca re-run; operator-profile.yaml existente = skip-exists
```

Este kit **não tem `questions:`** no `kit.install.yaml` (deliberado, YAGNI) —
`operator-profile.yaml` tem ~15 blocos de config real demais para caber em perguntas
discretas de installer; o caminho certo é copiar o example e ajustar manualmente (o
estágio `profile` já faz a cópia; nada além disso seria honesto).

## O que é seguro rodar de novo

O estágio `profile` **nunca sobrescreve** `operator-profile.yaml` se ele já existir.
Todos os 8 hooks e os 16 scripts degradam para defaults seguros se o profile estiver
ausente/malformado (nunca quebram o chamador). Rodar `kit_doctor.py install --apply` de
novo é seguro: customização no profile sobrevive.

## Wiring manual (gate humano — nunca automático)

> Editar `.claude/settings.local.json` é gate humano nesta doutrina — sessões
> automatizadas têm trava explícita contra auto-editar arquivo de settings/hooks. Ver
> `SETTINGS-WIRE.md` para os blocos completos de colar (os 8 hooks + a statusLine).

Smoke test pós-wire:
```bash
python operator-kit/hooks/autoprompt_resume.py --self-test
python operator-kit/scripts/done_gate.py --self-test
```

## Princípio de construção

**Reusar / generalizar / ativar — nunca duplicar (LC-3).** A maioria do kit generaliza
skills/hooks que já existiam neste repo; os mecanismos de loop/verificação (`ralph_gate`,
`determinism_harness`, `passk_eval`, `debt_ledger`) foram construídos a partir da doutrina
já codificada em `rules/` (ver `evolve/NOTICE-ECC.md` para crédito de padrões adotados de
fontes externas — sempre reimplementação clean-room, nunca cópia literal).

## `rules/` — doutrina instalável (13 regras + 1 doc)

Além dos mecanismos (scripts/hooks/skills), o kit traz a **doutrina em texto** por trás
deles: 13 arquivos de `.claude/rules/*.md` + `docs/ANTHROPIC-STANDARDS.md`,
generalizados e prontos pra instalar em qualquer projeto.

**Como instalar:** copiar `rules/*.md` para o `.claude/rules/` do projeto-alvo (cada um
já carrega seu próprio header `Auto-Trigger`/`Keywords`/`Prioridade` para auto-routing),
OU referenciar os arquivos direto do `CLAUDE.md` do projeto se preferir doutrina central
em vez de lazy-loading por keyword.

| Regra | Doutrina (1 linha) | Mecanizada por (deste kit) |
|-------|---------------------|------------------------------|
| `learned-corrections.md` (LC-1/2/3) | Auditar a fonte ao vivo antes de citar número; executar 100% quando autorizado; grep antes de criar/classificar | `scripts/live_count.py`, `scripts/audit_plan.py`, `scripts/drift_check.py`, `scripts/distill_corrections.py` |
| `stale-replay-guard.md` (LC-4) | Contexto restaurado é referência histórica, não fila de execução — nunca re-disparar o que já rodou | `hooks/autoprompt_resume.py`, `skills/pre-clear-boot-block` |
| `epistemic-standards.md` | Separar FATO (com fonte) de RECOMENDAÇÃO; declarar confiança; nunca inventar | `skills/live-source-prover`, `scripts/live_count.py` |
| `agent-integrity.md` | Todo conteúdo gerado sobre um agente/persona deve ser rastreável à fonte, nunca inventado | doutrina de referência (sem mecanismo dedicado neste kit) |
| `no-secrets-in-memory.md` | Nunca credencial em plaintext em arquivo que persiste (memória/doc/rule) | `hooks/secret_scan_on_write.py` |
| `gateguard.md` | Fato (importadores/schema/rollback) antes do 1º Edit; rollback+autorização+verify antes de Bash destrutivo | `hooks/snapshot_rollback_gate.py`, `hooks/project_root_confirm.py` |
| `loop-operator.md` | Pré-flight (baseline+rollback+branch) + 4 stop-conditions + ação tripla (pausa+aviso+demote) | `hooks/ralph_gate.py`, `templates/loop-charter-template.md` |
| `loop-cost-budget.md` (LC-5) | Orçamento de tokens/custo é condição de parada de 1ª classe, declarada ANTES do loop rodar | `hooks/ralph_gate.py` (kill-switch), `operator-profile.yaml` (`concorrencia.teto`) |
| `loop-maker-checker.md` | Quem constrói não é quem aprova; checker roda em modelo diferente, read-only | `skills/adversarial-refuter`, `skills/gated-improvement-proposal` |
| `loop-passk.md` | pass@k mede capacidade, pass^k mede regressão — 1 run verde não prova nada | `scripts/passk_eval.py`, `scripts/determinism_harness.py` |
| `loop-patterns-catalog.md` | Catálogo de 6 arquiteturas de loop autônomo (qual formato usar antes de armar um) | `templates/loop-charter-template.md` (referência ao escolher a forma) |
| `agent-cognition.md` | Protocolo de como um agente/persona deve carregar identidade e raciocinar em cascata | doutrina de referência (aplica-se a projetos com agentes/personas) |
| `partial-autonomy-slider.md` | Autonomia em slider (0-5) + intensidade (lite/full/ultra/off) — dimensões ortogonais; promoção exige eval real, demoção é automática em incidente | `operator-profile.yaml` (`autonomia.default`, `intensidade.default`), `hooks/operation_guard_portable.py` |
| `docs/ANTHROPIC-STANDARDS.md` | Convenções de hook/skill/sub-agent (timeout, exit codes, allowedTools explícito) | aplica-se a todos os hooks/skills deste próprio kit |

## Prova / aceite (saída real, executada)

```bash
python scripts/done_gate.py --self-test
```
```
self-test OK
```
<!-- executado: 2026-07-11 · exit=0 -->

## Desfazer

```
- Plugin: /plugin uninstall operator-kit@house-party-protocol
- Cópia: remover a pasta operator-kit/ do projeto + reverter os blocos colados em
  settings.local.json manualmente (gate humano também na remoção)
- Ponteiro de retomada: rm .claude/RESUME-NEXT.md (efêmero, regenerado no próximo Stop)
```

## Portabilidade honesta

- Os scripts/output-styles/templates aqui são **100% portáteis** (só dependem de Python
  stdlib + PyYAML + git).
- Todos os 8 hooks degradam para defaults seguros sem profile — nenhum quebra o
  chamador.
- Um pequeno subconjunto de mecanismos de análise (`drift_check.py`, `live_count.py`)
  produz resultados mais ricos quando o projeto-alvo tem sua própria estrutura de
  `docs/plans/` — funcionam em qualquer projeto, mas o valor cresce com a convenção.
