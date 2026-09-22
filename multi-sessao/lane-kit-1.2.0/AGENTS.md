# AGENTS.md — lane-kit

This kit coordinates concurrent sessions with claim, territory and separate maker/checker.

## Codex CLI

- Install by copy with `kit_doctor.py install --kit <lane-kit> --host codex --target <repo> --apply`.
- Use the scripts from `.agents/hpp/lane-kit/`.
- Claude Code territory hooks are not activated on Codex; run the checks explicitly or wire them into the host's native mechanism.

## Verification

```bash
python scripts/lane_board.py --self-test
python hooks/lane_git_guard.py --self-test
python hooks/lane_territory_guard.py --self-test
```
