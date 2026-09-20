---
name: claude-dev-setup
description: Instala hooks base do Claude Code num projeto novo — wiring de settings idempotente e reversível (nunca sobrescreve config alheia sem --force) + git hook chain-preserving (nunca substitui um hook pre-commit já existente).
---

> **Auto-Trigger:** Quando o usuário pede para configurar Claude Code num projeto novo, instalar hooks base, ou "preparar este repo pro Claude Code".
> **Keywords:** "setup claude code", "instalar hooks", "configurar projeto novo", "wire settings", "hook pre-commit", "claude dev kit"
> **Prioridade:** MÉDIA
> **Tools:** Bash, Read

## Quando NÃO Ativar
- Projeto já tem `.claude/settings.json` wired do jeito que o usuário quer — rode só `wire_settings.py` com `--force` se REALMENTE quiser sobrescrever, nunca por padrão.
- Precisa de guardrails específicos de autonomia/verificação/loop — isso é o `operator-kit` completo, não este kit enxuto.

## Contrato

**ENTRADA:** `settings.json`/`settings.local.json` alvo (para `wire_settings.py`) + um `.git/hooks/<nome>` alvo (para `install_git_hook.py`).

**SAÍDA:** settings wired (idempotente) + git hook encadeado (chain-preserving).

**EXIT CODES:**

| Exit | Significado |
|---|---|
| 0 | wired/encadeado com sucesso, ou já estava (no-op) |
| 1 | conflito sem `--force` (settings) — nada sobrescrito |
| 3 | erro (target ausente, payload ausente) |

**ESTADO QUE TOCA:**

| Recurso | Lê/Escreve | Propósito |
|---|---|---|
| `settings.json`/`settings.local.json` alvo | Lê+Escreve (com backup `.bak-<timestamp>`) | wiring aditivo |
| `.git/hooks/<nome>` | Lê+Escreve | chain-preserving (preserva o original como `.pre-kitforge`) |

## Processo
1. **Wire os hooks base** (secret-scan em Edit/Write) num settings de teste primeiro:
   ```bash
   python scripts/wire_settings.py --target /caminho/settings-copy.json --spec hooks/wiring-spec.yaml
   ```
2. **Confirme idempotência** rodando de novo — deve dar `no-op`, byte-idêntico.
3. **Instale o git hook** SEM medo de perder o hook que já existe:
   ```bash
   python scripts/install_git_hook.py --repo . --hook-name pre-commit --payload hooks/meu-payload.sh
   ```
4. **Se precisar desfazer** o wiring de settings:
   ```bash
   python scripts/wire_settings.py --undo --target /caminho/settings-copy.json
   ```

## Exemplos executados

```console
$ python scripts/install_git_hook.py --repo /tmp/projeto-teste --hook-name pre-commit --payload payload.sh
{"status": "chained", "hook": ".../pre-commit", "preserved_original": ".../pre-commit.pre-kitforge", "payload": ".../pre-commit.kitforge-payload"}
```
<!-- executado: 2026-07-10 · exit=0 -->
(hook pre-commit JÁ existente é preservado como `.pre-kitforge`, não sobrescrito.)

```console
$ python scripts/wire_settings.py --target conflict-settings.json --spec statusline-only-spec.yaml
{"status": "warn", "changed": [], "warnings": ["statusLine já ocupado por outra config; use --force para sobrescrever (atual: 'outro-dono-ja-configurou-isso')"]}
```
<!-- executado: 2026-07-10 · exit=1 -->
(conflito SEM `--force` — nada é sobrescrito; é a correção do defeito conhecido de `wire_statusline.py:47-49` que sobrescrevia silenciosamente.)

```console
$ sh .git/hooks/pre-commit log.txt && cat log.txt
original-pre-commit-ran
claude-dev-kit-payload-ran
```
<!-- executado: 2026-07-10 · exit=0 -->
(o original roda PRIMEIRO — se ele falhar, `set -e` aborta ANTES do payload novo rodar.)

```console
$ bash evals/hook-chain-test.sh
[OK] hook original + payload novo, ambos rodaram, original PRIMEIRO (chain-preserving provado)
```
<!-- executado: 2026-07-10 · exit=0 -->

## Prova

```bash
python scripts/install_git_hook.py --self-test
```
