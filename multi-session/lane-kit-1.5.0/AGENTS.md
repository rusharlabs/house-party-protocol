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

`lane_board.py set <item> CHECKPOINT-READY --evidence-record <record.json>` needs the HPP core (`python -m hpp`) importable and exits 2 without it. The board self-test always checks that fail-closed branch; it verifies real records (valid accepted, not-evidence and blocked refused) only when the core is on `PYTHONPATH`, and its summary says which branch ran.
