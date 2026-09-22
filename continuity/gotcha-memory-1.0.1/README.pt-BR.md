[English](README.md) · [Português](README.pt-BR.md)

# Gotcha Memory

Loop de aprendizado operacional **standalone**: a falha vira conhecimento. Depois de
cada comando Bash que FALHA, o `gotcha_postflight.py` registra o evento (classificado
por família de erro via `error_strategy`). Quando o MESMO tipo de falha recorre
**>= N vezes** numa janela de tempo, vira um **GOTCHA** — uma lição acionável que o
`gotcha_preflight.py` injeta no stderr ANTES da próxima execução da mesma tarefa.
Gotchas **curated** (regras suas, seedadas de arquivo) são always-on quando a chave
casa por substring. Dois hooks, uma fronteira clara: **preflight LÊ as lições,
postflight ESCREVE as falhas.** Tudo WARN-only (exit 0 sempre) — o loop de
aprendizado jamais bloqueia o fluxo.

**Doutrina embarcada:** detecção CONSERVADORA — só sinal claro de erro conta
(exit != 0, `is_error`, campo `error`); ambíguo = não-falha. O sistema nunca
inventa uma falha para "parecer que aprendeu".

## Pré-requisitos + APIs externas

| Requisito | Versão mínima | Obrigatório? |
|---|---|---|
| Python | 3.8 | sim |
| PyYAML | qualquer | não — só p/ profile e seed `.yaml` (seed `.jsonl` é stdlib) |

Serviços externos: **nenhum**. I/O é 100% local (JSONL append/read no store).

## O que tem nesta pasta

```
gotcha-memory/
├── README.md · README.pt-BR.md   ← this file (and its Portuguese twin)
├── profile.example.yaml          ← config subset to copy into your operator-profile.yaml
├── curated.seed.example.yaml     ← example curated lessons (generic — edit before seeding)
├── _lib/
│   ├── gotchas_memory.py         ← core: record/recurring/curated/preamble + CLI (--seed/--preamble/--self-test/demo)
│   ├── error_strategy.py         ← pure classifier error→family→strategy (vendored, stdlib)
│   └── profile_loader.py         ← finds + reads operator-profile.yaml (vendored; degrades to defaults)
├── hooks/
│   ├── hooks.json                ← PreToolUse Bash → preflight · PostToolUse + PostToolUseFailure Bash → postflight
│   ├── pyrun.sh                  ← resolves the project's Python interpreter for the hooks
│   ├── gotcha_preflight.py       ← injects the "⚠️ GOTCHAS" preamble into stderr before the command
│   └── gotcha_postflight.py      ← records the failure after the command (conservative)
├── skills/
│   └── gotcha-memory/SKILL.md    ← doctrine + executed examples
├── install/
│   └── kit.install.yaml          ← prereqs + verification (4 self-tests) + 1 question
├── .claude-plugin/
│   └── plugin.json               ← plugin manifest (declares hooks/hooks.json)
├── AGENTS.md                     ← Codex CLI entry point (what Codex reads on --host codex)
└── LICENSE · CHECKSUMS.txt · SANITIZATION.md   ← added by the forge at emission
```

## Instalar via plugin (1 clique)

```bash
/plugin marketplace add rushar-labs/house-party-protocol
/plugin install gotcha-memory@house-party-protocol
```

Instala os hooks (`PreToolUse` → preflight; `PostToolUse` **e** `PostToolUseFailure` →
postflight, matcher `Bash`) via `${CLAUDE_PLUGIN_ROOT}` — nenhum path relativo hardcoded.
O host emite `PostToolUseFailure` quando o Bash falha; ouvir só `PostToolUse` deixaria a
memória cega para a falha. A mesma chamada (`tool_use_id`) vira **um** registro, por
quantos eventos chegar.

## Instalar por cópia (wire manual)

Na distribuição emitida este módulo vive em `continuity/gotcha-memory-1.0.1/` (o
diretório carrega a versão — declare-a uma vez, em `KIT`). O instalador do marketplace
planeja primeiro e só escreve numa segunda invocação explícita com `--apply`; o estágio
`profile` dele copia `profile.example.yaml` → `profile.yaml` e
`curated.seed.example.yaml` → `curated.seed.yaml` para o alvo (nunca sobrescrevendo), e o
estágio `configure` pergunta `seedar_curated_agora` (seedar as lições curated agora?
default: não):

```bash
KIT=continuity/gotcha-memory-1.0.1
cp -r "$KIT" ../your-repo/gotcha-memory       # the copy itself (kit_doctor does not copy on claude-code)
python installers/kit-forge-1.4.1/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo
python installers/kit-forge-1.4.1/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo --apply
# Codex CLI: --host codex — the installer copies the module into .agents/hpp/gotcha-memory
#            and the skill into .agents/skills/hpp-gotcha-memory-<skill>; no cp -r needed
```

Depois cole em `.claude/settings.local.json` (o wire de hooks é **gate-humano** por design
— editar settings é decisão sua):

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash", "hooks": [
        { "type": "command", "command": "python \"gotcha-memory/hooks/gotcha_preflight.py\"", "timeout": 30 }
      ]}
    ],
    "PostToolUse": [
      { "matcher": "Bash", "hooks": [
        { "type": "command", "command": "python \"gotcha-memory/hooks/gotcha_postflight.py\"", "timeout": 30 }
      ]}
    ],
    "PostToolUseFailure": [
      { "matcher": "Bash", "hooks": [
        { "type": "command", "command": "python \"gotcha-memory/hooks/gotcha_postflight.py\"", "timeout": 30 }
      ]}
    ]
  }
}
```

## Config (operator-profile.yaml)

Copie de `profile.example.yaml` (o loader lê `operator-profile.yaml`, então o
`profile.yaml` que o instalador deixa precisa ser renomeado ou mesclado nele). Sem
profile, defaults: store `.claude/gotchas/`, janela 24h, min_count 3, top 5. Override de
store também via env `GOTCHA_STORE_DIR`. Recomendado **gitignorar o store** (memória
local regenerável).

## Uso direto (CLI)

```bash
python _lib/gotchas_memory.py                                  # demo of the whole loop (temporary store)
python _lib/gotchas_memory.py --self-test                      # core assertions
python _lib/gotchas_memory.py --seed curated.seed.example.yaml # seeds your rules (idempotent)
python _lib/gotchas_memory.py --preamble "run the deploy"      # what the agent would see before that task
```

## Verificação (o critério de "instalado e funcionando")

```bash
python _lib/error_strategy.py --self-test      # self-test OK
python _lib/gotchas_memory.py --self-test      # self-test OK ✓
python hooks/gotcha_preflight.py --self-test   # self-test OK
python hooks/gotcha_postflight.py --self-test  # self-test OK
```
<!-- executado: 2026-09-21 · exit=0 (the four) -->

Teste ponta-a-ponta do loop: provoque 3 falhas iguais (`bash -c "exit 1"` com a mesma
description) e confirme que o próximo preflight da mesma tarefa imprime
`[gotcha-memory] ⚠️ GOTCHAS … [3x]` no stderr.

## Limites honestos

- Só a tool **Bash** é observada (matcher dos hooks). Ampliar = novos matchers + derivação de task_key por tool.
- Falha silenciosa (exit 0 com resultado errado) não é capturada — por design (conservador).
- A task_key é `description || cmd[:80]`: descriptions estáveis geram aprendizado melhor que comandos longos e únicos.
- O seed de exemplo é genérico de propósito — as lições valiosas são as SUAS (e as que o próprio loop aprende).

## Proveniência

Extração standalone do loop de gotchas do repo-de-origem
(`gotchas_memory` + `error_strategy` + hooks agentic pre/postflight), despersonalizada:
o seed hardcoded do dono foi removido e substituído por `seed_from_file()` +
`curated.seed.example.yaml`. Licença MIT.
