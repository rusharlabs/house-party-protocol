[English](README.md) · [Português](README.pt-BR.md)

# Lane Kit

N agent sessions (lanes) working on the same repo at the same time, without collision.
A whiteboard of states (`CLAIMED → BUILDING → CHECKPOINT-READY → UNDER-REVIEW →
VERIFIED/NEEDS-FIX → MERGED`) with cross-model maker≠checker **enforced in code**
(not only by convention), a registry of live lanes with heartbeat/liveness, a git guard
(blocks `commit -a`/`add -A`/`reset --hard` while another lane is alive) and a territory
guard (red zones + exclusive territory per lane). **Depends on the `continuity-kit`**
(uses the `lane_id` field of handoff-v1.1) — install that one first. It does not do the
session handoff itself — that is the `continuity-kit`.

## Prerequisites + external APIs

| Requirement | Minimum version | Required? |
|---|---|---|
| Python | 3.9 | yes |
| PyYAML | any | yes |
| `continuity-kit` | 1.1.0+ | yes — lane-kit reads `lane_id` from its handoff-v1.1 schema |

External services: **none — stdlib + PyYAML, touches only the local filesystem + the target project's git.**

## Install as a plugin

```bash
/plugin marketplace add .
/plugin install lane-kit@house-party-protocol
```

## Install by copy

```bash
cp -r lane-kit-1.1.0 <seu-projeto>/lane-kit
cd <seu-projeto>
python lane-kit/instaladores/kit-forge/kit_doctor.py install lane-kit --target . --human
#                                                                          ^ plano, zero escrita
python lane-kit/instaladores/kit-forge/kit_doctor.py install lane-kit --target . --apply
#                                                                          ^ aplica de verdade
```

## What the installer detects

```
greenfield    → copia templates/lanes.example.yaml -> .claude/lanes/lanes.yaml (estágio profile)
em-andamento  → .claude/settings.local.json com hooks já configurados (reportado, não sobrescrito)
re-run        → registry (~/.claude-kits/registry.json) marca re-run; lanes.yaml existente = skip-exists
```

## What is safe to run again

`lanes.yaml` (real config, git-tracked by design — unlike the runtime state below) is
**never overwritten** if it already exists. Runtime state is always regenerable and must
NEVER be versioned:
```
.claude/lanes/registry.json   # regenerado a cada lane_register.py
.claude/lanes/board.jsonl     # append-only, cresce por evento
.claude/lanes/.lock/          # locks efêmeros
.claude/lanes/.registry.lock/
.claude/lanes/mailbox/
```

**Git-guard rollout:** ALWAYS start with `git_guard.mode: warn` for at least 1 week and zero
real false positives before considering `mode: block` in `lanes.yaml` (never through
wiring/settings again — only the config). Validate with `bash evals/collision-git-guard.sh`
(3 green rounds).

## Manual wiring (human gate — never automatic)

> Editing `.claude/settings.local.json` is a human gate in this doctrine. Paste the block
> below yourself — WARN-only + `timeout: 30`.

```jsonc
// wiring.settings.jsonc — bloco de colar (GATE HUMANO). ADITIVO: mesclar dentro dos arrays
// "hooks" já existentes — NUNCA substituir o arquivo inteiro.
{
  "hooks": {
    "SessionStart": [
      { "hooks": [{ "type": "command", "command": "python \"${CLAUDE_PLUGIN_ROOT}/hooks/lane_register.py\"", "timeout": 30 }] }
    ],
    "PreToolUse": [
      { "matcher": "Bash", "hooks": [{ "type": "command", "command": "python \"${CLAUDE_PLUGIN_ROOT}/hooks/lane_git_guard.py\"", "timeout": 30 }] },
      { "matcher": "Edit|Write", "hooks": [{ "type": "command", "command": "python \"${CLAUDE_PLUGIN_ROOT}/hooks/lane_territory_guard.py\"", "timeout": 30 }] }
    ],
    "PostToolUse": [
      { "hooks": [{ "type": "command", "command": "python \"${CLAUDE_PLUGIN_ROOT}/hooks/lane_register.py\" --heartbeat", "timeout": 30 }] }
    ]
  }
}
```

Post-wiring checklist:
```bash
python "${CLAUDE_PLUGIN_ROOT}/hooks/_lane_io.py" --self-test
python "${CLAUDE_PLUGIN_ROOT}/hooks/lane_register.py" --self-test
python "${CLAUDE_PLUGIN_ROOT}/hooks/lane_git_guard.py" --self-test
python "${CLAUDE_PLUGIN_ROOT}/hooks/lane_territory_guard.py" --self-test
```

Round-trip proof (registers a lane and confirms it in the registry):
```bash
CLAUDE_LANE_ID=exec-a echo '{"hook_event_name":"SessionStart","session_id":"proof"}' \
  | python "${CLAUDE_PLUGIN_ROOT}/hooks/lane_register.py"
python "${CLAUDE_PLUGIN_ROOT}/hooks/_lane_io.py" status   # deve listar exec-a
```

## Proof / acceptance (real output, executed)

```bash
python hooks/_lane_io.py --self-test
```
```
self-test OK — register cria/evicta mortas/preserva started_at, heartbeat throttle+avanço,
liveness alive/suspect/dead, who_owns exclusivo+glob**+ignora morta, alive_others exclui self,
lock contention falha rápido sem travar, registry corrompido degrada limpo
```
<!-- executado: 2026-07-11 · exit=0 -->

## Undo

```
- Plugin: /plugin uninstall lane-kit@house-party-protocol
- Cópia: remover a pasta lane-kit/ + reverter o bloco colado em settings.local.json
  manualmente (gate humano também na remoção)
- Estado runtime: rm -rf .claude/lanes/registry.json .claude/lanes/board.jsonl
  .claude/lanes/.lock/ .claude/lanes/mailbox/ (efêmero, seguro apagar)
- lanes.yaml (config real, git-tracked): remover manualmente se não quiser mais o kit
```

---

*See `LANE-KIT.md` for the complete doctrine (board states, maker≠checker, territories).*
