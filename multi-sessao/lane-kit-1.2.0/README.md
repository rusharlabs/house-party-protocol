# Lane Kit

N sessões de agente (lanes) trabalhando no mesmo repo ao mesmo tempo, sem colisão.
Quadro-branco de estados (`CLAIMED → BUILDING → CHECKPOINT-READY → UNDER-REVIEW →
VERIFIED/NEEDS-FIX → MERGED`) com maker≠checker cross-model **enforçado em código**
(não apenas convenção), registry de lanes vivas com heartbeat/liveness, guard de git
(bloqueia `commit -a`/`add -A`/`reset --hard` enquanto outra lane está viva) e guard de
território (zonas vermelhas + território exclusivo por lane). **Depende do
`continuity-kit`** (usa o campo `lane_id` do handoff-v1.1) — instale aquele primeiro.
Não faz o handoff de sessão em si — isso é o `continuity-kit`.

## Pré-requisitos + APIs externas

| Requisito | Versão mínima | Obrigatório? |
|---|---|---|
| Python | 3.9 | sim |
| PyYAML | qualquer | sim |
| `continuity-kit` | 1.1.0+ | sim — lane-kit lê `lane_id` do schema handoff-v1.1 dele |

Serviços externos: **nenhum — stdlib + PyYAML, só toca filesystem local + git do projeto-alvo.**

## Instalar via plugin

```bash
/plugin marketplace add .
/plugin install lane-kit@house-party-protocol
```

## Instalar por cópia

```bash
cp -r lane-kit-1.1.0 <seu-projeto>/lane-kit
cd <seu-projeto>
python lane-kit/instaladores/kit-forge/kit_doctor.py install lane-kit --target . --human
#                                                                          ^ plano, zero escrita
python lane-kit/instaladores/kit-forge/kit_doctor.py install lane-kit --target . --apply
#                                                                          ^ aplica de verdade
```

## O que o instalador detecta

```
greenfield    → copia templates/lanes.example.yaml -> .claude/lanes/lanes.yaml (estágio profile)
em-andamento  → .claude/settings.local.json com hooks já configurados (reportado, não sobrescrito)
re-run        → registry (~/.claude-kits/registry.json) marca re-run; lanes.yaml existente = skip-exists
```

## O que é seguro rodar de novo

`lanes.yaml` (config real, git-tracked por design — diferente do estado runtime abaixo)
**nunca é sobrescrito** se já existir. Estado runtime é sempre regenerável e NUNCA deve
ser versionado:
```
.claude/lanes/registry.json   # regenerado a cada lane_register.py
.claude/lanes/board.jsonl     # append-only, cresce por evento
.claude/lanes/.lock/          # locks efêmeros
.claude/lanes/.registry.lock/
.claude/lanes/mailbox/
```

**Rollout do git-guard:** comece SEMPRE com `git_guard.mode: warn` por ≥1 semana e zero
falso-positivo real antes de considerar `mode: block` em `lanes.yaml` (nunca via
wiring/settings de novo — só o config). Validar com `bash evals/collision-git-guard.sh`
(3 rodadas verdes).

## Wiring manual (gate humano — nunca automático)

> ⚠️ Editar `.claude/settings.local.json` é gate humano nesta doutrina. Cole você mesmo
> o bloco abaixo — WARN-only + `timeout: 30`.

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

Checklist pós-wiring:
```bash
python "${CLAUDE_PLUGIN_ROOT}/hooks/_lane_io.py" --self-test
python "${CLAUDE_PLUGIN_ROOT}/hooks/lane_register.py" --self-test
python "${CLAUDE_PLUGIN_ROOT}/hooks/lane_git_guard.py" --self-test
python "${CLAUDE_PLUGIN_ROOT}/hooks/lane_territory_guard.py" --self-test
```

Prova round-trip (registra uma lane e confirma no registry):
```bash
CLAUDE_LANE_ID=exec-a echo '{"hook_event_name":"SessionStart","session_id":"proof"}' \
  | python "${CLAUDE_PLUGIN_ROOT}/hooks/lane_register.py"
python "${CLAUDE_PLUGIN_ROOT}/hooks/_lane_io.py" status   # deve listar exec-a
```

## Prova / aceite (saída real, executada)

```bash
python hooks/_lane_io.py --self-test
```
```
self-test OK — register cria/evicta mortas/preserva started_at, heartbeat throttle+avanço,
liveness alive/suspect/dead, who_owns exclusivo+glob**+ignora morta, alive_others exclui self,
lock contention falha rápido sem travar, registry corrompido degrada limpo
```
<!-- executado: 2026-07-11 · exit=0 -->

## Desfazer

```
- Plugin: /plugin uninstall lane-kit@house-party-protocol
- Cópia: remover a pasta lane-kit/ + reverter o bloco colado em settings.local.json
  manualmente (gate humano também na remoção)
- Estado runtime: rm -rf .claude/lanes/registry.json .claude/lanes/board.jsonl
  .claude/lanes/.lock/ .claude/lanes/mailbox/ (efêmero, seguro apagar)
- lanes.yaml (config real, git-tracked): remover manualmente se não quiser mais o kit
```

---

*Ver `LANE-KIT.md` para a doutrina completa (estados do board, maker≠checker, territórios).*
