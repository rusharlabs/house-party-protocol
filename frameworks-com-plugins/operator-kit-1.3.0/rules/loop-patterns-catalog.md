# LOOP-PATTERNS-CATALOG — As 6 arquiteturas de loop autônomo mapeadas aos gates deste kit

> **Auto-Trigger:** Ao DESENHAR/ESCOLHER a arquitetura de um loop autônomo (antes de armar /goal, /loop, ralph-loop, squad em batch, workflow multi-onda, pipeline `claude -p`) — quando a pergunta é "QUAL formato de loop usar para esta tarefa?", não "este loop pode rodar?" (essa é `loop-operator.md`).
> **Keywords:** "qual loop", "que tipo de loop", "arquitetura de loop", "desenhar loop", "escolher loop", "sequential pipeline", "pipeline claude -p", "nanoclaw", "repl", "infinite agentic loop", "agentic loop", "continuous claude", "pr loop", "de-sloppify", "desloppify", "slop", "ralphinho", "rfc-dag", "rfc dag", "dag", "merge queue", "work unit", "decomposição", "decompose", "wave", "ondas", "parallel agents", "worktree loop", "catálogo de loops", "loop patterns"
> **Prioridade:** MÉDIA
> **Versão:** 1.0.0 (generalizada para o operator-kit)
> **Origem:** Destilado do catálogo público "ECC" (Excellence Compounding Cycle, github.com/affaan-m/ECC, MIT, © Affaan Mustafa) — 6 padrões de loop autônomo (Sequential Pipeline · NanoClaw REPL · Infinite Agentic Loop · Continuous Claude PR Loop · De-Sloppify · Ralphinho/RFC-DAG). Esta regra é o **CATÁLOGO DE FORMATOS** (qual loop usar); as regras `loop-*` deste kit são os **GATES de qualquer loop** (orçamento, maker≠checker, pass@k, stop-conditions, replay). Catálogo ⊕ gates = loop seguro com a forma certa.

---

## PRINCÍPIO

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   PRIMEIRO escolha a FORMA do loop (este catálogo). DEPOIS aplique os GATES   ║
║   (as rules loop-*). Forma errada = loop que mói no padrão errado; gate       ║
║   ausente = loop que mói sem freio. Os dois juntos, sempre.                  ║
║                                                                              ║
║   Todo loop deste catálogo PASSA pelos gates inquebráveis deste kit:         ║
║   • pré-flight + 4 stop-conditions ........ loop-operator.md                  ║
║   • orçamento token/custo (LC-5) .......... loop-cost-budget.md               ║
║   • maker ≠ checker cross-model ........... loop-maker-checker.md             ║
║   • pass@k / pass^k antes de promover ..... loop-passk.md                     ║
║   • contexto restaurado ≠ fila (LC-4) ..... stale-replay-guard.md             ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

## ESPECTRO DOS 6 PADRÕES (do mais simples ao mais sofisticado)

| # | Padrão | Complexidade | Melhor para |
|---|--------|--------------|-------------|
| 1 | Sequential Pipeline (`claude -p`) | Baixa | Passos de dev diários, workflow scriptado, fresh-context por etapa |
| 2 | NanoClaw REPL | Baixa | Sessão interativa persistente, contexto acumulado por turno |
| 3 | Infinite Agentic Loop | Média | Geração paralela de N variações de um spec (uniqueness por atribuição) |
| 4 | Continuous Claude PR Loop | Média | Projeto multi-dia iterativo com gate de CI + merge automático |
| 5 | De-Sloppify | Add-on | Passo de limpeza dedicado após qualquer Implementer |
| 6 | Ralphinho / RFC-DAG | Alta | Feature grande, N unidades interdependentes, merge-queue com eviction |

> ⚠️ **NÃO duplicar mecanismo:** este catálogo é referência de DESENHO (qual FORMA usar). Os
> gates que garantem que qualquer forma rode com segurança (orçamento, maker≠checker,
> anti-replay) vivem nas outras rules `loop-*` deste kit — use este catálogo para escolher a
> FORMA; use aquelas para RODAR com segurança.

---

## ÁRVORE DE DECISÃO (qual padrão usar)

```
A tarefa é uma mudança única e focada?
├─ SIM → Sequential Pipeline (1) ou NanoClaw REPL (2)
└─ NÃO → Existe spec/RFC escrito?
          ├─ SIM → Precisa de implementação PARALELA de unidades interdependentes?
          │         ├─ SIM → Ralphinho / RFC-DAG (6)
          │         └─ NÃO → Continuous Claude PR Loop (4)
          └─ NÃO → Precisa de MUITAS variações da mesma coisa?
                    ├─ SIM → Infinite Agentic Loop (3)
                    └─ NÃO → Sequential Pipeline (1) + De-Sloppify (5)
```

---

## 1 · SEQUENTIAL PIPELINE (`claude -p`)

**O que é.** O loop mais simples: quebrar o trabalho numa SEQUÊNCIA de chamadas `claude -p` não-interativas, cada uma um passo focado com prompt claro (implementar → de-sloppify → verificar → commitar). Cada chamada = janela de contexto FRESCA (zero context-bleed entre passos). `set -e` propaga exit-code e para o pipeline na falha. Suporta model-routing (`--model opus` p/ research/review, sonnet p/ implement) e `--allowedTools` para passes read-only vs write-only.

**Quando usar.** Passos de dev diários scriptados; um caminho linear conhecido; quando você quer isolamento de contexto entre etapas; integração CI/CD (é o que melhor encaixa em pipeline). NÃO use para trabalho exploratório multi-variação (→ #3) nem unidades interdependentes paralelas (→ #6).

**Liga aos gates deste kit:**
- **`loop-maker-checker.md`** — o passo "review" do pipeline DEVE ser o CHECKER cross-model, read-only, ANTES de commit/push. A REGRA 0 (escada YAGNI) governa o passo "implement".
- **`loop-cost-budget.md` (LC-5)** — cada `claude -p` consome quota; declarar `budget_iteracoes`/`budget_tempo` ANTES; o `set -e` é um freio de erro, NÃO de orçamento — adicionar o kill-switch de custo.
- **`loop-operator.md`** — pré-flight (baseline+rollback+branch) antes do 1º passo; instrução negativa é perigosa (deixa o modelo hesitante em todo o resto) — use um passo separado (#5), não um prompt restritivo.

---

## 2 · NANOCLAW REPL

**O que é.** Loop persistente: um REPL session-aware que chama `claude -p` sincronicamente com o histórico de conversa COMPLETO. Carrega histórico de um arquivo de sessão, anexa cada resposta (Markdown-como-banco), sessões sobrevivem a restart. Contexto ACUMULA por turno (≠ Sequential, que é fresco por passo).

**Quando usar.** Exploração interativa com memória de sessão; quando o contexto deve crescer entre turnos; mau encaixe em CI/CD (use #1 p/ automação).

**Liga aos gates deste kit:**
- **`stale-replay-guard.md` (LC-4)** — REPL persistente é EXATAMENTE o caso de "contexto restaurado". O histórico anexado descreve o PASSADO; NUNCA re-disparar uma ação que o histórico menciona como "a fazer" sem verificar ao vivo (idempotência).
- **`loop-cost-budget.md`** — contexto que cresce por turno = consumo de quota que cresce por turno; teto de turnos/tempo obrigatório.

---

## 3 · INFINITE AGENTIC LOOP

**O que é.** Sistema de DOIS PROMPTS p/ geração spec-driven paralela. PROMPT 1 (Orquestrador): lê o spec, escaneia o output-dir p/ achar a maior iteração, planeja, ATRIBUI a cada sub-agente uma direção criativa única + um número de iteração específico (sem conflito), gerencia ondas. PROMPT 2 (Sub-agentes): recebem spec+contexto, geram output único, salvam. Batching: 1-5 simultâneos · 6-20 em lotes de 5 · "infinite" em ondas de 3-5 com sofisticação progressiva até o contexto esgotar. **Insight-chave: uniqueness por ATRIBUIÇÃO** — o orquestrador atribui direção+número, não confia no agente p/ se auto-diferenciar (evita conceitos duplicados entre paralelos).

**Quando usar.** Gerar N variações da MESMA coisa a partir de um spec (componentes UI, criativos, opções de design); trabalho spec-driven com paralelismo. NÃO p/ mudança única (#1) nem unidades interdependentes (#6).

**Liga aos gates deste kit:**
- **`loop-operator.md`** — "ondas de 3-5" evita estourar rate-limit; o `budget_iteracoes` do pré-flight limita o "infinite". Stop-condition #1 (2 checkpoints sem progresso) corta a onda que para de produzir variação nova.
- **`loop-cost-budget.md`** — "infinite até esgotar contexto" é cost-drift por construção; converter "infinite" em `budget_iteracoes`/`budget_tokens` explícito.
- A "uniqueness por atribuição" resolve a colisão de dois agentes escrevendo o mesmo path — atribua lane/output por agente antes de disparar (ver `lane-kit`, se instalado, para um mecanismo de território explícito).

---

## 4 · CONTINUOUS CLAUDE PR LOOP

**O que é.** Script shell production-grade que roda Claude em loop contínuo: cria branch → `claude -p` → (opcional) reviewer pass → commit → push + `gh pr create` → aguarda CI → CI falhou? auto-fix pass → merge → volta p/ main → repete. **Inovação crítica: um arquivo de notas compartilhadas** persiste entre iterações (o modelo lê no início, atualiza no fim) — ponte de contexto entre invocações `claude -p` independentes. Limites: `--max-runs` · `--max-cost` · `--max-duration` · completion-signal (3 sinais consecutivos = para, evita rodar em trabalho terminado). CI-failure-recovery = pega run-id, spawna `claude -p` com contexto do log, conserta, re-aguarda.

**Quando usar.** Projeto multi-dia iterativo com gate de CI; quando você quer PR+merge automatizados. Instale scripts de terceiros só APÓS revisar o conteúdo; NUNCA pipe externo direto pra bash.

**Liga aos gates deste kit:**
- **`stale-replay-guard.md` (LC-4):** o ledger/notas compartilhadas é referência, NÃO re-disparar um item já marcado feito — idempotência.
- **`loop-cost-budget.md` (LC-5):** `--max-cost`/`--max-runs`/`--max-duration` SÃO exatamente os `budget_*` desta regra — no seu regime de billing declarado, "estourou" nunca autoriza escalar sozinho para pay-per-use.
- **`loop-maker-checker.md`:** o "reviewer pass" DEVE ser cross-model, não o mesmo modelo relendo o próprio código; gate ANTES do merge.
- **`loop-operator.md`:** "completion-signal" = o seu `done_predicate`; "auto-fix em CI-failure" — CUIDADO com stop-condition #2 (stack-trace idêntico 2× = abort, não auto-retry cego).

---

## 5 · DE-SLOPPIFY (add-on)

**O que é.** Padrão add-on p/ QUALQUER loop: após cada passo Implementer, um passo de LIMPEZA dedicado (contexto separado, foco em remover slop). Problema que resolve: um modelo em TDD leva "escreva testes" literal demais → testa o sistema de tipos, checks defensivos redundantes, testa comportamento de framework em vez de business-logic, error-handling excessivo. **Por que NÃO usar instrução negativa** ("não teste tipos"): tem efeito downstream — o modelo fica hesitante com TODO teste e pula edge-cases legítimos. **Solução:** deixe o Implementer ser thorough; depois um agente de cleanup focado remove o slop e roda a suíte. *"Dois agentes focados batem um agente restrito."*

**Quando usar.** Após qualquer passo de implementação em qualquer loop (#1, #4, #6). É um passo, não um loop.

**Liga aos gates deste kit:**
- **`loop-maker-checker.md` REGRA 0 (escada YAGNI):** De-Sloppify é o **complemento pós-código** da escada (que é pré-código). A escada impede criar slop; o de-sloppify remove o que escapou. Escopo idêntico ao da REGRA 0: vale SÓ para CÓDIGO.
- **`loop-maker-checker.md` REGRA 1:** o passo de-sloppify pode ser o próprio CHECKER cross-model apontando o slop (read-only) e o maker removendo.

---

## 6 · RALPHINHO / RFC-DRIVEN DAG ORCHESTRATION

**O que é.** O padrão mais sofisticado. RFC/PRD → DECOMPOSIÇÃO (a IA quebra em WorkUnits com DAG de dependências: `id/name/deps/acceptance/tier`) → RALPH LOOP (até 3 passes): por camada do DAG (sequencial por dependência), pipelines de qualidade PARALELOS por unidade (cada uma em worktree próprio: research→plan→implement→test→review, profundidade varia por tier trivial/small/medium/large) → MERGE QUEUE (rebase em main → testa → land OU evict; evicted re-entra com contexto do conflito). **Designs-chave:** (a) cada stage em janela de contexto SEPARADA com modelo próprio → **o revisor NUNCA escreveu o código** (elimina viés de autor); (b) merge-queue com EVICTION e contexto de conflito (re-run inteligente, não retry cego); (c) tier-driven depth (trivial pula research/review; large recebe escrutínio máximo); (d) estado resumível (persistido, não só em memória).

**Quando usar.** Feature grande; múltiplas unidades interdependentes; paralelismo necessário; conflitos de merge prováveis; spec/RFC já escrito. NÃO p/ mudança de arquivo único nem iteração rápida em uma coisa.

**Liga aos gates deste kit:**
- **`loop-maker-checker.md`:** "revisor nunca escreveu o código" = LITERALMENTE a REGRA 1 (maker ≠ checker, cross-model, read-only físico). Ralphinho é a forma multi-stage dessa regra. O timeout-box (REGRA 1b) protege contra o checker travado num pipeline longo.
- **`loop-passk.md`:** "tier-driven depth" casa com os thresholds — large tier (release-crítico) exige `pass^k = 1.00`; trivial pode parar em `pass@k ≥ 0.90`. Promoção de unidade ⇒ gate pass@k/pass^k.
- **`loop-operator.md`:** "merge-queue stall" e "eviction" = stop-condition #4 (merge-conflict → abort, NÃO auto-resolver em loop autônomo). "Ralph loop até 3 passes" = teto de iterações do pré-flight. Eviction-com-contexto ≠ blind-retry = stop-condition #2.

---

## COMBINAÇÕES (os padrões compõem)

```
1 + 5  Sequential + De-Sloppify ......... a combinação mais comum (cada implement → cleanup)
4 + 5  Continuous Claude + De-Sloppify ... --review-prompt com diretiva de de-sloppify por iteração
qualquer + verificação ................... gate antes de commit (self-test + loop-maker-checker)
6 (tiers) em loops simples ............... model-routing por complexidade (modelo leve=trivial, pesado=arquitetural)
```

---

## ANTI-PADRÕES

```
✗ Loop infinito sem condição de saída ........... → loop-cost-budget (budget_*) + loop-operator (done_predicate)
✗ Sem ponte de contexto entre iterações ......... → um ledger/notas persistentes (mas LC-4: é referência, não fila)
✗ Re-tentar a MESMA falha cegamente ............. → loop-operator stop-condition #2 (stack-trace idêntico 2× = abort)
✗ Instrução negativa em vez de cleanup pass ..... → De-Sloppify (#5) como passo separado
✗ Todos os agentes numa janela de contexto ...... → loop-maker-checker (maker ≠ checker, contextos separados)
✗ Ignorar overlap de arquivo em paralelo ........ → worktrees isoladas + uniqueness-por-atribuição (#3)
```

---

## CHECKLIST RÁPIDO (ao desenhar um loop)

```
[ ] Escolhi a FORMA pela árvore de decisão (1-6)?
[ ] Mapeei que a tarefa NÃO é melhor servida por um padrão mais simples (YAGNI de arquitetura)?
[ ] Apliquei os GATES de qualquer loop:
    [ ] loop-operator (pré-flight: baseline+rollback+branch · 4 stop-conditions)?
    [ ] loop-cost-budget (LC-5: budget_tokens/custo/iterações/tempo · kill-switch)?
    [ ] loop-maker-checker (maker ≠ checker cross-model read-only ANTES de push/merge/fechar-goal)?
    [ ] loop-passk (pass@k ≥0.90 capacidade · pass^k =1.00 antes de release/level 4-5)?
    [ ] stale-replay-guard (LC-4: contexto restaurado é referência, não re-disparar item já feito)?
[ ] De-Sloppify (#5) após cada Implementer — só p/ CÓDIGO?
[ ] Limites de loop são número/JSON ao vivo (LC-1), não "infinite" mágico?
```

---

*Catálogo de arquiteturas de loop autônomo. Universal — qualquer LLM que desenhe um loop
autônomo deve aplicar. Este é o "qual loop"; as outras rules `loop-*` são o "como rodar com
segurança". LC-1: medir ao vivo, não presumir; LC-3: não duplicar o que já existe.*
