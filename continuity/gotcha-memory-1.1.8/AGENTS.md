# AGENTS.md — gotcha-memory

This kit turns recurring failures into queryable operational lessons.

## Codex CLI

- Install by copy with `kit_doctor.py install --kit <gotcha-memory> --host codex --target <repo> --apply`.
- Runtime and example memory live in `.agents/hpp/gotcha-memory/`.
- Claude Code `PreToolUse`/`PostToolUse`/`PostToolUseFailure` hooks are not activated on Codex; use the scripts explicitly.

## Verification

```bash
python hooks/gotcha_preflight.py --self-test
python hooks/gotcha_postflight.py --self-test
```
