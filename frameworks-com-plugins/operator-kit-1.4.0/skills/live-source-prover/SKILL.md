---
name: live-source-prover
description: Antes de citar QUALQUER número/status/métrica, re-deriva na fonte viva e rotula "live @ HH:MM + fonte" — nunca repete dado stale
---

> **Auto-Trigger:** Antes de afirmar qualquer contagem, métrica, health, status de deploy/rota, ou completude
> **Keywords:** "quantos", "quantas", "contagem", "status", "health", "métrica", "número", "está no ar", "stale", "onde estamos", "% completo"
> **Prioridade:** ALTA
> **Tools:** Bash, Read, Grep
> **Doutrina relacionada:** `rules/learned-corrections.md` (LC-1, mecanizada em skill), `rules/epistemic-standards.md` (separar fato de recomendação).

# live-source-prover — verificar AO VIVO antes de citar (LC-1)

O trato #1: **trate todo dado herdado de sessão/doc/snapshot/outro-agente como SUSPEITO até confirmar na fonte viva.** Materializa LC-1 como skill portátil.

## Contrato

**ENTRADA:** a afirmação a citar (número/status/métrica) + o domínio dela (contagem/operacional/health/deploy/plano) + `sources.yaml` do projeto.

**SAÍDA:** o valor re-derivado + rótulo `live @ HH:MM · fonte: <comando/endpoint>` colado junto à afirmação.

**EXIT CODES** (o comando de re-derivação do domínio, seja `curl`/`urllib`/`git log`/`find`):

| Exit | Significado |
|---|---|
| 0 | fonte respondeu — valor confirmado, pode citar com o rótulo |
| ≠0 | fonte não respondeu/indisponível — NÃO cite o número velho; declare "não verificado" |

**ESTADO QUE TOCA:**

| Recurso | Lê/Escreve | Propósito |
|---|---|---|
| `sources.yaml` (ao lado desta skill) | Lê | comando de re-derivação por domínio |
| endpoint/disco/git da fonte viva | Lê (read-only) | o valor real |

## Processo
1. **Antes de citar** um número/status, identifique o domínio (contagem de arquivos, operacional, health de serviço, deploy/rota, completude de plano).
2. **Re-derive AO VIVO** rodando o comando do `sources.yaml` do projeto (veja `sources.example.yaml` ao lado):
   - contagem → `find/grep/ls`; serviço → `curl`/`urllib` num endpoint; deploy → curl numa **rota EXCLUSIVA do novo** + marca de build (não só o gate de auth); plano → `git log --grep` + disco (ver `audit_plan.py`).
3. **Cole o output** e **rotule** o valor: `live @ HH:MM · fonte: <comando/endpoint>`.
4. **TTL de frescor:** dado mais velho que `verificacao.fonte_suspeita_ttl_dias` (default 7) = re-verificar, não repetir.
5. **Sem `sources.yaml`** definido p/ aquele domínio → **WARN** ("não verificado"), nunca invente o comando nem o número.

> Caso deploy/routing: confirme que o **backend** trocou (rota/conteúdo exclusivo do novo), não só o status do processo nem o gate de auth. Cadeia de proxy/tunnel: confirme CADA hop.

## Quando NÃO Ativar
- Quando o número já foi verificado live **nesta mesma resposta**.
- Valores puramente ilustrativos/hipotéticos explicitamente marcados como tal.
- A pergunta é sobre plano vs realidade especificamente (checkboxes/deliverables) → use `doc-consolidator-dedup`'s extrator (`audit_plan.py`), que já é este princípio aplicado a planos.

## Exemplos executados

```console
$ git log --oneline -1
b2ea2af0 feat(P0.4): seed_pessoas.py — tabela _PESSOAS.md vira registry (52 pessoas + 28 links)
```
<!-- executado: 2026-07-10 · exit=0 -->
(domínio "completude de plano" — o commit real, não o que a sessão anterior dizia.)

```console
$ python -c "
import urllib.request
with urllib.request.urlopen('http://127.0.0.1:8099/health', timeout=3) as r:
    print(r.status, r.read()[:80])
"
200 b'{"status": "ok", "service": "example-api"}'
```
<!-- executado: 2026-07-10 · exit=0 -->
(domínio "health de serviço" — servidor local de exemplo na porta 8099; rotular:
`live @ 15:03 · fonte: python -c urllib 127.0.0.1:8099/health`. Troque a porta pelo
endpoint real do seu `sources.yaml`.)

```console
$ python -c "
import urllib.request
try:
    urllib.request.urlopen('http://127.0.0.1:1/health', timeout=2)
except Exception as e:
    print('ERRO:', type(e).__name__)
    raise SystemExit(1)
"
ERRO: URLError
```
<!-- executado: 2026-07-10 · exit=1 -->
(fonte indisponível — o passo 5 manda declarar "não verificado", NUNCA repetir um valor velho porque a fonte caiu.)

## Prova

```bash
python -c "import subprocess,sys; sys.exit(subprocess.run(['git','log','--oneline','-1'], capture_output=True).returncode)"
```
