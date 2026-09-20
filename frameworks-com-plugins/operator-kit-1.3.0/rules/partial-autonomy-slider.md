# Partial Autonomy Slider Protocol

> **Status:** ACTIVE (generalizada para o operator-kit)
> **Fonte:** Karpathy "Autonomy Slider" UX pattern (YC keynote, Jun/2025)
> **Keywords:** "autonomy" · "autonomy_level" · "human in the loop" · "auto mode" · "approve"
> **Prioridade:** ALTA

## Karpathy original

> "Build systems that can slide along a spectrum [of autonomy]. Cursor (Tab→Cmd+K→Cmd+L→Cmd+I) does this. Perplexity does this."

UX pattern: slider que regula nível de autonomia do AI · tab-complete conservador → agent mode full.

## Aplicação a um ecossistema multi-agente

Cada agente (CARGO · MINDS · CONCLAVE · SYSTEM) recebe campo `autonomy_level` (0-5) declarando quanto pode agir sem human-in-the-loop.

```yaml
# Em AGENT.md frontmatter
---
name: closer
type: cargo
autonomy_level: 2  # default conservative
autonomy_history:
  - level: 1
    start: 2026-04-01
    end: 2026-05-01
    reason: "initial onboarding"
  - level: 2
    start: 2026-05-01
    reason: "7 days clean · promoted"
---
```

## Os 6 níveis (0-5)

| Level | Nome | Comportamento | Use case |
|-------|------|---------------|----------|
| **0** | Suggest-only | Apenas propõe · NUNCA executa · o operador sempre aprova | Agentes novos · sensitive areas (contratos · pagamentos · DELETE SQL) |
| **1** | Approve-each | Executa após aprovação por ação · padrão para `awaits_max_scope` | Crons criando deliverables · novos clientes |
| **2** | Approve-batch | Aprovação em batch (N ações) · default safe | **DEFAULT para novos agents** |
| **3** | Approve-summary | Reporta sumário pós-execução · sem block | Crons rotina (briefing · digest · health) |
| **4** | Trusted-auto | Executa autonomamente · audit log obrigatório | Após 7d clean record + verifiable success |
| **5** | Full-auto | Executa + auto-recovery · só alerta em failures | Apenas após 30d clean + zero false-positive |

## Promotion criteria (subir level)

Para promover de level N para N+1:
1. **Time minimum:** 7 dias no nível atual
2. **Eval pass rate:** ≥80% nos últimos 50 outputs
3. **Zero incident:** nenhuma regressão / rollback / correção do operador
4. **Verifiability:** outputs com critério de sucesso testável (FW-AK-006)
5. **Audit trail:** logs registrados em `auth_audit` ou cron logs

Demotion (descer level) é AUTOMÁTICO em:
- Incident detected (false positive / regression / data loss)
- Correção explícita do operador ("não faz X")
- Eval pass rate cai <60%

## Conexão com um tier de autenticação de API (se houver)

Um eventual 3-tier de auth (admin/service/public) é tier de **API auth**, não autonomy level. Combinados:

```
agent.autonomy_level=4 + caller.auth_tier=service → OK (executa)
agent.autonomy_level=2 + caller.auth_tier=public  → DENY (level alto requer auth)
agent.autonomy_level=0 + qualquer caller          → propõe · não executa
```

## Implementação por fase (sugestão de rollout incremental)

### Fase 1 — piloto
- Doc canon (este arquivo) + o mecanismo que consulta `autonomy_level` antes de despachar uma ação
- Um pequeno grupo piloto de agentes/crons recebe `autonomy_level` (seeding manual)

### Fase 2 — migração
- Todos os agentes do seu ecossistema (contagem LIVE, nunca hardcode) recebem level inicial=2 (conservative)
- Job de promoção periódico (auto-promove se os critérios passam)
- Demoção automática em incidente

### Fase 3 — observabilidade
- Painel mostrando o level de cada agente
- Histórico de mudanças
- Override manual via o comando do seu canal de operação, se aplicável

## Default level inicial

Todos os agentes começam em **level 2 (Approve-batch)** exceto:
- **Sensitive areas (contratos · financeiro · DELETE):** level 0 forced
- **Heartbeat/monitoring crons (read-only):** level 4 OK
- **Health-sync (snapshot only):** level 3 OK

## Conexão DNA Karpathy

- MM-AK-009 (Autonomy Slider UX Pattern) — fonte canônica
- HEUR-AK-012 (Figure out which circuits) — jagged intelligence calibration
- FIL-AK-010 (Outsource Thinking, Not Understanding) — alguém precisa entender o que está acontecendo

## Dimensão 2 — Intensidade (lite/full/ultra/off)

> **Origem:** backlog "ponytail" (`docs/plans/2026-06-29-PONYTAIL-ANALYSIS.md` item #4) — vocabulário
> compartilhado com o resto do ecossistema, adotado aqui como doutrina do Operator Kit.

`autonomy_level` (acima) responde **"quanta aprovação humana esta ação precisa?"**. Intensidade
responde uma pergunta ORTOGONAL: **"quanta verificação/maquinaria roda por ação?"**. As duas
dimensões são independentes — um agente pode ter autonomia alta e intensidade baixa (age sozinho,
mas com pouca checagem) ou autonomia baixa e intensidade máxima (precisa aprovar cada passo, mas
quando age, verifica tudo).

```
              autonomy_level (QUEM aprova)          intensidade (QUANTO se verifica)
              ────────────────────────────          ─────────────────────────────────
level 0-5     suggest-only  →  full-auto             lite  →  full  →  ultra  (→ off)
```

| Modo | Verificação por ação | Quando usar |
|---|---|---|
| **lite** | Só o essencial — critério de aceite mínimo, sem passes extras | Iteração rápida/exploratória, prototipagem descartável |
| **full** | Verificação completa padrão (`done_gate`/`verify_ladder` nos níveis obrigatórios) | **DEFAULT** — trabalho normal |
| **ultra** | Verificação máxima — múltiplas passadas, checker cross-model sempre (`loop-maker-checker`), determinismo (`determinism_harness`) | Release-crítico, path sensível (financeiro/DELETE/engine vivo), promoção de agente a `autonomy_level` 4-5 |
| **off** | Zero verificação extra além do que a linguagem/runtime já força | **Emergência/debug apenas — NUNCA default, nunca em produção** |

**Configuração:** `intensidade.default: full` em `operator-profile.yaml` (ver seção `profile.example.yaml`
deste kit). Mecanismos que hoje leem `verificacao.*`/`ladder_score_minimo` podem futuramente escalar
o rigor com base neste campo — o escopo desta doutrina é o vocabulário + o config, não (ainda) um
consumidor automático.

**Combinação com `autonomy_level` (a matriz que importa):**

```
autonomy ALTO (4-5) + intensidade OFF   →  ⚠️ PERIGOSO — agente age sozinho E sem checar. Desencorajado
                                            explicitamente; se aparecer, tratar como incidente
                                            (demotion automática de autonomy_level, ver acima).
autonomy ALTO (4-5) + intensidade FULL  →  combinação normal de um agente "trusted" em regime.
autonomy BAIXO (0-1) + intensidade OFF  →  aceitável só em debug local, nunca contra path sensível.
autonomy BAIXO (0-1) + intensidade ULTRA→  o par mais conservador — usar em release-crítico
                                            enquanto o agente ainda não tem histórico de promoção.
```

**Contrapeso ao LC-2 (`learned-corrections.md`):** "execute 100%, sem enrolar" quando o operador
autoriza execução ampla (`/goal`, "máxima capacidade") NÃO dispensa a intensidade de verificação
escolhida. "100% de esforço" e "zero verificação" não são a mesma coisa — LC-2 manda ir a fundo
*dentro* do modo de intensidade vigente, nunca usá-lo como desculpa para rebaixar `intensidade`
para `off` sem decisão explícita.

## Anti-patterns

- ❌ **All-or-nothing:** binary `manual` vs `auto` — usar slider
- ❌ **Level 5 default:** sempre começar conservative
- ❌ **No demotion:** se algo deu ruim, level desce automaticamente
- ❌ **Level sem audit log:** sem trail = invisível regressão

## Sample agent config (post-fase 2)

```yaml
# agents/cargo/sales/closer/AGENT.md
---
name: closer
type: cargo
autonomy_level: 2
last_eval_pass_rate: 87
last_promotion: 2026-05-01
last_demotion: null
incidents_count_30d: 0
---
```

```yaml
# agents/minds/andrej-karpathy/AGENT.md
---
name: andrej-karpathy
type: mind
autonomy_level: 3  # advisory-only · safe default
last_eval_pass_rate: 95
---
```

---

*Karpathy autonomy slider adaptado a um ecossistema multi-agente.*
