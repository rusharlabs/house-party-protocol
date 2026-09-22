[English](SKILL-CONTRACT.md) · [Português](SKILL-CONTRACT.pt-BR.md)

# SKILL-CONTRACT — o que separa "pilha de scripts" de "sistema"

> **Versão:** 1.1.0 (2026-09-21 — os tokens de schema em inglês são canônicos; os em português
> são aceitos como legado) · **Origem:** destilado
> da régua de calibração das 4 melhores skills já construídas por este time (`source-sync`,
> `github-workflow`, `verify-6-levels` e uma quarta de busca semântica) mais a cláusula C3
> (execução real) que nem elas têm.
> **Enforcement:** `skill_lint.py` — `instaladores/kit-forge/tools/skill_lint.py` na raiz do
> marketplace, vendorizado como `tools/skill_lint.py` dentro do `claude-dev-kit`.

## Princípio

```
UMA SKILL É PRODUTO QUANDO UM ESTRANHO, NUM REPO VIRGEM, EM QUALQUER OS,
CONSEGUE: (1) saber QUANDO ela dispara, (2) saber O QUE entra e O QUE sai,
(3) copiar-colar um comando que FUNCIONA, (4) provar com exit 0 que funcionou.
Prosa numerada sem comando literal NAO e skill — e ensaio.
```

Uma skill que só descreve passos em prosa, sem contrato de I/O e sem prova executável, é um
ensaio sobre a tarefa — não uma ferramenta que um estranho pode operar sem adivinhar.

## Tokens de schema — canônicos e legados

O lint casa os tokens abaixo literalmente. **Inglês é canônico** (escreva skills novas com ele);
as **formas em português são aceitas como legado** (skills escritas antes de 2026-09-21 seguem
passando sem alteração). Cada cláusula aceita qualquer uma das duas formas por si só, então uma
skill que mistura formas linta exatamente como uma pura — o contrato é estrutural, e a língua de
um token não é cláusula.

| Cláusula | Canônico (inglês) | Legado aceito (português) |
|---|---|---|
| C1 header | `> **Priority:**` HIGH / MEDIUM / LOW | `> **Prioridade:**` ALTA / MÉDIA / BAIXA |
| C1 seção | `## When NOT to Activate` | `## Quando NÃO Ativar` |
| C2 seção | `## Contract` | `## Contrato` |
| C2 campos | `**INPUT:**` · `**OUTPUT:**` · `**EXIT CODES**` · `**STATE IT TOUCHES:**` | `**ENTRADA:**` · `**SAÍDA:**` · `**EXIT CODES**` · `**ESTADO QUE TOCA:**` |
| C2 linha do exit 0 | a palavra `always` na linha do exit 0 (contrato de exit único) | `sempre` |
| C3 marcador | `<!-- executed: YYYY-MM-DD · exit=N -->` | `<!-- executado: YYYY-MM-DD · exit=N -->` |
| C4 seção | `## Proof` | `## Prova` |

`Auto-Trigger`, `Keywords`, `Tools` e `EXIT CODES` nunca foram traduzidos e têm uma forma só.

## As 6 cláusulas

### C1 · HEADER
Frontmatter `name` + `description`, mais 4 linhas de metadado:
- `> **Auto-Trigger:**` — quando a skill dispara automaticamente.
- `> **Keywords:**` — mínimo 4 palavras/frases, sem wikilinks `[[...]]` (contaminação de staging).
- `> **Priority:**` — HIGH/MEDIUM/LOW (legado `Prioridade:` ALTA/MÉDIA/BAIXA). O lint confere o
  nome do campo (L1b); o valor é a convenção, não é checado por máquina.
- `> **Tools:**` — lista explícita das ferramentas que a skill usa.

Mais uma seção `## When NOT to Activate` (legado `## Quando NÃO Ativar`) com ≥2 bullets —
nomeando a skill vizinha quando há fronteira confundível (ex.: "não confundir com a skill X, que
cobre Y").

### C2 · CONTRATO DE I/O
Seção `## Contract` (legado `## Contrato`) com:
- **INPUT** (legado ENTRADA) — tipos aceitos (arquivo, string, flag).
- **OUTPUT** (legado SAÍDA) — paths + formato modelado (não "gera um relatório", mas o schema do
  relatório).
- **EXIT CODES** — tabela `0 / 1 / 2` (e além, se aplicável) com o significado de cada um. Um
  mecanismo que só consegue sair 0 (um conector que nunca quebra quem chama) diz isso com a
  palavra `always` (legado `sempre`) na linha do exit 0 — aí a C3 não cobra exemplo de falha.
- **STATE IT TOUCHES** (legado ESTADO QUE TOCA) — tabela `arquivo → lê/escreve → propósito`
  (o padrão de `.claude/skills/source-sync/SKILL.md:166-176`).

### C3 · ≥3 EXEMPLOS EXECUTADOS
Saída REAL colada (não inventada — viola `agent-integrity.md` inventar saída), com marcador
parseável `<!-- executed: YYYY-MM-DD · exit=N -->` (legado `executado:`) em cada exemplo. Pelo
menos 1 exemplo deve ser de FALHA (mostrar o exit != 0 e a mensagem real). Exemplos expiram em 90
dias (o lint emite WARN, não FAIL, para exemplo velho — ele pode ainda ser verdadeiro, mas merece
re-verificação).

### C4 · PROVA
Seção `## Proof` (legado `## Prova`) com um comando único, que roda em menos de 5 segundos, sem
rede, que demonstra o contrato e termina com exit 0 esperado. Herda o padrão dos scripts bons da
casa (`--self-test`). O `--run-proofs` executa a primeira linha do bloco a partir do diretório da
skill: um `# comentário` no fim da linha é removido antes de rodar (no Windows o shell é o
cmd.exe, onde `#` não é comentário e `>` é redirecionamento) e `${CLAUDE_PLUGIN_ROOT}` é
expandido para a raiz do módulo da skill.

### C5 · PORTABILIDADE
- Launcher: `python` sempre. **`py` é PROIBIDO** (Windows-only — bug real de
  `pre-clear-boot-block:16`).
- **`ScheduleWakeup` é PROIBIDO como dependência** — é uma tool exclusiva do main-loop `/loop`;
  subagentes e instalações externas não a enxergam (bug real de `ralph-loop-driver:23`).
- **Self-containment:** tudo que a skill executa é resolvível via `${CLAUDE_PLUGIN_ROOT}`
  (modo plugin) ou vendorizado pelo assembler (modo cópia). Referência a `operator-kit/scripts/`
  ou a um `_lib` solto sem essas duas vias = quebra garantida pós-install.

### C6 · CORPO EXECUTÁVEL
Comando literal por passo (não "rode o script apropriado" — o comando exato), formato de saída
modelado, templates INTEIROS quando a skill emite um artefato (não esboço/trecho), anti-patterns
documentados quando há armadilha conhecida, e cross-link entre skills irmãs quando há fronteira
compartilhada.

## Enforcement automático

`skill_lint.py` implementa os checks `L1a`–`L6` (mapeamento 1:1 às cláusulas acima). Os ids de
achado (`L1b.prioridade`, `L2a.contrato_ausente`, `L4a.prova_ausente`, ...) são o contrato
estável de saída do checker e não mudaram com os tokens em inglês — só as mensagens mudaram.
Contrato de exit do lint:

| Exit | Significado |
|---|---|
| `0` | PASS — nenhuma violação |
| `1` | Só WARNs (ex.: exemplo com >90 dias) |
| `2` | ≥1 FAIL (violação de cláusula obrigatória) |

Ajuste de C5 no lint: `${CLAUDE_PLUGIN_ROOT}/...` é referência VÁLIDA (L5c aceita). FAIL só ocorre
em path relativo cru tipo `operator-kit/scripts/...` ou `_lib` fora de resolução declarada.
