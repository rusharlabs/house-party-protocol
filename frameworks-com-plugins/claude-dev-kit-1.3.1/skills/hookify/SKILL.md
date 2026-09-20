---
name: hookify
description: Cria hooks REAIS para Claude Code — scripts executáveis (stdin JSON, exit 0/1/2), registrados via hooks.json de plugin ou colados em settings.json. Use quando o usuário quer criar hook, regra de segurança, validação customizada, lifecycle hook.
---

> **Auto-Trigger:** Quando o usuário quiser criar um hook, uma regra de segurança automática, uma validação customizada, ou um lifecycle hook (PreToolUse/PostToolUse/SessionStart/Stop/etc.).
> **Keywords:** "hook", "criar hook", "lifecycle", "safety rule", "validação", "regra de segurança", "pre-tool", "post-tool", "bloquear comando"
> **Prioridade:** ALTA
> **Tools:** Read, Write, Edit, Glob, Grep, Bash

## Quando NÃO Ativar
- Discussões sobre hooks existentes sem intenção de criar novos, ou debugging de um hook já implementado (leia o script direto, não recrie).
- **Criar uma SKILL** (SKILL.md acionada por keyword/contexto) — use `skill-writer` deste mesmo kit; skill ≠ hook (skill é instrução pro modelo seguir, hook é código que roda automaticamente no ciclo de vida da ferramenta).
- **Empacotar hooks num plugin distribuível** — depois de criar o hook, use `plugin-dev` deste mesmo kit para o `.claude-plugin/plugin.json` + `hooks.json` que o instala.

## Core Purpose

Criar hooks REAIS: **scripts executáveis** (não arquivos `.md` com frontmatter) que o Claude Code invoca em eventos do ciclo de vida, recebendo um payload JSON via **stdin** e comunicando a decisão via **exit code** (+ opcionalmente um JSON de saída).

## Contrato

**ENTRADA:** payload JSON via stdin — o shape varia por evento, mas tipicamente inclui `tool_name`, `tool_input.{...}`, `session_id`, `hook_event_name`.

**SAÍDA:** exit code (obrigatório) + opcionalmente texto em stdout/stderr ou JSON estruturado (`hookSpecificOutput`/`decision`/`permissionDecision`, conforme o evento).

**EXIT CODES** (o mecanismo REAL do Claude Code — não `mode: warn|block` em frontmatter):

| Exit | Significado |
|---|---|
| 0 | ok — silencioso, OU imprime aviso/injeta contexto SEM bloquear (modo WARN-only, o padrão desta doutrina) |
| 1 | erro NÃO-bloqueante — aparece como aviso, o fluxo segue |
| 2 | erro BLOQUEANTE (só faz efeito em `PreToolUse`) — stderr volta pro Claude, a ferramenta NÃO executa |

**ESTADO QUE TOCA:**

| Recurso | Lê/Escreve | Propósito |
|---|---|---|
| stdin | Lê | payload JSON do evento |
| `<plugin>/hooks/hooks.json` (modo plugin) | Escreve | registro declarativo, resolvido via `${CLAUDE_PLUGIN_ROOT}` |
| `.claude/settings.json`/`settings.local.json` (modo manual) | Escreve (colado pelo operador — gate humano) | registro direto, sem plugin |

## Eventos disponíveis

| Evento | Quando dispara |
|---|---|
| `SessionStart` | Início de sessão |
| `UserPromptSubmit` | Usuário envia uma mensagem |
| `PreToolUse` | Antes de uma ferramenta executar (única fase onde exit 2 bloqueia) |
| `PostToolUse` | Depois de uma ferramenta executar |
| `Stop` | Fim de sessão/resposta |
| `PreCompact` | Antes de compactar/limpar contexto |
| `SubagentStop` | Quando um subagente termina |
| `Notification` | Eventos de notificação |

`matcher` (só relevante em `PreToolUse`/`PostToolUse`): regex/pipe de nomes de ferramenta, ex. `"Bash"` ou `"Edit|Write|MultiEdit"`.

## Processo

### 1. Escreva o script (stdin → decisão → exit code)
Use `docs/hook-template.py` deste kit como scaffold — já tem a estrutura `decide(payload) -> (exit_code, mensagem)` separada de `main()` (facilita testar sem precisar simular um processo real) e um `--self-test`.

### 2. Escolha WARN-only (default) ou BLOCK (exceção)
WARN-only (exit 0 sempre, mensagem em stdout) é o padrão desta doutrina — um hook de segurança avisa, quem decide bloquear de verdade é o humano ou uma camada dedicada (ex. pre-commit). BLOCK (exit 2) é a exceção: só para casos onde a ação é irreversível E a detecção é confiável o bastante para nunca gerar falso-positivo bloqueante.

### 3. Registre — modo PLUGIN (recomendado, auto-wire)
```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash", "hooks": [
        { "type": "command", "command": "python \"${CLAUDE_PLUGIN_ROOT}/hooks/seu_hook.py\"", "timeout": 30 }
      ]}
    ]
  }
}
```
Salve como `<seu-plugin>/hooks/hooks.json` e referencie em `.claude-plugin/plugin.json` (`"hooks": "./hooks/hooks.json"`) — ver a skill `plugin-dev`.

### 4. OU registre — modo MANUAL (sem plugin, cola direto)
Adicione a mesma estrutura dentro do array `hooks` de `.claude/settings.json`/`settings.local.json`. **Isso costuma ser gate humano** — sessões automatizadas têm trava contra auto-editar settings/hooks; cole você mesmo.

### 5. Teste com o payload real
```bash
echo '{"tool_name":"Bash","tool_input":{"command":"..."}}' | python seu_hook.py
```

## Exemplo vivo neste kit: `secret_scan_on_write.py`

Um hook `PreToolUse` (matcher `Edit|Write|MultiEdit`) real e shipado, WARN-only: lê `tool_input.{file_path, content, ...}` do stdin, verifica se o path bate um glob "persistente" (memória/CLAUDE.md/docs) E o conteúdo bate um padrão de segredo, e avisa — nunca bloqueia (exit 0 sempre). Ver `hooks/secret_scan_on_write.py`.

## Exemplos executados

```console
$ echo '{"tool_name":"Write","tool_input":{"file_path":"CLAUDE.md","content":"api_key: \"sk-ant-abcdef1234567890ABCDEF\""}}' | python hooks/secret_scan_on_write.py
[secret_scan_on_write] AVISO: possível segredo em arquivo persistente `CLAUDE.md` (padrão `sk-ant-a...`).
  -> NÃO commitar credencial crua. Referencie o `.env` (ex.: "key: stored in `.env` as FOO_API_KEY"). WARN-only — o BLOCK definitivo é do pre-commit.
```
<!-- executado: 2026-07-10 · exit=0 -->
(detectou o segredo e AVISOU — mas exit=0: WARN-only nunca impede a escrita.)

```console
$ echo '{"tool_name":"Write","tool_input":{"file_path":"CLAUDE.md","content":"API key stored in .env as FOO_API_KEY"}}' | python hooks/secret_scan_on_write.py
```
<!-- executado: 2026-07-10 · exit=0 -->
(sem output — conteúdo limpo, hook silencioso.)

```console
$ echo '{"tool_name":"Bash","tool_input":{"command":"rm -rf /"}}' | python docs/hook-template.py
BLOQUEADO: comando destrutivo detectado ('rm -rf /'). Confirme a intenção antes de rodar manualmente.
```
<!-- executado: 2026-07-10 · exit=2 -->
(o modo BLOCK — exit 2 em `PreToolUse` realmente impede a ferramenta de rodar. Use com moderação.)

## Anti-patterns

- ❌ Escrever um hook como arquivo `.md` com frontmatter `trigger:`/`pattern:`/`mode:` — isso NÃO é como Claude Code hooks funcionam; hooks são executáveis, não markdown declarativo.
- ❌ Usar `mode: block` por padrão — block-mode falso-positivo trava o usuário no meio do trabalho; comece WARN-only, promova a block só com evidência de zero falso-positivo.
- ❌ Fixar `py` como launcher — use `python` sempre (portabilidade cross-OS).
- ❌ Hook que lança exceção não-tratada em payload malformado — sempre degrade pra exit 0 em erro de parsing (ver `docs/hook-template.py::main`).

## Prova

```bash
python docs/hook-template.py --self-test
```
