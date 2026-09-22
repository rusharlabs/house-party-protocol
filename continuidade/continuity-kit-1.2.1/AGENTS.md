# AGENTS.md — continuity-kit

This kit preserves resume state and requires re-derivation before repeating work.

## Codex CLI

- Install by copy with `kit_doctor.py install --kit <continuity-kit> --host codex --target <repo> --apply`.
- Templates and scripts live in `.agents/hpp/continuity-kit/`.
- Claude Code lifecycle hooks are not activated on Codex; invoke the scripts in the session flow.

## Verification

```bash
python scripts/doc_rollup.py --self-test
python scripts/state_mirror.py --self-test
```
