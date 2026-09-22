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

As contagens abaixo foram medidas com `ls scripts | wc -l` (17) e `ls skills | wc -l` (13)
no módulo emitido.

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

## Instalar via plugin (1 clique)

```bash
/plugin marketplace add rushar-labs/house-party-protocol
/plugin install operator-kit@house-party-protocol
```
O `.claude-plugin/plugin.json` declara `hooks/hooks.json` e `commands/`: os 8 hooks são
armados automaticamente (via `${CLAUDE_PLUGIN_ROOT}`), e skills, commands, agents e
output-styles são auto-descobertos. **statusLine** continua manual (limite do Claude
Code: plugin não embute `statusLine`) — ver `SETTINGS-WIRE.md` §3.

## Instalar por cópia

Na distribuição emitida este módulo vive em `frameworks-com-plugins/operator-kit-1.4.0/`
(o diretório carrega a versão — declare-a uma vez, em `KIT`). O instalador é
`instaladores/kit-forge-1.4.0/kit_doctor.py`; rode-o da raiz da distribuição. Ele planeja
primeiro e só escreve numa segunda invocação explícita com `--apply`:

```bash
KIT=frameworks-com-plugins/operator-kit-1.4.0
cp -r "$KIT" ../your-repo/operator-kit        # the copy itself (kit_doctor does not copy on claude-code)
python instaladores/kit-forge-1.4.0/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo
python instaladores/kit-forge-1.4.0/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo --apply
# Codex CLI: --host codex — the installer copies the module into .agents/hpp/operator-kit
#            and each skill into .agents/skills/hpp-operator-kit-<skill>; no cp -r needed
```
O estágio `profile` copia todo `*.example.*` da raiz do módulo para o alvo, tirando o
`.example` — então `profile.example.yaml` chega como `profile.yaml` (nunca sobrescrito se
já existir). Os loaders leem **`operator-profile.yaml`**: renomeie a cópia (ou aponte
`OPERATOR_PROFILE` para ela) e depois ajuste manualmente: `idioma`, `paths.*`,
`autonomia.default`, `intensidade.default`, `concorrencia.teto`,
`guardrails.protected_paths`/`protected_branches`, `verificacao.done_criterios` com os
comandos reais do seu stack. Smoke test:
```bash
python operator-kit/_lib/profile_loader.py             # prints the resolved profile
python operator-kit/scripts/done_gate.py --self-test   # self-test OK
python operator-kit/scripts/done_gate.py --profile py  # runs the 'py' criteria of the profile
```
gitignore do `paths.resume_pointer` (ex.: `.claude/RESUME-NEXT.md`). Output-styles:
copiar `output-styles/*.md` p/ `.claude/output-styles/` do projeto e ativar com
`/output-style`.

## O que o instalador detecta

O estágio `detect` classifica o alvo (só leitura) com exatamente estes três rótulos:

```
greenfield    -> no prior config in the target; profile stage would copy profile.example.yaml -> profile.yaml
in-progress   -> .claude/ exists, or settings(.local).json already has hooks/statusLine, or a real
                 profile is present, or the repo has more than 3 commits: reported, never overwritten (skip-exists)
re-run        -> this kit+target pair is already in the registry (~/.claude-kits/registry.json)
```

Este kit **não tem `questions:`** no `kit.install.yaml` (deliberado, YAGNI) —
`operator-profile.yaml` tem ~15 blocos de config real demais para caber em perguntas
discretas de installer; o caminho certo é copiar o example e ajustar manualmente (o
estágio `profile` já faz a cópia; nada além disso seria honesto).

## O que é seguro rodar de novo

O estágio `profile` **nunca sobrescreve** um profile que já existe. Todos os 8 hooks e os
17 scripts degradam para defaults seguros se o profile estiver ausente/malformado (nunca
quebram o chamador). Rodar `kit_doctor.py install --apply` de novo é seguro: customização
no profile sobrevive.

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
skills/hooks que já existiam no repo de origem; os mecanismos de loop/verificação
(`ralph_gate`, `determinism_harness`, `passk_eval`, `debt_ledger`) foram construídos a
partir da doutrina já codificada em `rules/` (ver `evolve/NOTICE-ECC.md` para crédito de
padrões adotados de fontes externas — sempre reimplementação clean-room, nunca cópia
literal).

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
<!-- executado: 2026-09-21 · exit=0 -->

## Desfazer

```
- Plugin:  /plugin uninstall operator-kit@house-party-protocol
- Copy:    remove the operator-kit/ folder from the project + revert the blocks pasted into
           settings.local.json by hand (removal is a human gate too)
- Resume pointer: rm .claude/RESUME-NEXT.md (ephemeral, regenerated at the next Stop)
```

## Portabilidade honesta

- Os scripts/output-styles/templates aqui são **100% portáteis** (só dependem de Python
  stdlib + PyYAML + git).
- Todos os 8 hooks degradam para defaults seguros sem profile — nenhum quebra o
  chamador.
- Um pequeno subconjunto de mecanismos de análise (`drift_check.py`, `live_count.py`)
  produz resultados mais ricos quando o projeto-alvo tem sua própria estrutura de
  `docs/plans/` — funcionam em qualquer projeto, mas o valor cresce com a convenção.
