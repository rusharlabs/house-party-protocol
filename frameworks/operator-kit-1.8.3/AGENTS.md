# AGENTS.md — operator-kit

This kit provides portable gates, rules and scripts for verifiable operation.

## Codex CLI

- Work from the kit root.
- Install by copy with `kit_doctor.py install --kit <operator-kit> --host codex --target <repo> --apply`.
- Skills live in `<repo>/.agents/skills/`; the full runtime lives in `<repo>/.agents/hpp/operator-kit/`.
- Hooks in `hooks/hooks.json` are Claude Code only and are not activated on Codex. Run the gates explicitly.

## Verification

```bash
python scripts/done_gate.py --self-test
python scripts/live_count.py --self-test
python scripts/claude_md_from_profile.py --self-test
```

Do not edit `CHECKSUMS.txt` or the emitted kit; changes are born in the source and go through the forge.
