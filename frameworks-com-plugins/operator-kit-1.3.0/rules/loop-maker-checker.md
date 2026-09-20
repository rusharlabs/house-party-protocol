# LOOP-MAKER-CHECKER — Maker ≠ Checker (cross-model) + hard tool-split

> **Auto-Trigger:** Em QUALQUER loop de build (/goal, /loop, workflow agent, ciclo de geração) — antes de revisar, ANTES de push/merge e ANTES de fechar (marcar [x]) um /goal.
> **Keywords:** "maker", "checker", "review", "revisão", "revisar", "cross-model", "de-viés", "gate", "goal", "/goal", "loop", "build", "push", "merge", "fechar goal", "code-review", "verificar", "checador", "construtor"
> **Prioridade:** ALTA
> **Versão:** 1.0.0 (generalizada para o operator-kit)
> **Origem:** codifica "Maker≠Checker em modelo diferente + hard tool-split" como regra do loop autônomo.

---

## PRINCÍPIO

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   QUEM CONSTRÓI NÃO É QUEM APROVA. E QUEM APROVA RODA EM OUTRO CÉREBRO.       ║
║                                                                              ║
║   MAKER  = constrói (Opus / workflow agent que escreveu o código)            ║
║   CHECKER = revisa, em MODELO/PROVEDOR DIFERENTE, SEM poder de escrita        ║
║                                                                              ║
║   O viés do maker (auto-justificação, "looks good", cegueira ao próprio       ║
║   erro) é cancelado por um revisor que (a) não tem amor pelo código e         ║
║   (b) fisicamente não consegue "consertar e seguir" — só PODE apontar.        ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

Por que cross-model (não só "outra instância"): dois Opus compartilham os mesmos vieses de treino — um aprova o que o outro erraria igual. Um modelo de outro provedor (Codex/GPT) erra em eixos diferentes, então pega o que o maker não vê. Isto é **de-viés cross-model**, não redundância.

---

## REGRA 0 · ESCADA YAGNI — o MAKER para no degrau que se sustenta ANTES de escrever código

> **Escopo INQUEBRÁVEL:** vale SÓ para CÓDIGO (`core/`, `scripts/`, `engine/`, `hooks/`). **NUNCA** para
> `AGENT.md`/`SOUL.md`/`DNA-CONFIG`/dossiers/`MEMORY` — lá a densidade rastreável `^[FONTE]` é a feature, não bloat;
> **`agent-integrity.md` sobrepõe SEMPRE**. "Menos linhas" NÃO é métrica de sucesso (proibido importar KPI de LOC).

Antes de o MAKER escrever QUALQUER código novo, descer a escada e **parar no 1º degrau que resolve**:

```
1. PRECISA EXISTIR?            — exige código novo, ou um doc/config/1 linha resolve? (YAGNI)
2. JÁ EXISTE?                  — grep/ls/codegraph: função/script/módulo que já faz isso? → reusar.
                                 (= learned-corrections.md LC-3, tornado gate PROATIVO pré-código)
3. STDLIB / FERRAMENTA NATIVA? — Read/Write/Edit/Bash/Grep ou stdlib resolvem? (CLAUDE.md: nativo > MCP)
4. DEP JÁ INSTALADA?           — uma dependência do repo já cobre? (não adicionar dep nova por preguiça)
5. CABE EM 1 LINHA / arquivo existente? — evitar arquivo/módulo novo se um trecho serve.
6. SÓ ENTÃO                    — o MÍNIMO que resolve a tarefa REAL (não o genérico/futuro imaginado).
```

O CHECKER cross-model (REGRA 1) ganha um critério de FAIL objetivo: **"o MAKER pulou a escada?"** — criou
dep/módulo/arquivo que stdlib, código existente ou 1 linha já resolviam = over-engineering → **FAIL**.

> A escada acima é a mesma disciplina do LC-3 (`learned-corrections.md`) virada gate numerado
> pré-código — o degrau 2 ("já existe?") é literalmente o LC-3 aplicado ANTES de escrever, não
> depois de descobrir a duplicata.

---

## REGRA 1 · MAKER ≠ CHECKER, EM MODELO DIFERENTE

```
SE há um loop de build (algo foi construído/editado por um agente):
   → o CHECKER que revisa DEVE ser modelo/provedor DIFERENTE do maker.

CHECKER PREFERENCIAL = um MCP de outro provedor (ex.: Codex), sandbox read-only, SE disponível no seu ambiente
   └─ de-viés cross-model: pega o que Opus não enxerga no próprio output.

PROIBIDO:
✗ Maker Opus revisado por outro Opus (mesmo viés de treino).
✗ O próprio agente que escreveu declarar "revisado, está bom".
✗ Pular o checker "porque é simples" (é onde o erro silencioso mora — LC-1).
```

Se `mcp__codex__codex` estiver indisponível, declarar explicitamente que a revisão cross-model NÃO foi feita (não fingir que foi) e tratar o gate como FALHO até rodar.

---

## REGRA 1b · CHECKER TIMEOUT-BOX & DRAIN (quando o checker cross-model trava/indisponível)

> **Por que:** um checker cross-model indisponível/travado pode prender o loop inteiro esperando
> uma resposta que nunca chega — e esse hang costuma ser SILENCIOSO (ninguém percebe até o
> downstream inteiro estar parado).

O CHECKER cross-model (REGRA 1) tem um **TIMEOUT-BOX**. Se ele não responde dentro do orçamento:
```
1. TIMEOUT          — o checker tem teto de tempo/tentativas; NÃO esperar indefinido.
2. DEFERIR EXPLÍCITO— ao expirar, NÃO travar nem fingir review: registrar no commit/log
                      "review cross-model DEFERIDO (checker indisponível)" — verdade, não silêncio.
3. BEST-EFFORT LOGADO— o MAKER faz o self-check possível (testes/diff) e segue, marcando o gate
                      PENDENTE (NÃO ✅). push/merge/fechar-goal continuam BLOQUEADOS até o review real.
4. PING             — avisar (não hang silencioso) que o checker está down + o item ficou pendente.
```
Casa com `loop-operator.md` (stack-trace idêntico 2× = abort) e `loop-cost-budget.md` (teto). Delta: o timeout é
do **próprio checker indisponível** (não do maker) — e o deferimento vira EVIDÊNCIA logada, não falso-FEITO.

---

## REGRA 2 · O CHECKER É READ-ONLY (suggest-only FÍSICO)

```
O CHECKER NÃO recebe Write nem Edit. Só lê e reporta.
   └─ allowedTools do checker = ["Read","Glob","Grep","Bash(ro)"]  — NUNCA Write/Edit.
   └─ mcp__codex__codex roda em sandbox read-only por padrão — mantê-lo assim.

Por quê físico, não "por confiança": se o checker pudesse editar, ele
"consertaria e seguiria" — e o defeito de processo (maker cego) nunca
apareceria. Sem caneta, ele é obrigado a APONTAR. O maker (modelo original)
aplica a correção e re-submete ao checker. Loop fecha quando o checker passa.
```

Isto é "suggest-only" tornado físico — alinhado ao `partial-autonomy-slider.md`.

---

## REGRA 3 · GATE OBRIGATÓRIO — rodar o checker cross-model ANTES de:

```
[ ] git push        → NUNCA empurrar sem revisão cross-model verde.
[ ] merge (PR)      → o checker é pré-requisito do merge (soma às demais camadas de review do seu fluxo).
[ ] fechar um /goal → ANTES de marcar como concluído / declarar 'pronto' no seu ledger,
                      rodar o checker cross-model sobre o diff do goal.

SE o checker retorna FAIL ou WARNING crítico:
   → NÃO push · NÃO merge · NÃO fechar goal.
   → Maker corrige · re-submete · repete até PASS.
```

Complementa (não substitui) a sua própria verificação de que o código funciona (testes, self-test):
aquilo valida que a coisa FUNCIONA; esta regra exige que **outro cérebro** confirme, sem caneta na mão.

---

## REGRA 4 · LIGAÇÃO COM AUTONOMY-SLIDER

```
O CHECKER opera sempre como autonomy_level 0/1 (propõe · NÃO executa):
   └─ level 0 (suggest-only) = read-only físico desta regra. É o piso do checker.

O MAKER respeita seu próprio autonomy_level (`partial-autonomy-slider.md`):
   └─ Em áreas sensíveis (financeiro · contratos · DELETE · engine/cron vivo),
      maker em level 0/1 → mesmo com checker verde, push/merge ainda depende do operador.
   └─ Checker verde NUNCA promove o maker acima do seu nível — só destrava o que
      o nível já permitia.
```

---

## EXEMPLO (loop de build → gate → fechar goal)

```
1. MAKER (Opus / workflow agent) escreve scripts/foo.py + testes.
2. MAKER roda os testes localmente (verification-before-completion) → verde.
3. CHECKER cross-model (mcp__codex__codex, sandbox read-only):
     "Revise o diff de scripts/foo.py vs main. Aponte bugs, edge cases,
      violações de regra. NÃO edite — só liste achados com severidade."
4. Checker retorna: 1 WARNING (path hardcoded vs core/paths.py) + 0 FAIL.
5. WARNING crítico → MAKER corrige o path → re-submete ao checker.
6. Checker retorna PASS → SÓ AGORA: push / merge / marcar o item como concluído no seu ledger.
```

Anti-exemplo (PROIBIDO): Opus escreve, Opus relê, diz "está ótimo", dá push, fecha o goal. Mesmo viés, sem caneta tirada, gate furado.

---

## CHECKLIST RÁPIDO

```
[ ] Há build neste loop? → então há um MAKER e precisa de CHECKER.
[ ] O CHECKER é modelo/provedor DIFERENTE do maker? (preferir mcp__codex__codex)
[ ] O CHECKER está SEM Write/Edit (read-only físico)?
[ ] Rodei o checker cross-model ANTES de push / merge / fechar o /goal?
[ ] Em FAIL/WARNING crítico: maker corrigiu e re-submeteu (não empurrei mesmo assim)?
[ ] Em área sensível: respeitei autonomy_level 0/1 (gate-humano) mesmo com checker verde?
```

---

*Regra do loop autônomo. Universal — qualquer LLM que rode um loop de build deve aplicar. LC-1: provar que o checker rodou, não presumir.*
