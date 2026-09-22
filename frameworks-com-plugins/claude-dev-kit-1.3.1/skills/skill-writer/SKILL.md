---
name: skill-writer
description: Guides the creation of Agent Skills for Claude Code — structure, frontmatter, effective descriptions, and validation against the SKILL-CONTRACT. Use when the user wants to create, write or structure a new skill.
---

> **Auto-Trigger:** When the user wants to create, write or structure a new skill for Claude Code, or convert a repeated prompt/process into a reusable skill.
> **Keywords:** "create skill", "new skill", "SKILL.md", "skill structure", "write skill", "author skill", "structure skill"
> **Priority:** MEDIUM
> **Tools:** Read, Grep, Glob, Write, Edit, Bash

## When NOT to Activate
- **Creating a HOOK** (PreToolUse/PostToolUse/SessionStart) — use the `hookify` skill from this same module; hooks are scripts with stdin→JSON and exit codes, not SKILL.md.
- **Creating a PLUGIN** (`.claude-plugin/plugin.json` + `hooks.json`/`commands/`) — use the `plugin-dev` skill from this same module; a plugin is the packaging that groups skills/hooks/commands, not a skill itself.
- **Editing a vendored skill / one from another plugin** (an identical copy from a marketplace) — do not rewrite it; those update through their plugin of origin.
- **Writing project documentation or an implementation plan** — that is not a Skill (it has no trigger and no I/O contract).

## Contract

**INPUT:** the model (via conversation with the user) determines the scope/name/triggers/tools of the new skill.

**OUTPUT:** a `<skill-name>/SKILL.md` directory (+ optional companions) that passes `tools/skill_lint.py` with no FAIL.

**EXIT CODES** (from `tools/skill_lint.py`, used to validate the result):

| Exit | Meaning |
|---|---|
| 0 | skill compliant with the SKILL-CONTRACT (PASS, 0 FAIL) |
| 1 | WARN only (e.g. an example executed >90 days ago) — usable, but review |
| 2 | ≥1 FAIL (violation of a mandatory clause — see `docs/SKILL-CONTRACT.md`) |

**STATE IT TOUCHES:**

| Resource | Reads/Writes | Purpose |
|---|---|---|
| `<skill-dir>/SKILL.md` | Writes | the skill itself |
| `<skill-dir>/examples.md`, `troubleshooting.md`, `reference.md` (optional) | Writes | progressive disclosure — long content moves out of the main SKILL.md |
| `docs/SKILL-CONTRACT.md` | Reads | the 6 clauses every PRODUCT skill must meet |
| `tools/skill_lint.py` | Runs (read-only) | validates the created skill against the contract |

## Process

### 1. Determine the scope
Ask (or infer from the conversation): what single capability does this skill solve? When should it fire? Which tools does it need? **Rule: one skill = one capability.**

### 2. Choose the location
| Location | Use |
|-------|-----|
| `~/.claude/skills/` | Personal, experimental |
| `.claude/skills/` | Team/project, versioned in git |
| `<kit>/skills/` | Distributed via plugin/marketplace |

### 3. Create the structure
```bash
mkdir -p .claude/skills/skill-name
```
Multi-file (progressive disclosure — use it when the body would exceed ~500 lines):
```
skill-name/
├── SKILL.md (obrigatório)
├── examples.md (opcional — ver examples.md deste kit para o padrão)
├── troubleshooting.md (opcional — ver troubleshooting.md deste kit para o padrão)
└── scripts/ (opcional)
```

### 4. Write the complete header (C1 of the contract)
```yaml
---
name: skill-name
description: O que faz + quando usar. Máx 1024 chars.
---
```
```markdown
> **Auto-Trigger:** quando dispara automaticamente
> **Keywords:** "termo1", "termo2", "termo3", "termo4" (mínimo 4, sem sintaxe de wikilink duplo-colchete)
> **Priority:** HIGH | MEDIUM | LOW
> **Tools:** lista explícita

## When NOT to Activate
- (≥2 bullets — nomeie a skill vizinha se há fronteira confundível)
```

| Field | Rule |
|-------|-------|
| `name` | lowercase, hyphens, max 64 chars, **must match the folder name** |
| `description` | max 1024 chars, include WHAT + WHEN to use |
| `allowed-tools`/`Tools` | explicit list of tools |

### 5. Write the description (formula: WHAT + WHEN + key triggers)
```yaml
# Boa
description: Extrai texto de PDFs, preenche formulários. Use quando o usuário mencionar PDFs ou extração de documentos.

# Ruim
description: Ajuda com documentos
```
See `examples.md` for more good/bad description patterns.

### 6. Write the I/O contract (C2) — INPUT / OUTPUT / EXIT CODES / STATE IT TOUCHES

### 7. Collect ≥3 GENUINELY EXECUTED examples (C3)
Run the real command, paste the real output, mark it `<!-- executed: YYYY-MM-DD · exit=N -->`. At least 1 example must show a FAILURE (exit != 0). Never invent output — if it did not run, do not paste it.

### 8. Write the Proof section (C4)
A single command, <5s, no network, that proves the contract with exit 0. Usually `--self-test`.

### 9. Validate against the contract
```bash
python tools/skill_lint.py <skill-dir>/SKILL.md
```
Fix every FAIL reported (do not ignore a stale-example WARN without re-verifying).

### 10. Activation test
1. Restart Claude Code to load the skill.
2. Ask a question that matches the `description`.
3. Confirm it activates and behaves as expected.

## Executed examples

```console
$ python tools/skill_lint.py skills/claude-dev-setup/SKILL.md
[PASS] skills/claude-dev-setup/SKILL.md

skill_lint: 1 pass · 0 warn · 0 fail (de 1)
```
<!-- executed: 2026-07-10 · exit=0 -->
(a skill in full compliance with the 6 clauses — 0 FAIL, 0 WARN.)

```console
$ cat bad-skill/SKILL.md
---
name: bad-skill
description: Helps with stuff
---

Do the thing.

$ python tools/skill_lint.py bad-skill/SKILL.md
[FAIL] bad-skill/SKILL.md
    FAIL L1b.auto-trigger             header sem linha '> **Auto-Trigger:**'
    FAIL L1b.keywords                 header sem linha '> **Keywords:**'
    FAIL L1b.prioridade               header sem linha '> **Prioridade:**'
    FAIL L1b.tools                    header sem linha '> **Tools:**'
    FAIL L1d.quando_nao_ativar        seção '## Quando NÃO Ativar' ausente
    FAIL L2a.contrato_ausente         seção '## Contrato' ausente
    FAIL L3a.exemplos_min3            0 exemplo(s) executado(s) < 3
    FAIL L4a.prova_ausente            seção '## Prova' ausente
    WARN L6a.corpo_sem_comando        apenas 0 bloco(s) de código no corpo — pode ser prosa sem comando literal

skill_lint: 0 pass · 0 warn · 1 fail (de 1)
```
<!-- executed: 2026-07-10 · exit=2 -->
(a vague description ("Helps with stuff") and an unstructured body fail 8 checks at once — exactly the "essay without a contract" the SKILL-CONTRACT exists to prevent.)

```console
$ mkdir -p .claude/skills/exemplo-novo && ls .claude/skills/exemplo-novo
```
<!-- executed: 2026-07-10 · exit=0 -->
(step 3 of the process — creating the structure before writing the SKILL.md.)

## Anti-patterns

- ❌ Vague description ("helps with X") without specific triggers — the skill never activates when it should.
- ❌ Folder name different from the `name` in the frontmatter — silent breakage, the skill simply is not found.
- ❌ Pasting "probable" output instead of actually running the command — violates C3 and this marketplace's integrity doctrine (never invent output).
- ❌ Deep nesting of companion files (`SKILL.md → a.md → b.md → c.md`) — keep it flat: `SKILL.md → examples.md`, `SKILL.md → troubleshooting.md`.

## Proof

```bash
python tools/skill_lint.py --self-test
```

## Additional resources

- **Patterns and examples**: see [examples.md](examples.md)
- **Debugging skills that do not activate**: see [troubleshooting.md](troubleshooting.md)
- **The full contract (6 clauses)**: see [`docs/SKILL-CONTRACT.md`](../../docs/SKILL-CONTRACT.md)
