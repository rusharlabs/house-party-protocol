---
name: health-check
description: Sonda uma lista config-driven de serviços (HTTP ou comando local) e grava um cache JSON que outra ferramenta (ex.: statusline) pode ler sem tocar rede — nunca no próprio caminho quente, só gera o cache.
---

> **Auto-Trigger:** Ao configurar monitoramento de saúde de serviços de um projeto, ou quando o usuário pede "verifica se os serviços estão no ar", "health check", "sonda de saúde".
> **Keywords:** "health check", "saude dos servicos", "sonda", "probe", "servicos no ar", "status dos servicos", "monitoramento", "health probe"
> **Prioridade:** MÉDIA
> **Tools:** Bash, Read

## Quando NÃO Ativar
- Verificação de UM endpoint pontual e único — use `curl`/`urllib` direto, sem o overhead de configurar `health.probes`.
- Quando o "health" a verificar é sobre DADO (uma tabela populada, um job que rodou), não sobre SERVIÇO no ar — health de serviço ≠ health de dado; este script só prova que o processo responde, não que os dados dentro dele estão corretos.

## Contrato

**ENTRADA:** `health.probes` (lista de `{name, type: http|cmd, target}`) do `operator-profile.yaml`.

**SAÍDA:** cache JSON em `paths.health_cache` (default `.claude/health-cache.json`) + resumo impresso.

**EXIT CODES:**

| Exit | Significado |
|---|---|
| 0 | sempre — o connector nunca quebra o fluxo do chamador, mesmo com serviços DOWN |

**ESTADO QUE TOCA:**

| Recurso | Lê/Escreve | Propósito |
|---|---|---|
| `operator-profile.yaml` (`health.probes`, `paths.health_cache`) | Lê | config das sondas |
| endpoint HTTP / comando local | Lê (read-only) | sonda de fato |
| `paths.health_cache` | Escreve | cache que outra ferramenta (ex.: `statusline.py`) lê sem rede |

## Processo
1. **Declare as sondas** no profile: `type: http` (GET via `urllib`, nunca `curl`/`wget` — deny-list) ou `type: cmd` (comando shell do profile, confiável).
2. **Rode o probe** — sob demanda, no `SessionStart`, ou via cron:
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/health_probe.py
   ```
3. **Consumidores** (ex.: `statusline.py`, segmento `health`) leem SÓ o cache gerado — nunca chamam rede no caminho quente. O segmento `health` mostra o detalhe por-serviço (`api:OK db:DOWN`) até 6 serviços; acima disso degrada para o agregado (`⚕up/tot`).

## Exemplos executados

```console
$ python scripts/health_probe.py
⚕ 1/2 UP (DOWN: servico-down)
```
<!-- executado: 2026-07-10 · exit=0 -->

```console
$ python scripts/health_probe.py --json
{
  "ts": "2026-07-10 21:34 BRT",
  "health": {"services_online": 1, "services_total": 2},
  "services": {
    "servico-ok": {"online": true, "type": "cmd", "target": "python -c \"import sys; sys.exit(0)\""},
    "servico-down": {"online": false, "type": "cmd", "target": "python -c \"import sys; sys.exit(1)\""}
  }
}
```
<!-- executado: 2026-07-10 · exit=0 -->

```console
$ python scripts/health_probe.py --quiet
```
(sem output — `--quiet` suprime o resumo mesmo com serviços DOWN, útil p/ cron que só quer o cache)
<!-- executado: 2026-07-10 · exit=0 -->

```console
$ python statusline/statusline.py --statusline
servico-ok:OK servico-down:DOWN
```
(o mesmo cache acima, lido pelo segmento `health` da statusline — detalhe por-serviço, critério de aceite do kit)
<!-- executado: 2026-07-10 · exit=0 -->

## Prova

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/health_probe.py --self-test
python ${CLAUDE_PLUGIN_ROOT}/statusline/statusline.py --self-test
```
