---
name: gotcha-memory
description: Loop de aprendizado operacional — registra falhas de comandos, detecta recorrência e injeta a lição como preâmbulo antes da próxima execução da mesma tarefa. Use para consultar/seedar/depurar a memória de gotchas do projeto.
---

> **Auto-Trigger:** Quando o usuário pergunta "por que isso falha sempre?", "o que já aprendemos sobre essa tarefa?", quer seedar regras curated, ou quer inspecionar/limpar a memória de falhas do projeto.
> **Keywords:** "gotcha", "gotchas", "falha recorrente", "erro recorrente", "lição aprendida", "memória de falhas", "preâmbulo", "curated", "seed de regras", "aprendizado operacional"
> **Prioridade:** MÉDIA
> **Tools:** Bash, Read

## Quando NÃO Ativar
- Depuração de UMA falha pontual e nova — este kit trata RECORRÊNCIA (>= N falhas iguais numa janela); para a primeira ocorrência, debugue normal.
- Gestão de memória conversacional/semântica (contexto de sessão, RAG) — este kit é memória de FALHAS DE EXECUÇÃO, não de conhecimento.

## Contrato

**ENTRADA:** eventos de falha de Bash (gravados automaticamente pelo hook `gotcha_postflight.py`) + lições curated suas (seed YAML/JSONL). Config em `gotchas.*`/`paths.gotcha_store` do `operator-profile.yaml`.

**SAÍDA:** `failures.jsonl` + `curated.jsonl` no store (default `.claude/gotchas/`) e um preâmbulo "⚠️ GOTCHAS" no stderr do preflight quando há lição que casa com a tarefa.

**EXIT CODES:**

| Exit | Significado |
|---|---|
| 0 | sempre (hooks e CLI) — o loop de aprendizado nunca quebra o fluxo do chamador |
| 1 | só no `--self-test` quando uma asserção falha |

**ESTADO QUE TOCA:**

| Recurso | Lê/Escreve | Propósito |
|---|---|---|
| `operator-profile.yaml` (`gotchas.*`, `paths.gotcha_store`) | Lê | config (janela, min_count, top, store) |
| `<store>/failures.jsonl` | Escreve (append) | eventos de falha classificados por família |
| `<store>/curated.jsonl` | Lê/Escreve (append idempotente) | suas regras always-on |

## Processo
1. **Instale os hooks** (via plugin ou wire manual — ver README): `PreToolUse Bash → gotcha_preflight.py` e `PostToolUse Bash → gotcha_postflight.py`, ambos `timeout: 30`, WARN-only.
2. **Seede suas regras** (opcional, idempotente):
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/_lib/gotchas_memory.py" --seed curated.seed.example.yaml
   ```
3. **Consulte o que o sistema aprendeu** para uma tarefa:
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/_lib/gotchas_memory.py" --preamble "rodar o deploy do site"
   ```
4. **Veja o loop inteiro funcionando** (demo com store temporário, zero efeito no projeto):
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/_lib/gotchas_memory.py"
   ```

## Exemplos executados

Os três abaixo foram rodados de verdade (2026-09-19) contra um store temporário via
`GOTCHA_STORE_DIR` — zero efeito no projeto. A saída é a real, com o caminho do store
abreviado para `<store>`.

**1 · Seedar as regras curated (primeira vez):**

```
$ GOTCHA_STORE_DIR=<store> python "${CLAUDE_PLUGIN_ROOT}/_lib/gotchas_memory.py" --seed curated.seed.example.yaml
Seedados 5 gotchas curated em <store>/curated.jsonl
$ echo $?
0
```
<!-- executado: 2026-09-19 · exit=0 -->

**2 · Seedar de novo o MESMO arquivo — a prova de idempotência:**

```
$ GOTCHA_STORE_DIR=<store> python "${CLAUDE_PLUGIN_ROOT}/_lib/gotchas_memory.py" --seed curated.seed.example.yaml
Seedados 0 gotchas curated em <store>/curated.jsonl
```
<!-- executado: 2026-09-19 · exit=0 -->

Zero, não cinco de novo: re-seedar não duplica. É isso que permite deixar o seed no
setup de um projeto e rodá-lo em toda sessão.

**3 · Consultar o que o sistema sabe sobre uma tarefa:**

```
$ GOTCHA_STORE_DIR=<store> python "${CLAUDE_PLUGIN_ROOT}/_lib/gotchas_memory.py" --preamble "rodar o deploy do site"
⚠️ GOTCHAS (evite repetir — aprendido de falhas anteriores):
  • [regra] Deploy/routing: verifique que o BACKEND trocou (rota exclusiva da versão nova + marca de build), não só o gate de auth ou o status do processo.
$ echo $?
0
```
<!-- executado: 2026-09-19 · exit=0 -->

A regra que apareceu é uma **curated** (seedada no exemplo 1) — casou por substring
com "deploy". Uma lição **aprendida** (de falhas recorrentes) apareceria na mesma lista
com o contador `[Nx]` na frente.

## Prova

```bash
python "${CLAUDE_PLUGIN_ROOT}/_lib/gotchas_memory.py" --self-test     # -> self-test OK ✓  · exit 0
python "${CLAUDE_PLUGIN_ROOT}/_lib/error_strategy.py" --self-test     # -> self-test OK    · exit 0
python "${CLAUDE_PLUGIN_ROOT}/hooks/gotcha_preflight.py" --self-test  # -> self-test OK
python "${CLAUDE_PLUGIN_ROOT}/hooks/gotcha_postflight.py" --self-test # -> self-test OK
```

Os quatro self-tests cobrem: classificação por família (com fronteira de palavra —
`ENOTFOUND` isolado é rede, `ModuleNotFoundError` é dependência), recorrência que vira
gotcha após `min_count` falhas na janela, idempotência do seed, e a detecção
conservadora dos hooks (ambíguo = não-falha).

**Critério de sucesso operacional:** após 3 falhas iguais registradas em < 24h,
`--preamble "<mesma task>"` devolve preâmbulo não-vazio com `[3x]`.

## Falhas conhecidas / limites
- Detecção de falha é CONSERVADORA: só exit-code != 0, `is_error: true` ou campo `error` não-vazio contam. Falha "silenciosa" (exit 0 com output errado) não é capturada — por design (não inventa falha).
- Cobre só a tool Bash (matcher dos hooks). Outras tools exigiriam novos matchers.
- Seed em YAML exige PyYAML; sem PyYAML, use seed `.jsonl` (stdlib).
