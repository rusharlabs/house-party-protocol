---
name: gate-sheet-collector
description: Drena tudo que depende do humano para UM formulário (comando exato + o-que-destrava), sem nunca bloquear o loop
---

> **Auto-Trigger:** Durante um loop autônomo, ao esbarrar em algo que só o humano resolve (billing/OAuth/legal/cliente/deploy-go/secret/decisão)
> **Keywords:** "gate", "depende do humano", "preciso do operador", "aprovação", "billing", "oauth", "deploy", "secret", "formulário", "bloqueado"
> **Prioridade:** ALTA
> **Tools:** Read, Write, Edit
> **Doutrina relacionada:** `rules/learned-corrections.md` (LC-1: fonte única, sem lista paralela), `rules/gateguard.md` (gate humano antes de destrutivo).

# gate-sheet-collector — a parede vira um formulário

O que genuinamente depende do humano **nunca é desculpa para o loop parar** — vira uma linha num único formulário que o humano limpa numa sentada.

## Contrato

**ENTRADA:** item que só o humano resolve (billing/OAuth/legal/cliente/deploy-go/secret/decisão), detectado durante um loop.

**SAÍDA:** 1 linha append-only em `paths.gate_sheet`, formato `{gate · motivo · comando/passo EXATO · o-que-destrava}`.

**EXIT CODES** (validação de formato da linha, ver Prova):

| Exit | Significado |
|---|---|
| 0 | linha bate o formato `gate · motivo · comando · destrava` |
| 1 | linha malformada (faltou 1+ dos 4 campos separados por `·`) |

**ESTADO QUE TOCA:**

| Recurso | Lê/Escreve | Propósito |
|---|---|---|
| SSoT (itens marcados pelo `ralph-loop-driver`) | Lê | fonte ÚNICA dos gates — nunca 2ª lista paralela |
| `paths.gate_sheet` | Escreve (append-only) | 1 linha por gate |

## Processo
1. **Detecte o gate.** Categorias típicas: billing, OAuth/login, legal, mensagem a cliente, deploy-prod-go, rotação de secret, decisão de produto/arquitetura, edição de `settings.local.json` (classifier).
2. **NÃO bloqueie.** Deixe o item **staged** (preparado + backup quando aplicável) e siga para o próximo item autônomo.
3. **Drene para a gate-sheet** (`paths.gate_sheet`), uma linha por gate, no formato:
   `{gate · motivo · comando/passo EXATO que o humano roda · o-que-destrava ao concluir}`.
4. **Fonte única.** Drene dos itens que o `ralph-loop-driver` já marcou no SSoT — **não mantenha uma segunda lista paralela** (duas listas divergem → o erro clássico que LC-1 pega).
5. **Reporte ao final** a gate-sheet consolidada como a única coisa que falta para 100%.

## Quando NÃO Ativar
- Fora de um loop autônomo (peça a aprovação pontual na hora).
- Quando o item é, na verdade, fazível autonomamente (não rotule de gate o que você consegue fazer — prove que não dá antes).

## Exemplos executados

```console
$ python -c '
import re
line = "billing · renovar assinatura vencendo 15/07 · acessar console e renovar · destrava: crons headless voltam"
pattern = re.compile(r"^[\w-]+ · .+ · .+ · .+$")
print("formato valido:", bool(pattern.match(line)))
'
formato valido: True
```
<!-- executado: 2026-07-10 · exit=0 -->

```console
$ python -c '
import re, sys
pattern = re.compile(r"^[\w-]+ · .+ · .+ · .+$")
line = "so um texto solto sem separador"
ok = bool(pattern.match(line))
print("formato valido:", ok)
sys.exit(0 if ok else 1)
'
formato valido: False
```
<!-- executado: 2026-07-10 · exit=1 -->
(linha sem os 4 campos separados por `·` — rejeitada; é o que garante 1 formulário parseável, não prosa livre.)

```console
$ python -c '
import re
lines = ["gate1 · m1 · c1 · d1", "gate2 · m2 · c2 · d2"]
pattern = re.compile(r"^[\w-]+ · .+ · .+ · .+$")
print("todas validas:", all(pattern.match(l) for l in lines))
'
todas validas: True
```
<!-- executado: 2026-07-10 · exit=0 -->

## Prova

```bash
python -c 'import re,sys; sys.exit(0 if re.match(r"^[\w-]+ · .+ · .+ · .+$", "billing · x · y · z") else 1)'
```

## Veja também
`ralph-loop-driver` (marca os itens), `execute-100pct` output-style (a parede nunca para o loop).
