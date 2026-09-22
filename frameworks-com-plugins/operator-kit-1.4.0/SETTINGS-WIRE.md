[English](SETTINGS-WIRE.md) · [Português](SETTINGS-WIRE.pt-BR.md)

# SETTINGS-WIRE — activating the hooks (HUMAN GATE)

> ⚠️ **Editing `.claude/settings.local.json` is a human gate** — automated sessions usually have an explicit lock against self-editing settings/hooks files (by design — mutating one's own permission should not be automatic). Paste the blocks below yourself. Everything is **WARN-only (exit 0)** + `timeout: 30` (Anthropic standard).

The hooks **MERGE** into the existing `hooks` arrays of your `settings.local.json` (they do not replace them) — add the entries below to the same arrays, without deleting what is already there.

## 0. RECOMMENDED path: install as a PLUGIN (1-click auto-wire)
Instead of pasting hook by hook, install `operator-kit` as a plugin — `hooks/hooks.json` arms the 7 WARN-only hooks at once (via `${CLAUDE_PLUGIN_ROOT}`):
```bash
/plugin marketplace add .                            # registers the marketplace (name = "name" of marketplace.json)
/plugin install operator-kit@<marketplace-name>      # installs + arms the 7 hooks automatically
```
The statusLine (§2) and the output-styles remain manual (Claude Code limit: a plugin cannot embed a statusLine). Section 1 below is the alternative MANUAL path (no plugin).

---

## 1. Manual path (alternative to the plugin) — the kit's 7 hooks

Copy the entries of this kit's `hooks/hooks.json` into the `PreToolUse`/`UserPromptSubmit`/`Stop` arrays of your `settings.local.json`, adjusting the path to wherever you placed the kit (e.g. `operator-kit/hooks/...`):

```jsonc
"PreToolUse": [
  {
    "matcher": "Bash",
    "hooks": [
      { "type": "command", "command": "python operator-kit/hooks/operation_guard_portable.py", "timeout": 30 },
      { "type": "command", "command": "python operator-kit/hooks/snapshot_rollback_gate.py", "timeout": 30 },
      { "type": "command", "command": "python operator-kit/hooks/external_send_draft_gate.py", "timeout": 30 }
    ]
  },
  {
    "matcher": "Edit|Write|MultiEdit",
    "hooks": [
      { "type": "command", "command": "python operator-kit/hooks/secret_scan_on_write.py", "timeout": 30 },
      { "type": "command", "command": "python operator-kit/hooks/project_root_confirm.py", "timeout": 30 }
    ]
  }
],
"UserPromptSubmit": [
  {
    "matcher": "*",
    "hooks": [
      { "type": "command", "command": "python operator-kit/hooks/rule_capture.py", "timeout": 30 }
    ]
  }
],
"Stop": [
  {
    "matcher": "*",
    "hooks": [
      { "type": "command", "command": "python operator-kit/hooks/ralph_gate.py", "timeout": 120 },
      { "type": "command", "command": "python operator-kit/hooks/autoprompt_resume.py", "timeout": 30 }
    ]
  }
]
```

All 7 read `operator-profile.yaml` (via `_lib/profile_loader.py`) and degrade to safe defaults if the profile does not exist — none of them breaks the caller's flow.

## 2. gitignore (mandatory when activating the `autoprompt_resume` Stop hook)
Add the profile's `paths.resume_pointer` line to `.gitignore`:
```
.claude/RESUME-NEXT.md
```

## 3. statusLine — the live progress bar (does NOT go in the plugin; settings only)
Claude Code does not accept `statusLine` inside a plugin — it has to go in `settings.json`/`settings.local.json`. Point it at the kit's portable statusline (it reads `operator-profile.yaml`):
```jsonc
"statusLine": { "type": "command", "command": "python operator-kit/statusline/statusline.py --statusline", "padding": 0 }
```
Reopen the session for it to appear in the footer. Render example (default segments `progress,health,commits,branch`): `🧠 meu-projeto 58% █████░░░ ▸ 34c hoje ▸ feat/minha-branch` (the `health` segment only appears if `health.probes` is configured — see `health-kit`).

## Post-wire smoke test
```bash
python operator-kit/hooks/autoprompt_resume.py --self-test
python operator-kit/hooks/autoprompt_resume.py --print   # checks the profile's paths
python operator-kit/scripts/done_gate.py --self-test
```

## What is NOT a gate (already built, no settings touched)
- `operator-profile.yaml`, `profile.example.yaml`, `_lib/profile_loader.py`
- `scripts/done_gate.py --profile <tipo>`
- `templates/loop-charter-template.md`
- `output-styles/direct-register.md`, `output-styles/execute-100pct.md` (activate with `/output-style` after copying to `.claude/output-styles/`)
