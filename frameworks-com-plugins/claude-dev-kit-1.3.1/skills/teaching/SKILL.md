---
name: teaching
description: Transforma qualquer output técnico (criação, estrutura, decisão arquitetural) numa oportunidade de aprendizado — árvore de onde o elemento mora, raio-x de o-que-é/onde-fica/pra-que-serve, mapa de conexões, analogia de negócio, e decisões explicadas. Use sempre em output técnico para um leitor não-programador.
---

> **Auto-Trigger:** Sempre ativo em todo output técnico que envolva criação, estrutura, ou decisões arquiteturais.
> **Keywords:** "ensinar", "explicar", "como funciona", "onde fica", "arquitetura", "teaching", "por que"
> **Prioridade:** MÉDIA
> **Tools:** Read, Write, Bash

## Quando ativar
SEMPRE. Em todo output que envolva:
- Criação de arquivos
- Proposta de estrutura
- Planos de execução
- Decisões técnicas
- Menção a caminhos, pastas, formatos, conexões

## Quando NÃO Ativar

Mesmo sendo "SEMPRE ativo" para output técnico, NÃO aplicar os 5 blocos de ensino quando:

- **Resposta conversacional/não-técnica** (status, "onde paramos?", confirmação simples, pergunta de negócio sem elemento técnico) — não há arquivo/estrutura/conexão a ensinar.
- **Output puramente factual de dados ao vivo** (métricas, health score, contagens) — o foco é o dado verificado, não a arquitetura.
- **Edições triviais** (typo, vírgula, ajuste de 1 linha sem impacto estrutural) — o overhead de ensino vira ruído.
- **Execução interna em batch de subagente** onde o output vai para outro agente/orquestrador, não para um humano aprendiz.
- **Quando o usuário pedir explicitamente brevidade** ("só faz", "sem explicação", "resposta curta") — respeitar a instrução direta.

## Contrato

**ENTRADA:** qualquer output técnico (texto) que o modelo está prestes a entregar, cobrindo criação/estrutura/decisão arquitetural.

**SAÍDA:** o mesmo output, com os 5 blocos de ensino anexados (árvore, raio-x, conexões, analogia, decisões).

**EXIT CODES:**

| Exit | Significado |
|---|---|
| 0 | sempre — esta é uma skill de FORMATAÇÃO/COMPORTAMENTO, não há falha de execução possível; o "contrato" é sobre completude do output, verificável via o validador da seção Prova |

**ESTADO QUE TOCA:**

| Recurso | Lê/Escreve | Propósito |
|---|---|---|
| (nenhum arquivo) | — | esta skill não lê/escreve estado — molda a FORMA da resposta do modelo |

## Formato obrigatório de cada output técnico

### BLOCO 1: 🗺️ ONDE ESTAMOS (Tree Arquitetural)

Desenhe a árvore COMPLETA do projeto mostrando ONDE o elemento atual mora.
Marque com ➡️ o arquivo ou pasta em questão.
Use linguagem visual clara.

```
projeto-raiz/
├── CLAUDE.md              ← Regras gerais (o "handbook da empresa")
├── agents/                ← Todos os agentes moram aqui
│   ├── vendedor.md
│   └── analista.md
├── skills/                ← Todas as competências reutilizáveis
│   ├── teaching/
│   │   └── SKILL.md
│   └── copywriting/
│       └── SKILL.md
├── workflows/             ← Todos os processos orquestrados
│   ├── qualificar-lead.yml    ➡️ ESTAMOS AQUI
│   └── onboarding-cliente.yml
├── hooks/                 ← Todos os gatilhos automáticos
│   └── on-lead-entry.yml
└── tasks/                 ← Tarefas unitárias (opcional, podem viver dentro dos workflows)
```

REGRAS DO TREE:
- Sempre mostrar a árvore A PARTIR DA RAIZ do projeto
- Nunca mostrar só o caminho parcial — sempre o contexto completo
- Marcar com ➡️ o elemento que está sendo criado/modificado/explicado
- Se o projeto for muito grande, mostrar os 2 níveis mais relevantes + o caminho completo até o elemento

---

### BLOCO 2: 🔍 RAIO-X DO ELEMENTO

Para CADA arquivo ou pasta mencionado, responda OBRIGATORIAMENTE:

| Pergunta | Resposta |
|----------|----------|
| **O que é isso?** | Explicação em 1 frase, sem jargão. Use analogia do mundo de negócios. |
| **Onde fica?** | Caminho completo desde a raiz. Ex: `/projeto/workflows/qualificar-lead.yml` |
| **Dentro de quê?** | Qual pasta contém esse arquivo e por que essa pasta existe. |
| **Quantos desse tipo existem?** | 1 por processo? 1 por agente? Sem limite? Explique a regra. |
| **A quem está ligado?** | Liste TODOS os outros arquivos que se conectam a este. Mostre a direção: quem chama quem. |
| **Quem o aciona?** | O que faz este arquivo ser executado? Um comando? Um hook? Outro workflow? |
| **O que tem dentro?** | Estrutura interna resumida. Quais seções, campos ou blocos existem dentro desse arquivo. |
| **Por que esse formato?** | `.yml`, `.md`, `.json` — por que esse e não outro? Qual a vantagem prática? |
| **O que acontece se eu apagar?** | Consequência real. O que quebra, o que para de funcionar. |
| **Alternativa possível?** | Existia outra forma de fazer isso? Se sim, por que escolhemos esta? |

---

### BLOCO 3: 🔗 MAPA DE CONEXÕES

Desenhe como este elemento se conecta com os demais usando setas simples:

```
[CLAUDE.md] ──define regras para──▶ [agents/vendedor.md]
                                          │
                                    usa skill de
                                          │
                                          ▼
                                   [skills/copywriting/SKILL.md]
                                          │
                                  é chamado pelo workflow
                                          │
                                          ▼
                              [workflows/qualificar-lead.yml]  ➡️ ESTE
                                          │
                                   disparado por
                                          │
                                          ▼
                                [hooks/on-lead-entry.yml]
```

REGRAS:
- Sempre mostrar no mínimo 1 nível acima e 1 nível abaixo do elemento atual
- Usar verbos claros nas setas: "chama", "define", "dispara", "usa", "lê", "escreve"
- Se houver mais de um caminho, mostre todos

---

### BLOCO 4: 💡 TRADUÇÃO PARA O MUNDO REAL

Faça uma analogia direta com operação de empresa:

> **Na sua empresa:** Esse workflow é como o processo que seu time de vendas segue
> quando entra um lead novo. O arquivo `.yml` é o checklist escrito que qualquer
> vendedor novo receberia no primeiro dia. O hook que dispara ele é como o alerta
> automático que o CRM manda quando um formulário é preenchido. A skill que ele
> usa é como o script de qualificação que o vendedor segue na ligação.

REGRAS:
- Sempre usar analogia com operação de empresa, vendas, marketing ou gestão
- Nunca usar jargão técnico sem tradução imediata
- Se o conceito não tiver analogia óbvia, criar uma e ser explícito: "Não tem analogia perfeita, mas pense assim..."

---

### BLOCO 5: ⚠️ DECISÕES QUE TOMEI E POR QUÊ

Quando o agente tomar qualquer decisão técnica, DEVE explicar:

```
DECISÃO: Criei o workflow em formato .yml e não .md
POR QUÊ: Porque .yml permite que o sistema leia e interprete a estrutura
         automaticamente (parsing). Um .md é só texto legível por humanos —
         o sistema não consegue extrair etapas dele sem interpretação.
ALTERNATIVA: Poderia ser .json, mas .json é mais difícil de ler e editar
             manualmente. .yml é o meio-termo: legível por humanos E por máquinas.
CONSEQUÊNCIA: Se no futuro quiser que o sistema execute workflows automaticamente,
              .yml já está pronto. Se tivesse usado .md, precisaria reescrever.
```

---

## Regras de linguagem

1. **Nunca encurtar caminhos sem contexto.**
   - ❌ "Fica em `/workflows/`"
   - ✅ "Fica em `/projeto-raiz/workflows/qualificar-lead.yml` — a pasta `workflows` é onde moram TODOS os processos orquestrados do projeto, e fica diretamente na raiz."

2. **Nunca usar termo técnico sem tradução imediata.**
   - ❌ "Isso é um parser de YAML"
   - ✅ "Isso é um leitor automático de arquivos .yml (YAML é só o formato do arquivo — pense nele como uma planilha simplificada onde cada linha tem uma chave e um valor)"

3. **Nunca assumir que o leitor sabe o que existe dentro de uma pasta.**
   - Sempre listar o conteúdo, mesmo que seja "por enquanto está vazia, mas vai conter X"

4. **Sempre responder a pergunta antes que ela seja feita.**
   - Se mencionou um formato, explique o formato
   - Se mencionou uma conexão, mostre a conexão visualmente
   - Se mencionou uma pasta, mostre o que tem dentro

5. **Profundidade controlada.**
   - Vá até 2 níveis de "porquê".
   - Se a explicação puxar um terceiro nível, pare e diga: "Isso abre outro assunto (X). Quer que eu aprofunde?"

## Exemplo completo de output com Teaching Mode ativo

**Cenário:** O agente precisa criar um workflow de qualificação de leads.

---

**Output do agente:**

Vou criar o workflow de qualificação de leads.

🗺️ **ONDE ESTAMOS:**
```
meu-projeto/
├── CLAUDE.md
├── agents/
│   └── qualificador.md
├── skills/
│   └── perguntas-spin/
│       └── SKILL.md
├── workflows/
│   └── qualificar-lead.yml    ➡️ CRIANDO ESTE AGORA
└── hooks/
    └── novo-lead.yml
```

🔍 **RAIO-X:**

| Pergunta | Resposta |
|----------|----------|
| **O que é?** | Um processo escrito que define passo-a-passo como qualificar um lead. É o "checklist do vendedor". |
| **Onde fica?** | `/meu-projeto/workflows/qualificar-lead.yml` |
| **Dentro de quê?** | Pasta `workflows/`, que fica na raiz do projeto. Essa pasta existe para guardar TODOS os processos do projeto. Cada processo é um arquivo separado. |
| **Quantos desse tipo?** | 1 arquivo por processo. Se você tem 5 processos diferentes, terá 5 arquivos `.yml` dentro de `workflows/`. Sem limite. |
| **A quem está ligado?** | Chama o agente `agents/qualificador.md` para executar. O agente usa a skill `skills/perguntas-spin/SKILL.md`. |
| **Quem o aciona?** | O hook `hooks/novo-lead.yml` dispara quando entra lead novo. Ou pode ser chamado manualmente por comando. |
| **O que tem dentro?** | Nome do workflow, descrição, lista de steps (etapas), e para cada step: qual agente executa, qual skill usa, qual o output esperado. |
| **Por que .yml?** | Porque máquina e humano conseguem ler. Diferente de .md (só humano lê bem) e .json (só máquina lê bem). |
| **Se apagar?** | O hook vai tentar chamar esse workflow e vai dar erro. O agente continua existindo mas ninguém vai acioná-lo automaticamente. |
| **Alternativa?** | Poderia ser .md se fosse só documentação. Mas como queremos que o sistema execute as etapas, precisa de formato estruturado. |

🔗 **CONEXÕES:**
```
[hooks/novo-lead.yml] ──dispara──▶ [workflows/qualificar-lead.yml] ➡️
                                           │
                                     chama agente
                                           ▼
                                   [agents/qualificador.md]
                                           │
                                      usa skill
                                           ▼
                                [skills/perguntas-spin/SKILL.md]
```

💡 **NO SEU MUNDO:**
É como quando o CRM da sua empresa detecta um novo cadastro (hook),
abre automaticamente o processo de qualificação (workflow),
que escala pro SDR responsável (agente),
que segue o script SPIN selling (skill).

⚠️ **DECISÕES:**
```
DECISÃO: Separei o workflow do agente em arquivos diferentes
POR QUÊ: O mesmo agente pode ser usado em vários workflows diferentes.
         Se juntasse, teria que duplicar o agente toda vez.
CONSEQUÊNCIA: Mais flexível. O qualificador pode ser chamado por outros
              processos no futuro sem reescrever nada.
```

---

## Exemplos executados

O contrato desta skill (completude dos 5 blocos) é verificável com um pequeno validador:

```console
$ python -c "
def missing_teaching_blocks(text):
    checks = {'arvore': '🗺️' in text, 'raio-x': '🔍' in text, 'conexoes': '🔗' in text, 'analogia': '💡' in text, 'decisoes': '⚠️' in text}
    return [k for k, ok in checks.items() if not ok]
completo = '🗺️ x\n🔍 x\n🔗 x\n💡 x\n⚠️ x'
print('faltando:', missing_teaching_blocks(completo))
"
faltando: []
```
<!-- executado: 2026-07-10 · exit=0 -->
(output com os 5 blocos presentes — Teaching Mode completo, 0 blocos faltando.)

```console
$ python -c "
def missing_teaching_blocks(text):
    checks = {'arvore': '🗺️' in text, 'raio-x': '🔍' in text, 'conexoes': '🔗' in text, 'analogia': '💡' in text, 'decisoes': '⚠️' in text}
    return [k for k, ok in checks.items() if not ok]
incompleto = 'Vou criar o arquivo X.'
faltando = missing_teaching_blocks(incompleto)
print('faltando:', faltando)
import sys; sys.exit(1 if faltando else 0)
"
faltando: ['arvore', 'raio-x', 'conexoes', 'analogia', 'decisoes']
```
<!-- executado: 2026-07-10 · exit=1 -->
(um output técnico sem NENHUM dos 5 blocos — exatamente o que esta skill existe para prevenir.)

```console
$ python -c "
def missing_teaching_blocks(text):
    checks = {'arvore': '🗺️' in text, 'raio-x': '🔍' in text, 'conexoes': '🔗' in text, 'analogia': '💡' in text, 'decisoes': '⚠️' in text}
    return [k for k, ok in checks.items() if not ok]
parcial = '🗺️ x\n🔍 x'
print('faltando:', missing_teaching_blocks(parcial))
"
faltando: ['conexoes', 'analogia', 'decisoes']
```
<!-- executado: 2026-07-10 · exit=0 -->
(output PARCIAL — só árvore e raio-x — ainda faltam 3 blocos; útil pra revisar um output em progresso.)

## Anti-patterns

- ❌ Aplicar os 5 blocos numa resposta puramente conversacional ("oi", "onde paramos?") — vira ruído, veja "Quando NÃO Ativar".
- ❌ Mencionar uma pasta sem mostrar o que tem dentro dela.
- ❌ Usar termo técnico (parser, hook, schema) sem traduzir na mesma frase.
- ❌ Ir além de 2 níveis de "por quê" sem perguntar se o leitor quer aprofundar.

## Prova

```bash
python -c "
def missing_teaching_blocks(text):
    checks = {'arvore': '🗺️' in text, 'raio-x': '🔍' in text, 'conexoes': '🔗' in text, 'analogia': '💡' in text, 'decisoes': '⚠️' in text}
    return [k for k, ok in checks.items() if not ok]
assert missing_teaching_blocks('🗺️🔍🔗💡⚠️') == []
assert len(missing_teaching_blocks('nada aqui')) == 5
print('self-test OK')
"
```

## Instrução final para o CLAUDE.md

Cole este bloco no seu CLAUDE.md para ativar o Teaching Mode globalmente:

```markdown
## 🧠 Teaching Mode (SEMPRE ATIVO)

Ao criar, modificar ou explicar qualquer elemento técnico, OBRIGATORIAMENTE inclua:
1. 🗺️ Tree arquitetural completo mostrando ONDE o elemento mora (desde a raiz)
2. 🔍 Raio-X com: o que é, onde fica, dentro de quê, ligado a quê, formato e porquê
3. 🔗 Mapa de conexões visual com setas e verbos
4. 💡 Analogia com operação de empresa (vendas, marketing, gestão)
5. ⚠️ Cada decisão técnica explicada: o que, por quê, alternativa, consequência

Regras:
- Nunca encurtar caminhos sem mostrar o contexto completo
- Nunca usar termo técnico sem tradução imediata
- Nunca mencionar pasta sem mostrar o que tem dentro
- Ir até 2 níveis de profundidade. No 3º nível, perguntar se quer aprofundar.
- Usar linguagem de negócios como analogia primária.

Referência completa: ${CLAUDE_PLUGIN_ROOT}/skills/teaching/SKILL.md
```
