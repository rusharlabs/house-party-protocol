---
name: agent-framework-scaffold
description: Roda o wizard de 6 passos que gera o esqueleto de um projeto novo (operator-profile.yaml + templates do TEMPLATE-SET escolhidos) — método genérico (check ambiente → configurar → validar → gerar), reescrito do zero.
---

> **Auto-Trigger:** Quando o usuário quer começar um projeto novo com a estrutura do operator-kit/continuity-kit, ou pede "monta o esqueleto", "cria o profile inicial", "wizard de setup".
> **Keywords:** "scaffold", "wizard", "projeto novo", "esqueleto", "operator-profile inicial", "setup wizard", "montar estrutura"
> **Prioridade:** MÉDIA
> **Tools:** Bash, Read, Write

## Quando NÃO Ativar
- Projeto já tem `operator-profile.yaml` — rode o wizard só se quiser regenerar do zero (ele não faz merge, sobrescreve os arquivos que gera).
- Precisa reproduzir alguma automação COMERCIAL de terceiro (ex.: instalador de produto pago) — este wizard é MÉTODO genérico de scaffold, não clone de nenhuma ferramenta específica.

## Contrato

**ENTRADA:** `--out <dir>` (destino) + `--project-name` (opcional, default "agente-teste" em `--demo`).

**SAÍDA:** `operator-profile.yaml` + templates do TEMPLATE-SET escolhidos, instanciados com `{{project_name}}` substituído, em `<out>/docs/plans/execucao/`.

**EXIT CODES:**

| Exit | Significado |
|---|---|
| 0 | scaffold gerado (ou já estava idêntico — no-op) |
| 2 | pré-requisito ausente (Python <3.9, git ausente, PyYAML ausente) ou config inválida |

**ESTADO QUE TOCA:**

| Recurso | Lê/Escreve | Propósito |
|---|---|---|
| `templates/*.template.md` (bundled) | Lê | fonte dos templates a instanciar |
| `<out>/operator-profile.yaml` | Escreve | perfil gerado (escada R0-R4 + nome do projeto) |
| `<out>/docs/plans/execucao/*.md` | Escreve | templates instanciados |

## Processo
1. **Rode o wizard** (modo `--demo` = não-interativo, defaults sensatos):
   ```bash
   python wizard.py --demo --out /caminho/do/projeto-novo
   ```
2. **Confirme limpeza de IP/PII** no output (deve ser sempre exit 0 — o scaffold é 100% genérico):
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/../instaladores/kit-forge/ip_pii_linter.py /caminho/do/projeto-novo
   ```
3. **Re-rodar é seguro** — mesmo conteúdo = no-op, nunca duplica nem corrompe.

## Exemplos executados

```console
$ python wizard.py --demo --out /tmp/agente-teste
[1/6] check_python — Python 3.14.3
[2/6] check_git — git version 2.52.0.windows.1
[3/6] check_deps — PyYAML disponível
[4/6] configure
[5/6] validate
[6/6] generate_and_summary
{"project_name": "agente-teste", "files_written": ["operator-profile.yaml", "docs\\plans\\execucao\\00-LEIA-PRIMEIRO.md", "docs\\plans\\execucao\\00-STATE.md", "docs\\plans\\execucao\\00-VISION.md", "docs\\plans\\execucao\\00-PROCESSES.md"], "no_op": false}
```
<!-- executado: 2026-07-10 · exit=0 -->

```console
$ python wizard.py --demo --out /tmp/agente-teste
{"project_name": "agente-teste", "files_written": [...], "no_op": true}
```
<!-- executado: 2026-07-10 · exit=0 -->
(2ª rodada com o mesmo destino = no-op — sha256 do diretório idêntico, nada reescrito.)

```console
$ python wizard.py --out /tmp/sem-demo
uso: wizard.py --demo --out <dir>
```
<!-- executado: 2026-07-10 · exit=2 -->
(sem `--demo`, o wizard recusa — modo interativo real não está implementado ainda, e o script é honesto sobre isso em vez de fingir.)

## Prova

```bash
python wizard.py --self-test
```
