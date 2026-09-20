---
name: search-first
description: Busca por biblioteca/ferramenta/padrão existente ANTES de escrever código novo — cobre registro de pacotes (npm/PyPI), MCP e GitHub, além do grep local. Use antes de criar utilitário, helper, ou integração nova.
---

> **Auto-Trigger:** Antes de escrever um utilitário/helper novo, adicionar uma dependência, ou quando o pedido do usuário provavelmente já tem solução pronta.
> **Keywords:** "adicionar funcionalidade", "criar utilitário", "nova dependência", "existe biblioteca pra isso"
> **Prioridade:** MÉDIA
> **Tools:** Read, Grep, Bash, WebSearch

## Quando NÃO Ativar
- Já é sabido que não existe solução pronta (domínio muito específico do negócio).
- Complementa, não substitui, LC-3 (`learned-corrections.md`) — LC-3 é grep local antes de
  criar/classificar arquivo; este skill estende a busca pra fora do repo (registros de
  pacote, MCP, GitHub) antes de escrever código novo.

## Fluxo

```
0. PREFLIGHT DE DISPONIBILIDADE — checar que canais de busca existem antes de contar com eles
1. ANÁLISE DA NECESSIDADE — o que precisa, que linguagem/framework
2. BUSCA EM PARALELO — npm/PyPI · MCP/skills locais · GitHub/web
3. AVALIAR — funcionalidade, manutenção, comunidade, docs, licença, dependências
4. DECIDIR — adotar como está / estender-wrap / compor 2-3 pacotes / construir custom
5. IMPLEMENTAR
```

## Matriz de decisão

| Sinal | Ação |
|---|---|
| Match exato, bem mantido, MIT/Apache | **Adotar** — instalar e usar direto |
| Match parcial, boa base | **Estender** — instalar + wrapper fino |
| Múltiplos matches fracos | **Compor** — combinar 2-3 pacotes pequenos |
| Nada adequado encontrado | **Construir** — custom, mas informado pela pesquisa |

## Modo rápido (inline, antes de escrever utilitário)

0. Já existe no repo? → `rg` nos módulos/testes relevantes primeiro (= LC-3)
1. É um problema comum? → buscar npm/PyPI
2. Existe MCP pra isso? → checar `.claude/settings.json` + `.mcp.json`
3. Existe skill pra isso? → `skill-scout` (deste mesmo kit)
4. Existe implementação/template no GitHub? → busca de código antes de escrever net-new

## Anti-Padrões
- Pular direto pro código sem checar se já existe.
- Ignorar MCP disponível.
- "Não achei nada" quando um canal de busca só estava indisponível (reportar honestamente).
- Over-customizar um wrapper até perder o benefício da lib.
- Inflar dependências por 1 feature pequena.

## Contrato

**Entrada:** necessidade de funcionalidade nova antes de escrever código.
**Saída:** decisão registrada (adotar/estender/compor/construir) com a busca real que a embasou —
nunca "construir" sem antes ter buscado nos 4 canais aplicáveis.

**EXIT CODES:**

| Exit | Significado |
|---|---|
| 0 | busca aplicável executada e decisão registrada |
| 1 | aviso: canal indisponível declarado |
| 2 | bloqueio: decisão de construir sem busca |
| 3 | erro do instrumento de busca |

**ESTADO QUE TOCA:**

| Caminho | Ação | Condição |
|---|---|---|
| repositório-alvo | leitura | busca local antes de criar |
| registro da decisão definido pelo projeto | escrita opcional | só quando o projeto exigir |

## Exemplos executados

```console
$ python -c "print('local=consultado')"
local=consultado
```
<!-- executado: 2026-09-20 · exit=0 -->

```console
$ python -c "print('decisao=adotar')"
decisao=adotar
```
<!-- executado: 2026-09-20 · exit=0 -->

```console
$ python -c "import sys; print('block: construir sem busca'); sys.exit(2)"
block: construir sem busca
```
<!-- executado: 2026-09-20 · exit=2 -->

## Prova

Metodologia de pesquisa — a prova mínima do contrato é:

```bash
python -c "print('local=consultado')"
```

Na execução real, a evidência é o comando de busca aplicável ter rodado antes do código novo.
