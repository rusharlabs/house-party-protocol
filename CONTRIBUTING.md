[English](CONTRIBUTING.md) · [Português](CONTRIBUTING.pt-BR.md)

# Contributing

Thank you. This repository is the **emitted product** — versioned modules, each sealed with
`CHECKSUMS.txt`. That changes how a contribution works: a module is never edited in place; the
source is edited, the module is re-emitted by the forge, and the gate proves the result.

## Rules without exception

1. **No client name, personal e-mail, machine path, internal port or credential.**
   The `ip_pii_linter` runs before every emission and has no `--skip`. If it rejects, the problem
   is the content, not the linter.
2. **Every new `.py` in a module has a `--self-test`** that passes on Windows, macOS and Linux, and
   the self-test must not depend on a bare `python` (use `sys.executable`).
3. **Every `SKILL.md` passes `skill_lint`**: an I/O contract, at least 3 examples that were really
   executed (with the marker `<!-- executado: AAAA-MM-DD · exit=N -->`), a `## Prova` section, and
   paths anchored in `${CLAUDE_PLUGIN_ROOT}`.
4. **Hooks are WARN-only** unless an explicit decision, documented in the module's `hooks.json`,
   says otherwise.
5. **A bug fix ships with the test that failed before it.** A test written after the fix proves
   that today's code works; it does not prove that anything was fixed.

## Flow

```bash
# 1. verify the module you are about to touch
python instaladores/kit-forge-1.4.0/kit_doctor.py verify frameworks-com-plugins/operator-kit-1.4.0

# 2. make the change in the module SOURCE (open an issue first if it is large)

# 3. re-emit through the forge and prove it
python instaladores/kit-forge-1.4.0/kit_assembler.py --manifest <module-manifest> --out <dir>
python instaladores/kit-forge-1.4.0/kit_doctor.py verify <dir>/<module>-<version>
python instaladores/kit-forge-1.4.0/tools/skill_lint.py <dir>/<module>-<version>/skills/<skill>

# 4. bump the module version (semver) -- new behaviour under the same number breaks the
#    CHECKSUMS of whoever already has the module -- and record it in CHANGELOG.md
```

## Documentation in two languages

A document a **person** reads before deciding whether to use the project exists in both
languages, paired as `NAME.md` (English, the source of truth) and `NAME.pt-BR.md` (Brazilian
Portuguese). The first useful line of both is the language pair:

```
[English](NAME.md) · [Português](NAME.pt-BR.md)
```

A file an **agent** reads in order to execute — anything under `skills/`, `commands/` or
`rules/` — stays in English only. A translated copy there doubles the maintenance and invites
silent divergence between what the two copies instruct.

A gate in the source repository (`test_documentacao_bilingue.py`) rejects whoever breaks the
rule: a missing counterpart, a top link that does not point at the sibling, structural
divergence (the two sides carry the same headings, in the same order — translation changes
words, not structure), differing code blocks (a command is a command in any language), and any
`.pt-BR.md` inside the agent layer. `NOTICE`, `CITATION.cff` and `LICENSE` are legal and
citation instruments and stay in English only: a translation would create ambiguity about which
version binds.

## Commits and licence

- Conventional commits (`feat(kit):`, `fix(kit-forge):`, `docs:`).
- Sign your commits with the **Developer Certificate of Origin**: `git commit -s`. The sign-off
  states that you have the right to contribute the code under this repository's licence.
- Contributions enter under the project's licence (**MIT**). Do not send code you cannot license
  that way — including code generated from a repository without a licence.

## What is not welcome

- A new dependency where the stdlib solves it.
- An "improvement" on a neighbouring line that has nothing to do with the request (the diff has
  to trace back to the problem).
- An executed example that was not executed.
