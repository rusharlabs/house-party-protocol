[English](README.md) · [Português](README.pt-BR.md)

# Continuity Kit

An agent session survives a stop/`/clear`/crash without losing the next step. The
handoff (schema `handoff-v1.1`) records a git block (branch/commit/staged) + a
`re_derive_cmd` (LC-1 — re-derive the state live, never trust what was left written)
+ a `verify_first_cmd` (LC-4 — before continuing an action the handoff describes,
check whether it was already done, never re-fire blindly). It also includes **doc-rollup**
(project history/evolution that consolidates itself, with built-in degradation above size
thresholds). It does not do multi-session/lanes — for that, see `lane-kit` (which depends
on this kit).

## Prerequisites + external APIs

| Requirement | Minimum version | Required? |
|---|---|---|
| Python | 3.8 | yes |
| PyYAML | any | yes — `doc_rollup.py` exits 2 without it; `state_mirror.py` becomes a silent no-op without it |

External services: **none — stdlib + PyYAML, touches only the local filesystem + the target project's git.**

## Install as a plugin

```bash
/plugin marketplace add rushar-labs/house-party-protocol
/plugin install continuity-kit@house-party-protocol
```
`.claude-plugin/plugin.json` declares `hooks/hooks.json`, so the plugin wires three
entries through `${CLAUDE_PLUGIN_ROOT}` (each launched by `hooks/pyrun.sh`, which resolves
the project's Python; WARN-only, `timeout: 30`): `handoff_inject.py` on `SessionStart`
(injects the newest valid handoff, ≤4 KB, and records `consumed`), and `handoff_guard.py`
on `Stop` and on `PreCompact` (makes sure a fresh handoff exists, never blocking for real).
`hooks/session_boot.py` — a generic `SessionStart` that adds git HEAD/branch/tags and the
live sections of your state doc, then delegates to `handoff_inject.py` — is not wired by
the plugin; paste it yourself if you want it. Skills are auto-discovered.

## Install by copy

In the emitted distribution this module lives in `continuidade/continuity-kit-1.2.1/` (the
directory carries the version — state it once, in `KIT`). The installer is
`instaladores/kit-forge-1.4.0/kit_doctor.py` — the single installation engine of the whole
marketplace, see `INSTALL-CONTRACT.md` at the distribution root. Run it from the
distribution root; it plans first and writes only on a second, explicit `--apply`:

```bash
KIT=continuidade/continuity-kit-1.2.1
cp -r "$KIT" ../your-repo/continuity-kit      # the copy itself (kit_doctor does not copy on claude-code)
python instaladores/kit-forge-1.4.0/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo
python instaladores/kit-forge-1.4.0/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo --apply
# Codex CLI: --host codex — the installer copies the module into .agents/hpp/continuity-kit
#            and each skill into .agents/skills/hpp-continuity-kit-<skill>; no cp -r needed
```

## What the installer detects

The `detect` stage classifies the target (read-only) with exactly these three labels:

```
greenfield    -> no prior config in the target; profile stage would copy rollup.example.yaml -> rollup.yaml; no previous handoff
in-progress   -> .claude/ exists, or settings(.local).json already has hooks/statusLine, or rollup.yaml is
                 already present, or the repo has more than 3 commits: reported, never overwritten (skip-exists)
re-run        -> this kit+target pair is already in the registry (~/.claude-kits/registry.json)
```

## What is safe to run again

The `profile` stage of `kit_doctor.py` **never overwrites** `rollup.yaml` if it already
exists (skip-exists, reported explicitly — not silently). The handoff content itself
(`.claude/handoff/HANDOFF-LEDGER.jsonl`) is append-only by design (each event becomes a
new line; nothing is rewritten). Running `kit_doctor.py install --apply` again is safe:
customisation in `rollup.yaml` survives.

## Manual wiring (human gate — never automatic)

> Editing `.claude/settings.local.json` is a human gate in this doctrine — automated
> sessions have an explicit lock against self-editing settings/hooks files. On the copy
> path there is no `${CLAUDE_PLUGIN_ROOT}`: paste the block below yourself, with the
> folder you copied the kit to — WARN-only + `timeout: 30`.

```jsonc
// Paste block (HUMAN GATE — the classifier blocks self-editing of settings/hooks).
// ADDITIVE: merge into the "hooks" arrays that already exist in
// settings.json/settings.local.json — NEVER replace the whole file.
//
// Launcher: NEVER hardcode "py" — detect it at install time (hooks/pyrun.sh, or the Python the
// installer resolved). The commands below use "python" (right on most PATHs); swap in the
// absolute path of the venv if the target project has one.
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          { "type": "command", "command": "python \"continuity-kit/hooks/handoff_inject.py\"", "timeout": 30 }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "python \"continuity-kit/hooks/handoff_guard.py\"", "timeout": 30 }
        ]
      }
    ],
    "PreCompact": [
      {
        "hooks": [
          { "type": "command", "command": "python \"continuity-kit/hooks/handoff_guard.py\"", "timeout": 30 }
        ]
      }
    ]
  }
}
```

Post-wiring checklist (run the real round-trip, do not presume — LC-1):
```bash
python continuity-kit/hooks/_handoff_io.py --self-test
python continuity-kit/hooks/_handoff_io.py write --demo --lane solo
echo '{"hook_event_name":"SessionStart","session_id":"proof"}' | python continuity-kit/hooks/handoff_inject.py
tail -1 .claude/handoff/HANDOFF-LEDGER.jsonl   # confirm "event": "consumed"
```

## Proof / acceptance (real output, executed)

```bash
python hooks/_handoff_io.py --self-test
```
```
self-test OK — write válido+ledger, rejeita sem verify_first_cmd, rejeita sem re_derive_cmd, rejeita segredo, rejeita degraded-auto sem porcelain, render com LC-4, staleness, consume, degraded-auto
```
<!-- executado: 2026-09-21 · exit=0 -->

Extended proof (real round-trip through the hook interface — stdin JSON → stdout JSON, C1-C4:
round-trip, staleness, degraded-auto <5s, anti-replay LC-4):
```bash
bash evals/handoff-roundtrip-C1-C4.sh
```

## Undo

```
- Plugin:  /plugin uninstall continuity-kit@house-party-protocol
- Copy:    remove the continuity-kit/ folder from the project + revert the block pasted into
           settings.local.json by hand (removal is a human gate too)
- Handoff ledger: .claude/handoff/HANDOFF-LEDGER.jsonl is append-only — remove the whole
           file to reset the history (it does not affect the newest handoff in
           .claude/RESUME-NEXT.md, which is regenerated at every Stop)
```

---

*For multi-session/lanes see `LANE-KIT.md` inside the `lane-kit` module — this kit is the single-lane foundation.*
