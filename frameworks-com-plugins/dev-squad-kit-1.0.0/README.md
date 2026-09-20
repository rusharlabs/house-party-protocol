# Dev Squad Kit

## 1. O que é

Um squad de 12 agentes de papel via slash-command (`*master`, `*analyst`, `*architect`,
`*data-engineer`, `*dev`, `*devops`, `*pm`, `*po`, `*qa`, `*sm`, `*squad-creator`,
`*ux-design-expert`) — cada um com persona própria, comandos numerados e checklist de
colaboração com os outros — mais 3 skills de leitura/consolidação paralela token-safe
(`pp-discovery`, `pp-raiox`, `pp-consolidate`).

**O que este kit NÃO faz:** não inclui a árvore proprietária de tasks/templates/checklists
que os comandos `*create`, `*task`, `*workflow`, `*execute-checklist` esperam encontrar em
`.devsquad-core/{tasks,templates,checklists,data,utils,workflows}/`. Sem essa árvore, esses
comandos específicos vão falhar ou improvisar. Use os 12 agentes para persona, `*help`,
`*guide` e delegação de raciocínio entre papéis — ou construa/traga sua própria árvore de
tasks se quiser os comandos de criação de documento completos.

## 2. Pré-requisitos + APIs externas

| Requisito | Versão mínima | Obrigatório? |
|---|---|---|
| Python | 3.9 | só para o `skill_lint.py`/`kit_doctor.py` do instalador |

Serviços externos: **nenhum — stdlib only.** Os 12 agentes são arquivos `.md` de persona
(prompt), não código executável, e não chamam nenhuma API.

## 3. Instalar via plugin

```bash
/plugin marketplace add .
/plugin install dev-squad-kit@house-party-protocol
```

## 4. Instalar por cópia

```bash
cp -r dev-squad-kit <seu-projeto>/dev-squad-kit
cd <seu-projeto>
python dev-squad-kit/../instaladores/kit-forge/kit_doctor.py install dev-squad-kit --target . --human
python dev-squad-kit/../instaladores/kit-forge/kit_doctor.py install dev-squad-kit --target . --apply
```

## 5. O que o instalador detecta

```
greenfield    → copia os 12 comandos + 3 skills, nada mais a gerar (não há profile.yaml)
em-andamento  → se já existir commands/<nome>.md com o mesmo nome, reporta conflito, não sobrescreve
re-run        → cópia idempotente; nenhum estado externo pra perder
```

## 6. O que é seguro rodar de novo

Tudo. Não há profile customizável nem estado gerado — os comandos e skills são estáticos.
Rodar a instalação de novo apenas re-copia os mesmos arquivos.

## 7. Wiring manual

Nenhum. Este kit não tem hooks — só `commands/` e `skills/`, ambos auto-descobertos pelo
Claude Code via `.claude-plugin/plugin.json`.

## 8. Prova (saída real, executada)

```
$ python ../instaladores/kit-forge/tools/skill_lint.py --all skills --run-proofs

[FAIL] skills\pp-consolidate\SKILL.md
    FAIL L1d.quando_nao_ativar        seção '## Quando NÃO Ativar' ausente
    FAIL L2a.contrato_ausente         seção '## Contrato' ausente
    FAIL L3a.exemplos_min3            0 exemplo(s) executado(s) < 3
    FAIL L4a.prova_ausente            seção '## Prova' ausente
[FAIL] skills\pp-discovery\SKILL.md   (mesmos 4 achados)
[FAIL] skills\pp-raiox\SKILL.md       (mesmos 4 achados)
skill_lint: 0 pass · 0 warn · 3 fail (de 3)
```

**Honestidade de produto:** as 3 skills `pp-*` são metodologia de investigação (prosa
guiando como inventariar/ler um repo antes de mergulhar), não scripts com output
determinístico — por isso não têm `--self-test` nem seção `## Prova` no formato que o
`SKILL-CONTRACT.md` deste marketplace exige para skills-ferramenta. Elas ainda não foram
atualizadas pro contrato v1.0 formal (seção `## Contrato`, 3 exemplos executados). Funcionam
como guia de raciocínio; não têm prova mecânica de execução. Documentado aqui em vez de
escondido — decida se isso serve seu caso antes de instalar.

Os 12 agentes de persona não têm mecanismo de self-test (são prompt, não código) — a prova
possível é a leitura do `.md` em si, que define determinística e explicitamente comandos,
personas e regras de colaboração.

## 9. Desfazer

```
- Plugin: /plugin uninstall dev-squad-kit@house-party-protocol
- Cópia: remover a pasta dev-squad-kit/ do projeto (nenhum outro arquivo foi tocado)
```
