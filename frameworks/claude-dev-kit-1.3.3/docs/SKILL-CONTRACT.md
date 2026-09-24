[English](SKILL-CONTRACT.md) · [Português](SKILL-CONTRACT.pt-BR.md)

# SKILL-CONTRACT — what separates a "pile of scripts" from a "system"

> **Version:** 1.1.0 (2026-09-21 — English schema tokens are canonical; the Portuguese ones are
> accepted as legacy).
> **Enforcement:** `skill_lint.py` — `installers/kit-forge/tools/skill_lint.py` at the
> marketplace root, vendorized as `tools/skill_lint.py` inside `claude-dev-kit`.

## Principle

```
UMA SKILL É PRODUTO QUANDO UM ESTRANHO, NUM REPO VIRGEM, EM QUALQUER OS,
CONSEGUE: (1) saber QUANDO ela dispara, (2) saber O QUE entra e O QUE sai,
(3) copiar-colar um comando que FUNCIONA, (4) provar com exit 0 que funcionou.
Prosa numerada sem comando literal NAO e skill — e ensaio.
```

(A skill is a product when a stranger, in a pristine repo, on any OS, can: (1) know WHEN it
fires, (2) know WHAT goes in and WHAT comes out, (3) copy-paste a command that WORKS, (4) prove
with exit 0 that it worked. Numbered prose without a literal command is not a skill — it is an
essay.)

A skill that only describes steps in prose, with no I/O contract and no executable proof, is an
essay about the task — not a tool a stranger can operate without guessing.

## Schema tokens — canonical and legacy

The lint matches the tokens below literally. **English is canonical** (write new skills with
it); the **Portuguese forms are accepted as legacy** (skills written before 2026-09-21 keep
passing unchanged). Each clause accepts either form on its own, so a skill that mixes forms lints
exactly like a pure one — the contract is structural, and the language of a token is not a clause.

| Clause | Canonical (English) | Accepted legacy (Portuguese) |
|---|---|---|
| C1 header | `> **Priority:**` HIGH / MEDIUM / LOW | `> **Prioridade:**` ALTA / MÉDIA / BAIXA |
| C1 section | `## When NOT to Activate` | `## Quando NÃO Ativar` |
| C2 section | `## Contract` | `## Contrato` |
| C2 fields | `**INPUT:**` · `**OUTPUT:**` · `**EXIT CODES**` · `**STATE IT TOUCHES:**` | `**ENTRADA:**` · `**SAÍDA:**` · `**EXIT CODES**` · `**ESTADO QUE TOCA:**` |
| C2 exit-0 row | the word `always` in the exit-0 row (single-exit-code contract) | `sempre` |
| C3 marker | `<!-- executed: YYYY-MM-DD · exit=N -->` | `<!-- executado: YYYY-MM-DD · exit=N -->` |
| C4 section | `## Proof` | `## Prova` |

`Auto-Trigger`, `Keywords`, `Tools` and `EXIT CODES` were never translated and have one form.

## The 6 clauses

### C1 · HEADER
Frontmatter `name` + `description`, plus 4 metadata lines:
- `> **Auto-Trigger:**` — when the skill fires automatically.
- `> **Keywords:**` — at least 4 words/phrases, no wikilinks `[[...]]` (staging contamination).
- `> **Priority:**` — HIGH/MEDIUM/LOW (legacy `Prioridade:` ALTA/MÉDIA/BAIXA). The lint checks
  the field name (L1b); the value is the convention, not machine-checked.
- `> **Tools:**` — explicit list of the tools the skill uses.

Plus a `## When NOT to Activate` section (legacy `## Quando NÃO Ativar`) with ≥2 bullets — naming
the neighbouring skill when there is a confusable boundary (e.g. "not to be confused with skill X,
which covers Y").

### C2 · I/O CONTRACT
A `## Contract` section (legacy `## Contrato`) with:
- **INPUT** (legacy ENTRADA) — accepted types (file, string, flag).
- **OUTPUT** (legacy SAÍDA) — paths + modelled format (not "generates a report", but the schema of
  the report).
- **EXIT CODES** — table `0 / 1 / 2` (and beyond, if applicable) with the meaning of each. A
  mechanism that can only exit 0 (a connector that never breaks the caller) says so with the word
  `always` (legacy `sempre`) in the exit-0 row — then C3 does not demand a failure example.
- **STATE IT TOUCHES** (legacy ESTADO QUE TOCA) — table `file → reads/writes → purpose`
  (one row per file the skill reads or writes).

### C3 · ≥3 EXECUTED EXAMPLES
REAL output pasted (not invented — inventing output violates `agent-integrity.md`), with the
parseable marker `<!-- executed: YYYY-MM-DD · exit=N -->` (legacy `executado:`) on each example.
At least 1 example must be a FAILURE (show the exit != 0 and the real message). Examples expire in
90 days (the lint emits WARN, not FAIL, for an old example — it may still be true, but it deserves
re-verification).

### C4 · PROOF
A `## Proof` section (legacy `## Prova`) with a single command, running in under 5 seconds,
without network, that demonstrates the contract and ends with the expected exit 0. It inherits the
`--self-test` pattern of a well-behaved script. `--run-proofs` executes the first line of the
block from the skill directory: a trailing `# comment` is stripped before running (on Windows the
shell is cmd.exe, where `#` is not a comment and `>` is a redirect) and `${CLAUDE_PLUGIN_ROOT}`
is expanded to the skill's module root.

### C5 · PORTABILITY
- Launcher: always `python`. **`py` is FORBIDDEN** (Windows-only — real bug in
  `pre-clear-boot-block:16`).
- **`ScheduleWakeup` is FORBIDDEN as a dependency** — it is a tool exclusive to the `/loop`
  main-loop; subagents and external installs do not see it (real bug in `ralph-loop-driver:23`).
- **Self-containment:** everything the skill executes is resolvable through `${CLAUDE_PLUGIN_ROOT}`
  (plugin mode) or vendorized by the assembler (copy mode). A reference to `operator-kit/scripts/`
  or to a loose `_lib` without those two routes = guaranteed post-install breakage.

### C6 · EXECUTABLE BODY
A literal command per step (not "run the appropriate script" — the exact command), a modelled
output format, WHOLE templates when the skill emits an artefact (not a sketch/excerpt),
documented anti-patterns when there is a known trap, and cross-links between sibling skills when
there is a shared boundary.

## Automatic enforcement

`skill_lint.py` implements the checks `L1a`–`L6` (1:1 mapping to the clauses above). The finding
ids (`L1b.prioridade`, `L2a.contrato_ausente`, `L4a.prova_ausente`, ...) are the checker's stable
output contract and did not change with the English tokens — only the messages did. Exit contract
of the lint:

| Exit | Meaning |
|---|---|
| `0` | PASS — no violation |
| `1` | WARNs only (e.g. an example older than 90 days) |
| `2` | ≥1 FAIL (violation of a mandatory clause) |

C5 adjustment in the lint: `${CLAUDE_PLUGIN_ROOT}/...` is a VALID reference (L5c accepts it). FAIL
only occurs on a raw relative path such as `operator-kit/scripts/...` or a `_lib` outside a
declared resolution.
