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

## Install as a plugin (1 click)

```bash
/plugin marketplace add rusharlabs/house-party-protocol
/plugin install gotcha-memory@house-party-protocol
```

Installs the hooks (`PreToolUse` → preflight; `PostToolUse` **and** `PostToolUseFailure` →
postflight, matcher `Bash`) through `${CLAUDE_PLUGIN_ROOT}` — no hardcoded relative path.
The host emits `PostToolUseFailure` when Bash fails; listening only to `PostToolUse` would
leave the memory blind to the failure. The same call (`tool_use_id`) becomes **one** record,
however many events arrive.

## Install by copy (manual wire)

In the emitted distribution this module lives in `continuity/gotcha-memory-1.0.1/` (the
directory carries the version — state it once, in `KIT`). The marketplace installer plans
first and writes only on a second, explicit `--apply`; its `profile` stage copies
`profile.example.yaml` → `profile.yaml` and `curated.seed.example.yaml` →
`curated.seed.yaml` into the target (never overwriting), and its `configure` stage asks
`seedar_curated_agora` (seed the curated lessons now? default: no):

```bash
KIT=continuity/gotcha-memory-1.0.1
cp -r "$KIT" ../your-repo/gotcha-memory       # the copy itself (kit_doctor does not copy on claude-code)
python installers/kit-forge-1.4.1/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo
python installers/kit-forge-1.4.1/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo --apply
# Codex CLI: --host codex — the installer copies the module into .agents/hpp/gotcha-memory
#            and the skill into .agents/skills/hpp-gotcha-memory-<skill>; no cp -r needed
```

Then paste into `.claude/settings.local.json` (wiring hooks is a **human gate** by design —
editing settings is your decision):

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

Copy from `profile.example.yaml` (the loader reads `operator-profile.yaml`, so the
`profile.yaml` the installer leaves must be renamed or merged into it). Without a profile,
defaults: store `.claude/gotchas/`, 24h window, min_count 3, top 5. The store can also be
overridden through the `GOTCHA_STORE_DIR` env var. Recommended: **gitignore the store**
(regenerable local memory).

## Direct use (CLI)

```bash
python _lib/gotchas_memory.py                                  # demo of the whole loop (temporary store)
python _lib/gotchas_memory.py --self-test                      # core assertions
python _lib/gotchas_memory.py --seed curated.seed.example.yaml # seeds your rules (idempotent)
python _lib/gotchas_memory.py --preamble "run the deploy"      # what the agent would see before that task
```

## Verification (the criterion for "installed and working")

```bash
python _lib/error_strategy.py --self-test      # self-test OK
python _lib/gotchas_memory.py --self-test      # self-test OK ✓
python hooks/gotcha_preflight.py --self-test   # self-test OK
python hooks/gotcha_postflight.py --self-test  # self-test OK
```
<!-- executado: 2026-09-21 · exit=0 (the four) -->

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
