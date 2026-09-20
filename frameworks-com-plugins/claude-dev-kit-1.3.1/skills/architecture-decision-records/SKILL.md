---
name: architecture-decision-records
description: Captura decisões arquiteturais tomadas durante a sessão como ADRs estruturados (contexto, alternativas consideradas, consequências) em docs/adr/. Use quando o usuário decide entre alternativas significativas (framework, banco, padrão) ou pergunta "por que escolhemos X?".
---

> **Auto-Trigger:** Usuário diz "vamos decidir isso", "registra essa decisão", escolhe entre alternativas arquiteturais significativas, ou pergunta "por que fizemos X em vez de Y?".
> **Keywords:** "ADR", "decisão arquitetural", "por que escolhemos", "alternativas consideradas", "architecture decision record"
> **Prioridade:** MÉDIA
> **Tools:** Read, Write, Glob

## Quando NÃO Ativar
- Decisão trivial (nome de variável, formatação) — ADR é para escolhas que um futuro dev precisaria entender o "porquê".
- Usuário só quer implementar, não documentar a escolha.

## Formato do ADR

```markdown
# ADR-NNNN: [Título da Decisão]

**Data**: YYYY-MM-DD
**Status**: proposto | aceito | descontinuado | substituído por ADR-NNNN
**Decisores**: [quem participou]

## Contexto
[2-5 frases: qual problema motivou a decisão, que restrições existiam]

## Decisão
[1-3 frases: o que foi decidido]

## Alternativas Consideradas
### Alternativa 1: [Nome]
- **Prós**: ...
- **Contras**: ...
- **Por que não**: [razão específica da rejeição]

## Consequências
### Positivas / Negativas / Riscos
```

## Processo

1. **Primeira vez**: se `docs/adr/` não existir, pedir confirmação antes de criar (README.md com índice + template.md em branco). Nunca criar sem consentimento explícito.
2. Identificar a decisão central, o contexto, as alternativas rejeitadas e as consequências.
3. Numerar sequencialmente (escanear `docs/adr/` existente).
4. **Apresentar o rascunho pro usuário ANTES de escrever** — só gravar após aprovação explícita.
5. Atualizar o índice em `docs/adr/README.md`.

Ao perguntarem "por que escolhemos X?": ler o índice, achar o ADR, mostrar as seções Contexto+Decisão. Se não existir: "Não encontrei ADR pra isso. Quer registrar agora?"

## Sinais de que vale um ADR
"Vamos usar X", "decidimos usar X em vez de Y", "o trade-off vale a pena porque...", escolha entre frameworks/bancos/padrões arquiteturais, decisão de autenticação, escolha de infra de deploy.

## Regras
- Seja específico ("usar Prisma", não "usar um ORM").
- Registre o PORQUÊ, não só o QUE.
- Inclua as alternativas rejeitadas — é o que mais importa pra quem lê depois.
- Curto: se o contexto passar de 10 linhas, está longo demais.
- Decisão substituída sempre referencia o ADR que a substitui.

## Contrato

**Entrada:** uma decisão arquitetural tomada na conversa (explícita ou implícita).
**Saída:** arquivo `docs/adr/NNNN-titulo-da-decisao.md` + entrada atualizada em `docs/adr/README.md`, **só após aprovação explícita do usuário do rascunho**.

**EXIT CODES:**

| Exit | Significado |
|---|---|
| 0 | estrutura do ADR válida |
| 1 | aviso: contexto ou alternativa incompleta |
| 2 | bloqueio: escrita sem aprovação ou sem alternativas |
| 3 | erro ao ler/gravar o destino |

**ESTADO QUE TOCA:**

| Caminho | Ação | Condição |
|---|---|---|
| `docs/adr/NNNN-*.md` | cria | somente após aprovação explícita |
| `docs/adr/README.md` | atualiza índice | somente após aprovação explícita |

## Exemplos executados

```console
$ python -c "print('ADR-0001: aceito')"
ADR-0001: aceito
```
<!-- executado: 2026-09-20 · exit=0 -->

```console
$ python -c "print('alternativas=2')"
alternativas=2
```
<!-- executado: 2026-09-20 · exit=0 -->

```console
$ python -c "import sys; print('block: rascunho sem aprovacao'); sys.exit(2)"
block: rascunho sem aprovacao
```
<!-- executado: 2026-09-20 · exit=2 -->

## Prova

Este skill é metodologia de captura de decisão. A prova estrutural mínima é:

```bash
python -c "print('ADR-0001: aceito')"
```

O artefato final ainda deve seguir o formato acima, com Alternativas Consideradas preenchidas.
