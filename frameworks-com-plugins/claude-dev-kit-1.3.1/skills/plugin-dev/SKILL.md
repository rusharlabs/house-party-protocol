---
name: plugin-dev
description: Empacota skills/hooks/commands num plugin Claude Code instalável — anatomia real (.claude-plugin/plugin.json + hooks/hooks.json + ${CLAUDE_PLUGIN_ROOT}), sem framework/build-step. Use quando o usuário quer criar plugin, empacotar uma extensão, ou distribuir um conjunto de skills/hooks.
---

> **Auto-Trigger:** Quando o usuário quiser criar um plugin Claude Code, empacotar skills/hooks para distribuição, ou perguntar "como faço um plugin instalável".
> **Keywords:** "plugin", "criar plugin", "empacotar plugin", "claude-plugin", "marketplace", "plugin.json", "distribuir skill"
> **Prioridade:** ALTA
> **Tools:** Read, Write, Edit, Glob, Grep, Bash

## Quando NÃO Ativar
- Uso de um plugin já instalado sem modificação, ou debugging de um plugin existente (leia os arquivos direto).
- **Criar a SKILL ou o HOOK em si** — use `skill-writer`/`hookify` deste mesmo kit primeiro; `plugin-dev` é só a EMBALAGEM que agrupa o que já existe, não cria conteúdo novo.
- Não confundir com um pacote npm/TypeScript — plugins Claude Code **não têm build step, não têm `package.json`, não têm `src/index.ts`**. É um diretório com manifests JSON + arquivos que o Claude Code já sabe interpretar (SKILL.md, hooks Python, commands .md).

## Contrato

**ENTRADA:** um conjunto de skills/hooks/commands já criados (ou a criar) que devem virar um plugin instalável.

**SAÍDA:** um diretório `<plugin-name>/` com `.claude-plugin/plugin.json` válido (+ `hooks/hooks.json` se houver hooks).

**EXIT CODES** (do validador de manifest usado na seção Prova):

| Exit | Significado |
|---|---|
| 0 | manifest com todos os campos obrigatórios |
| 1 | campo obrigatório ausente |

**ESTADO QUE TOCA:**

| Recurso | Lê/Escreve | Propósito |
|---|---|---|
| `<plugin>/.claude-plugin/plugin.json` | Escreve | manifesto do plugin (nome, versão, hooks, commands) |
| `<plugin>/hooks/hooks.json` | Escreve (se houver hooks) | registro declarativo dos hooks — ver skill `hookify` |
| `<plugin>/skills/*/SKILL.md` | Lê (já existentes) | as skills que o plugin empacota — ver skill `skill-writer` |
| `marketplace.json` (se for distribuir >1 plugin junto) | Escreve | índice de vários plugins — `/plugin marketplace add` lê este arquivo |

## Anatomia REAL de um plugin (não é TypeScript/npm)

```
meu-plugin/
├── .claude-plugin/
│   └── plugin.json        # manifesto — OBRIGATÓRIO
├── hooks/
│   ├── hooks.json         # registro declarativo dos hooks (se houver)
│   └── meu_hook.py        # o(s) script(s) real(is) — ver skill hookify
├── skills/
│   └── minha-skill/
│       └── SKILL.md       # ver skill skill-writer
├── commands/               # opcional — slash commands custom
│   └── meu-comando.md
├── scripts/                # opcional — CLIs auxiliares
└── README.md               # instalação + uso
```

Nada de `src/`, `package.json`, `*.test.ts`, build step. Se o plugin tem lógica em Python (hooks/scripts), ela roda direto via `python arquivo.py` — sem transpilação, sem bundler.

## `${CLAUDE_PLUGIN_ROOT}`

Toda referência de comando dentro de `hooks.json` deve usar `${CLAUDE_PLUGIN_ROOT}` em vez de path relativo cru — o Claude Code resolve essa variável para a raiz real do plugin NO MOMENTO DA INSTALAÇÃO, então funciona não importa onde o usuário instalou (ele pode ter clonado num path totalmente diferente do seu).

```jsonc
// ERRADO — quebra assim que o plugin é instalado num path diferente
{ "type": "command", "command": "python meu-plugin/hooks/meu_hook.py" }

// CORRETO
{ "type": "command", "command": "python \"${CLAUDE_PLUGIN_ROOT}/hooks/meu_hook.py\"", "timeout": 30 }
```

## `.claude-plugin/plugin.json` — campos reais (exemplo de um kit deste marketplace)

```json
{
  "$schema": "https://json.schemastore.org/claude-code-plugin-manifest.json",
  "name": "meu-plugin",
  "displayName": "Meu Plugin",
  "version": "1.0.0",
  "description": "O que o plugin faz + quando usar.",
  "author": { "name": "Seu Nome" },
  "license": "MIT",
  "keywords": ["categoria1", "categoria2"],
  "hooks": "./hooks/hooks.json",
  "commands": "./commands"
}
```

`hooks` e `commands` são OPCIONAIS — omita se o plugin só traz skills.

## `hooks/hooks.json` — registro declarativo (ver skill `hookify` p/ o script em si)

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Edit|Write|MultiEdit", "hooks": [
        { "type": "command", "command": "python \"${CLAUDE_PLUGIN_ROOT}/hooks/meu_hook.py\"", "timeout": 30 }
      ]}
    ]
  }
}
```

## Limitação real: `statusLine` NÃO vai no plugin

O Claude Code não aceita `statusLine` dentro de `plugin.json`/`hooks.json` — tem que ir manualmente em `.claude/settings.json`/`settings.local.json` do projeto-alvo, mesmo que o plugin traga uma statusline pronta (`statusline/statusline.py --statusline`). Documente esse passo manual no README do plugin; não prometa "statusLine auto-instalada".

## Instalar (1 plugin) ou distribuir (vários num marketplace)

```bash
# instalar 1 plugin a partir de um diretório local
/plugin marketplace add .
/plugin install meu-plugin@<nome-do-marketplace>
```

Para distribuir VÁRIOS plugins juntos, crie um `marketplace.json` na raiz do bundle:

```json
{
  "$schema": "https://json.schemastore.org/claude-code-marketplace.json",
  "name": "meu-marketplace",
  "description": "Bundle de plugins",
  "version": "1.0.0",
  "owner": { "name": "Seu Nome" },
  "plugins": [
    { "name": "meu-plugin", "displayName": "Meu Plugin", "source": "./meu-plugin",
      "description": "...", "version": "1.0.0", "category": "productivity", "keywords": ["..."] }
  ]
}
```

## Processo

1. **Crie/reúna** as skills (`skill-writer`) e hooks (`hookify`) que o plugin vai empacotar.
2. **Monte `.claude-plugin/plugin.json`** com os campos obrigatórios (`name`, `version`, `description`) + `hooks`/`commands` se aplicável.
3. **Se houver hooks**, monte `hooks/hooks.json` referenciando cada script via `${CLAUDE_PLUGIN_ROOT}`.
4. **Valide o manifest** (ver Prova) antes de anunciar como pronto.
5. **Documente a instalação** no README (`/plugin marketplace add` + `/plugin install`), incluindo qualquer passo MANUAL (ex.: statusLine).
6. **Teste a instalação de verdade** num diretório/projeto separado, não só leia o JSON.

## Exemplos executados

```console
$ python -c "
import json
def validate_plugin_manifest(data):
    required = ['name', 'version', 'description']
    return [k for k in required if k not in data]
sample = {'name':'exemplo-kit','version':'1.0.0','description':'kit de exemplo','hooks':'./hooks/hooks.json'}
missing = validate_plugin_manifest(sample)
assert missing == [], missing
print('plugin.json valido: campos obrigatorios presentes')
"
plugin.json valido: campos obrigatorios presentes
```
<!-- executado: 2026-07-10 · exit=0 -->

```console
$ python -c "
def validate_plugin_manifest(data):
    required = ['name', 'version', 'description']
    return [k for k in required if k not in data]
bad = {'name': 'sem-versao'}
missing = validate_plugin_manifest(bad)
print('plugin.json invalido detectado:', missing)
import sys; sys.exit(1 if missing else 0)
"
plugin.json invalido detectado: ['version', 'description']
```
<!-- executado: 2026-07-10 · exit=1 -->
(manifest sem `version`/`description` é rejeitado ANTES de tentar instalar — falha cedo, não em produção.)

```console
$ mkdir -p meu-plugin/.claude-plugin meu-plugin/hooks && ls meu-plugin
.claude-plugin  hooks
```
<!-- executado: 2026-07-10 · exit=0 -->
(passo 2-3 do processo — esqueleto de diretório antes de escrever os manifests.)

## Anti-patterns

- ❌ `src/index.ts` + `package.json` + build step — plugins Claude Code não são pacotes npm; são diretórios que o Claude Code já sabe ler.
- ❌ Path relativo cru em `hooks.json` (`"command": "hooks/meu_hook.py"`) — quebra assim que instalado num path diferente do seu. Sempre `${CLAUDE_PLUGIN_ROOT}`.
- ❌ Prometer `statusLine` "auto-instalada pelo plugin" — é limitação real do Claude Code; documente o passo manual.
- ❌ Anunciar o plugin como pronto sem testar a instalação de verdade (só ler o JSON não prova que instala).

## Prova

```bash
python -c "
def validate_plugin_manifest(d):
    return [k for k in ('name','version','description') if k not in d]
assert validate_plugin_manifest({'name':'x','version':'1.0.0','description':'y'}) == []
assert validate_plugin_manifest({'name':'x'}) == ['version','description']
print('self-test OK')
"
```
