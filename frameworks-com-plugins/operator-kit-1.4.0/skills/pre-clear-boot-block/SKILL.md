---
name: pre-clear-boot-block
description: Antes de um /clear, emite o bloco DONE / FALTA / leia-nesta-ordem para a sessão fresca retomar com zero perda
---

> **Auto-Trigger:** Quando o contexto está crescendo, uma wave/feature fecha, ou o operador sinaliza intenção de /clear ou fim de sessão longa
> **Keywords:** "/clear", "vou limpar", "pré-clear", "boot", "handoff", "retomar", "próxima sessão", "fechar sessão"
> **Prioridade:** MÉDIA
> **Tools:** Bash, Read, Write
> **Doutrina relacionada:** `rules/stale-replay-guard.md` (LC-4: o boot bundle é referência, não fila), `rules/learned-corrections.md` (LC-1: re-verificar ao vivo no PASSO 0).

# pre-clear-boot-block — handoff de 1 bloco antes do /clear

Antes de um `/clear`, a sessão fresca precisa retomar sem perder o fio. Este comando produz um bloco auto-contido. **Reusa o `autoprompt_resume` — não re-extrai estado.**

## Contrato

**ENTRADA:** nenhuma (lê o SSoT declarado em `paths.boot_doc`/`paths.state_ssot` do `operator-profile.yaml` + `git log` local).

**SAÍDA:** bloco Markdown impresso em stdout com 3 seções (DONE / FALTA / BOOT), pronto para colar na próxima sessão; opcionalmente 1 commit (0 push).

**EXIT CODES:**

| Exit | Significado |
|---|---|
| 0 | bloco gerado e impresso |
| 2 | script não encontrado / path do hook não resolvido (instalação quebrada) |

**ESTADO QUE TOCA:**

| Arquivo/recurso | Lê/Escreve | Propósito |
|---|---|---|
| `paths.state_ssot` (ex.: `docs/plans/execucao/00-STATE.md`) | Lê | pendências abertas |
| `paths.boot_doc` | Lê | ordem de leitura sugerida |
| `git log` | Lê | últimos commits (contexto de "o que já é DONE") |
| `.git` (commit opcional) | Escreve | se `commita: true` no profile — commit por path, 0 push |

## Processo
1. **Dispare/leia o RESUME-NEXT:** `python ${CLAUDE_PLUGIN_ROOT}/hooks/autoprompt_resume.py --print` (já agrega pendências abertas do SSoT + últimos commits, honesto). Não reimplemente extração.
2. **Acrescente a ordem de leitura** (boot-docs do `paths.boot_doc` + correlatos) — "leia estes arquivos NESTA ordem".
3. **Monte o bloco** com 3 seções:
   - **DONE** — o que está duravelmente feito (commitado).
   - **FALTA** — o que resta, por owner (autônomo / gate-humano / delegável).
   - **BOOT** — ordem de leitura + o self-prompt colável.
4. **Opcionalmente commite** o estado (`commita s/n` configurável) — commit por path, 0 push.
5. **Imprima o bloco** pronto para colar na próxima sessão.

## Quando NÃO Ativar
- Sessão curta sem estado acumulado.
- Quando `save`/`autoprompt_resume` já cobrem (não duplicar handoff).
- Skill vizinha `dual-report-builder` cobre relatório de audiência dupla — não é isto (aqui é handoff de sessão, não relatório de negócio).

## Exemplos executados

```console
$ python hooks/autoprompt_resume.py --print
# RESUME-NEXT — retomada automática (autoprompt cross-sessão)

> Gerado pelo Stop hook `autoprompt_resume.py` (Operator Kit) em 2026-07-10 14:51 BRT.
> **Boot-doc canônico:** `docs\plans\...` · **SSoT:** `docs\plans\execucao\00-STATE.md`.

## PASSO 0 (re-verificar AO VIVO — LC-1)
    git log --oneline -3
    # revise as pendências abertas em docs\plans\execucao\00-STATE.md

[... bloco completo continua com DONE/FALTA/BOOT — truncado aqui por brevidade ...]
```
<!-- executado: 2026-07-10 · exit=0 -->

```console
$ python hooks/autoprompt_resume.py --self-test
self-test OK
```
<!-- executado: 2026-07-10 · exit=0 -->

```console
$ python operator-kit/hooks/autoprompt_resume.py --print
python.exe: can't open file '...\operator-kit\hooks\autoprompt_resume.py': [Errno 2] No such file or directory
```
<!-- executado: 2026-07-10 · exit=2 -->
(reprodução real do bug que esta skill tinha antes do fix: path relativo cru sem `${CLAUDE_PLUGIN_ROOT}` quebra fora do diretório do kit — por isso o passo 1 agora usa a âncora.)

## Prova

```bash
python ${CLAUDE_PLUGIN_ROOT}/hooks/autoprompt_resume.py --self-test
```

## Veja também
`autoprompt_resume.py` (insumo), `loop-charter-template` (o BOOT-PROMPT canônico), `gate-sheet-collector` (a parte FALTA → gate-humano).
