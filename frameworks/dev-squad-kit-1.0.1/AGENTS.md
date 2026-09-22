# AGENTS.md — dev-squad-kit

This kit offers development roles as commands and subagents, plus three parallel-reading skills.

## Codex CLI

- Install by copy with `kit_doctor.py install --kit <dev-squad-kit> --host codex --target <repo> --apply`.
- Skills are mirrored into `.agents/skills`; `agents/*.md` are Claude Code artifacts and serve as role specifications on Codex.
- Checkers are read-only: never grant `Write` or `Edit` to the review roles.

## Verification

```bash
python <marketplace>/installers/kit-forge-*/tools/skill_lint.py --all skills
```
