# GateGuard — Forçar fatos ANTES do 1º Edit / destructive Bash

> **Auto-Trigger:** Antes do PRIMEIRO Edit/Write num arquivo já existente; antes de QUALQUER Bash destrutivo (rm, rm -rf, DROP, TRUNCATE, git push --force, git clean -fd, mv/rename de path crítico).
> **Keywords:** "gateguard", "antes do 1", "primeiro edit", "antes de editar", "rm", "rm -rf", "DROP", "TRUNCATE", "force-push", "force push", "git clean", "rollback", "destructive", "importadores", "schema", "blast radius", "quem usa", "quem importa"
> **Prioridade:** CRÍTICA
> **Versão:** 1.0.0 (generalizada para o operator-kit)
> **Origem:** destilado como ENFORCEMENT acionável de `learned-corrections.md` LC-3 (grep/ls antes de criar/classificar) + doutrina de proteção de código-fonte vivo. Universal (qualquer LLM que use este kit).

---

## Princípio

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   NÃO TOQUE NO ARQUIVO ATÉ SABER O QUE QUEBRA SE VOCÊ ERRAR.                 ║
║                                                                              ║
║   LC-3 já diz "grep/ls antes de criar/classificar". GateGuard estende:      ║
║   grep/ls TAMBÉM antes do 1º EDIT e antes de TODA ação destrutiva.          ║
║                                                                              ║
║   O fato (importadores · schema · rollback) vem ANTES da ação. Sempre.       ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

GateGuard é o portão (gate) que transforma a lição reativa do LC-3 e de qualquer doutrina de
proteção de código-fonte vivo num checklist PRÉ-AÇÃO obrigatório. Não substitui nenhuma das
duas — as torna acionáveis no momento exato em que o dano aconteceria.

---

## GATE 1 · Antes do PRIMEIRO Edit num arquivo

Antes do 1º `Edit`/`Write` num arquivo que **já existe**, levantar 3 fatos (grep + ls/Glob):

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  1. IMPORTADORES / CONSUMIDORES — quem usa este arquivo?                      │
│     └─ grep do nome do módulo/função/símbolo no repo                          │
│     └─ Python:  grep -rn "import <modulo>\|from <modulo>" .                   │
│     └─ JS/TS:   grep -rn "require('<path>')\|from '<path>'" .                  │
│     └─ Config/rules/.md: grep do nome do arquivo (quem referencia?)           │
│                                                                              │
│  2. SCHEMA / CONTRATO — qual a forma que outros esperam?                      │
│     └─ Assinatura de função, chaves de JSON/YAML, colunas de tabela,          │
│        header de rule, formato de saída que consumidores parseiam.            │
│     └─ Mudar a FORMA sem checar consumidores = quebra silenciosa.             │
│                                                                              │
│  3. ROLLBACK — como desfaço se der errado?                                    │
│     └─ Arquivo rastreado por git? (`git status` / `git ls-files <path>`)      │
│        → SIM: rollback = `git checkout -- <path>`. Pode editar.               │
│        → NÃO (gitignored/novo): edição não-trivial exige cópia/backup         │
│          ANTES, ou declarar explicitamente "sem rede de segurança".          │
└──────────────────────────────────────────────────────────────────────────────┘
```

Edit aditivo trivial em arquivo git-tracked (ex.: acrescentar 1 linha a um `.md`/rule)
= GATE 1 satisfeito pelo próprio git (rollback garantido). O peso do gate é
**proporcional ao blast radius**: quanto mais consumidores, mais grep antes.

### Exceções (GATE 1 não se aplica)
- Arquivo **NOVO** (sua criação) → não há importadores prévios; LC-3 (grep antes de criar) cobre.
- Scratchpad / arquivo temporário descartável.

---

## GATE 2 · Antes de Bash destrutivo (rm / DROP / force-push / clean)

Para `rm`, `rm -rf`, `DROP TABLE`, `TRUNCATE`, `git push --force`, `git clean -fd`,
`mv`/rename de path crítico — **e os "aparentemente-seguros-mas-destrutivos"** (rebuilds que
descartam incrementos · recreate forçado de container que apaga estado efêmero · escrita em
índices/caches regeneráveis mas caros de recomputar) — **EXIGIR antes de executar**:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  A. ROLLBACK ESCRITO — frase explícita de como reverter ESTA ação            │
│     └─ Ex.: "snapshot em backups/<x>-$(date) antes do rm; restauro           │
│        com cp -r de volta" · "DROP só após dump/export em <path>".            │
│     └─ Sem rollback escrito = NÃO executar. (SNAPSHOT → ROLLBACK → VERIFY     │
│        é a forma longa deste gate.)                                          │
│                                                                              │
│  B. AUTORIZAÇÃO DO OPERADOR CITADA — onde/quando foi autorizado ISTO         │
│     └─ Citar a fala/sessão/gate. Autorização de execução ampla (LC-2) NÃO    │
│        autoriza destrutivo em path crítico sem rollback. Áreas sensíveis     │
│        (financeiro/contratos/DELETE/cron/engine vivo) = autonomy level 0/1   │
│        (`partial-autonomy-slider`): propor, não auto-executar.               │
│                                                                              │
│  C. VERIFY pós-ação — comando que prova que o sistema sobreviveu             │
│     └─ Ex.: curl no /health do seu serviço · re-grep do que ficou.           │
└──────────────────────────────────────────────────────────────────────────────┘
```

### PROIBIDO incondicionalmente (proteção de código-fonte vivo)
```
✗ rm -rf em paths contendo `engine`, `src`, `apps` (código-fonte vivo do produto)
✗ git clean -fd no repo de produção
✗ mover/renomear pastas de aplicação/engine em uso
✗ rm/DROP/force-push disparado por BUSCA de string ambígua (um nome pode ter múltiplos
   sentidos no seu projeto — processo, volume, pasta legada). NUNCA deletar por match de string
   sem confirmar QUAL dos sentidos você está mirando.
✗ Tocar código-fonte vivo, `.env`, ou infraestrutura de produção a partir de uma sessão de
   planejamento (read-only).
```
Nada acima é desbloqueado por rollback — é piso duro. GATE 2 (A/B/C) vale para o
destrutivo *permitido*; o proibido continua proibido.

---

## Fluxo (decisão em uma olhada)

```
Vou Editar arquivo existente? ──► GATE 1 (importadores · schema · rollback)
Vou rodar Bash destrutivo?    ──► path crítico/proibido? ──► PARE (piso duro)
                                   senão ──► GATE 2 (rollback escrito + autorização + verify)
Vou CRIAR arquivo / classificar pendente? ──► LC-3 (grep+ls antes)
```

---

## Aplicação como hook (gate-humano — NÃO ativar sozinho)

> ⚠️ Ligar isto como hook **PreToolUse** mexe em `settings.json` → **gate-humano**
> (edições em settings/hooks costumam exigir revisão humana antes de aplicar).
> Esta rule é a doutrina; o wiring abaixo é um **diff SUGERIDO** para o operador aplicar.

Diff sugerido (revisão humana antes de aplicar — `timeout: 30`, exit 0=ok / 1=warn / 2=block).
Recomendação: começar em **WARN (exit 1)**, nunca block, até validar zero falso-positivo:

```jsonc
// settings.json → hooks → PreToolUse (ADITIVO; matcher cobre Edit/Write/Bash)
{
  "matcher": "Edit|Write|Bash",
  "hooks": [
    {
      "type": "command",
      "command": "python3 .claude/hooks/gateguard.py",
      "timeout": 30
    }
  ]
}
```

Esboço do hook (a ser criado pelo operador, fora do escopo desta rule):
- Lê o tool input do stdin (JSON).
- Edit/Write em arquivo existente sem grep recente na sessão → injeta lembrete GATE 1 (WARN).
- Bash com `rm -rf`/`DROP`/`--force`/`git clean` → exige rollback+autorização no contexto;
  match de path proibido (`engine`/`src`/`apps`) → BLOCK (exit 2).

---

## Liga-se a

| Regra | Relação |
|-------|---------|
| `learned-corrections.md` LC-3 | GateGuard é o ENFORCEMENT pré-ação do LC-3 (grep antes de criar/classificar) estendido ao 1º Edit e ao destrutivo. |
| `learned-corrections.md` LC-1 | O VERIFY pós-ação (curl /health) prova o estado ao vivo, não assume. |
| `partial-autonomy-slider.md` | Destrutivo em área sensível = level 0/1 (propor, não auto). |

---

*GateGuard v1.0.0 — fato antes da ação. Aplica a qualquer LLM que use este kit.*
