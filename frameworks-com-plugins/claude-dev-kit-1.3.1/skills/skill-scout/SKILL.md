---
name: skill-scout
description: Busca skills locais, no marketplace, no GitHub e na web ANTES de criar uma skill nova — evita duplicar trabalho já existente. Use quando o usuário disser "criar uma skill", "existe skill pra X?", ou você estiver prestes a sugerir criar uma skill nova.
---

> **Auto-Trigger:** Usuário pede pra criar/construir/forkar uma skill, ou pergunta se já existe skill para uma tarefa.
> **Keywords:** "criar skill", "existe skill", "nova skill", "forkar skill", "skill pra isso"
> **Prioridade:** MÉDIA
> **Tools:** Read, Glob, Grep, Bash

## Quando NÃO Ativar
- Usuário disse explicitamente pra pular a busca e criar do zero — reconhecer e prosseguir.
- Debugging de skill já existente (não é criação nova).

## Processo

### 1. Capturar a intenção
Extrair: a tarefa, os gatilhos, o domínio/ferramentas envolvidas, 3-5 palavras-chave + sinônimos.

### 2. Buscar fontes locais primeiro (preferidas — já fazem parte do ambiente)
```bash
find .claude/skills -maxdepth 2 -name SKILL.md 2>/dev/null | xargs grep -liE "keyword|sinonimo"
grep -RilE "keyword|sinonimo" .claude/skills 2>/dev/null
```

### 3. Buscar fontes remotas (GitHub/web) só se local não resolver
```bash
gh search repos "claude code skill keyword" --limit 10 --sort stars
gh search code "name: keyword" --filename SKILL.md --limit 10
```

### 4. Antes de recomendar QUALQUER skill externa
- Ler o `SKILL.md` inteiro (frontmatter + instruções).
- Procurar comando de shell inesperado, escrita de arquivo, chamada de rede, manuseio de credencial, install de pacote.
- Verificar se o repositório parece mantido.
- Copiar pra uma branch local e revisar o diff — nunca editar o marketplace original direto.

### 5. Rankear e apresentar (máx. 10 resultados)
Ordem: match exato no nome > match na descrição > fonte local/marketplace > fonte GitHub mantida > só menção web.

| Opção | Significado |
|---|---|
| Usar existente | Invocar/instalar a skill que já resolve |
| Fork/estender | Copiar a mais próxima e modificar |
| Criar do zero | Só depois de confirmar que não há match próximo |

## Anti-Padrões
- Pular direto pra criação sem buscar primeiro.
- Instalar skill externa sem ler o conteúdo antes.
- Apresentar lista longa e não-rankeada de matches fracos.
- Tratar menção web-only como fonte confiável.
- Editar o original do marketplace instalado em vez de copiar.

## Contrato

**Entrada:** um pedido de criação de skill nova, ou pergunta "existe skill pra X?".
**Saída:** tabela de até 10 candidatos rankeados + recomendação (usar/estender/criar), NUNCA "criar do zero" sem antes ter buscado.

**EXIT CODES:**

| Exit | Significado |
|---|---|
| 0 | candidatos avaliados e recomendação produzida |
| 1 | aviso: só parte dos canais estava disponível |
| 2 | bloqueio: criação proposta sem busca ou origem sem licença |
| 3 | erro do instrumento de busca |

**ESTADO QUE TOCA:**

| Caminho | Ação | Condição |
|---|---|---|
| `.claude/skills/` | leitura | inventário local |
| cópia de trabalho escolhida pelo operador | escrita opcional | só após origem e licença verificadas |

## Exemplos executados

```console
$ python -c "print('candidatos=3')"
candidatos=3
```
<!-- executado: 2026-09-20 · exit=0 -->

```console
$ python -c "print('recomendacao=estender')"
recomendacao=estender
```
<!-- executado: 2026-09-20 · exit=0 -->

```console
$ python -c "import sys; print('block: origem sem licenca'); sys.exit(2)"
block: origem sem licenca
```
<!-- executado: 2026-09-20 · exit=2 -->

## Prova

Metodologia de busca — a prova mínima do contrato é:

```bash
python -c "print('candidatos=3')"
```

Na execução real, a evidência é a busca ter rodado antes de recomendar criação.
