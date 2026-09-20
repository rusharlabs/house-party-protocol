---
name: doc-consolidator-dedup
description: Funde N docs/planos sobrepostos num work-list único deduplicado, arquiva os superseded com stub-redirect — grep/ls antes de criar/classificar (LC-3)
---

> **Auto-Trigger:** Quando há múltiplos docs/planos cobrindo o mesmo escopo, ou antes de criar um doc-mestre "novo"
> **Keywords:** "consolidar", "dedup", "docs sobrepostos", "doc-mestre", "work-list único", "arquivar", "superseded", "duplicado"
> **Prioridade:** MÉDIA
> **Tools:** Bash, Read, Grep, Glob, Write, Edit
> **Doutrina relacionada:** `rules/learned-corrections.md` (LC-3: grep/ls antes de criar ou classificar).

# doc-consolidator-dedup — um work-list, sem duplicata

Vários docs-mestre concorrentes viram ruído. Consolide num único, arquivando os superseded — **mas grep/ls ANTES de criar ou classificar qualquer coisa (LC-3)**.

## Contrato

**ENTRADA:** N paths de docs/planos candidatos a sobreposição.

**SAÍDA:** 1 doc canônico com work-list deduplicado; os superseded viram stub-redirect ("DEPRECATED → ver `<canônico>`").

**EXIT CODES** (do `audit_plan.py`, usado no passo 2 para extrair itens):

| Exit | Significado |
|---|---|
| 0 | extração ok (self-test ou extração real) |
| 1 | doc não encontrado / parsing falhou |

**ESTADO QUE TOCA:**

| Recurso | Lê/Escreve | Propósito |
|---|---|---|
| docs/planos candidatos | Lê | extrai itens (via `audit_plan.py`) |
| doc eleito canônico | Escreve (com confirmação humana) | recebe o work-list fundido |
| docs superseded | Escreve (com confirmação humana) | vira stub-redirect |

## Processo
1. **LC-3 primeiro:** `grep`/`ls`/`Glob` nos paths-alvo para confirmar o que já existe. Trate "novo doc-mestre" como hipótese — talvez já exista o canônico.
2. **Extraia os itens** de cada doc (reuse o extrator do `${CLAUDE_PLUGIN_ROOT}/scripts/audit_plan.py` — não reimplemente parsing de plano).
3. **Colapse aliases:** o MESMO item sob IDs/nomes diferentes vira uma entrada canônica (regra de alias configurável).
4. **Eleja o canônico** e funda tudo nele (work-list único deduplicado).
5. **Arquive os superseded** deixando um **stub-redirect** ("DEPRECATED → ver `<canônico>`"). Critério de superseded configurável: marker `_DEPRECATED`, data mais antiga, ou versão menor.
6. **NUNCA mova/arquive sem confirmação** (respeita o directory-contract e LC-3).

## Quando NÃO Ativar
- Um único doc / sem sobreposição real.
- Quando arquivar exigiria decisão de qual é canônico que só o operador toma → proponha, não execute.

## Exemplos executados

```console
$ python scripts/audit_plan.py --self-test
self-test OK
```
<!-- executado: 2026-07-10 · exit=0 -->

```console
$ python scripts/audit_plan.py plano-exemplo.md --no-git --json
{
  "total": 2,
  "resumo": {"FEITO": 1, "PARCIAL": 0, "AUSENTE": 1},
  "itens": [
    {"texto": "Criar `README.md`", "status": "FEITO", "on_disk": true},
    {"texto": "Criar `arquivo-que-nao-existe-nunca.xyz`", "status": "AUSENTE", "on_disk": false}
  ]
}
```
<!-- executado: 2026-07-10 · exit=0 -->
(prova o passo 2: nada é "provavelmente feito" — o que não existe no disco vira AUSENTE.)

```console
$ python scripts/audit_plan.py
uso: audit_plan.py <plano.md> [--json] [--no-git] [--repo <dir>] [--extra-regex <re>]
```
<!-- executado: 2026-07-10 · exit=2 -->
(uso inválido — sem o plano.md, o extrator não tem o que auditar; nunca "assume" um doc.)

## Prova

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/audit_plan.py --self-test
```

## Veja também
`${CLAUDE_PLUGIN_ROOT}/scripts/audit_plan.py` (extrator de deliverables), LC-3 (grep antes de criar/classificar).
