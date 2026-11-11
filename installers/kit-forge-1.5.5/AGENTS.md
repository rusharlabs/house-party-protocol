# AGENTS.md — kit-forge

This kit assembles, validates and installs the other House Party Protocol kits.

## Codex CLI

- Use `kit_doctor.py install --kit <kit> --host codex --target <repo> --apply` for install-by-copy.
- The generator `tools/codex_skills.py` creates namespaced skills in `.agents/skills` and keeps the runtime in `.agents/hpp`.
- Claude Code hooks are not activated on Codex.

## Verification

```bash
python kit_doctor.py --self-test
python tools/codex_skills.py --self-test
python tools/skill_lint.py --self-test
```

Never relax the linter to make a package pass; fix the source.
