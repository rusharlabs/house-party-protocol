[English](skill-template.md) · [Português](skill-template.pt-BR.md)

# skill-template.md — copie para `<seu-projeto>/.claude/skills/<name>/SKILL.md`

> Scaffold vazio já estruturado nas 6 cláusulas do SKILL-CONTRACT (ver `docs/SKILL-CONTRACT.md`).
> Preencha cada `<...>`, apague os comentários, rode `python tools/skill_lint.py <seu-arquivo>` até PASS.
> Guia passo-a-passo: skill `skill-writer` deste kit.

````markdown
---
name: <skill-name>
description: <What it does> + <when to use it>. Max 1024 chars.
---

> **Auto-Trigger:** <when it fires automatically>
> **Keywords:** "<term1>", "<term2>", "<term3>", "<term4>"
> **Priority:** HIGH | MEDIUM | LOW
> **Tools:** <explicit list of the tools used>

## When NOT to Activate
- <situation 1 where it should NOT fire>
- <situation 2 — name the neighbouring skill if there is a confusable boundary: "not to be confused with skill X, which covers Y">

## Contract

**INPUT:** <accepted types — file, string, flag>

**OUTPUT:** <paths + modelled format — not "generates a report", but the SCHEMA of the report>

**EXIT CODES:**

| Exit | Meaning |
|---|---|
| 0 | <success> |
| 1 | <warning/non-fatal rejection> |
| 2 | <error/invalid usage> |

**STATE IT TOUCHES:**

| Resource | Reads/Writes | Purpose |
|---|---|---|
| <file/path 1> | Reads/Writes | <why> |

## Process

1. **<Step 1>** — literal command:
   ```bash
   <exact command, not "run the appropriate script">
   ```
2. **<Step 2>** ...

## Executed examples

<!-- Paste REAL output of commands you actually ran — never invent.
     At least 1 of the 3 examples must show a FAILURE (exit != 0). -->

```console
$ <real command 1>
<real output 1>
```
<!-- executed: YYYY-MM-DD · exit=0 -->

```console
$ <real command 2 — FAILURE case>
<real output 2>
```
<!-- executed: YYYY-MM-DD · exit=1 -->

```console
$ <real command 3>
<real output 3>
```
<!-- executed: YYYY-MM-DD · exit=0 -->

## Anti-patterns

- ❌ <known trap 1>
- ❌ <known trap 2>

## Proof

```bash
<single command, <5s, no network, that proves the contract — usually --self-test>
```
````

## Checklist antes de considerar pronto

- [ ] `name` bate exatamente com o nome da pasta
- [ ] `description` tem O QUE + QUANDO, sem sintaxe de wikilink duplo-colchete nas Keywords
- [ ] `## When NOT to Activate` tem ≥2 bullets
- [ ] `## Contract` tem as 4 sub-seções (INPUT/OUTPUT/EXIT CODES/STATE IT TOUCHES)
- [ ] ≥3 exemplos executados, ≥1 de falha (exit != 0), cada um com `<!-- executed: ... -->`
- [ ] `## Proof` roda em <5s sem rede
- [ ] `python tools/skill_lint.py <seu-arquivo>` → PASS
