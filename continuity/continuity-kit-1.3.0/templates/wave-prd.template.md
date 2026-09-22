# PRD — {{wave_name}}

> **Hard rule:** every PRD MUST have the `## DoD (done_predicates)` block filled in with
> REAL shell commands (not prose like "it should work correctly"). Without that block, the
> executor MUST derive 3-6 predicates BEFORE starting to build — never builds
> "blind" without knowing what proves "done". `/ralph-gate` and `goal_review.py`
> consume this block directly (`goal_review.extract_criteria`).

## Objective (1 sentence)

{{objective}}

## Scope

- Includes: {{what_it_includes}}
- Excludes: {{what_it_explicitly_excludes}}

## Context/motivation

{{why_now}}

## DoD (done_predicates) — MANDATORY

```bash
# Each line = 1 shell criterion. ALL must exit 0 for the PRD to be considered DONE.
{{criterion_command_1}}
{{criterion_command_2}}
{{criterion_command_3}}
```

## Risk tier

- [ ] 🟢 repo-safe (the loop may attack it autonomously)
- [ ] 🟠 touches a live VM/infra (requires extra attention, does not block autonomy)
- [ ] 🔴 gate (requires human approval before applying)

## Expected readiness at the end

{{expected_level_r0_to_r4}} — see `00-PROCESSES.template.md` for what each level requires.
