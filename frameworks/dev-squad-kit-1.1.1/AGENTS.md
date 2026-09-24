# AGENTS.md — dev-squad-kit

This kit offers development roles as commands and subagents, plus three parallel-reading skills.

## Codex CLI

- Install by copy with `kit_doctor.py install --kit <dev-squad-kit> --host codex --target <repo> --apply`.
- Skills are mirrored into `.agents/skills`; `agents/*.md` are Claude Code artifacts and serve as role specifications on Codex.
- Checkers are read-only: never grant `Write` or `Edit` to the review roles.

## In-kit fallbacks (optional prerequisites)

- When their task file is absent, `*evidence-check`, `*console-check`, every mode of `*verify-subtask` and the `*pre-push` evidence check fall back to `python -m hpp evidence`; `pp-consolidate` checks its `[ID:x]` markers with `python -m hpp cite check`.
- They need the HPP core (`python -m hpp`); the browser/e2e checks also need Node and an end-to-end runner. Without the HPP core the command says so and does not pass — it never skips silently.
- `hpp evidence verify` only reads. `hpp evidence run` writes a record, so a read-only reviewer runs it with `--out` pointing to its own scratch directory inside the workspace.
- A browser agent is a maker/exploration tool; a verdict is the exit code of a versioned spec recorded with `hpp evidence run`.

```bash
python -m hpp evidence run --id <story>-<subtask> --artifact "<out>/**/trace.zip" -- npx playwright test <spec> --output <out> --trace on
python -m hpp evidence verify .hpp/evidence/<id>-<UTC>.json
python -m hpp cite check --text CONSOLIDATED.md --context inputs.json
```

## Verification

```bash
python <marketplace>/installers/kit-forge-*/tools/skill_lint.py --all skills
```
