"""
gotchas_memory (portable) — loop de aprendizado operacional: a falha vira conhecimento.

Cópia versionada e DESPERSONALIZADA de `core/intelligence/gotchas_memory.py`
(repo-de-origem) para o kit distribuível `gotcha-memory`. Diferenças da origem:

  1. Import de `error_strategy` é do SIBLING `_lib/` (vendorizado), não de `core.*`.
  2. Store resolvido DINAMICAMENTE por chamada: profile (`paths.gotcha_store`)
     → env `GOTCHA_STORE_DIR` → `.claude/gotchas/` sob a cwd do projeto.
  3. O seed hardcoded de guardrails do dono-de-origem foi REMOVIDO (era
     conteúdo pessoal/PII — proibido em kit distribuível). No lugar:
     `seed_from_file(path)` lê lições curated de um YAML/JSONL SEU
     (ver `curated.seed.example.yaml` na raiz do kit).

PRINCÍPIO: quando uma tarefa falha, o evento é registrado e classificado (via
error_strategy). Quando o MESMO tipo de falha recorre >= N vezes numa janela de
tempo, vira um GOTCHA — uma lição ACIONÁVEL injetada como preâmbulo ANTES da
próxima execução da mesma tarefa, pra o agente/cron não repetir o erro.
Gotchas "curated" (seedados por você) são always-on quando a chave casa.

FLUXO:
    record_failure(task_key, erro)  ->  failures.jsonl  (append, classificado)
    recurring_gotchas()             ->  agrupa por (task_key, family); >=min_count na janela
    gotchas_for_task(task_key)      ->  curated(match) + recurring(match); top-N por severidade
    inject_preamble(task_key)       ->  string "⚠️ GOTCHAS" pra colar no prompt pré-task

I/O: só append/read em JSONL no store. stdlib only (+ error_strategy vendorizado;
PyYAML é OPCIONAL — apenas para seed em YAML e profile). Determinístico: `now` é
injetável (testes). NUNCA lança em uso normal: leitura de store ausente/corrompido
degrada pra lista vazia (honestidade > crash).

v1.0.0 — 2026-07-11 (kit gotcha-memory · extração standalone)
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from error_strategy import select_strategy  # noqa: E402  (sibling vendorizado)

try:
    import profile_loader  # sibling — config opcional via operator-profile.yaml
except ImportError:  # degrade: sem profile, defaults
    profile_loader = None  # type: ignore[assignment]

# Severidade base por família de erro (0-100). Famílias do error_strategy.
_FAMILY_SEVERITY = {
    "fatal": 100,
    # Why: as familias instrument e lock nasceram no error_strategy e o consumidor nao as
    # conhecia — caiam no default 35 e na licao de "unknown". instrument e a mais cara: o
    # numero mente e ninguem repete.
    "instrument": 85,
    "lock": 50,
    "dependency": 75,
    "state": 70,
    "config": 65,
    "ratelimit": 55,
    "transient": 40,
    "unknown": 35,
    "manual": 90,  # curated do dono = peso alto by design
}

# Lição preventiva derivada da família (o "como evitar"). Fundida com a estratégia.
_FAMILY_PREVENTION = {
    "transient": "Falha transitória recorrente: aplicar retry com backoff/jitter antes de escalar; checar saúde do upstream.",
    "ratelimit": "Rate-limit recorrente: throttle preemptivo (parar em ~80% do teto) + respeitar Retry-After.",
    "dependency": "Dependência faltando/quebrada: verificar que o serviço/módulo está VIVO antes de chamar; não assumir.",
    "state": "Estado inconsistente recorrente: rollback + re-sync antes de re-tentar; não operar sobre estado sujo.",
    "config": "Config/env ausente: validar env no boot (fail-fast); não rodar com credencial/porta faltando.",
    "fatal": "Erro fatal recorrente: ESCALAR ao humano — não re-tentar cego; capturar a causa raiz.",
    "instrument": "O instrumento respondeu e o número não mede o que parece: NÃO repita o comando — rode um controle conhecido-bom e troque a régua.",
    "lock": "Outro processo segura o recurso (lock/index): esperar ou identificar o dono — nunca remover a trava sem provar que o dono morreu.",
    "unknown": "Falha recorrente não classificada: investigar causa raiz manualmente antes de re-tentar.",
}

_STRATEGY_HINT = {
    "retry": "→ retry",
    "rollback_and_retry": "→ rollback+retry",
    "skip": "→ skip (não-crítico)",
    "escalate": "→ ESCALAR ao humano",
    "recovery_workflow": "→ workflow de recuperação",
    "remeasure": "→ REMEDIR com outro instrumento (não repita o comando)",
}


@dataclass(frozen=True)
class Gotcha:
    """Uma lição acionável aprendida (recurring) ou imposta (curated)."""
    key: str            # task_key (recurring) ou tag/substring (curated; "*" = always-on)
    family: str
    prevention: str
    severity: int       # 0-100
    source: str         # "recurring" | "curated"
    count: int = 0      # quantas falhas na janela (0 p/ curated)
    strategy: str = ""
    first_seen: float = 0.0
    last_seen: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "family": self.family, "prevention": self.prevention,
            "severity": self.severity, "source": self.source, "count": self.count,
            "strategy": self.strategy, "first_seen": self.first_seen, "last_seen": self.last_seen,
        }


# ─────────────────────────── config / store ───────────────────────────

def config() -> dict[str, Any]:
    """Config efetiva do kit: profile (`gotchas.*`) por cima dos defaults. Nunca lança."""
    cfg: dict[str, Any] = {"window_hours": 24.0, "min_count": 3, "top": 5, "store_dir": None, "seed_file": None}
    if profile_loader is not None:
        try:
            prof = profile_loader.load_profile()
            cfg["store_dir"] = profile_loader.get(prof, "paths.gotcha_store") or profile_loader.get(prof, "gotchas.store_dir")
            cfg["window_hours"] = float(profile_loader.get(prof, "gotchas.window_hours", cfg["window_hours"]))
            cfg["min_count"] = int(profile_loader.get(prof, "gotchas.min_count", cfg["min_count"]))
            cfg["top"] = int(profile_loader.get(prof, "gotchas.top", cfg["top"]))
            cfg["seed_file"] = profile_loader.get(prof, "gotchas.seed_file")
        except Exception:
            pass
    return cfg


def _store(store_dir: str | Path | None) -> Path:
    """Resolve o store: argumento > profile > env GOTCHA_STORE_DIR > .claude/gotchas/ na cwd."""
    if store_dir:
        return Path(store_dir)
    cfg_dir = config().get("store_dir")
    if cfg_dir:
        return Path(cfg_dir)
    env = os.environ.get("GOTCHA_STORE_DIR")
    if env:
        return Path(env)
    return Path.cwd() / ".claude" / "gotchas"


# ─────────────────────────── helpers internos ───────────────────────────

def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Lê JSONL. Arquivo ausente -> []. Linhas corrompidas são puladas (degrada, não crasha)."""
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue  # linha corrompida — pula
    except OSError:
        return []
    return out


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _matches(gotcha_key: str, task_key: str) -> bool:
    """Curated key casa com task_key se for '*' (always-on) ou substring (qualquer direção)."""
    gk, tk = (gotcha_key or "").lower().strip(), (task_key or "").lower().strip()
    if gk in ("*", ""):
        return True
    return gk in tk or tk in gk


def _severity(family: str, strategy: str) -> int:
    base = _FAMILY_SEVERITY.get(family, 35)
    if strategy == "escalate":
        base = max(base, 85)
    return base


def _prevention(family: str, strategy: str) -> str:
    base = _FAMILY_PREVENTION.get(family, _FAMILY_PREVENTION["unknown"])
    hint = _STRATEGY_HINT.get(strategy, "")
    return f"{base} {hint}".strip()


# ─────────────────────────── API pública ───────────────────────────

def record_failure(
    task_key: str,
    error_message: str,
    *,
    context: dict[str, Any] | None = None,
    attempt: int = 1,
    max_retries: int = 3,
    is_critical: bool = True,
    store_dir: str | Path | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Registra uma falha (classificada via error_strategy) em failures.jsonl. Retorna o evento."""
    ts = time.time() if now is None else now
    dec = select_strategy(error_message, attempt=attempt, max_retries=max_retries, is_critical=is_critical)
    event = {
        "task_key": str(task_key),
        "error": str(error_message or "")[:500],
        "family": dec.family,
        "strategy": dec.strategy,
        "terminal": dec.terminal,
        "context": context or {},
        "ts": ts,
    }
    _append_jsonl(_store(store_dir) / "failures.jsonl", event)
    return event


def rotate_failures(
    *,
    max_lines: int = 5000,
    keep_days: float = 45,
    store_dir: str | Path | None = None,
    now: float | None = None,
) -> dict[str, int]:
    """Rotaciona failures.jsonl: o excedente vai para failures.archive.jsonl.

    # Why: o append era sem teto (1,9 MB / 1.744 linhas em um mes) e o preflight rele o
    # arquivo INTEIRO a cada comando Bash — crescer o store e latencia em toda sessao.
    # keep_days=45 cobre a janela de revisao (30d) com folga; max_lines=5000 ~= 3 meses do
    # pior mes medido. Best-effort e idempotente: sem excedente, e no-op. Rewrite atomico
    # (tmp+replace) para nunca corromper o store se cair no meio.
    """
    store = _store(store_dir)
    failures_path = store / "failures.jsonl"
    events = _read_jsonl(failures_path)
    n = len(events)
    if n == 0:
        return {"kept": 0, "archived": 0}

    cutoff = (time.time() if now is None else now) - keep_days * 86400
    in_window = sum(1 for e in events if float(e.get("ts", 0) or 0) >= cutoff)
    # append-order == time-order (record_failure usa time.time()); mantem as trailing
    keep_count = min(in_window, max_lines)
    if keep_count >= n:
        return {"kept": n, "archived": 0}

    split = n - keep_count
    archived, kept = events[:split], events[split:]

    with (store / "failures.archive.jsonl").open("a", encoding="utf-8") as f:
        for e in archived:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    tmp = failures_path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for e in kept:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    tmp.replace(failures_path)

    return {"kept": len(kept), "archived": len(archived)}


def recurring_gotchas(
    *,
    window_hours: float = 24,
    min_count: int = 3,
    store_dir: str | Path | None = None,
    now: float | None = None,
) -> list[Gotcha]:
    """Agrupa falhas por (task_key, family) na janela; as que recorrem >= min_count viram Gotcha."""
    ts = time.time() if now is None else now
    cutoff = ts - window_hours * 3600
    events = _read_jsonl(_store(store_dir) / "failures.jsonl")
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for e in events:
        if float(e.get("ts", 0)) >= cutoff:
            groups.setdefault((e.get("task_key", ""), e.get("family", "unknown")), []).append(e)
    out: list[Gotcha] = []
    for (task_key, family), evs in groups.items():
        if len(evs) >= min_count:
            evs.sort(key=lambda x: float(x.get("ts", 0)))
            strat = evs[-1].get("strategy", "retry")
            out.append(Gotcha(
                key=task_key, family=family, prevention=_prevention(family, strat),
                severity=_severity(family, strat), source="recurring", count=len(evs),
                strategy=strat, first_seen=float(evs[0]["ts"]), last_seen=float(evs[-1]["ts"]),
            ))
    out.sort(key=lambda g: (g.severity, g.count), reverse=True)
    return out


def curated_gotchas(*, store_dir: str | Path | None = None) -> list[Gotcha]:
    """Lê os gotchas curated (always-on quando a chave casa; seedados por você)."""
    out: list[Gotcha] = []
    for c in _read_jsonl(_store(store_dir) / "curated.jsonl"):
        out.append(Gotcha(
            key=c.get("key", "*"), family=c.get("family", "manual"),
            prevention=c.get("prevention", ""), severity=int(c.get("severity", 90)),
            source="curated", strategy="curated",
        ))
    return out


def add_curated_gotcha(
    key: str,
    prevention: str,
    *,
    family: str = "manual",
    severity: int = 90,
    store_dir: str | Path | None = None,
) -> bool:
    """Adiciona um gotcha curated (idempotente por (key, prevention)). Retorna True se adicionou."""
    path = _store(store_dir) / "curated.jsonl"
    existing = _read_jsonl(path)
    for c in existing:
        if c.get("key") == key and c.get("prevention") == prevention:
            return False  # já existe — não duplica
    _append_jsonl(path, {"key": key, "prevention": prevention, "family": family, "severity": int(severity)})
    return True


def seed_from_file(seed_path: str | Path, *, store_dir: str | Path | None = None) -> int:
    """Seeda gotchas curated de um arquivo SEU (.yaml lista de {key, prevention, severity?, family?}
    ou .jsonl com os mesmos campos). Idempotente. Retorna nº adicionados. -1 se ilegível."""
    p = Path(seed_path)
    if not p.exists():
        return -1
    entries: list[dict[str, Any]] = []
    if p.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml  # PyYAML — opcional
        except ImportError:
            return -1
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception:
            return -1
        if isinstance(data, list):
            entries = [e for e in data if isinstance(e, dict)]
    else:  # JSONL
        entries = _read_jsonl(p)
    added = 0
    for e in entries:
        key, prevention = str(e.get("key", "")).strip(), str(e.get("prevention", "")).strip()
        if not key or not prevention:
            continue
        if add_curated_gotcha(key, prevention, family=str(e.get("family", "manual")),
                              severity=int(e.get("severity", 90)), store_dir=store_dir):
            added += 1
    return added


def gotchas_for_task(
    task_key: str,
    *,
    top: int = 5,
    window_hours: float = 24,
    min_count: int = 3,
    store_dir: str | Path | None = None,
    now: float | None = None,
) -> list[Gotcha]:
    """Gotchas relevantes p/ uma tarefa: curated(match) + recurring(match), top-N por severidade."""
    task_key = str(task_key)
    curated = [g for g in curated_gotchas(store_dir=store_dir) if _matches(g.key, task_key)]
    recurring = [
        g for g in recurring_gotchas(window_hours=window_hours, min_count=min_count, store_dir=store_dir, now=now)
        if _matches(g.key, task_key)
    ]
    combined = curated + recurring
    combined.sort(key=lambda g: (g.severity, g.count), reverse=True)
    return combined[:top]


def inject_preamble(
    task_key: str,
    *,
    top: int = 5,
    window_hours: float = 24,
    min_count: int = 3,
    store_dir: str | Path | None = None,
    now: float | None = None,
) -> str:
    """Renderiza os top-N gotchas como preâmbulo pra colar no prompt pré-task. '' se nenhum."""
    gs = gotchas_for_task(task_key, top=top, window_hours=window_hours, min_count=min_count, store_dir=store_dir, now=now)
    if not gs:
        return ""
    lines = ["⚠️ GOTCHAS (evite repetir — aprendido de falhas anteriores):"]
    for g in gs:
        tag = f"[{g.count}x]" if g.source == "recurring" else "[regra]"
        lines.append(f"  • {tag} {g.prevention}")
    return "\n".join(lines)


# ─────────────────────────── CLI / self-test / demo ───────────────────────────

def _demo() -> None:
    """Demo VISÍVEL: usa store temporário, simula 3 falhas, mostra o aprendizado."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        store = Path(d)
        print("═" * 70)
        print("DEMO gotcha-memory — o sistema aprendendo com a própria falha")
        print("═" * 70)
        add_curated_gotcha("deploy", "Verifique que o BACKEND trocou (rota exclusiva do novo), não só o gate de auth.", store_dir=store)
        print("\n[1] 1 gotcha curated adicionado (regra sua, always-on quando casa)\n")

        # Tarefa exemplo: um cron que bate rate-limit repetidamente
        t0 = 1_000_000.0
        ev: dict[str, Any] = {}
        for i in range(3):
            ev = record_failure(
                "cron:ingest",
                "upstream: overloaded (429 rate limit)",
                store_dir=store, now=t0 + i * 60,
            )
        print(f"[2] cron:ingest falhou 3x em 3min — classificado: family={ev['family']} strategy={ev['strategy']}")

        rec = recurring_gotchas(store_dir=store, now=t0 + 200)
        print(f"\n[3] recurring_gotchas detectou {len(rec)} padrão(ões):")
        for g in rec:
            print(f"    • [{g.count}x] family={g.family} sev={g.severity}: {g.prevention}")

        print("\n[4] PREÂMBULO injetado ANTES do próximo cron:ingest (o que o agente vê):")
        print("-" * 70)
        print(inject_preamble("cron:ingest", store_dir=store, now=t0 + 200))
        print("-" * 70)

        print("\n[5] PREÂMBULO numa tarefa de deploy (curated dispara por substring):")
        print("-" * 70)
        print(inject_preamble("subir o deploy do servico X", store_dir=store, now=t0 + 200))
        print("-" * 70)
        print("\nDEMO OK — falha→conhecimento→prevenção, em código, verificável.\n")


def _self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        store = Path(d)
        t0 = 5_000_000.0
        # 2 falhas NÃO viram gotcha; 3 viram
        record_failure("task:x", "ETIMEDOUT", store_dir=store, now=t0)
        record_failure("task:x", "ETIMEDOUT", store_dir=store, now=t0 + 10)
        assert recurring_gotchas(store_dir=store, now=t0 + 20, min_count=3) == [], "2 falhas não deveriam virar gotcha"
        record_failure("task:x", "ETIMEDOUT", store_dir=store, now=t0 + 20)
        rec = recurring_gotchas(store_dir=store, now=t0 + 30, min_count=3)
        assert len(rec) == 1 and rec[0].count == 3, "3 falhas deveriam virar 1 gotcha count=3"
        assert rec[0].family == "transient", f"esperava transient, veio {rec[0].family}"
        # Janela: falha velha fora da janela não conta
        assert recurring_gotchas(store_dir=store, now=t0 + 30 + 25 * 3600, window_hours=24, min_count=3) == [], "falhas fora da janela não contam"
        # Curated idempotente
        assert add_curated_gotcha("deploy", "cheque o backend", store_dir=store) is True
        assert add_curated_gotcha("deploy", "cheque o backend", store_dir=store) is False, "re-add deve ser idempotente"
        # Match curated por substring
        pre = inject_preamble("mexer no deploy do servico", store_dir=store, now=t0 + 30)
        assert "backend" in pre.lower(), "curated de deploy deveria disparar"
        # Seed de arquivo JSONL (stdlib) — idempotente
        seed = store / "seed.jsonl"
        seed.write_text(
            json.dumps({"key": "migracao", "prevention": "faça backup antes", "severity": 95}) + "\n",
            encoding="utf-8",
        )
        assert seed_from_file(seed, store_dir=store) == 1, "seed deveria adicionar 1"
        assert seed_from_file(seed, store_dir=store) == 0, "re-seed deve ser idempotente (0)"
        assert seed_from_file(store / "nao-existe.jsonl", store_dir=store) == -1, "arquivo ausente = -1"
        # Store ausente degrada pra vazio (não crasha)
        assert curated_gotchas(store_dir=store / "sub" / "que-nao-existe") == []
        print("self-test OK ✓")


if __name__ == "__main__":
    # Console Windows é cp1252 — força utf-8 pra não quebrar nos chars ⚠️/•/═/✓.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

    arg = sys.argv[1] if len(sys.argv) > 1 else "--demo"
    if arg in ("--self-test", "-t"):
        _self_test()
    elif arg == "--seed" and len(sys.argv) > 2:
        n = seed_from_file(sys.argv[2])
        print(f"Seedados {n} gotchas curated em {_store(None) / 'curated.jsonl'}" if n >= 0
              else f"seed ilegível/ausente: {sys.argv[2]} (YAML exige PyYAML; alternativa: .jsonl)")
    elif arg == "--preamble" and len(sys.argv) > 2:
        print(inject_preamble(" ".join(sys.argv[2:])) or "(nenhum gotcha p/ essa tarefa)")
    else:
        _demo()
