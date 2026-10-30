# AGENTS.md — health-kit

This kit measures service health and keeps a cache-first statusline.

## Codex CLI

- Install by copy with `kit_doctor.py install --kit <health-kit> --host codex --target <repo> --apply`.
- Scripts live in `.agents/hpp/health-kit/`; skills live in `.agents/skills`.
- The Claude Code `SessionStart` hook is not activated on Codex. Schedule or run `health_probe.py` explicitly.

## Verification

```bash
python scripts/health_probe.py --self-test
python statusline/statusline.py --self-test
```
