# SKILL-CONTRACT — o que separa "pilha de scripts" de "sistema"

> **Versão:** 1.0.0 · **Enforcement:** `tools/skill_lint.py` (vendorizado neste kit)

## Princípio

```
UMA SKILL É PRODUTO QUANDO UM ESTRANHO, NUM REPO VIRGEM, EM QUALQUER OS,
CONSEGUE: (1) saber QUANDO ela dispara, (2) saber O QUE entra e O QUE sai,
(3) copiar-colar um comando que FUNCIONA, (4) provar com exit 0 que funcionou.
Prosa numerada sem comando literal NAO e skill — e ensaio.
```

Uma skill que só descreve passos em prosa, sem contrato de I/O e sem prova executável, é um
ensaio sobre a tarefa — não uma ferramenta que um estranho pode operar sem adivinhar.

## As 6 cláusulas

### C1 · HEADER
Frontmatter `name` + `description`, mais 4 linhas de metadado:
- `> **Auto-Trigger:**` — quando a skill dispara automaticamente.
- `> **Keywords:**` — mínimo 4 palavras/frases, sem wikilinks `[[...]]` (contaminação de staging).
- `> **Prioridade:**` — ALTA/MÉDIA/BAIXA.
- `> **Tools:**` — lista explícita das ferramentas que a skill usa.

Mais uma seção `## Quando NÃO Ativar` com ≥2 bullets — nomeando a skill vizinha quando há
fronteira confundível (ex.: "não confundir com a skill X, que cobre Y").

### C2 · CONTRATO DE I/O
Seção `## Contrato` com:
- **ENTRADA** — tipos aceitos (arquivo, string, flag).
- **SAÍDA** — paths + formato modelado (não "gera um relatório", mas o schema do relatório).
- **EXIT CODES** — tabela `0 / 1 / 2` (e além, se aplicável) com o significado de cada um.
- **ESTADO QUE TOCA** — tabela `arquivo → lê/escreve → propósito`.

### C3 · ≥3 EXEMPLOS EXECUTADOS
Saída REAL colada (não inventada — inventar saída é o oposto do que uma skill de integridade
de agente deve fazer), com marcador parseável `<!-- executado: YYYY-MM-DD · exit=N -->` em cada
exemplo. Pelo menos 1 exemplo deve ser de FALHA (mostrar o exit != 0 e a mensagem real).
Exemplos expiram em 90 dias (o lint emite WARN, não FAIL, para exemplo velho — ele pode ainda
ser verdadeiro, mas merece re-verificação).

### C4 · PROVA
Seção `## Prova` com um comando único, que roda em menos de 5 segundos, sem rede, que demonstra
o contrato e termina com exit 0 esperado. Herda o padrão `--self-test`.

### C5 · PORTABILIDADE
- Launcher: `python` sempre. **`py` é PROIBIDO** (Windows-only).
- **Tools exclusivas de um main-loop/orquestrador específico são PROIBIDAS como dependência**
  — se uma tool só existe dentro de um contexto de execução particular (ex.: um main-loop
  autônomo), subagentes e instalações externas não a enxergam; documentar como opcional, nunca
  como requisito do fluxo principal.
- **Self-containment:** tudo que a skill executa é resolvível via `${CLAUDE_PLUGIN_ROOT}`
  (modo plugin) ou vendorizado pelo assembler (modo cópia). Referência a um path relativo cru
  de outro kit, ou a um `_lib` solto sem essas duas vias, é quebra garantida pós-install.

### C6 · CORPO EXECUTÁVEL
Comando literal por passo (não "rode o script apropriado" — o comando exato), formato de saída
modelado, templates INTEIROS quando a skill emite um artefato (não esboço/trecho), anti-patterns
documentados quando há armadilha conhecida, e cross-link entre skills irmãs quando há fronteira
compartilhada.

## Enforcement automático

`tools/skill_lint.py` (vendorizado neste kit) implementa os checks `L1a`–`L6` (mapeamento 1:1 às
cláusulas acima). Contrato de exit do lint:

| Exit | Significado |
|---|---|
| `0` | PASS — nenhuma violação |
| `1` | Só WARNs (ex.: exemplo com >90 dias) |
| `2` | ≥1 FAIL (violação de cláusula obrigatória) |

Ajuste de C5 no lint: `${CLAUDE_PLUGIN_ROOT}/...` é referência VÁLIDA (L5b aceita). FAIL só ocorre
em path relativo cru tipo `algum-outro-kit/scripts/...` ou `_lib` fora de resolução declarada.
