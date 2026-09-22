# AGENTS.md — claude-dev-kit

This kit builds and validates skills, hooks and plugins; the historical name does not limit the use of the skills on Codex.

## Codex CLI

- Install by copy with `kit_doctor.py install --kit <claude-dev-kit> --host codex --target <repo> --apply`.
- Skills are generated in `.agents/skills`; tools live in `.agents/hpp/claude-dev-kit/`.
- `wire_settings.py`, `hooks.json` and `.claude-plugin` plugins remain Claude Code specific.

## Verification

```bash
python tools/skill_lint.py --self-test
python scripts/wire_settings.py --self-test
python scripts/install_git_hook.py --self-test
```
