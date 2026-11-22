# AGENTS.md — lane-kit

This kit coordinates concurrent sessions with claim, territory and separate maker/checker.

## Codex CLI

- Install by copy with `kit_doctor.py install --kit <lane-kit> --host codex --target <repo> --apply`.
- The skills `lane-coordinator` and `house-session` also come through the Codex plugin channel: `codex plugin marketplace add rusharlabs/house-party-protocol`, then `codex plugin add lane-kit@house-party-protocol`. That plugin registers skills only (its `.codex-plugin/plugin.json` carries an empty `hooks` object); the scripts and hooks still come from the copy above.
- Use the scripts from `.agents/hpp/lane-kit/`.
- Claude Code territory hooks are not activated on Codex; run the checks explicitly or wire them into the host's native mechanism.
- Mail for your lane (`.claude/lanes/mailbox/*.md`, routed by a `## To: <lane_id>` line) is announced only when you run `CLAUDE_LANE_ID=<lane> python .agents/hpp/lane-kit/hooks/lane_register.py --heartbeat` (or the bare register) yourself — HPP wires no hook on this host; the JSON on stdout is the announcement, once per message. A verdict recorded on the board for your lane is written there by default (`mailbox.notify_on_verdict`) and, when `codex` is on PATH and `mailbox.native_doorbell` is on, also queued to your session with `codex queue --thread <your session id>`.

- The Lane Dashboard (`python .agents/hpp/lane-kit/scripts/lane_dashboard.py --project-dir .`) runs on this host too: it launches `codex` with `--model` when `agents.codex.model` is declared in `.claude/lanes/dashboard.json`, and every action it offers is also a terminal command you can run yourself (the action table in `README.md`; `lane_dashboard.py <command> --help` lists a command's options — the bare `--help` shows only those of `serve`).

## Verification

```bash
python scripts/lane_board.py --self-test
python scripts/lane_dashboard.py --self-test
python hooks/lane_git_guard.py --self-test
python hooks/lane_territory_guard.py --self-test
```

`lane_board.py set <item> CHECKPOINT-READY --evidence-record <record.json>` needs the HPP core (`python -m hpp`) importable and exits 2 without it. The board self-test always checks that fail-closed branch; it verifies real records (valid accepted, not-evidence and blocked refused) only when the core is importable — on `PYTHONPATH`, or, inside the product layout (`multi-session/<kit>/scripts` beside `hpp/`), taken by the self-test alone from that checkout — and its summary says which branch ran. An installed or copied kit, and every other command, still need the core installed.
