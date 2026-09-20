---
name: adversarial-refuter
description: Antes de aceitar "feito/pronto", despacha refutadores read-only que tentam DERRUBAR a claim no disco/fonte viva
---

> **Auto-Trigger:** Ao receber um "pronto/feito/corrigido/implementado" — próprio ou de agente/workflow/cron delegado
> **Keywords:** "feito", "pronto", "concluído", "corrigido", "implementado", "done", "verificar", "tem certeza", "refutar"
> **Prioridade:** ALTA
> **Tools:** Task/Agent, Read, Glob, Grep, Bash
> **Doutrina relacionada:** `rules/loop-maker-checker.md` (checker cross-model, read-only), `rules/learned-corrections.md` (LC-1).

# adversarial-refuter — refutar antes de aceitar

O "done" mente. Em vez de confiar, despache céticos cuja **única missão é provar que a claim é FALSA**. Materializa o trato #1 do operador (LC-1) como verificação multi-agente.

## Contrato

**ENTRADA:** 1 claim falsificável (afirmação testável contra disco/fonte viva).

**SAÍDA:** veredicto — "sobrevive" (nenhum refutador conseguiu derrubar) ou "refutada" (≥1 refutador provou falsa, com o gap exato).

**EXIT CODES** (a claim vira 1+ critério do `done_gate.py` — o refutador roda o critério e reporta o resultado bruto):

| Exit | Significado |
|---|---|
| 0 | claim SOBREVIVE — critério passou, nenhuma refutação encontrada |
| 1 | claim REFUTADA — critério falhou, a claim era falsa |
| 2 | claim não-falseável / critério mal-formado (reformule antes de despachar) |

**ESTADO QUE TOCA:**

| Recurso | Lê/Escreve | Propósito |
|---|---|---|
| disco/fonte viva citada na claim | Lê (read-only) | verificação real |
| `gotcha-memory` | Escreve | registra a refutação mais forte tentada |

## Processo
1. **Formule a claim** como afirmação falsificável (ex.: "o arquivo X existe e contém Y", "a rota /Z responde 200", "o teste T passa", "o deploy trocou o backend").
2. **Despache N refutadores** (N e teto vêm de `concorrencia` do profile, default 2-3) — cada um **read-only** (allowedTools: Read/Glob/Grep/Bash só-leitura). Prompt: *"Tente PROVAR que esta claim é falsa contra o disco/fonte viva. Default = refutado se houver qualquer dúvida."*
3. **Lentes distintas** quando a claim pode falhar de vários jeitos (existe-no-disco / conteúdo-correto / endpoint-responde / teste-roda / não-é-stale).
4. **Veredicto:** aceita **só se TODAS as tentativas de refutação falharem**. Qualquer refutação bem-sucedida → **re-enfileira** o trabalho com o gap exato.
5. **Registre** a refutação mais forte tentada (vira evidência + alimenta `gotcha-memory`).

## Quando NÃO Ativar
- Mudança trivial já verificada na mesma resposta (ex.: 1 linha + teste rodado e mostrado).
- Quando não há fonte-de-verdade para confrontar (claim subjetiva).
- Sem 2º agente disponível → caia para verificação local single-pass (`verification-before-completion`).
- A claim é sobre o RETORNO de 1 delegação específica (não uma afirmação solta) → use o gate embutido em `delegate-with-handback`.

## Exemplos executados

```console
$ python -c "import os; print('claim sobrevive:', os.path.exists('ip_pii_linter.py') and 'self-test' in open('ip_pii_linter.py',encoding='utf-8').read())"
claim sobrevive: True
```
<!-- executado: 2026-07-10 · exit=0 -->
(claim: "ip_pii_linter.py existe e tem self-test" — tentativa de refutação FALHOU, claim sobrevive.)

```console
$ python -c "import os,sys; ok = os.path.exists('nao-existe-nunca.py'); print('claim REFUTADA (arquivo nao existe):', not ok); sys.exit(0 if ok else 1)"
claim REFUTADA (arquivo nao existe): True
```
<!-- executado: 2026-07-10 · exit=1 -->
(claim: "nao-existe-nunca.py existe" — refutação teve SUCESSO; exit 1 = a claim era falsa.)

```console
$ python scripts/done_gate.py "python -c \"import os; assert os.path.exists('kit_assembler.py')\""
  [OK ] (exit 0) python -c "import os; assert os.path.exists('kit_assembler.py')"

DONE-GATE: DONE (1/1 criterios)
```
<!-- executado: 2026-07-10 · exit=0 -->
(a claim vira critério do done_gate — o mecanismo comum a `delegate-with-handback`/`gated-improvement-proposal`.)

## Prova

```bash
python -c "import os,sys; sys.exit(0 if os.path.exists('SKILL.md') else 1)"
```
