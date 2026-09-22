# PRD — {{onda_nome}}

> **Hard rule:** every PRD MUST have the `## DoD (done_predicates)` block filled in with
> REAL shell commands (not prose like "it should work correctly"). Without that block, the
> executor MUST derive 3-6 predicates BEFORE starting to build — never builds
> "blind" without knowing what proves "done". `/ralph-gate` and `goal_review.py`
> consume this block directly (`goal_review.extract_criteria`).

## Objective (1 sentence)

{{objetivo}}

## Scope

- Includes: {{o_que_inclui}}
- Excludes: {{o_que_exclui_explicitamente}}

## Context/motivation

{{por_que_agora}}

## DoD (done_predicates) — MANDATORY

```bash
# Each line = 1 shell criterion. ALL must exit 0 for the PRD to be considered DONE.
{{comando_criterio_1}}
{{comando_criterio_2}}
{{comando_criterio_3}}
```

## Risk tier

- [ ] 🟢 repo-safe (the loop may attack it autonomously)
- [ ] 🟠 touches a live VM/infra (requires extra attention, does not block autonomy)
- [ ] 🔴 gate (requires human approval before applying)

## Expected readiness at the end

{{nivel_r0_a_r4_esperado}} — see `00-PROCESSES.template.md` for what each level requires.
