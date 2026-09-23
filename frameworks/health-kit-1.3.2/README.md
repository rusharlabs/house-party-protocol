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
├── README.md · README.pt-BR.md   ← this file (and its Portuguese twin)
├── profile.example.yaml          ← commented template to copy into a new project
├── _lib/
│   └── profile_loader.py         ← finds + reads the profile (stdlib + PyYAML)
├── scripts/
│   ├── health_probe.py           ← probes the services, writes the cache
│   ├── gate_sheet_panel.py       ← panel of items that depend on a human (portable)
│   └── wire_statusline.py        ← wires the statusLine into settings.json (idempotent + --undo)
├── statusline/
│   └── statusline.py             ← composable bar; 'health' segment with per-service detail
├── hooks/
│   ├── hooks.json                ← SessionStart → health_probe.py --quiet (cache refresh)
│   └── pyrun.sh                  ← resolves the project's Python interpreter for the hook
├── skills/
│   ├── health-check/SKILL.md     ← doctrine + executed examples
│   └── dashboard-builder/SKILL.md← monitoring dashboards that answer operator questions
├── install/
│   └── kit.install.yaml          ← manifest read by kit_doctor.py install (1 question)
├── .claude-plugin/
│   └── plugin.json               ← plugin manifest (declares hooks/hooks.json)
├── AGENTS.md                     ← Codex CLI entry point (what Codex reads on --host codex)
└── LICENSE · CHECKSUMS.txt · SANITIZATION.md   ← added by the forge at emission
```

## Install as a plugin (1 click)

```bash
/plugin marketplace add rusharlabs/house-party-protocol
/plugin install health-kit@house-party-protocol
```
Installs the `SessionStart` hook (automatic cache refresh at every new session) through
`${CLAUDE_PLUGIN_ROOT}`. The **statusLine remains manual** — run `wire_statusline.py`
(a Claude Code limit: a plugin cannot embed `statusLine`).

## Install by copy

In the emitted distribution this module lives in `frameworks/health-kit-1.3.2/`
(the directory carries the version — state it once, in `KIT`). The installer is
`installers/kit-forge-1.4.1/kit_doctor.py`; run it from the distribution root. It plans
first and writes only on a second, explicit `--apply`:

```bash
KIT=frameworks/health-kit-1.3.2
cp -r "$KIT" ../your-repo/health-kit          # the copy itself (kit_doctor does not copy on claude-code)
python installers/kit-forge-1.4.1/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo
python installers/kit-forge-1.4.1/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo --apply
# Codex CLI: --host codex — the installer copies the module into .agents/hpp/health-kit
#            and each skill into .agents/skills/hpp-health-kit-<skill>; no cp -r needed
```
The `configure` stage has one question, `configurar_probes_agora` — configure
`health.probes` now, or copy `profile.example.yaml` as is and adjust later (the default;
answer it for real with `--answers <file.json|yaml>`). The `profile` stage copies
`profile.example.yaml` into the target as `profile.yaml` (never overwritten); the loader
reads **`operator-profile.yaml`**, so rename it (or merge it into the Operator Kit profile
you already have). Manual smoke test, if you prefer not to use `kit_doctor.py`:
```bash
cp profile.example.yaml operator-profile.yaml   # or merge into an existing Operator Kit profile
python health-kit/scripts/health_probe.py            # probes + writes the cache
echo '{}' | python health-kit/statusline/statusline.py --statusline   # reads the cache, prints the segment
```

## What the installer detects

The `detect` stage classifies the target (read-only) with exactly these three labels:

```
greenfield    -> no prior config in the target; profile stage would copy profile.example.yaml -> profile.yaml
in-progress   -> .claude/ exists, or settings(.local).json already has hooks/statusLine, or a real
                 profile is present, or the repo has more than 3 commits: reported, never overwritten (skip-exists)
re-run        -> this kit+target pair is already in the registry (~/.claude-kits/registry.json)
```

## What is safe to run again

`wire_statusline.py` is **idempotent** (running it again is a no-op) and **never
overwrites** a `statusLine` already configured by another tool without `--force`:
```bash
python health-kit/scripts/wire_statusline.py --target .claude/settings.local.json
python health-kit/scripts/wire_statusline.py --undo --target .claude/settings.local.json
```
A profile that already exists is also never overwritten by the `profile` stage.

## Manual wiring (human gate — never automatic)

> Editing `.claude/settings.local.json` is a human gate. `statusLine` is **always**
> manual (Claude Code does not accept `statusLine` inside a plugin) — run
> `wire_statusline.py` yourself (commands above). `SessionStart`/`hooks` come for free
> through the plugin path; on the copy path, paste `hooks/hooks.json` by hand into
> `.claude/settings.local.json`.

## Proof / acceptance (real output, executed)

Proof that the segment reacts to a real service going up and down — no mock. The profile
used declares one probe, `api` → `http://127.0.0.1:18823/`, and
`statusline.segments: ["health"]`; `statusline.py` reads the host's JSON on stdin, hence
the `echo '{}' |` when you drive it from a shell:

```bash
# 1. start a real HTTP server on port 18823
python -m http.server 18823 &
SRV_PID=$!

# 2. probe: the service is UP
python health-kit/scripts/health_probe.py
# ⚕ 1/1 UP

echo '{}' | python health-kit/statusline/statusline.py --statusline
# api:OK

# 3. kill the server
kill $SRV_PID

# 4. probe again: the service is DOWN
python health-kit/scripts/health_probe.py
# ⚕ 0/1 UP (DOWN: api)

echo '{}' | python health-kit/statusline/statusline.py --statusline
# api:DOWN
```
<!-- executado: 2026-09-21 · exit=0 -->

Actually executed in that run (port 18823, probe `type: http`): UP → `⚕ 1/1 UP`,
DOWN after `kill` → `⚕ 0/1 UP (DOWN: api)`. With `statusline.segments: ["health"]` alone,
the segment shows the service name: `api:OK` / `api:DOWN`.

**`health` segment — aggregate vs. detail:** 1-6 services show per-service detail
(`api:OK db:DOWN`); 7+ degrade to the aggregate `⚕<online>/<total>` (avoids blowing the
statusline width).

**Cache (schema — the file left by step 4 above):**
```json
{
  "ts": "2026-09-21 18:45 BRT",
  "health": {"services_online": 0, "services_total": 1},
  "services": {
    "api": {"online": false, "type": "http", "target": "http://127.0.0.1:18823/"}
  }
}
```

## Undo

```
- Plugin:  /plugin uninstall health-kit@house-party-protocol
- Copy:    remove the health-kit/ folder from the project
- statusLine: python health-kit/scripts/wire_statusline.py --undo --target .claude/settings.local.json
- Cache:   rm .claude/health-cache.json (ephemeral, safe to delete — regenerated by the next probe)
```

## Honest portability

`health_probe.py`, `statusline.py`, `wire_statusline.py`, `gate_sheet_panel.py` and
`_lib/profile_loader.py` are **100% portable** — they depend only on Python stdlib + PyYAML.
No mechanism depends on a network/service specific to any project: everything comes from
`health.probes` in the profile.
