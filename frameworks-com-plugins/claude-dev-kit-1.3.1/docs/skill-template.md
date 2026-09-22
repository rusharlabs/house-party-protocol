# skill-template.md — copie para `<seu-projeto>/.claude/skills/<nome>/SKILL.md`

> Scaffold vazio já estruturado nas 6 cláusulas do SKILL-CONTRACT (ver `docs/SKILL-CONTRACT.md`).
> Preencha cada `<...>`, apague os comentários, rode `python tools/skill_lint.py <seu-arquivo>` até PASS.
> Guia passo-a-passo: skill `skill-writer` deste kit.

```markdown
---
name: <nome-da-skill>
description: <O que faz> + <quando usar>. Máx 1024 chars.
---

> **Auto-Trigger:** <quando dispara automaticamente>
> **Keywords:** "<termo1>", "<termo2>", "<termo3>", "<termo4>"
> **Priority:** HIGH | MEDIUM | LOW
> **Tools:** <lista explícita de ferramentas usadas>

## When NOT to Activate
- <situação 1 onde NÃO deveria disparar>
- <situação 2 — nomeie a skill vizinha se há fronteira confundível: "não confundir com a skill X, que cobre Y">

## Contract

**INPUT:** <tipos aceitos — arquivo, string, flag>

**OUTPUT:** <paths + formato modelado — não "gera um relatório", mas o SCHEMA do relatório>

**EXIT CODES:**

| Exit | Significado |
|---|---|
| 0 | <sucesso> |
| 1 | <aviso/rejeição não-fatal> |
| 2 | <erro/uso inválido> |

**STATE IT TOUCHES:**

| Recurso | Lê/Escreve | Propósito |
|---|---|---|
| <arquivo/path 1> | Lê/Escreve | <por quê> |

## Processo

1. **<Passo 1>** — comando literal:
   ```bash
   <comando exato, não "rode o script apropriado">
   ```
2. **<Passo 2>** ...

## Exemplos executados

<!-- Cole saída REAL de comandos que você rodou de verdade — nunca invente.
     Pelo menos 1 dos 3 exemplos precisa mostrar uma FALHA (exit != 0). -->

```console
$ <comando real 1>
<saída real 1>
```
<!-- executed: YYYY-MM-DD · exit=0 -->

```console
$ <comando real 2 — caso de FALHA>
<saída real 2>
```
<!-- executed: YYYY-MM-DD · exit=1 -->

```console
$ <comando real 3>
<saída real 3>
```
<!-- executed: YYYY-MM-DD · exit=0 -->

## Anti-patterns

- ❌ <armadilha conhecida 1>
- ❌ <armadilha conhecida 2>

## Proof

```bash
<comando único, <5s, sem rede, que prova o contrato — normalmente --self-test>
```
```

## Checklist antes de considerar pronto

- [ ] `name` bate exatamente com o nome da pasta
- [ ] `description` tem O QUE + QUANDO, sem sintaxe de wikilink duplo-colchete nas Keywords
- [ ] `## When NOT to Activate` tem ≥2 bullets
- [ ] `## Contract` tem as 4 sub-seções (INPUT/OUTPUT/EXIT CODES/STATE IT TOUCHES)
- [ ] ≥3 exemplos executados, ≥1 de falha (exit != 0), cada um com `<!-- executed: ... -->`
- [ ] `## Proof` roda em <5s sem rede
- [ ] `python tools/skill_lint.py <seu-arquivo>` → PASS
