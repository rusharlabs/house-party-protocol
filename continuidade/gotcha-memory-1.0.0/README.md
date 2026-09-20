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
├── README.md                     ← este arquivo
├── profile.example.yaml          ← subset de config p/ copiar no seu operator-profile.yaml
├── curated.seed.example.yaml     ← lições curated de exemplo (genéricas — edite antes de seedar)
├── _lib/
│   ├── gotchas_memory.py         ← núcleo: record/recurring/curated/preamble + CLI (--seed/--preamble/--self-test/demo)
│   ├── error_strategy.py         ← classificador puro erro→família→estratégia (vendorizado, stdlib)
│   └── profile_loader.py         ← acha+lê o operator-profile.yaml (vendorizado; degrada p/ defaults)
├── hooks/
│   ├── hooks.json                ← PreToolUse Bash → preflight · PostToolUse Bash → postflight
│   ├── gotcha_preflight.py       ← injeta o preâmbulo "⚠️ GOTCHAS" no stderr antes do comando
│   └── gotcha_postflight.py      ← registra a falha depois do comando (conservador)
├── skills/
│   └── gotcha-memory/SKILL.md    ← doutrina + exemplos executados
├── install/
│   └── kit.install.yaml          ← prereqs + verification (4 self-tests)
└── .claude-plugin/
    └── plugin.json               ← manifesto do plugin
```

## Instalar via plugin (1 clique)

```bash
/plugin marketplace add .
/plugin install gotcha-memory@house-party-protocol
```

Instala os 2 hooks (`PreToolUse`/`PostToolUse`, matcher `Bash`) via
`${CLAUDE_PLUGIN_ROOT}` — nenhum path relativo hardcoded.

## Instalar por cópia (wire manual)

Copie a pasta para o seu projeto e cole em `.claude/settings.local.json` (o wire de
hooks é **gate-humano** por design — editar settings é decisão sua):

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
    ]
  }
}
```

## Config (operator-profile.yaml)

Copie de `profile.example.yaml`. Sem profile, defaults: store `.claude/gotchas/`,
janela 24h, min_count 3, top 5. Override de store também via env `GOTCHA_STORE_DIR`.
Recomendado **gitignorar o store** (memória local regenerável).

## Uso direto (CLI)

```bash
python _lib/gotchas_memory.py                                  # demo do loop inteiro (store temporário)
python _lib/gotchas_memory.py --self-test                      # asserções do núcleo
python _lib/gotchas_memory.py --seed curated.seed.example.yaml # seeda suas regras (idempotente)
python _lib/gotchas_memory.py --preamble "rodar o deploy"      # o que o agente veria antes dessa task
```

## Verificação (o critério de "instalado e funcionando")

```bash
python _lib/error_strategy.py --self-test      # OK
python _lib/gotchas_memory.py --self-test      # self-test OK ✓
python hooks/gotcha_preflight.py --self-test   # self-test OK
python hooks/gotcha_postflight.py --self-test  # self-test OK
```

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
