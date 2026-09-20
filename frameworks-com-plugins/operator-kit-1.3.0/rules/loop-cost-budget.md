# LOOP-COST-BUDGET — LC-5 · Orçamento de tokens/custo é condição de PARADA de 1ª classe

> **Auto-Trigger:** Ao iniciar/declarar QUALQUER loop autônomo (/goal, /loop, ralph-loop, workflow multi-onda, cron de execução contínua, dispatch de squad em batch) — ANTES de disparar a 1ª iteração; e a cada checkpoint do loop antes de continuar.
> **Keywords:** "loop", "/goal", "/loop", "ralph", "ralph-loop", "autônomo", "auto mode", "máxima capacidade", "100%", "budget", "orçamento", "token budget", "budget_tokens", "budget_custo", "custo", "cost", "kill-switch", "killswitch", "estourar orçamento", "limite semanal", "weekly limit", "rate limit", "quota", "subscription", "assinatura", "pay-per-use", "parar loop", "stop condition", "condição de parada", "circuit breaker", "onda", "batch", "iteração"
> **Prioridade:** ALTA
> **Versão:** 1.0.0 (generalizada para o operator-kit)
> **Origem:** orçamento de tokens/custo como condição de PARADA de 1ª classe, destilado em regra — registrada como **LC-5**. Extensão de `learned-corrections.md` (LC-1/LC-2/LC-3 + LC-4 em `stale-replay-guard.md`). Universal: aplica a qualquer loop autônomo. Contrapesa o LC-2 ("fazer tudo 100%" — mas dentro do orçamento).

---

## LC-5 · Todo loop declara seu orçamento ANTES de rodar; estourar o orçamento PARA o loop

Um loop autônomo sem orçamento explícito é um loop sem freio. Tokens e custo NÃO são "efeito colateral" do trabalho — são um **recurso finito** cujo esgotamento é uma **condição de parada de 1ª classe**, no mesmo nível de `done_predicate` (objetivo atingido) e `circuit breaker` (falha repetida). Um loop pode terminar por TRÊS razões legítimas: (1) **concluiu** o objetivo, (2) **travou** (circuit breaker), ou (3) **estourou o orçamento** (kill-switch de custo). A terceira é tão válida e tão obrigatória quanto as duas primeiras.

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  ORÇAMENTO ESTOURADO = PARADA LEGÍTIMA (não é falha, não é desistência)       ║
║                                                                              ║
║  done_predicate satisfeito   →  PARA · objetivo atingido                      ║
║  circuit breaker (N falhas)  →  PARA · loop travado, escalar ao operador      ║
║  budget_tokens/custo estourou →  PARA · kill-switch · reporta e aguarda        ║
║                                                                              ║
║  Loop sem budget declarado = loop PROIBIDO de iniciar.                        ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

### 1. DECLARAR o orçamento antes da 1ª iteração (obrigatório)

Todo loop autônomo declara, no seu ledger/estado/header, ANTES de disparar:

| Campo | O que é | Default conservador |
|-------|---------|---------------------|
| `budget_tokens` | Teto de tokens consumidos pelo loop inteiro (soma das iterações) | Definir explícito — sem default mágico |
| `budget_custo` | Teto de custo monetário equivalente, quando rastreável | `0` em regime subscription-only (ver §3) |
| `budget_iteracoes` | Teto de iterações/ondas antes de checkpoint obrigatório | ≤ 3 ondas (evita estourar rate-limit em rajada) |
| `budget_tempo` | Janela máxima de relógio antes de pausar e reportar | Declarar (ex: "até X" ou "N horas") |
| `consumido_ate_agora` | Contador vivo do que já foi gasto (atualizado a cada iteração) | `0` no início |

Sem esses campos declarados, o loop **não inicia** — proponha o orçamento ao operador e aguarde, ou aplique os defaults conservadores acima e DECLARE que aplicou.

### 2. KILL-SWITCH ao estourar (obrigatório)

A cada checkpoint do loop (fim de iteração/onda), ANTES de continuar:

1. Atualizar `consumido_ate_agora` (tokens/custo/iterações/tempo) com número REAL — auditado ao vivo (LC-1), nunca estimado de cabeça.
2. Comparar com o orçamento declarado.
3. **Se `consumido_ate_agora >= budget_*` em QUALQUER dimensão → KILL-SWITCH:**
   - PARAR o loop imediatamente (não iniciar a próxima iteração).
   - NÃO re-disparar, NÃO "só mais uma" (isso é exatamente o que o orçamento existe para barrar).
   - Reportar ao operador: o que foi feito, quanto custou (real), o que falta, e o orçamento adicional necessário para concluir.
   - Aguardar autorização explícita para estender o orçamento — estender orçamento é decisão do operador, nunca auto-concedida pelo loop.
4. Registrar a parada por orçamento no ledger como término legítimo (status `paused-budget`), não como falha silenciosa.

```
SE consumido >= budget em qualquer dimensão:
   → KILL-SWITCH · pare AGORA · reporte real · aguarde o operador
SENÃO:
   → continue a próxima iteração (dentro do orçamento)
```

### 3. Regime de billing declarado no profile (nunca escale sozinho para um provider mais caro)

O regime de custo (assinatura fixa vs pay-per-use vs quota compartilhada entre processos) é
uma decisão do operador, declarada no profile — não algo que o loop decide sozinho quando
aperta:

- **PROIBIDO** trocar de provider/chave para "ganhar mais orçamento" quando o loop estourar —
  o kill-switch NÃO autoriza contornar o limite dessa forma. Estourou = para e reporta; não =
  "abre a torneira paga".
- **Se o regime é assinatura com quota compartilhada** entre múltiplos processos/agentes (ex.:
  um cron 24/7 e uma sessão interativa dividindo a mesma conta), o orçamento real do loop é a
  fração da quota que ele pode consumir sem faminto os outros processos. `budget_custo` nesse
  regime é fração da quota, não dinheiro — declare quanto da janela o loop pode queimar e pare
  ao atingir.
- Se o loop precisa de mais volume e estourou a quota, a saída é **delegar a um provider/conta
  alternativa já autorizada no profile** (se houver) OU pausar e reportar — nunca escalar
  para pay-per-use sem autorização explícita do operador.
- Não confie cegamente em monitores de quota com parsing frágil — audite o consumo real ao
  vivo (LC-1) antes de declarar "quota estourada" ou "quota ok".

### 4. CONTRAPESO sadio ao LC-2 (fazer 100% — mas dentro do orçamento)

O `LC-2` manda executar de verdade, 100% em batch, sem enrolar, quando o operador autoriza
("máxima capacidade", "/goal", "concluir tudo 100%"). Esta regra NÃO contradiz o LC-2 — ela o
**delimita**:

```
LC-2:  "execute TODO o escopo, 100%, sem meias-execuções"
LC-5:  "...dentro do orçamento declarado. Estourou o orçamento ANTES de
        concluir 100%? → pare, reporte o gap real, e peça mais orçamento —
        não enrole, mas também não queime o orçamento inteiro às cegas."
```

"100% de esforço" e "100% do escopo nesta janela" não são a mesma coisa quando o recurso é
finito. O comportamento perfeito é: ir a fundo de verdade (LC-2) **até** o orçamento, e ao
bater o teto, fazer a parada honesta e rastreável (LC-5) — reportar exatamente onde parou e
quanto custou, para o operador decidir estender. Estourar o orçamento em silêncio (sem
reportar) viola LC-5; parar antes do escopo "para economizar" sem autorização viola LC-2. O
equilíbrio é: **máximo esforço dentro do envelope declarado, parada transparente no limite.**

---

## Checklist (antes de iniciar QUALQUER loop)

```
[ ] budget_tokens declarado? (sem default mágico)
[ ] budget_custo declarado? (0 em subscription-only, ou fração da quota compartilhada)
[ ] budget_iteracoes / budget_tempo declarados? (≤3 ondas default)
[ ] consumido_ate_agora inicializado e será atualizado a cada checkpoint (LC-1: real)?
[ ] kill-switch definido: estourou qualquer dimensão → PARA + reporta + aguarda o operador?
[ ] PROIBIDO trocar de provider/chave para escapar do limite sem autorização?
[ ] Fallback de volume (se houver) é uma conta/provider já autorizado, não pay-per-use surpresa?
[ ] Parada por orçamento registrada como término legítimo (paused-budget), não falha?
```

```
⚠️ LOOP SEM ORÇAMENTO = LOOP SEM FREIO = PROIBIDO INICIAR
⚠️ ORÇAMENTO ESTOURADO = PARADA DE 1ª CLASSE (igual a done_predicate / circuit breaker)
⚠️ ESTOUROU ≠ "abre a torneira paga" — o limite declarado É o limite
```

---

*Orçamento de tokens/custo como condição de parada de 1ª classe. Universal — aplica a
qualquer LLM que rode loops autônomos. Casa com `learned-corrections.md` LC-2 (contrapeso) e
`loop-operator.md` (trigger 3). Estado de quota/custo vivo = auditar AO VIVO (LC-1).*
