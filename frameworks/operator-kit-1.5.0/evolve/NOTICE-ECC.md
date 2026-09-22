# NOTICE — ECC inspiration (`evolve/instinct_promote.py`)

`evolve/instinct_promote.py` implements a pattern **inspired** by the
"instinct + confidence-scoring" mechanism of the **ECC** project
(Excellence Compounding Cycle):

- Repository: https://github.com/affaan-m/ECC
- Author: Affaan Mustafa
- License: MIT, © 2026 Affaan Mustafa

**No line of ECC code was copied.** The original ECC CLI
(`skills/continuous-learning-v2/scripts/instinct-cli.py`, ~2000 lines) solves a far larger
scope — per-project and global instincts, remote import/export with SSRF-safe validation,
clustering across skills/commands/agents, TTL/prune across several projects.
`instinct_promote.py` is a minimal, new reimplementation, written from scratch for this kit,
covering only the piece this kit's `/ralph-gate` needs: a recurring `done_gate` failure
becomes a candidate; confidence is the recurrence count (via an idempotent cursor over
`HANDOFF-LEDGER.jsonl`); promotion into `LEARNINGS.md` is **always a human act** (never
automatic — the same principle as `partial-autonomy-slider`: propose, do not self-execute
something that persists and teaches the team).

Credit is also given to the official **`ralph-loop`** plugin (Anthropic) for the original
Stop-hook mechanic with `<promise>` — see `RALPH-GATE.md` at the root of this kit.

If this file (or `instinct_promote.py`) is ever expanded by incorporating literal text or
code from ECC, this section must be updated to read "Portions derived from ECC
(github.com/affaan-m/ECC), MIT, © 2026 Affaan Mustafa" — today that is NOT the case; what
exists is inspiration from a pattern, not derivation of code.
