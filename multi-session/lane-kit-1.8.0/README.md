[English](README.md) · [Português](README.pt-BR.md)

# Lane Kit

N agent sessions (lanes) working on the same repo at the same time, without collision.
A whiteboard of states (`CLAIMED → BUILDING → CHECKPOINT-READY → UNDER-REVIEW →
VERIFIED/NEEDS-FIX → MERGED`) with cross-model maker≠checker **enforced in code**
(not only by convention), a registry of live lanes with heartbeat/liveness, a git guard
(blocks `commit -a`/`add -A`/`reset --hard` while another lane is alive) and a territory
guard (red zones + exclusive territory per lane). It does not do the session handoff
itself — that is the `continuity-kit`, which complements this kit: the two are recommended
together, and neither requires the other. The continuity-kit hooks resolve a session's lane in
the order this kit's register uses (`CLAUDE_LANE_ID`, then the hook payload, then `solo`). The board can also be followed and
operated from a local page, the [Lane Dashboard](#lane-dashboard--the-board-as-a-local-page-every-action-a-terminal-command),
where every action is a terminal command too.

## Prerequisites + external APIs

| Requirement | Minimum version | Required? |
|---|---|---|
| Python | 3.9 | yes |
| PyYAML | any | yes |
| `continuity-kit` | any | no — recommended: it keeps each session's handoff; no lane-kit code reads its files |
| HPP core (`python -m hpp`) | 2.6.0 or newer (the first release with `hpp evidence`) | no — only for `--evidence-record` |

External services: **none — stdlib + PyYAML, touches only the local filesystem + the target project's git.**

Optional: `lane_board.py set <item> CHECKPOINT-READY --evidence-record .hpp/evidence/<id>-<UTC>.json`
attaches a run recorded by `hpp evidence run` instead of pasted text. The board asks the HPP core to
verify the record and accepts it only as `valid` (an intact record of a passed run), storing
`{path, record_sha256, id}` in the event; `render` shows the id and a hash prefix. Without the core
importable the flag exits 2 and writes nothing — free-text `--evidence` needs nothing extra.

## Install as a plugin

```bash
/plugin marketplace add rusharlabs/house-party-protocol
/plugin install lane-kit@house-party-protocol
```
`.claude-plugin/plugin.json` declares `hooks/hooks.json`, so the plugin wires four entries
through `${CLAUDE_PLUGIN_ROOT}` (each launched by `hooks/pyrun.sh`, which resolves the
project's Python; WARN-only, `timeout: 30`): `lane_register.py` on `SessionStart`
(registers this session as a live lane and announces unread mail) and again on `PostToolUse`
with `--heartbeat` (liveness, plus the announcement of mail that arrived mid-session);
`lane_git_guard.py` on `PreToolUse` for `Bash` (flags `add -A`/`commit -a`/`reset --hard`
and the like while another lane is alive); `lane_territory_guard.py` on `PreToolUse` for
`Edit|Write` (red zones + territory collisions). Skills are auto-discovered.

On Codex CLI the same repository is a plugin marketplace of its own, and lane-kit is one of its
plugins:

```bash
codex plugin marketplace add rusharlabs/house-party-protocol
codex plugin add lane-kit@house-party-protocol
```
There the plugin registers the two skills, `lane-coordinator` and `house-session`, and nothing
else: its `.codex-plugin/plugin.json` carries an empty `hooks` object, so the four hooks above
stay Claude Code's, and the runtime (scripts and hooks) still comes through the verified copy
below (`--host codex`).

## Install by copy

In the emitted distribution this module lives in `multi-session/lane-kit-1.8.0/` (the
directory carries the version — state it once, in `KIT`). The installer is
`installers/kit-forge-1.5.2/kit_doctor.py`; run it from the distribution root. It plans
first and writes only on a second, explicit `--apply`:

```bash
KIT=multi-session/lane-kit-1.8.0
cp -r "$KIT" ../your-repo/lane-kit            # the copy itself (kit_doctor does not copy on claude-code)
python installers/kit-forge-1.5.2/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo
python installers/kit-forge-1.5.2/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo --apply
# Codex CLI: --host codex — the installer copies the module into .agents/hpp/lane-kit
#            and each skill into .agents/skills/hpp-lane-kit-<skill>; no cp -r needed
```
The config file is yours to create — the `profile` stage only copies `*.example.*` files
found at the module **root**, and `lanes.example.yaml` lives in `templates/`:
```bash
mkdir -p .claude/lanes && cp lane-kit/templates/lanes.example.yaml .claude/lanes/lanes.yaml
```

## What the installer detects

The `detect` stage classifies the target (read-only) with exactly these three labels:

```
greenfield    -> no prior config in the target; nothing to copy (lanes.yaml is created by you, see above)
in-progress   -> .claude/ exists, or settings(.local).json already has hooks/statusLine, or the repo has
                 more than 3 commits: reported, never overwritten
re-run        -> this kit+target pair is already in the registry (~/.claude-kits/registry.json)
```

## What is safe to run again

`lanes.yaml` (real config, git-tracked by design — unlike the runtime state below) is
never touched by the installer. Runtime state is what the kit writes as it runs, and it must
NEVER be versioned:
```
.claude/lanes/registry.json       # regenerated by every lane_register.py
.claude/lanes/board.jsonl         # append-only, grows per event
.claude/lanes/effects.json        # the effect ledger: which verdict was decided, which was delivered
.claude/lanes/mailbox/            # messages between lanes + .announced/ (what each lane was already told, one .lock per lane)
.claude/lanes/rescue/             # rescue patches of evicted lanes: full copies of work nobody committed
.claude/lanes/sessions/           # prompts, launch and run records and logs of the sessions the dashboard started
.claude/lanes/waves/              # the wave requests the dashboard recorded
.claude/lanes/decision-briefs/    # the briefs the dashboard asked for
.claude/lanes/.lock/              # ephemeral locks: the board's,
.claude/lanes/.registry.lock/     # the registry's,
.claude/lanes/.effects.lock/      # the effect ledger's,
.claude/lanes/.dashboard-*.lock/  # and the dashboard's (backlog, waves, one per session)
```
The session logs (`sessions/<lane>.log`, and a brief's `<lane>.stderr.log`) hold what an agent
printed, and a rescue patch holds uncommitted work verbatim: never commit either.

**Git-guard rollout:** ALWAYS start with `git_guard.mode: warn` for at least 1 week and zero
real false positives before considering `mode: block` in `lanes.yaml` (never through
wiring/settings again — only the config). Validate with `bash evals/collision-git-guard.sh`
(3 green rounds).

## Lane identity — how a session says which lane it is

Every hook of this kit acts for one lane, and a session names its lane in the environment it
is started with — the hooks inherit it. Not in `lanes.yaml`, not on the board:

| Variable | Read by | When it is absent |
|---|---|---|
| `CLAUDE_LANE_ID` | `lane_register.py` (register and heartbeat), `lane_git_guard.py`, `lane_territory_guard.py` | the register takes `lane_id` from the hook payload, then `solo`; the two guards go straight to `solo` |
| `CLAUDE_LANE_ID` | continuity-kit, when installed: `handoff_inject.py` (which handoff `SessionStart` injects; with none for that lane, the newest of any lane) and `handoff_guard.py` (which lane's handoff `Stop` and `PreCompact` check for and write) | both take `lane_id` from the hook payload, then `solo` |
| `CLAUDE_LANE_ROLE` | `lane_register.py` | the payload's `role`, then `adhoc` |
| `CLAUDE_LANE_MODEL` | `lane_register.py` | the payload's `model`, then `unknown` |

```bash
CLAUDE_LANE_ID=exec-a CLAUDE_LANE_ROLE=executor CLAUDE_LANE_MODEL=claude-opus-5-5 claude
```

**Two sessions started without `CLAUDE_LANE_ID` are one lane, `solo`.** The registry keeps one
entry per lane id, so the second register takes over the first one's entry, and each guard skips
its own lane id when it looks for other live lanes — neither session is warned about the other.
Give every concurrent session its own id. The sessions the Lane Dashboard starts get all three
from it. The board does not read these variables: `lane_board.py` takes `--lane`, `--role` and
`--model` on every call.

## Rescue patch + delivered effects — the two things a lane used to lose

| Script | What it writes | When it runs | Exit |
|---|---|---|---|
| `scripts/lane_rescue.py` | `.claude/lanes/rescue/lane-<id>-<ts>.patch` + `.meta.json` with the base commit | on `SessionStart`, for every dead lane `lane_register.py` evicts; by hand before `git worktree remove` | 0 ok (nothing to rescue included) · 1 refused · 2 usage |
| `scripts/lane_effects.py` | `.claude/lanes/effects.json` — `state{pending,accepted}` + `effect_state{pending,delivered}` per `reservation_id`, plus the `doorbell` outcome when one was rung | from `lane_board.py` on every VERIFIED / NEEDS-FIX / DEFERRED / NOT-SELECTED / WITHDRAWN | 0 ok · 1 refused · 2 usage |

A lane is a worktree, and evicting a dead lane is the moment its worktree becomes unowned: the
next `worktree remove --force` or idle-cleanup cron takes the uncommitted work with it and
nothing says what was lost. `lane_rescue.py` captures a `git diff --binary` — untracked files
included, through a private `GIT_INDEX_FILE` so a shared index cannot falsify it — and records
the base commit beside it. Reapplying refuses **whole** when the base moved or the patch does not
apply, because a half-restored rescue looks like the work came back. The second script separates
two facts the board used to collapse: a verdict being *decided* and the builder lane being
*told*. Collapse them and a restart never notifies (it looks handled) while a retry notifies
twice (nothing says it already went). The `reservation_id` is deterministic over
`(item, decision, target, effect, round)`, so a retry reconciles against the same reservation and
a genuinely new round gets its own; `python lane-kit/scripts/lane_effects.py pending` is the
durable list a restart works through, and `lane_board.py render` prints it under **UNDELIVERED**.

**Behaviour change in this version: the board delivers the message itself** (`mailbox.notify_on_verdict`,
**default ON**). Every verdict that targets a builder lane — VERIFIED, NEEDS-FIX, DEFERRED, NOT-SELECTED,
WITHDRAWN — writes `.claude/lanes/mailbox/<item>-<verdict>-<reservation>.md`, routed with `## To: <lane>`
and carrying the item, the verdict, the reason, the evidence and the round, then marks the reservation
`delivered` with that path as evidence: `pending` is empty and **UNDELIVERED** disappears. Idempotent by
`reservation_id` — a retry writes no second message, a new round writes its own. A mailbox that cannot
be written leaves the verdict on the board and the reservation `pending`, reported on stderr. Set
`notify_on_verdict: false` in `lanes.yaml` to go back to delivering by hand: nothing is written, the
reservation stays `pending` on purpose — an undelivered verdict that looks delivered is the failure this
ledger exists to make visible — and whoever tells the lane closes the loop with
`python lane-kit/scripts/lane_effects.py deliver <reservation_id> --evidence <where>`.

## Mailbox — messages between lanes, and how a lane hears them

`.claude/lanes/mailbox/*.md` is the asynchronous post box between lanes (`templates/REORIENT-MAILBOX.template.md`
is the hand-written form; the board writes the verdict form above). A message is addressed by a routing
**line**, matched whole, with the lane id bounded — `## To: exec-b` never reaches `exec-bb`, and a line
quoted inside the prose routes nothing. The legacy `## Para:` line still routes, for mailboxes written
before this version.

```
## To: exec-b                       <- the routing line: one lane id, alone on the line
## From: coord (planner)
## When: 2026-01-01T00:00:00
## Affected item(s): ITEM-1
```

How a lane hears it, per host:

| Host | Register (SessionStart) | Mail that arrives while the lane runs | Native doorbell |
|---|---|---|---|
| Claude Code | `lane_register.py` lists every unread message as `additionalContext` | the `--heartbeat` on `PostToolUse` announces it **once**, as `hookSpecificOutput.additionalContext` (`hookEventName: PostToolUse`), on the first heartbeat that lands after the file appears — a throttled heartbeat (`liveness.heartbeat_throttle_seconds`, 60s by default) waits for the next one | none — the host has no CLI that reaches a running session |
| Codex CLI | HPP wires no hook on this host: the lane hears about mail when it runs `lane_register.py` itself (register, or `--heartbeat`; the JSON on stdout is the announcement) | same command, run explicitly — a Codex lane is never interrupted by a hook | `codex queue --thread <the lane's session id> --message "<path + item + verdict>"` after a verdict message is written for it (`mailbox.native_doorbell`, default ON) |

What was announced is kept per lane in `mailbox/.announced/<lane_id>.json` (runtime state, beside the
mailbox), so the register and the heartbeats never repeat each other; a corrupt file is rebuilt, and
any failure inside the scan fails open — the heartbeat still lands, the hook prints `{}`, the lane is
told at the next beat. Messages moved to `mailbox/_read/` are never announced: the mailbox is
write-once, read-and-archive. `mailbox.check_on_register` and `mailbox.check_on_heartbeat` switch each
half off.

The doorbell is for Codex lanes only (registry `host: codex`, or an OpenAI model family), only when
`codex` is on PATH, bounded (5s), no retry, and fail-open: its outcome — `sent (...)`, `failed (exit N)`,
`failed (timeout after 5s)`, `skipped (codex not on PATH)`, `none (claude-code lane ...)` — is recorded as
`doorbell` beside the delivery evidence in `effects.json` and never changes the delivery. The file is the
delivery; the doorbell only shortens the wait for it.

## Operator hand-offs — release-fix, start-review, approve

Three board commands belong to the operator, not to a lane (contributed with the Lane Dashboard by
@kleinelizeu). Each writes one event, and each is what a dashboard button calls:

```bash
python lane-kit/scripts/lane_board.py release-fix ITEM-1 --target-lane exec-b
python lane-kit/scripts/lane_board.py start-review ITEM-1 --target-lane rev-x
python lane-kit/scripts/lane_board.py approve ITEM-1
```

| Command | From → to | Refused (exit 1) unless |
|---|---|---|
| `release-fix <item> --target-lane <executor>` | NEEDS-FIX → FIX-QUEUED | the target is a registered, live executor the board would let build the item (never the builder of a rival candidate); a queued fix whose lane stopped beating can be routed again, and the event says from where |
| `start-review <item> --target-lane <reviewer>` | CHECKPOINT-READY or DEFERRED → UNDER-REVIEW | the target is a registered, live reviewer that built no attempt at the item |
| `approve <item>` | VERIFIED → APPROVED | the item is red and verified, and its competition, if any, is decided; the event is the human gate |

`release-fix` and `start-review` write a kickoff to the target's mailbox (`## To: <lane>`, with the
NEEDS-FIX direction or the evidence to check) and ring the Codex doorbell as a verdict does. Only the
named lane may take a queued fix; the executor that built the item can still resume a NEEDS-FIX
directly. **APPROVED is not MERGED:** MERGED is written after the merge, and a red item needs the
approval first — APPROVED, or `--human-approved` on the MERGED itself. `claim` and `set` take
`--branch <branch>` on the build states, so the board records the builder's branch.

Two rules of the verdict were tightened with these commands. The model family of a checker is
compared with every lane that built the item, not only with the claimer, and the OpenAI aliases
(`codex-*`, `openai-*`, `chatgpt-*`, `o<digit>…`) count as the `gpt` family. And the tag belongs to
the item: once an item is red, every later event of it is red, whatever `--tag` the caller passed.

## Lane Dashboard — the board as a local page, every action a terminal command

`scripts/lane_dashboard.py` (contributed by @kleinelizeu) serves the board as a page on `127.0.0.1`:
the columns of the board, the live lanes, competitions, the mailbox, the deliveries with their
doorbell outcomes, the sessions it started, the backlog of specs with its waves and — asked of git,
not of the board — whether each reviewed item is integrated. It is optional. Every action on it is
a terminal command that does exactly the same thing, and the page only calls that command.

```bash
python lane-kit/scripts/lane_dashboard.py --project-dir . --open
python lane-kit/scripts/lane_dashboard.py snapshot --project-dir .
python lane-kit/scripts/lane_dashboard.py --self-test
```

The first line is the same on macOS, Linux and Windows (with `py` or `python3` where that is the
interpreter's name); it prints the URL, and Ctrl+C stops it. `--project-dir` repeats for several
projects on one page, and the other worktrees of each repository that use lane-kit join it.

| Page action | Terminal command |
|---|---|
| New spec | `lane_dashboard.py spec add` |
| Start a wave | `lane_dashboard.py wave start` |
| Route the fix, to a live executor | `lane_board.py release-fix` |
| Route the fix, to a new session | `lane_dashboard.py fix launch` |
| Start review, with a live reviewer | `lane_board.py start-review` |
| Start review, with a new session | `lane_dashboard.py review launch` |
| Approve merge | `lane_board.py approve` |
| Record merged | `lane_dashboard.py merged` |
| Ask for a brief | `lane_dashboard.py brief request` |
| Integration report | `lane_dashboard.py integration report` |
| Start the session again | `lane_dashboard.py session relaunch` |
| Stop a session | `lane_dashboard.py session cancel` |

Every `lane_dashboard.py` command takes `--project-dir DIR`, and every one but `serve` prints one
JSON object; `lane_dashboard.py <command> --help` lists a command's options. Exit: 0 done ·
1 refused · 2 invalid usage, or for `serve` the port in use · 3 the hand-off is recorded and its
session did not start (run `session relaunch`), or an error. `merged` writes MERGED only when git
shows the builder's branch in the target, measured now: by ancestry first
(`git merge-base --is-ancestor`, which sees merge commits too), and only for a branch that is not
an ancestor by patch-id (`git cherry`), with no merge commit of the branch left outside the
target. The measurement is the event's evidence.

**Security model.** You start the server and Ctrl+C stops it; nothing starts it on its own. It binds
loopback and answers only a loopback `Host`, so a DNS-rebound name is refused. Every action is a POST
that carries a token issued for this run, as `application/json`, which a page on another site cannot
send. The page refuses to be framed (`frame-ancestors 'none'` and `X-Frame-Options: DENY`;
`--frame-ancestor SOURCE`, repeatable, allows the ancestors you name). A GET only reads: it never writes and never
starts an agent. Every board write goes through `lane_board.py` and every lane through `_lane_io.py`,
so the page is refused exactly what a lane would be. An agent session starts only when you confirm an
action, never on a timer. Nothing leaves the machine.

**Where a session runs.** Every launcher starts the session itself; the page never hands you a command
to paste. The prompt is written to `.claude/lanes/sessions/<lane>.prompt.md` and read from there, so no
shell ever parses it. On Windows an agent that is a batch file (an npm shim) receives a one-line pointer
to that file instead, because `cmd.exe` re-parses a batch file's arguments.

| Launcher | macOS | Linux | Windows |
|---|---|---|---|
| `orca` | a terminal in the project's Orca worktree | the same | the same |
| `tmux` | a window in the tmux session the dashboard runs in, or in `hpp-lanes` | the same | — |
| `terminal` | Terminal.app (`open -a Terminal <script>`) | `$TERMINAL`, then `x-terminal-emulator`, `gnome-terminal`, `konsole`, `xfce4-terminal`, `kitty`, `alacritty`, `wezterm`, `xterm` | a PowerShell console |
| `iterm` | iTerm2 (`osascript`, with the script passed as an argument) | — | — |
| `external` | the terminal you declare in `dashboard.json` | the same | the same, with a `.ps1` for `{script}` |
| `headless` | the agent's non-interactive mode, under a supervisor | the same | the same |

A headless session runs under `lane_dashboard.py session supervise`: a timeout (3600 s by default), a
stop (`session cancel`), a log capped at 5 MB, and `.claude/lanes/sessions/<lane>.run.json` saying
`running`, `exited` with its code, `timeout`, `cancelled` or `failed-to-start`. A session whose
supervisor still beats is never started twice: one supervisor per lane, under an exclusive lock the
supervisor holds for its whole run. Stopping a session stops everything it started, whether or not
the agent's main process is still there.

**Model identity.** Maker ≠ checker compares the family of the model a session actually runs. Declare
that model in `.claude/lanes/dashboard.json`: it is passed to the CLI with its model flag and recorded on
the board. A single-vendor CLI with no model declared is recorded as its vendor's family (`gpt (Codex
default model)`); Cursor Agent serves several vendors and is refused until you declare its model, and a
declared model the CLI does not run is refused.

```json
{
  "agents": {
    "codex": {"model": "gpt-5.6-sol"},
    "cursor": {"model": "claude-opus-5-5", "roles": {"reviewer": {"model": "gpt-5.6-sol"}}}
  },
  "launcher": "iterm",
  "external": {"argv": ["wezterm", "start", "--", "sh", "{script}"], "label": "WezTerm"},
  "headless": {"timeout_seconds": 3600, "log_cap_bytes": 5242880}
}
```

`launcher` picks the default; `terminal` (an argv with `{script}`) replaces the detected terminal on
macOS and Linux, for example `["open", "-a", "Warp", "{script}"]`.

**Briefs.** *Ask for a brief* runs, once you confirm it, one headless agent of a model family none of
the builders is, which answers with options, a recommendation and the risks. It never writes the board.
With only the builders' family at hand it is refused: a second opinion from the maker's family is the
same opinion twice. The agent runs as a supervised session like any other (`brief-<item>-…` in
*Sessions*: a 180 s timeout, a stop, a capped log), and the brief names the session that wrote it.

**The mailbox, read-only.** The *Mailbox* panel lists each lane's messages as the register reads them —
unread, announced (the register or a heartbeat told the lane) or read (moved to `_read/`) — and
*Delivered* lists the verdicts delivered from `effects.json`, each with its message and its doorbell
outcome. The page never writes the mailbox.

Limits: the page shows files, and is as current as `board.jsonl`, `registry.json`, `effects.json` and
the mailbox on disk. It merges nothing: the integration report says what a merge would bring, and
`merged` records one that already happened.

## Best-of-N — N lanes, one task, one winner

Sometimes the cheapest way to a good result is to let two or three lanes attempt the same task
independently and keep the best attempt. Each attempt is an ordinary item on the board, claimed by
its own lane; `compete` declares that those items are candidates for one task, and `select` records
which one won. The choice is an append-only event on the board, carrying the reviewer, the reason
and the evidence that was compared.

```bash
python lane-kit/scripts/lane_board.py compete --task TASK-1 --items ITEM-A,ITEM-B --lane coord --model claude-opus-5-5
python lane-kit/scripts/lane_board.py select --task TASK-1 --winner ITEM-A --lane rev-x --model gpt-5.6-sol --reason "same tests, half the diff"
python lane-kit/scripts/lane_board.py select --task TASK-1 --checker-unavailable --lane rev-x --model gpt-5.6-sol
python lane-kit/scripts/lane_board.py withdraw --task TASK-1 --item ITEM-C --lane coord --model claude-opus-5-5 --reason "lane exec-c died mid-build"
```

| Rule (otherwise refused, exit 1) | Why |
|---|---|
| `compete` takes 2+ distinct items, each already claimed, and no builder lane is shared between two candidates | two candidates from one lane are one attempt made twice |
| an item competes in one task only; a task is declared once | the board is append-only — a second declaration would make the history ambiguous |
| `select` needs every remaining candidate CHECKPOINT-READY with evidence, or VERIFIED | comparing against an unfinished attempt is not a comparison |
| `withdraw` needs a reason, an undecided task, a remaining candidate, a coordinator that built no rival candidate, and leaves at least 1 candidate | a candidate whose lane died would otherwise keep the task undecidable forever; taking one out is a recorded decision, not a silent one |
| the reviewer's lane differs from every candidate's builder lanes, and its model family from every builder's family | the maker≠checker rule of a verdict, applied to all candidates at once |
| the winner is one of the candidates, and a decided task is not decided again | a second decision would silently overwrite the first |
| a candidate cannot be MERGED while its task has no winner | otherwise whoever finishes first wins without a comparison |
| `--checker-unavailable` records DEFERRED for the competition, never a winner | the same meaning DEFERRED has on an item |

The losers become `NOT-SELECTED`, a terminal state that only `select` writes, so a losing attempt
cannot drift on to MERGED; each losing lane is owed the news in `effects.json` — delivered to its
mailbox by default, or shown under **UNDELIVERED** until someone tells it when `notify_on_verdict`
is `false`. The winner keeps its own state and still goes through its
ordinary review — a selection compares attempts, it does not verify one. A withdrawn candidate
becomes `WITHDRAWN` (terminal, written only by `withdraw`), stops counting for readiness and for
selection, and its lane is owed the news the same way; with exactly 1 candidate left, `select` of
that one is allowed. `render` prints a **COMPETITIONS** section with each task's outcome and its
withdrawals, and `status <task>` lists the competition's events.

`select --task TASK-1 --deliberation RECORD` decides a competition with a sealed House Session
(`design`, its options exactly the remaining candidates, a recommendation). The panel's judge becomes the
reviewer of record, so the lane and family rules above apply to the judge; it needs the HPP core.

## House Session — seat a panel on this host, read-only by proof

`scripts/house_session.py` runs the seats of a House Session (the core's `hpp deliberate`); the
core itself calls no model. `families` answers whether this host can seat two model families — the
maker's plus every other CLI `checker_router.py` detects; one family is `DEFERRED` (exit 1), never
a one-family panel. `seat` runs one seat's command in that seat's worktree and fingerprints the
repository before and after (status, the diff against HEAD, untracked contents, HEAD, every ref and
the stash, the worktree list, the config, the hooks and `info/exclude`): if anything moved, the seat wrote, the turn is invalid and nothing is written (exit 2). A seat that
fails or times out is not judged (exit 1). A good answer becomes an `hpp.turn/v1` with its verbatim
text beside it. `/deliberate` (Claude Code) and the `house-session` skill (Claude Code and Codex)
walk the whole session.

```bash
python lane-kit/scripts/house_session.py families --maker claude
python lane-kit/scripts/house_session.py seat --panel panel.json --seat a --round 1 --out turns --root ../seat-a -- codex exec --sandbox read-only "$(cat prompt-a.md)"
python lane-kit/scripts/house_session.py --self-test
```

Limits: a write into a path the repository ignores is outside git's view and is not seen; give
every seat its own worktree, or two seats are blamed for each other's writes.

## Manual wiring (human gate — never automatic)

> Editing `.claude/settings.local.json` is a human gate in this doctrine. On the copy path
> there is no `${CLAUDE_PLUGIN_ROOT}`: paste the block below yourself, with the folder you
> copied the kit to — WARN-only + `timeout: 30`. Every command goes through `hooks/pyrun.sh`,
> the shim the plugin uses too: it runs the project's `.venv` Python when there is one, otherwise
> `python3` or `python` as the system names it — a stock Mac has only `python3`.

```jsonc
// Paste block (HUMAN GATE). ADDITIVE: merge into the "hooks" arrays that already exist —
// NEVER replace the whole file. Paths assume the kit was copied to lane-kit/ at the project root.
{
  "hooks": {
    "SessionStart": [
      { "hooks": [{ "type": "command", "command": "bash \"lane-kit/hooks/pyrun.sh\" \"lane-kit/hooks/lane_register.py\"", "timeout": 30 }] }
    ],
    "PreToolUse": [
      { "matcher": "Bash", "hooks": [{ "type": "command", "command": "bash \"lane-kit/hooks/pyrun.sh\" \"lane-kit/hooks/lane_git_guard.py\"", "timeout": 30 }] },
      { "matcher": "Edit|Write", "hooks": [{ "type": "command", "command": "bash \"lane-kit/hooks/pyrun.sh\" \"lane-kit/hooks/lane_territory_guard.py\"", "timeout": 30 }] }
    ],
    "PostToolUse": [
      { "hooks": [{ "type": "command", "command": "bash \"lane-kit/hooks/pyrun.sh\" \"lane-kit/hooks/lane_register.py\" --heartbeat", "timeout": 30 }] }
    ]
  }
}
```

Post-wiring checklist:
```bash
python lane-kit/hooks/_lane_io.py --self-test
python lane-kit/hooks/lane_register.py --self-test
python lane-kit/hooks/lane_git_guard.py --self-test
python lane-kit/hooks/lane_territory_guard.py --self-test
```

Round-trip proof (registers a lane and confirms it in the registry):
```bash
echo '{"hook_event_name":"SessionStart","session_id":"proof"}' \
  | CLAUDE_LANE_ID=exec-a python lane-kit/hooks/lane_register.py
python lane-kit/hooks/_lane_io.py status   # must list exec-a
```

## Proof / acceptance (real output, executed)

```bash
python hooks/_lane_io.py --self-test
```
```
self-test OK — register creates/evicts dead lanes/keeps started_at, heartbeat throttle+advance, liveness alive/suspect/dead, who_owns exclusive+glob**+ignores dead, alive_others excludes self, lock contention fails fast without hanging, corrupt registry degrades cleanly
```
<!-- executado: 2026-09-21 · exit=0 -->

## Undo

```
- Plugin:  /plugin uninstall lane-kit@house-party-protocol
- Copy:    remove the lane-kit/ folder + revert the block pasted into settings.local.json
           by hand (removal is a human gate too)
- Runtime state: rm -rf .claude/lanes/registry.json .claude/lanes/board.jsonl
           .claude/lanes/effects.json .claude/lanes/mailbox/ .claude/lanes/sessions/
           .claude/lanes/waves/ .claude/lanes/decision-briefs/ .claude/lanes/.lock/
           .claude/lanes/.registry.lock/ .claude/lanes/.effects.lock/ .claude/lanes/.dashboard-*.lock/
           (ephemeral, safe to delete; mailbox/ takes mailbox/.announced/ and its locks with it)
- Rescue:  .claude/lanes/rescue/ holds the only copy of work an evicted lane never committed —
           reapply it (lane_rescue.py reapply <patch>) or keep what you need, then remove it
- lanes.yaml (real config, git-tracked): remove it by hand if you no longer want the kit
```

---

*See `LANE-KIT.md` for the complete doctrine (board states, maker≠checker, territories).*
