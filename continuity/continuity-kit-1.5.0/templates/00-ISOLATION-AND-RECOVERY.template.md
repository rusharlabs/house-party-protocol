# 00-ISOLATION-AND-RECOVERY — {{project_name}}

> Answers the question no handoff doc answers on its own: **"will another session
> overwrite this while I work?"** If you do not know the answer before editing a shared
> file, stop and check here first.

> `{{lane_board}}` = path to lane-kit's `scripts/lane_board.py` (the board ships in lane-kit, not
> in this kit, so this template cannot resolve it from its own plugin root).

## Isolation — who may touch what, NOW

1. **Check the registry of live lanes** (if the lane-kit is installed):
   ```bash
   python {{lane_board}} status
   ```
2. **Without the lane-kit installed** — minimum heuristic before editing a shared file:
   - `git status --porcelain` — is there uncommitted work from another session?
   - mtime of the target file — did it change in the last {{window_minutes}} minutes from another source?
3. **Exclusive territory** (if declared): `{{list_of_paths_exclusive_to_this_lane}}` — outside
   of it, assume shared and confirm before editing.

## Recovery — if something was overwritten/lost

1. **Durability first**: `docs/_state-mirror/` (or this project's `mirror_dir`) keeps
   copies of the critical gitignored files — `state_mirror.py` regenerates them; it does not
   guarantee lost originals, but it prevents TOTAL loss.
2. **Git is the real safety net**: `git log --all --oneline -- <path>` finds earlier versions even
   of an overwritten tracked file.
3. **Handoff/ledger**: `.claude/handoff/HANDOFF-LEDGER.jsonl` holds the history of what each
   lane left behind — useful to rebuild the timeline of who touched what.

## Known gap (inherited, honest)

Backup/isolation covers files INSIDE the repo. If the source of truth lives outside it (e.g.
a VM, an external database), this template does NOT cover that — declare explicitly
the backup mechanism of that external system here: {{external_backup_or_declared_gap}}.
