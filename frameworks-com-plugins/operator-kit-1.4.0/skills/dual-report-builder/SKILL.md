---
name: dual-report-builder
description: Gera DUAS versoes da mesma analise/relatorio — INTERNA (crua, falhas expostas, dark) e EXTERNA (premium, positiva, sem expor falhas, light) — em HTML self-contained com charts CSS-puro e print-friendly. A versao externa passa por gate de registro sobrio (frases banidas do profile). Use ao produzir relatorio/dashboard que tem audiencia dupla (time interno + cliente/stakeholder).
type: skill
---

> **Auto-Trigger:** Quando o usuario pede relatorio/dashboard que sera visto tanto pelo time interno quanto por cliente/stakeholder; quando menciona "versao interna e externa", "relatorio pra mostrar pro cliente", "dashboard interno", "duas versoes", "prestacao de contas", ou pede um report apos uma tarefa de geracao/auditoria em massa.
> **Keywords:** "relatorio dual", "versao interna", "versao externa", "interno e externo", "dashboard cliente", "dashboard interno", "duas versoes", "relatorio premium", "prestacao de contas", "report pro cliente", "antes/depois"
> **Prioridade:** MEDIA
> **Tools:** Read, Write, Glob, Grep
> **Doutrina relacionada:** `rules/agent-integrity.md` (a externa omite falha, nunca fabrica sucesso), `rules/learned-corrections.md` (LC-1: números rastreáveis).

## Quando NÃO Ativar

- Relatorio de audiencia UNICA (so interno OU so cliente) — gere uma versao so, sem o overhead das duas.
- Pedido de dado bruto/numero pontual ("quantos X?") — use `status_now.py` ou `delta_inventory.py` direto.
- Construir o motor visual/CSS do zero — o desenho fica a cargo da skill `frontend-design`; esta skill orquestra o PROCESSO das duas versoes, nao reimplementa layout.
- Envio ao cliente — esta skill PRODUZ os dois artefatos; o disparo externo e gate humano (aprovacao do operador), nunca automatico.

---

# dual-report-builder — Interna (crua) + Externa (premium) da MESMA analise

O CLAUDE.md exige, para relatorio de cliente: **versao interna (sem filtro, dados brutos)** + **versao externa (resultados positivos, sem expor falhas internas)**. Esta skill descreve o processo de produzir as DUAS a partir de uma unica analise — mesmos numeros-fonte, recortes diferentes — e de submeter a externa a um gate de registro sobrio antes de declarar pronta.

**Principio:** a analise (os fatos/numeros) e UMA. As duas versoes diferem no RECORTE e no TOM, nunca nos numeros. Nada de inventar dado positivo para a externa (AGENT-INTEGRITY). A externa OMITE falhas; nunca FABRICA sucesso.

## Contrato

**ENTRADA:** a analise unica (fatos/numeros rastreaveis, LC-1) + `report.*`/`paths.draft_dir` do `operator-profile.yaml`.

**SAÍDA:** 2 artefatos HTML self-contained — interna (completa, dark) em logs do projeto + externa (premium, light) em `paths.draft_dir` como RASCUNHO.

**EXIT CODES** (do gate de registro sobrio, passo 4 — a varredura de frases banidas):

| Exit | Significado |
|---|---|
| 0 | texto da externa limpo — nenhuma frase banida encontrada, pode declarar "pronta p/ revisao" |
| 1 | >=1 frase banida encontrada — reescrever o trecho e revarrer, NAO declarar pronta |

**ESTADO QUE TOCA:**

| Recurso | Lê/Escreve | Propósito |
|---|---|---|
| `operator-profile.yaml` (`report.*`, `paths.draft_dir`) | Lê | temas, frases banidas, destino do rascunho |
| logs do projeto (versao interna) | Escreve | relatorio completo, sem filtro |
| `paths.draft_dir` (versao externa) | Escreve | rascunho — envio e gate humano |

## Parametrizacao (lida do operator-profile.yaml)

Leia via o loader do kit (`_lib/profile_loader.get(profile, "report.X")`):

| Chave | Uso |
|-------|-----|
| `report.estilo_interno` (ex.: `dark`) | tema visual da versao interna |
| `report.estilo_externo` (ex.: `light`) | tema visual da versao externa (premium) |
| `report.frases_banidas` (lista) | termos PROIBIDOS na externa — gate de registro sobrio |
| `paths.draft_dir` | onde gravar a versao externa (rascunho, ate liberacao do operador) |
| `idioma` | idioma do conteudo (default pt-BR) |

Sem profile → defaults seguros: interna=dark, externa=light, frases_banidas=`[]` (gate vira no-op mas a estrutura dual continua), draft em `drafts/`.

## Pipeline

```
PASSO 0 — ESCOPO + FONTES
  -> Definir o que e o relatorio (cliente/projeto/janela) e a audiencia dupla.
  -> Reunir os numeros-fonte UMA vez. Cada numero rastreavel a uma fonte real (LC-1):
     contagens via delta_inventory.py, estado via status_now.py, metricas via MCP/arquivo.
     Numero sem fonte = NAO entra (nem na interna).

PASSO 1 — ANALISE UNICA (a verdade crua)
  -> Liste TUDO: o que foi bem, o que falhou, gargalos, dividas, riscos, gaps.
  -> Esta e a materia-prima das duas versoes.

PASSO 2 — VERSAO INTERNA (tema = report.estilo_interno)
  -> Tudo da analise, SEM filtro: falhas expostas, numeros crus, pendencias abertas,
     tabela antes/depois/delta (delta_inventory.py), proximos passos honestos.
  -> Audiencia: time/operador. Tom direto, plano (ver output-style direct-register).
  -> Gravar em logs/relatorio interno do projeto.

PASSO 3 — VERSAO EXTERNA (tema = report.estilo_externo, premium)
  -> Mesmos numeros-fonte; recorte nos RESULTADOS POSITIVOS e proximos passos.
  -> OMITIR falhas internas/gargalos/dividas (nao expor cozinha) — mas NUNCA inventar
     ganho que nao existe. Se nao houve resultado positivo real, dizer o que ESTA em
     andamento, sem floreio.
  -> Registro corporativo SOBRIO.
  -> Gravar em paths.draft_dir como RASCUNHO (envio = gate humano).

PASSO 4 — GATE DA EXTERNA (registro sobrio)
  -> Varrer o texto da externa contra report.frases_banidas (case-insensitive).
  -> Se encontrar QUALQUER frase banida -> reescrever o trecho e revarrer. So declarar
     a externa "pronta p/ revisao" quando passar limpa.
  -> Este gate e a aplicacao do registro sobrio que o CLAUDE.md exige.

PASSO 5 — ENTREGA
  -> Reportar os dois caminhos (interna + externa-rascunho) e que a externa AGUARDA
     liberacao do operador para envio. Nunca enviar direto.
```

## Padroes visuais (delegados a frontend-design)

Esta skill NAO reimplementa CSS. Ao montar o HTML, siga as regras de dashboard do CLAUDE.md (e acione `frontend-design` para o acabamento):

- HTML **self-contained** (sem libs JS externas; Google Fonts CDN ok).
- Charts em **CSS puro**: `conic-gradient` (pizza/gauge), barras por `width`, SVG gauge. **Sem Chart.js/D3.**
- **Interna = dark**, **externa = light/premium** (vindo do profile).
- **Print-friendly**: `@media print` em ambas.
- Tabela comparativa **antes/depois/delta** (preferencia registrada no profile) — alimentada por `delta_inventory.py`.

## Gate de registro sobrio (esboco do mecanismo)

A varredura de frases banidas reusa o profile, nao reimplementa config:

```python
import os, sys
from pathlib import Path
# ${CLAUDE_PLUGIN_ROOT} em modo plugin; senão sobe 2 níveis (skills/<nome>/ -> skills/ -> operator-kit/)
# FIX 2026-07-10: era parents[1] (resolvia para .../skills, off-by-one) — parents[2] e o correto.
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
_kit_root = Path(_plugin_root) if _plugin_root else Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_kit_root))
from _lib.profile_loader import load_profile, get

prof = load_profile()
banidas = [f.lower() for f in (get(prof, "report.frases_banidas", []) or [])]
texto_externo = "..."  # conteudo da versao externa
ofensas = [f for f in banidas if f and f in texto_externo.lower()]
# ofensas != [] -> reescrever os trechos e revarrer ANTES de declarar pronta.
```

## Checklist de saida

```
[ ] Numeros-fonte coletados UMA vez, cada um rastreavel (LC-1)?
[ ] Versao INTERNA expoe falhas/gargalos/dividas (tema interno do profile)?
[ ] Versao EXTERNA omite falhas SEM inventar sucesso (tema externo do profile)?
[ ] Tabela antes/depois/delta presente (delta_inventory.py)?
[ ] HTML self-contained, charts CSS-puro, print-friendly (via frontend-design)?
[ ] Externa varrida contra report.frases_banidas e passou limpa?
[ ] Externa gravada em draft_dir como RASCUNHO; envio sinalizado como gate humano?
```

## Exemplos executados

```console
$ python -c "
import os, sys
from pathlib import Path
_kit_root = Path(os.environ.get('CLAUDE_PLUGIN_ROOT') or Path.cwd())
sys.path.insert(0, str(_kit_root))
from _lib.profile_loader import load_profile, get
prof = load_profile()
print('kit_root aponta pro operator-kit?', (_kit_root / 'operator-profile.yaml').exists())
print('frases_banidas:', [f.lower() for f in (get(prof, 'report.frases_banidas', []) or [])])
"
kit_root aponta pro operator-kit? True
frases_banidas: ['consider it done', 'com certeza!', 'otima pergunta', 'risco']
```
<!-- executado: 2026-07-10 · exit=0 -->
(prova o fix do off-by-one: `parents[2]` resolve pro `operator-kit/` de verdade — `operator-profile.yaml` existe ali.)

```console
$ python -c "
banidas = ['consider it done', 'com certeza!', 'risco']
texto = 'O deploy foi tranquilo, consider it done, zero risco daqui pra frente.'
ofensas = [f for f in banidas if f in texto.lower()]
print('ofensas encontradas:', ofensas)
import sys; sys.exit(1 if ofensas else 0)
"
ofensas encontradas: ['consider it done', 'risco']
```
<!-- executado: 2026-07-10 · exit=1 -->
(passo 4 — gate BLOQUEIA: 2 frases banidas no rascunho da externa; reescrever e revarrer ANTES de declarar pronta.)

```console
$ python -c "
banidas = ['consider it done', 'com certeza!', 'risco']
texto = 'O deploy concluiu com os 3 checks passando; monitoramento segue ativo nas proximas 24h.'
ofensas = [f for f in banidas if f in texto.lower()]
print('ofensas encontradas:', ofensas)
import sys; sys.exit(1 if ofensas else 0)
"
ofensas encontradas: []
```
<!-- executado: 2026-07-10 · exit=0 -->
(mesmo texto reescrito em registro sobrio — gate passa limpo, pode declarar "pronta p/ revisao".)

## Prova

```bash
python -c "
banidas = ['risco']; texto = 'monitoramento ativo nas proximas 24h'
import sys; sys.exit(1 if any(b in texto.lower() for b in banidas) else 0)
"
```
