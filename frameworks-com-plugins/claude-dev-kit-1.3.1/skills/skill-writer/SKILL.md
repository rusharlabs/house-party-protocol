---
name: skill-writer
description: Guia a criação de Agent Skills para Claude Code — estrutura, frontmatter, descrições eficazes, e validação contra o SKILL-CONTRACT. Use quando o usuário quer criar, escrever ou estruturar uma nova skill.
---

> **Auto-Trigger:** Quando o usuário quer criar, escrever ou estruturar uma nova skill para Claude Code, ou converter um prompt/processo repetido numa skill reutilizável.
> **Keywords:** "criar skill", "nova skill", "SKILL.md", "skill structure", "write skill", "author skill", "estruturar skill"
> **Prioridade:** MÉDIA
> **Tools:** Read, Grep, Glob, Write, Edit, Bash

## Quando NÃO Ativar
- **Criar um HOOK** (PreToolUse/PostToolUse/SessionStart) — use a skill `hookify` deste mesmo kit; hooks são scripts com stdin→JSON e exit codes, não SKILL.md.
- **Criar um PLUGIN** (`.claude-plugin/plugin.json` + `hooks.json`/`commands/`) — use a skill `plugin-dev` deste mesmo kit; plugin é a embalagem que agrupa skills/hooks/commands, não uma skill em si.
- **Editar uma skill vendored/de outro plugin** (cópia idêntica de um marketplace) — não reescrever; essas atualizam pelo próprio plugin de origem.
- **Escrever documentação de projeto ou plano de implementação** — isso não é uma Skill (não tem gatilho nem contrato de I/O).

## Contrato

**ENTRADA:** o modelo (via conversa com o usuário) determina escopo/nome/gatilhos/ferramentas da nova skill.

**SAÍDA:** um diretório `<skill-name>/SKILL.md` (+ companions opcionais) que passa em `tools/skill_lint.py` sem FAIL.

**EXIT CODES** (de `tools/skill_lint.py`, usado para validar o resultado):

| Exit | Significado |
|---|---|
| 0 | skill em conformidade com o SKILL-CONTRACT (PASS, 0 FAIL) |
| 1 | só WARN (ex.: exemplo executado há >90 dias) — utilizável, mas revisar |
| 2 | ≥1 FAIL (violação de cláusula obrigatória — ver `docs/SKILL-CONTRACT.md`) |

**ESTADO QUE TOCA:**

| Recurso | Lê/Escreve | Propósito |
|---|---|---|
| `<skill-dir>/SKILL.md` | Escreve | a skill em si |
| `<skill-dir>/examples.md`, `troubleshooting.md`, `reference.md` (opcionais) | Escreve | progressive disclosure — conteúdo extenso sai do SKILL.md principal |
| `docs/SKILL-CONTRACT.md` | Lê | as 6 cláusulas que toda skill PRODUTO deve cumprir |
| `tools/skill_lint.py` | Executa (read-only) | valida a skill criada contra o contrato |

## Processo

### 1. Determine o escopo
Pergunte (ou infira da conversa): que capacidade única esta skill resolve? Quando ela deve disparar? Quais ferramentas ela precisa? **Regra: uma skill = uma capacidade.**

### 2. Escolha a localização
| Local | Uso |
|-------|-----|
| `~/.claude/skills/` | Pessoal, experimental |
| `.claude/skills/` | Time/projeto, versionado em git |
| `<kit>/skills/` | Distribuído via plugin/marketplace |

### 3. Crie a estrutura
```bash
mkdir -p .claude/skills/skill-name
```
Multi-arquivo (progressive disclosure — use quando o corpo passaria de ~500 linhas):
```
skill-name/
├── SKILL.md (obrigatório)
├── examples.md (opcional — ver examples.md deste kit para o padrão)
├── troubleshooting.md (opcional — ver troubleshooting.md deste kit para o padrão)
└── scripts/ (opcional)
```

### 4. Escreva o header completo (C1 do contrato)
```yaml
---
name: skill-name
description: O que faz + quando usar. Máx 1024 chars.
---
```
```markdown
> **Auto-Trigger:** quando dispara automaticamente
> **Keywords:** "termo1", "termo2", "termo3", "termo4" (mínimo 4, sem sintaxe de wikilink duplo-colchete)
> **Prioridade:** ALTA | MÉDIA | BAIXA
> **Tools:** lista explícita

## Quando NÃO Ativar
- (≥2 bullets — nomeie a skill vizinha se há fronteira confundível)
```

| Campo | Regra |
|-------|-------|
| `name` | minúsculas, hífens, máx 64 chars, **deve bater com o nome da pasta** |
| `description` | máx 1024 chars, inclua O QUE + QUANDO usar |
| `allowed-tools`/`Tools` | lista explícita de ferramentas |

### 5. Escreva a descrição (fórmula: O QUE + QUANDO + gatilhos-chave)
```yaml
# Boa
description: Extrai texto de PDFs, preenche formulários. Use quando o usuário mencionar PDFs ou extração de documentos.

# Ruim
description: Ajuda com documentos
```
Ver `examples.md` para mais padrões de descrição boa/ruim.

### 6. Escreva o Contrato de I/O (C2) — ENTRADA / SAÍDA / EXIT CODES / ESTADO QUE TOCA

### 7. Colete ≥3 exemplos EXECUTADOS DE VERDADE (C3)
Rode o comando real, cole a saída real, marque `<!-- executado: YYYY-MM-DD · exit=N -->`. Pelo menos 1 exemplo deve mostrar uma FALHA (exit != 0). Nunca invente saída — se não rodou, não cole.

### 8. Escreva a seção Prova (C4)
Um comando único, <5s, sem rede, que prova o contrato com exit 0. Normalmente `--self-test`.

### 9. Valide contra o contrato
```bash
python tools/skill_lint.py <skill-dir>/SKILL.md
```
Corrija cada FAIL apontado (não ignore WARN de exemplo velho sem reverificar).

### 10. Teste de ativação
1. Reinicie o Claude Code para carregar a skill.
2. Faça uma pergunta que bate com a `description`.
3. Confirme que ela ativa e se comporta como esperado.

## Exemplos executados

```console
$ python tools/skill_lint.py skills/claude-dev-setup/SKILL.md
[PASS] skills/claude-dev-setup/SKILL.md

skill_lint: 1 pass · 0 warn · 0 fail (de 1)
```
<!-- executado: 2026-07-10 · exit=0 -->
(uma skill em conformidade total com as 6 cláusulas — 0 FAIL, 0 WARN.)

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
<!-- executado: 2026-07-10 · exit=2 -->
(uma descrição vaga ("Helps with stuff") e um corpo sem estrutura falham em 8 checks de uma vez — exatamente o "ensaio sem contrato" que o SKILL-CONTRACT existe para impedir.)

```console
$ mkdir -p .claude/skills/exemplo-novo && ls .claude/skills/exemplo-novo
```
<!-- executado: 2026-07-10 · exit=0 -->
(passo 3 do processo — criação da estrutura antes de escrever o SKILL.md.)

## Anti-patterns

- ❌ Descrição vaga ("ajuda com X") sem gatilhos específicos — a skill nunca ativa quando deveria.
- ❌ Nome da pasta diferente do `name` no frontmatter — quebra silenciosa, a skill simplesmente não é encontrada.
- ❌ Colar saída "provável" em vez de rodar o comando de verdade — viola C3 e a doutrina de integridade deste marketplace (nunca inventar saída).
- ❌ Aninhamento profundo de arquivos-companion (`SKILL.md → a.md → b.md → c.md`) — mantenha achatado: `SKILL.md → examples.md`, `SKILL.md → troubleshooting.md`.

## Prova

```bash
python tools/skill_lint.py --self-test
```

## Recursos adicionais

- **Padrões e exemplos**: ver [examples.md](examples.md)
- **Debugging de skills que não ativam**: ver [troubleshooting.md](troubleshooting.md)
- **O contrato completo (6 cláusulas)**: ver [`docs/SKILL-CONTRACT.md`](../../docs/SKILL-CONTRACT.md)
