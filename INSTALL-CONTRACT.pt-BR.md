[English](INSTALL-CONTRACT.md) · [Português](INSTALL-CONTRACT.pt-BR.md)

# INSTALL-CONTRACT — o contrato de instalação de qualquer kit deste marketplace

> **Versão:** 1.0.0 · **Enforcement:** `installers/kit-forge/kit_doctor.py` (subcomando `install`)
> **Irmão de:** `SKILL-CONTRACT.md` (contrato de SKILL.md) — este é o contrato do INSTALADOR.

## Princípio

```
INSTALLING A KIT IS NEVER A SURPRISE.
The operator sees the PLAN before any write happens, knows whether the target project
is NEW or ALREADY HAS CONFIG, and only a second, explicit invocation (--apply) acts.
No installer in this marketplace blocks waiting for terminal input() —
the human's "yes" is the re-invocation with --apply, not a prompt.
```

(Instalar um kit nunca é uma surpresa. O operador vê o PLANO antes de qualquer escrita
acontecer, sabe se o projeto-alvo é NOVO ou JÁ TEM CONFIG, e só uma segunda invocação explícita
(`--apply`) age. Nenhum instalador deste marketplace bloqueia esperando `input()` de terminal —
o "sim" do humano é a re-invocação com `--apply`, não um prompt.)

Todo kit deste marketplace que tem passos de instalação (cópia de arquivo, profile,
wiring de hooks/statusLine) é instalado pelo MESMO motor (`kit_doctor.py install`),
que lê um manifesto declarativo por-kit (`install/kit.install.yaml`). O motor nunca
tem conhecimento hardcoded de um kit específico — todo o conhecimento kit-específico
vive no YAML.

## Os 6 estágios (ordem fixa)

```
detect → prereqs → profile → configure → wire-suggest → smoke
```

### 1. `detect` (novo — sempre primeiro, read-only)
Classifica o projeto-alvo (`--target`, default cwd) em uma de três categorias:

| Classificação | Sinais |
|---|---|
| `greenfield` | sem `.claude/`, sem `settings.json`/`settings.local.json`, git com poucos/nenhum commit, nenhum profile real presente |
| `in-progress` | `.claude/` existe, `settings*.json` tem hooks/statusLine ocupados, profile real (`operator-profile.yaml`/`rollup.yaml`/etc.) presente, histórico git não-trivial |
| `re-run` | este `kit_dir` já tem entrada em `~/.claude-kits/registry.json` apontando para este `--target` |

Saída: `{"stage": "detect", "classification": "...", "signals": {...}, "existing_config": [lista de itens já configurados que serão preservados]}`. Nunca escreve nada.

### 2. `prereqs` (existente — python/PyYAML/dependências declaradas em `requires:`)

### 3. `profile` (existente — copia `*.example.*` → real; **nunca sobrescreve** se o alvo já existe com conteúdo diferente do gerado; `skip-exists` reportado, não silencioso)

### 4. `configure` (novo)
Lê `questions:` do `kit.install.yaml`. Sem `--answers`: usa os `default` de cada pergunta e lista, no plano, quais perguntas ficaram pendentes de decisão humana. Com `--answers <file.json|yaml>`: carrega, valida contra o schema (tipo/opções), aplica; campos ausentes = default.

### 5. `wire-suggest` (existente — NUNCA escreve settings/hooks; só detecta o que existe — `.claude-plugin/plugin.json`, `install/wiring-spec.yaml`, `README.md`/guia — e sugere o comando textual. Mutar settings/hooks continua gate humano, sempre.)

### 6. `smoke` (existente — roda `--self-test` em todo `.py` do kit; scripts sem esse suporte são `skipped`, não falha)

## O fluxo plano → apply (Confirm step)

```
$ python kit_doctor.py install <kit_dir> --target <project_dir>
   → runs the 6 stages in PLAN MODE (no real write happens)
   → prints the full plan (JSON) and EXITS 0 (1 if the smoke or the profile stage failed)
   → the human reads the plan (in the conversation, if an agent is operating)

$ python kit_doctor.py install <kit_dir> --target <project_dir> --apply
   → runs the 6 stages for real, applying the profile and registering the install
   → wire-suggest still NEVER writes (the human gate is always manual)
```

(Primeira invocação: roda os 6 estágios em MODO PLANO — nenhuma escrita real acontece —,
imprime o plano completo em JSON e SAI COM EXIT 0 (1 se o estágio `smoke` ou o `profile`
falhou); o humano lê o plano, na conversa se for um agente operando. Segunda invocação, com
`--apply`: roda os 6 estágios de verdade, aplicando o profile e registrando o install; o
`wire-suggest` continua NUNCA escrevendo — o gate humano é sempre manual.)

Não existe (e não deve existir) um `input()` bloqueante em lugar nenhum deste
mecanismo — o operador real deste ecossistema é frequentemente um agente atuando
em nome de um humano; um prompt de stdin trava exatamente nesse contexto de uso.
O "Confirm" é a dupla invocação (plano, depois `--apply`), auditável e reprodutível.

## Schema de `install/kit.install.yaml`

```yaml
kit: <kit-name>
requires:
  python: ">=3.9"          # optional, default ">=3.8"
  pyyaml: true              # optional, default false
  external_services: []     # e.g. the supabase-pack declares [{name: Supabase, via: MCP, credenciais: "URL + anon key"}]
                             # HARD RULE: never declare ANTHROPIC_API_KEY here — model authentication belongs to the host, never to the kit
questions:                  # optional — consumed by the `configure` stage AND by the --interview mode of wizards
  - id: <identifier>
    prompt: "<the question>"
    type: choice|bool|string
    options: [...]           # if type: choice
    default: <value>
verification:               # post-install acceptance commands (each must be executable and exit 0)
  - "python scripts/<script>.py --self-test"
hosts:
  claude-code:               # native plugin host — see the "Host seam" section below
    plugin: true|false        # does .claude-plugin/plugin.json exist?
    wiring_spec: install/wiring-spec.yaml   # if there is hooks/statusLine wiring
    manual_gates: [statusLine]              # what must NEVER be auto-armed (always a human gate)
  codex:                     # host installed by explicit copy, with no automatic activation of hooks
    plugin: false
    agents: AGENTS.md
    skills_path: .agents/skills
    runtime_path: .agents/hpp/<kit-name>
    manual_gates: [hooks]
docs: README.md
```

Lendo o bloco: `requires.python` é opcional (default `">=3.8"`); `requires.pyyaml` é opcional
(default `false`); `requires.external_services` nomeia cada serviço externo (ex.: o supabase-pack
declara `[{name: Supabase, via: MCP, credenciais: "URL + anon key"}]` — `credenciais` é a chave
que o manifesto dele usa de fato) — REGRA DURA: nunca declarar `ANTHROPIC_API_KEY` aqui, a
autenticação do modelo é do host, nunca do kit; `questions` é opcional e é consumido pelo
estágio `configure` E pelo modo `--interview` de wizards, com `options` valendo quando
`type: choice`; `verification` lista comandos de aceite pós-install, cada um executável e
saindo 0; em `hosts`, `claude-code` é o host nativo de plugin (ver "Seam de host" abaixo) —
`plugin` diz se existe `.claude-plugin/plugin.json`, `wiring_spec` aponta o wiring de
hooks/statusLine se houver, e `manual_gates` lista o que NUNCA pode ser auto-armado (sempre gate
humano); `codex` é o host por cópia explícita, sem ativação automática de hooks.

## Schema de perguntas (`questions:`)

Mesmo schema é consumido em dois lugares: pelo estágio `configure` do `kit_doctor.py`,
e pelo modo `--interview` de wizards standalone (ex. `agent-framework-wizard/wizard.py`).
Isso garante que "responder perguntas" tem UM formato só, não dois.

```json
{"id": "lane_mode", "prompt": "Does the project run multi-session (lanes) or solo?", "type": "choice", "options": ["solo", "lanes"], "default": "solo"}
```

## Seam de host (Claude Code + Codex CLI)

O motor mantém um dict interno com os dois hosts comprovados:

```python
HOSTS = {
    "claude-code": {
        "settings_path": ".claude/settings.local.json",
        "plugin_manifest": ".claude-plugin/plugin.json",
        "path_token": "${CLAUDE_PLUGIN_ROOT}",
    },
    "codex": {
        "agents_file": "AGENTS.md",
        "skills_path": ".agents/skills",
        "runtime_path": ".agents/hpp",
        "path_token": "{{HPP_CODEX_RUNTIME}}",
    },
}
```

Fontes NOVAS (`kit.install.yaml`, `install/wiring-spec.yaml`) usam o token neutro
`{{KIT_ROOT}}`, resolvido para `path_token` do host ativo (`--host`; o default segue
`claude-code`). Os usos EXISTENTES de `${CLAUDE_PLUGIN_ROOT}` em
`hooks.json`/scripts NÃO são reescritos — são artefatos nativos do Claude Code e
continuam assim. No Codex, `codex_skills.py` copia o runtime para
`.agents/hpp/<kit>` e gera skills namespaced em `.agents/skills/`, substituindo o
token somente nessas cópias. Hooks permanecem desligados. Um adaptador
de host novo = nova entrada em `HOSTS` + bloco `hosts.<novo>:` nos YAMLs —
zero mudança nos 6 estágios. Não inventar
vocabulário de evento "neutro" fingido: eventos tipo `Stop`/`PreCompact` são conceitos
Claude Code e ficam declarados sob `hosts.claude-code`, honestamente.

## Exit codes (`kit_doctor.py install`)

| Exit | Significado |
|---|---|
| 0 | plano impresso (modo padrão) OU aplicado com sucesso (`--apply`) |
| 1 | o estágio `smoke` falhou, ou o estágio `profile` falhou (a cópia do host Codex) |
| 3 | erro de uso (kit_dir/target ausente) |

## Checklist antes de considerar um kit "instalável de verdade"

```
[ ] install/kit.install.yaml existe e valida contra o schema acima
[ ] requires.external_services declarado (mesmo que vazio) — nunca ANTHROPIC_API_KEY
[ ] questions (se houver) têm default sensato — instalar sem --answers nunca trava
[ ] verification: tem ≥1 comando real, executável, que sai 0 quando tudo está ok
[ ] hosts.claude-code.manual_gates lista tudo que NUNCA deve ser auto-armado
[ ] hosts.codex declara AGENTS.md, .agents/skills, runtime namespaced e hooks em manual_gates
[ ] README.md segue o INSTALL-GUIDE-TEMPLATE.md
[ ] kit_doctor.py install <kit> --target <dir-virgem> roda sem erro (plano)
[ ] kit_doctor.py install <kit> --target <dir-virgem> --apply roda sem erro (aplica)
[ ] rodar de novo (--apply) sobre o MESMO dir → detect classifica re-run, nada duplica
```
