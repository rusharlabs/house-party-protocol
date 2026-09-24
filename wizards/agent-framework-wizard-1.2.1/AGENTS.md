# AGENTS.md — agent-framework-wizard

This kit generates agent and skill skeletons through a six-step wizard.

## Codex CLI

- Install by copy with `kit_doctor.py install --kit <agent-framework-wizard> --host codex --target <repo> --apply`.
- The runtime lives in `.agents/hpp/agent-framework-wizard/`; the generated skill lives in `.agents/skills`.
- Review every generated file before integrating it into the project.

## Verification

```bash
python wizard.py --self-test
```
