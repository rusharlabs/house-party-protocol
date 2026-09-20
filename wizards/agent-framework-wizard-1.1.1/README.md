# Agent Framework Wizard

Wizard de 6 passos (`check_python → check_git → check_deps → configure → validate →
generate_and_summary`) que faz o scaffold de um agente/projeto novo: gera
`operator-profile.yaml` (escada de verificação R0-R4) + os templates escolhidos
(`00-LEIA-PRIMEIRO`, `00-STATE`, `00-VISION`, `00-PROCESSES`). Não instala o
`operator-kit` em si — gera o esqueleto inicial que um projeto novo usaria com ele.

## Pré-requisitos + APIs externas

| Requisito | Versão mínima | Obrigatório? |
|---|---|---|
| Python | 3.9 | sim |
| git | qualquer | sim — o wizard confirma `git --version` no passo 2 |
| PyYAML | qualquer | sim |

Serviços externos: **nenhum — stdlib + PyYAML.**

## Instalar via plugin

```bash
/plugin marketplace add .
/plugin install agent-framework-wizard@house-party-protocol
```

## Instalar por cópia

```bash
cp -r agent-framework-wizard-1.0.0 <seu-projeto>/agent-framework-wizard
cd <seu-projeto>/agent-framework-wizard
```
Este kit não tem hooks/wiring — depois de copiado, use direto (seção seguinte).

## Como usar (não-interativo — nenhum modo bloqueia em stdin)

O operador real deste ecossistema é frequentemente um agente atuando pelo humano — um
`input()` de terminal trava exatamente nesse contexto. O "Confirm" deste wizard é
`--interview` (imprime o schema de perguntas) seguido de `--answers` (aplica as respostas):

```bash
# 1. Ver o schema de perguntas (JSON, exit 0, não gera nada)
python wizard.py --interview

# 2a. Scaffold rápido com defaults sensatos (sem perguntar nada)
python wizard.py --demo --out <dir>

# 2b. OU scaffold a partir de respostas prontas (o agente monta o JSON após ler --interview)
python wizard.py --answers respostas.json --out <dir>
```

Exemplo de `respostas.json`:
```json
{"project_name": "meu-agente", "templates": ["00-STATE", "00-VISION"]}
```

## O que o instalador detecta / o wizard detecta

```
greenfield    → gera operator-profile.yaml + templates do zero em <out>/docs/plans/execucao/
em-andamento  → arquivo já existe com conteúdo DIFERENTE do que seria gerado -> skip
                (reportado em "files_skipped_customized", nunca sobrescrito)
re-run        → conteúdo idêntico ao que já existe -> no_op:true (nada muda, nada quebra)
```

## O que é seguro rodar de novo

`generate_and_summary()` **nunca sobrescreve** um arquivo que já existe com conteúdo
diferente do que seria gerado (customização do usuário) — o campo
`files_skipped_customized` no JSON de retorno lista exatamente o que foi preservado.
Rodar duas vezes sem editar nada dá `no_op: true`. Para forçar regeneração de propósito
(descartando customização), use `--force`.

## Wiring manual

Nenhum — este kit não tem hooks nem toca `settings.local.json`. É uma ferramenta de
linha de comando pura.

## Prova / aceite (saída real, executada)

```bash
python wizard.py --self-test
```
```
self-test OK — 6 passos rodam, 1a run gera, 2a run = no-op, placeholders substituídos, validate pega
config vazia, --interview/--answers sem NotImplementedError, skip-exists preserva edição, --force sobrescreve
```
<!-- executado: 2026-07-11 · exit=0 -->

Prova do `--interview` (schema real impresso, não inventado):
```bash
python wizard.py --interview
```
```json
{
  "questions": [
    {
      "id": "project_name",
      "prompt": "Qual o nome do projeto/agente?",
      "type": "string",
      "default": "agente-teste"
    },
    {
      "id": "templates",
      "prompt": "Quais templates instanciar? (lista dentre os disponíveis)",
      "type": "choice",
      "options": ["00-LEIA-PRIMEIRO", "00-PROCESSES", "00-STATE", "00-VISION"],
      "default": ["00-LEIA-PRIMEIRO", "00-STATE", "00-VISION", "00-PROCESSES"]
    }
  ]
}
```
<!-- executado: 2026-07-11 · exit=0 -->

## Desfazer

```
- Plugin: /plugin uninstall agent-framework-wizard@house-party-protocol
- Cópia: remover a pasta agent-framework-wizard/ do projeto
- Scaffold gerado: remover manualmente operator-profile.yaml + docs/plans/execucao/*.md
  do projeto onde o wizard rodou (não há wiring/settings para desfazer)
```
