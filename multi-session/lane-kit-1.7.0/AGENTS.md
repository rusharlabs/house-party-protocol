# AGENTS.md — lane-kit

This kit coordinates concurrent sessions with claim, territory and separate maker/checker.

## Codex CLI

- Install by copy with `kit_doctor.py install --kit <lane-kit> --host codex --target <repo> --apply`.
- Use the scripts from `.agents/hpp/lane-kit/`.
- Claude Code territory hooks are not activated on Codex; run the checks explicitly or wire them into the host's native mechanism.
- Mail for your lane (`.claude/lanes/mailbox/*.md`, routed by a `## To: <lane_id>` line) is announced only when you run `CLAUDE_LANE_ID=<lane> python .agents/hpp/lane-kit/hooks/lane_register.py --heartbeat` (or the bare register) yourself — there are no lifecycle hooks on this host; the JSON on stdout is the announcement, once per message. A verdict recorded on the board for your lane is written there by default (`mailbox.notify_on_verdict`) and, when `codex` is on PATH and `mailbox.native_doorbell` is on, also queued to your session with `codex queue --thread <your session id>`.

- The Lane Dashboard (`python .agents/hpp/lane-kit/scripts/lane_dashboard.py --project-dir .`) runs on this host too: it launches `codex` with `--model` when `agents.codex.model` is declared in `.claude/lanes/dashboard.json`, and every action it offers is also a terminal command you can run yourself (`lane_dashboard.py --help`).

## Verification

```bash
python scripts/lane_board.py --self-test
python scripts/lane_dashboard.py --self-test
python hooks/lane_git_guard.py --self-test
python hooks/lane_territory_guard.py --self-test
```

`lane_board.py set <item> CHECKPOINT-READY --evidence-record <record.json>` needs the HPP core (`python -m hpp`) importable and exits 2 without it. The board self-test always checks that fail-closed branch; it verifies real records (valid accepted, not-evidence and blocked refused) only when the core is on `PYTHONPATH`, and its summary says which branch ran.
