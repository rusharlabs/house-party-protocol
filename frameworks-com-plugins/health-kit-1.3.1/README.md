[English](README.md) · [Português](README.pt-BR.md)

# Health Kit

Config-driven probe of service health (HTTP or local command) + a **statusline**
segment that shows per-service detail (`api:OK db:DOWN`) without ever touching the
network on the hot path — it only reads a cache that `health_probe.py` writes.
`health_probe.py` probes the services declared in `health.probes` and writes a JSON cache;
`statusline.py` (or any other tool) reads **only the cache** — it never does network I/O on
the path that runs at every keystroke/prompt. Two processes, one clear boundary: whoever
probes is not whoever displays. **Embedded doctrine:** SERVICE health ≠ DATA health — this
kit proves the process is up, not that the data it serves is correct/up to date.

## Prerequisites + external APIs

| Requirement | Minimum version | Required? |
|---|---|---|
| Python | 3.8 | yes |
| PyYAML | any | yes |

External services: **none kit-specific** — `health.probes` in your profile points at the
services OF YOUR project (HTTP or local command); the kit itself talks to no fixed service.

## What is in this folder

```
health-kit/
├── README.md                     ← este arquivo
├── profile.example.yaml          ← template comentado p/ copiar em projeto novo
├── _lib/
│   └── profile_loader.py         ← acha+lê o profile (stdlib + PyYAML)
├── scripts/
│   ├── health_probe.py           ← sonda os serviços, grava o cache
│   ├── gate_sheet_panel.py       ← painel de itens que dependem do humano (portável)
│   └── wire_statusline.py        ← arma a statusLine em settings.json (idempotente + --undo)
├── statusline/
│   └── statusline.py             ← barra composável; segmento 'health' com detalhe por-serviço
├── hooks/
│   └── hooks.json                ← SessionStart → health_probe.py --quiet (refresh do cache)
├── skills/
│   └── health-check/SKILL.md     ← doutrina + exemplos executados
└── .claude-plugin/
    └── plugin.json               ← manifesto do plugin
```

## Install as a plugin (1 click)

```bash
/plugin marketplace add .
/plugin install health-kit@house-party-protocol
```
Installs the `SessionStart` hook (automatic cache refresh at every new session) through
`${CLAUDE_PLUGIN_ROOT}`. The **statusLine remains manual** — run `wire_statusline.py`
(a Claude Code limit: a plugin cannot embed `statusLine`).

## Install by copy

```bash
cp -r health-kit-1.1.0 <seu-projeto>/health-kit
cd <seu-projeto>
python health-kit/instaladores/kit-forge/kit_doctor.py install health-kit --target . --human
#                                                                              ^ plano, zero escrita
python health-kit/instaladores/kit-forge/kit_doctor.py install health-kit --target . --apply
#                                                                              ^ aplica de verdade
```
The `configure` stage asks whether you want to configure `health.probes` now or copy
`profile.example.yaml` as is and adjust later (default: adjust later). Manual smoke test,
if you prefer not to use `kit_doctor.py`:
```bash
cp profile.example.yaml operator-profile.yaml   # ou mesclar com um já existente do Operator Kit
python health-kit/scripts/health_probe.py            # sonda + grava o cache
python health-kit/statusline/statusline.py --statusline   # lê o cache, mostra o segmento
```

## What the installer detects

```
greenfield    → copia profile.example.yaml -> operator-profile.yaml (estágio profile)
em-andamento  → operator-profile.yaml já existe com health.probes configurado (skip-exists)
re-run        → registry (~/.claude-kits/registry.json) marca re-run
```

## What is safe to run again

`wire_statusline.py` is **idempotent** (running it again is a no-op) and **never
overwrites** a `statusLine` already configured by another tool without `--force`:
```bash
python health-kit/scripts/wire_statusline.py --target .claude/settings.local.json
python health-kit/scripts/wire_statusline.py --undo --target .claude/settings.local.json
```
`operator-profile.yaml` is also never overwritten by the `profile` stage if it already exists.

## Manual wiring (human gate — never automatic)

> Editing `.claude/settings.local.json` is a human gate. `statusLine` is **always**
> manual (Claude Code does not accept `statusLine` inside a plugin) — run
> `wire_statusline.py` yourself (commands above). `SessionStart`/`hooks` come for free
> through the plugin path; on the copy path, paste `hooks/hooks.json` by hand into
> `.claude/settings.local.json`.

## Proof / acceptance (real output, executed)

Proof that the segment reacts to a real service going up and down — no mock:

```bash
# 1. sobe um servidor HTTP real na porta 18823
python -m http.server 18823 &
SRV_PID=$!

# 2. sonda: o serviço está UP
python health-kit/scripts/health_probe.py
# ⚕ 1/1 UP

python health-kit/statusline/statusline.py --statusline
# api:OK

# 3. mata o servidor
kill $SRV_PID

# 4. sonda de novo: o serviço está DOWN
python health-kit/scripts/health_probe.py
# ⚕ 0/1 UP (DOWN: api)

python health-kit/statusline/statusline.py --statusline
# api:DOWN
```
<!-- executado: 2026-07-10 · exit=0 -->

Actually executed in that run (port 18823, probe `type: http`): UP → `⚕ 1/1 UP`,
DOWN after `kill` → `⚕ 0/1 UP (DOWN: api)`. With `statusline.segments: ["health"]` alone,
the segment shows the service name: `api:OK` / `api:DOWN`.

**`health` segment — aggregate vs. detail:** 1-6 services show per-service detail
(`api:OK db:DOWN`); 7+ degrade to the aggregate `⚕<online>/<total>` (avoids blowing the
statusline width).

**Cache (schema):**
```json
{
  "ts": "2026-07-10 21:34 BRT",
  "health": {"services_online": 1, "services_total": 2},
  "services": {
    "servico-ok": {"online": true, "type": "cmd", "target": "..."},
    "servico-down": {"online": false, "type": "cmd", "target": "..."}
  }
}
```

## Undo

```
- Plugin: /plugin uninstall health-kit@house-party-protocol
- Cópia: remover a pasta health-kit/ do projeto
- statusLine: python health-kit/scripts/wire_statusline.py --undo --target .claude/settings.local.json
- Cache: rm .claude/health-cache.json (efêmero, seguro apagar — regenerado pelo próximo probe)
```

## Honest portability

`health_probe.py`, `statusline.py`, `wire_statusline.py`, `gate_sheet_panel.py` and
`_lib/profile_loader.py` are **100% portable** — they depend only on Python stdlib + PyYAML.
No mechanism depends on a network/service specific to any project: everything comes from
`health.probes` in the profile.
