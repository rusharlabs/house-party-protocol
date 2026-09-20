# LOOP-PASSK — pass@k (capacidade) vs pass^k (regressão) com thresholds

> **Auto-Trigger:** Em QUALQUER eval-driven (eval suite de agente/squad/skill), antes de promover um agente no autonomy-slider, e antes de declarar uma release/feature "estável".
> **Keywords:** "pass@k", "pass^k", "eval", "eval suite", "pass rate", "k=3", "threshold", "capacidade", "regressão", "regression", "flaky", "promoção", "promote", "autonomy_level", "release", "gate", "determinismo", "estabilidade"
> **Prioridade:** ALTA
> **Versão:** 1.1.0 · **Criado:** 2026-06-29 · **Atualizado:** 2026-06-30 (REGRA 4 · graders/layout/comandos do ECC eval-harness)
> **Origem:** ECC (Excellence Compounding Cycle) padrão #6 — minerado em `docs/plans/2026-06-28-ECC-VIDEOS-ADOPTION.md`. Codifica "pass@k vs pass^k com thresholds" como gate do loop autônomo (onda 1 · tarefa `loop-passk`).

---

## PRINCÍPIO

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   DUAS PERGUNTAS DIFERENTES, DOIS GATES DIFERENTES.                           ║
║                                                                              ║
║   pass@k  = "CONSEGUE fazer?"  (CAPACIDADE)                                   ║
║             passa em PELO MENOS 1 das k tentativas → o teto existe.           ║
║                                                                              ║
║   pass^k  = "faz SEMPRE?"      (REGRESSÃO / DETERMINISMO)                     ║
║             passa em TODAS as k tentativas → o piso é confiável.              ║
║                                                                              ║
║   1 run verde NÃO prova nenhum dos dois. Um run verde num agente flaky        ║
║   é sorte, não capacidade nem estabilidade.                                   ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

Por que k>1 (não "rodou uma vez, passou"): LLMs são estocásticos. Uma única run esconde flakiness — o agente pode acertar 1 vez em 5 e parecer pronto. Rodar a eval suite **k vezes** (k=3 default) separa "tem a capacidade" (pass@k) de "é confiável o bastante pra produção" (pass^k). É a diferença entre poder fazer e poder confiar.

---

## DEFINIÇÕES (com k=3 default)

```
Seja um eval suite com N cases. Rode a suite k vezes (k=3).

pass@k  (por case): o case passa em ≥1 das k tentativas.
        Métrica agregada = fração de cases com pass@k.
        Mede CAPACIDADE — "o agente é capaz de resolver isto?"

pass^k  (por case): o case passa em TODAS as k tentativas.
        Métrica agregada = fração de cases com pass^k.
        Mede REGRESSÃO/DETERMINISMO — "o agente resolve isto SEMPRE?"

Sempre: pass^k ≤ pass@k.  O gap entre os dois = ZONA DE FLAKINESS.
        Gap grande = o agente "sabe mas não confia" → não promover.
```

---

## REGRA 1 · pass@k ≥ 0.90 (em k=3) = GATE DE CAPACIDADE

```
GATE DE CAPACIDADE:  pass@k ≥ 0.90  (k=3)

Significa: em ≥90% dos cases, o agente acerta em pelo menos 1 de 3 tentativas.
   → Abaixo de 0.90 = o agente NÃO TEM a capacidade (não é flakiness, é buraco).
   → Falhou pass@k: o trabalho de IMPLEMENTAÇÃO não terminou. Não é "calibrar",
     é "ainda não sabe fazer". Voltar ao maker (ver loop-maker-checker.md).

Use pass@k para: aceitar um agente/skill NOVO como "minimamente capaz",
gate de entrada antes de qualquer promoção.
```

---

## REGRA 2 · pass^k = 1.00 (em k=3) = GATE DE REGRESSÃO (release-crítico)

```
GATE DE REGRESSÃO (release-crítico):  pass^k = 1.00  (k=3)

Significa: 100% dos cases passam em TODAS as 3 tentativas — zero flakiness.
   → Exigido ANTES de: declarar release/feature estável, marcar [x] release-crítica,
     ou subir um agente para autonomy_level 4/5 (trusted-auto / full-auto).
   → pass@k alto MAS pass^k < 1.00 = capaz porém FLAKY → NÃO release-ready.
     O gap é a zona de flakiness: corrigir a não-determinação (prompt, ferramenta,
     ordem, dependência de estado) até pass^k=1.00 OU rebaixar o escopo do gate.

Por que 1.00 e não 0.95 em release-crítico: num path crítico (financeiro, deploy,
DELETE, engine/cron vivo), 1 falha em 20 é 1 incidente real. O piso TEM que ser sólido.
```

---

## REGRA 3 · PROMOÇÃO NO AUTONOMY-SLIDER PASSA A EXIGIR pass^k

```
ANTES (partial-autonomy-slider.md, critério 2):  "Eval pass rate ≥80% nos últimos 50 outputs"
   └─ ambíguo: 80% de quê? 1 run verde por output não distingue capaz-flaky de confiável.

AGORA (refinado por esta regra):
   Promover de level N → N+1 exige, ALÉM dos outros critérios do slider:
   ┌────────────────────────────────────────────────────────────────────────┐
   │ Promover até level 3 (approve-summary):  pass@k ≥ 0.90  (k=3)           │
   │ Promover a level 4/5 (trusted/full-auto): pass^k = 1.00 (k=3)           │
   │    └─ "verifiable success" (critério 4 do slider) = pass^k=1.00, NÃO    │
   │       "1 run verde". Trusted-auto sem pass^k é confiança sem prova.     │
   └────────────────────────────────────────────────────────────────────────┘

DEMOTION: qualquer case que era pass^k=1.00 e volta a falhar (cai abaixo de 1.00)
   = regressão detectada → demotion automática (alinhado ao slider: "incident detected").
```

A "1 run verde" deixa de ser suficiente para promoção. Promoção exige rodar a eval suite k vezes e bater o threshold da faixa-alvo.

---

## REGRA 4 · MECÂNICA DE EVAL — 4 graders + layout de artefato + comandos (ECC eval-harness)

> As REGRAS 1-3 definem COMO PONTUAR (pass@k / pass^k). Esta define COMO MONTAR a eval: que grader julga cada case, ONDE o artefato vive, e os comandos. Adotado do ECC `skills/eval-harness` (repo-safe). NÃO repete os thresholds — só a mecânica.

### 4.1 · OS 4 TIPOS DE GRADER (quem decide PASS/FAIL de um case)
| # | Grader | O que é | Quando | Confiabilidade |
|---|--------|---------|--------|----------------|
| 1 | **CODE** | exit-code, `grep -q`, teste, build, schema | sucesso verificável por código. **Preferir.** | Alta — re-rodável |
| 2 | **RULE** | regex, schema, `contains`/`avoids`, formato | output textual de forma fixa (cita `^[FONTE]`? sem PII?) | Alta — só pega a FORMA |
| 3 | **MODEL** (LLM-judge) | rubric julgada por LLM (1-5) | qualidade aberta (tom, completude) | Média — estocástica; **conta na flakiness (REGRA 2)** |
| 4 | **HUMAN** | adjudicação manual | área sensível (financeiro/DELETE/cron-engine) + ambiguidade | Gate, não métrica |

```
REGRA DE OURO: CODE > RULE > MODEL > HUMAN — desce a escada só quando o de cima não serve.
 • Área sensível (autonomy level 0/1) → SEMPRE grader HUMAN no gate (segurança nunca 100% auto).
 • Case por MODEL grader = estocástico → pass^k pode cair por ruído do JUIZ, não do agente
   (investigar AMBOS antes de culpar o maker).
```

### 4.2 · LAYOUT DO ARTEFATO (onde vive)
> ⚠️ COEXISTÊNCIA, não substituição. `EVALS.yaml` + `python -m core.intelligence.evals.cli` (skill `eval-driven-development`) = CANÔNICO p/ agente/squad/mind. `.claude/evals/` abaixo = caminho LEVE p/ feature/skill sem dono-agente. NÃO migrar `EVALS.yaml` pra cá.

```
.claude/evals/
├── <feature>.md     ← DEFINIÇÃO: capability + regression cases + grader por case
├── <feature>.log    ← HISTÓRICO append-only (data, k, pass@k, pass^k, status)
└── baseline.json    ← BASELINES de regressão (o "antes" que pass^k não pode quebrar)
# Snapshot release → artifacts/audit/eval-summary-<feature>-<YYYYMMDD>.md (NÃO docs/releases/ — directory-contract)
```

### 4.3 · COMANDOS (namespaced `ecc-eval`)
> ⚠️ **Os 3 `/ecc-eval` são CONCEITUAIS (a implementar)** — NÃO há runner/binário pra eles hoje. Runner VIVO = `python -m core.intelligence.evals.cli run`. `/ecc-eval` descreve o FLUXO leve (sobre `.claude/evals/`), não um comando existente.

| Comando (conceitual) | Fluxo | Quando |
|---------|-------|--------|
| `/ecc-eval define <f>` | cria `.claude/evals/<f>.md` (cases + grader) | ANTES de codar |
| `/ecc-eval check <f>` | roda cases k=3× (REGRA 1-3), reporta pass@k/pass^k | DURANTE |
| `/ecc-eval report <f>` | snapshot `artifacts/audit/` + append `.log` | ANTES de fechar goal/release |

Casa com `loop-maker-checker` (checker cross-model + report = gate de SAÍDA) e `verification-before-completion`.

### 4.4 · EVAL ANTI-PATTERNS (do ECC — diferentes dos 4 da skill eval-driven-development)
```
✗ OVERFIT no eval (decorar cases conhecidos). Fix: cases adversariais + holdout.
✗ SÓ HAPPY-PATH. Fix: regression cases de incident REAL (audit_log link).
✗ IGNORAR custo/latência caçando pass rate. Fix: loop-cost-budget LC-5 (custo = parada 1ª classe).
✗ GRADER FLAKY no gate de release (MODEL instável decide pass^k). Fix: gate release usa CODE/RULE.
```

---

## LIGAÇÃO COM OUTRAS REGRAS

| Regra | Como se liga |
|-------|--------------|
| `eval-driven-development` (skill) | Fornece o **eval suite YAML** (N cases reais + regressões). Esta regra define COMO pontuá-lo: rodar k vezes e calcular pass@k / pass^k em vez de "rodou, passou". |
| `partial-autonomy-slider.md` | Esta regra TROCA o critério vago "pass rate ≥80% / 1 run verde" por thresholds pass@k (até level 3) e pass^k=1.00 (level 4/5). Demotion em regressão de pass^k. |
| `loop-maker-checker.md` | Falha de **capacidade** (pass@k < 0.90) = volta ao MAKER (não terminou). O CHECKER cross-model valida o diff; este gate valida o COMPORTAMENTO em k runs. Complementares. |
| `verification-before-completion` | Aquela exige que a coisa funcione UMA vez; esta exige que funcione k vezes com o piso/teto certos. |

---

## EXEMPLO

```
Eval suite do agente `closer`: 20 cases. Rodar k=3.

Resultado:
  pass@k  = 19/20 = 0.95   ✅ ≥ 0.90  → CAPACIDADE ok (passou no gate de entrada)
  pass^k  = 17/20 = 0.85   ❌ < 1.00  → 3 cases flaky (passam às vezes)

Decisão:
  • Promover até level 3? SIM (pass@k ≥ 0.90).
  • Promover a level 4 (trusted-auto)? NÃO — pass^k ≠ 1.00.
  • Declarar release-crítica estável? NÃO.
  → Caçar a não-determinação nos 3 cases flaky (prompt/ferramenta/estado),
    corrigir, re-rodar k=3 até pass^k=1.00. SÓ ENTÃO level 4 / release.
```

Anti-exemplo (PROIBIDO): rodar a eval suite 1 vez, ver verde, declarar "pass rate 100%", promover a trusted-auto. 1 run não mede flakiness — o piso (pass^k) ficou desconhecido.

---

## CHECKLIST RÁPIDO

```
[ ] Rodei a eval suite k vezes (k=3 default), não 1?
[ ] Calculei pass@k (≥1 de k) E pass^k (todas as k) por case?
[ ] Gate de capacidade: pass@k ≥ 0.90? (senão → maker, não "calibrar")
[ ] Promoção a level 4/5 OU release-crítica: pass^k = 1.00? (senão → caçar flakiness)
[ ] Gap pass@k − pass^k tratado como zona de flakiness (não ignorado)?
[ ] Case que era pass^k=1.00 e regrediu → demotion automática registrada?
```

---

*Regra do loop autônomo. Universal — qualquer LLM que rode eval-driven ou promova agentes deve aplicar. Refina `partial-autonomy-slider.md` (1 run verde → pass^k). LC-1: provar com k runs, não presumir com 1.*
