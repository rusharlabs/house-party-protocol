[English](README.md) · [Português](README.pt-BR.md)

# Gotcha Memory

**Standalone** operational learning loop: the failure becomes knowledge. After each Bash
command that FAILS, `gotcha_postflight.py` records the event (classified by error family
through `error_strategy`). When the SAME kind of failure recurs **>= N times** within a
time window, it becomes a **GOTCHA** — an actionable lesson that `gotcha_preflight.py`
injects into stderr BEFORE the next execution of the same task. **Curated** gotchas (your
rules, seeded from a file) are always-on when the key matches by substring. Two hooks, one
clear boundary: **preflight READS the lessons, postflight WRITES the failures.** Everything
WARN-only (exit 0 always) — the learning loop never blocks the flow.

**Embedded doctrine:** CONSERVATIVE detection — only a clear error signal counts
(exit != 0, `is_error`, `error` field); ambiguous = not a failure. The system never
invents a failure to "look like it learned".

## Prerequisites + external APIs

| Requirement | Minimum version | Required? |
|---|---|---|
| Python | 3.8 | yes |
| PyYAML | any | no — only for the profile and `.yaml` seed (`.jsonl` seed is stdlib) |

External services: **none**. I/O is 100% local (JSONL append/read in the store).

## What is in this folder

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
│   ├── hooks.json                ← PreToolUse Bash → preflight · PostToolUse + PostToolUseFailure Bash → postflight
│   ├── gotcha_preflight.py       ← injeta o preâmbulo "⚠️ GOTCHAS" no stderr antes do comando
│   └── gotcha_postflight.py      ← registra a falha depois do comando (conservador)
├── skills/
│   └── gotcha-memory/SKILL.md    ← doutrina + exemplos executados
├── install/
│   └── kit.install.yaml          ← prereqs + verification (4 self-tests)
└── .claude-plugin/
    └── plugin.json               ← manifesto do plugin
```

## Install as a plugin (1 click)

```bash
/plugin marketplace add .
/plugin install gotcha-memory@house-party-protocol
```

Installs the hooks (`PreToolUse` → preflight; `PostToolUse` **and** `PostToolUseFailure` →
postflight, matcher `Bash`) through `${CLAUDE_PLUGIN_ROOT}` — no hardcoded relative path.
The host emits `PostToolUseFailure` when Bash fails; listening only to `PostToolUse` would
leave the memory blind to the failure. The same call (`tool_use_id`) becomes **one** record,
however many events arrive.

## Install by copy (manual wire)

Copy the folder into your project and paste into `.claude/settings.local.json` (wiring
hooks is a **human gate** by design — editing settings is your decision):

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

Copy from `profile.example.yaml`. Without a profile, defaults: store `.claude/gotchas/`,
24h window, min_count 3, top 5. The store can also be overridden through the
`GOTCHA_STORE_DIR` env var. Recommended: **gitignore the store** (regenerable local memory).

## Direct use (CLI)

```bash
python _lib/gotchas_memory.py                                  # demo do loop inteiro (store temporário)
python _lib/gotchas_memory.py --self-test                      # asserções do núcleo
python _lib/gotchas_memory.py --seed curated.seed.example.yaml # seeda suas regras (idempotente)
python _lib/gotchas_memory.py --preamble "rodar o deploy"      # o que o agente veria antes dessa task
```

## Verification (the criterion for "installed and working")

```bash
python _lib/error_strategy.py --self-test      # OK
python _lib/gotchas_memory.py --self-test      # self-test OK ✓
python hooks/gotcha_preflight.py --self-test   # self-test OK
python hooks/gotcha_postflight.py --self-test  # self-test OK
```

End-to-end test of the loop: provoke 3 identical failures (`bash -c "exit 1"` with the same
description) and confirm that the next preflight of the same task prints
`[gotcha-memory] ⚠️ GOTCHAS … [3x]` to stderr.

## Honest limits

- Only the **Bash** tool is observed (the hooks' matcher). Widening = new matchers + task_key derivation per tool.
- Silent failure (exit 0 with a wrong result) is not captured — by design (conservative).
- The task_key is `description || cmd[:80]`: stable descriptions produce better learning than long, unique commands.
- The example seed is generic on purpose — the valuable lessons are YOURS (and the ones the loop itself learns).

## Provenance

Standalone extraction of the gotcha loop from the origin repo
(`gotchas_memory` + `error_strategy` + agentic pre/postflight hooks), de-personalised:
the owner's hardcoded seed was removed and replaced by `seed_from_file()` +
`curated.seed.example.yaml`. MIT licence.
