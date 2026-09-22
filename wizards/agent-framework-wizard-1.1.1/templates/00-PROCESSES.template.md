# 00-PROCESSES — verification ladder + authority matrix — {{project_name}}

## The R0→R4 ladder (config in `verificacao.escada` of the profile)

Nobody declares readiness above what the evidence supports. `goal_ledger.py --readiness <id> <RN> --evidence <ref>`
refuses (exit 2) if the evidence does not match the level.

| Level | Name | What it proves | Mechanism that certifies it | Who declares it |
|---|---|---|---|---|
| R0 | Declared | "I wrote/changed it" | — (the maker's word) | executor |
| R1 | Self-verified | self-test/unit test green | `--self-test`/pytest exit 0 | executor (evidence pasted) |
| R2 | Gate | the PRD's DoD passes LIVE | `done_gate.py` exit 0 (probes) | only the script (never prose) |
| R3 | Reviewed | another brain confirmed it | `goal_review.py` + cross-model checker; unavailable → `DEFERRED`, never R3 | reviewer (family ≠ maker) |
| R4 | Accepted | a human accepted it in real use | human gate / production | human |

## Authority matrix (role × right)

| | Planner (architect) | Executor (builder) | Reviewer (auditor) |
|---|---|---|---|
| **Writes to** | `docs/plans/**`, `00-STATE.md` (single-writer), BOOT prompts | code/artifacts inside the claimed territory; `00-STATE-LANE-<id>.md`; board (builder states) | **NOTHING** (physically read-only — no Write/Edit; only `lane_board.py --set VERDICT`) |
| **Git** | commits docs only, with pathspec | commits with strict pathspec; NEVER push/merge | zero commits |
| **Autonomy (slider 0-5)** | 2 | 2-3 (🟢🟠 auto; 🔴 proposes) | 0 (suggest-only by construction) |
| **Forbidden** | mutating code/engine/VM; installing; wiring settings | closing its own item as VERIFIED; touching `00-STATE.md` (only its own LANE file); red zones | editing any file; being the same lane/model as the builder |
| **Who approves** | {{humano}} (specs become a pasteable BOOT) | Reviewer (VERDICT) + {{humano}} (🔴 gates, merge) | {{humano}} (only they close a DEFERRED) |

**Enforcement:** this matrix is not just discipline — `lane_board.py` (lane-kit) encodes it as a
state machine: `CHECKPOINT-READY` only by the lane that claimed + evidence; `VERIFIED`/`NEEDS-FIX`
only by a reviewer from ANOTHER lane AND ANOTHER model family (maker≠checker refused with exit 2, not
merely suggested in prose).

## Red zones (WARN for ALL lanes, always — even solo)

`.claude/settings*.json` · `**/MEMORY.md` · `{{state_doc}}` (outside the single-writer flow) ·
any path listed in `lanes.yaml → zonas_vermelhas`.
