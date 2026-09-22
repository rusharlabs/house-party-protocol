#!/usr/bin/env python3
"""
statusline (health-kit) — barra de progresso viva no rodape do CLI/IDE, PORTATIL e COMPOSAVEL.

Copia derivada de operator-kit/statusline/statusline.py, com UMA diferenca: o
segmento `health` aqui mostra o detalhe POR-SERVICO ("api:OK db:DOWN"), nao so
o agregado — porque a saude de servicos e o produto inteiro deste kit, nao
"1 segmento entre 8" (ver seg_health). A barra e montada a partir de SEGMENTOS
configuraveis (statusline.segments no operator-profile.yaml); cada segmento e
best-effort e DEGRADA p/ vazio se a fonte nao existir (nunca trava).

Segmentos embutidos (todos opcionais, ordem definida pelo profile):
  progress  -> 🧠 <projeto> <pct>% ████░░   (checklist do tracker_doc/state_ssot)
  health    -> api:OK db:DOWN (ou ⚕<up>/<tot> acima de 6 servicos) — cache de health_probe.py
  tokens    -> <stdout de statusline.token_cmd>  (ex: "◔41% $63/100"; vazio = omite)
  autonomy  -> 🎚L<n>                         (statusline.autonomy_level 0-5; omite se null)
  donegate  -> ✅DoD / ❌DoD                  (cache em statusline.donegate_cache; omite se ausente)
  gates     -> gates:<n>                      (itens '- [ ]' abertos no paths.gate_sheet)
  commits   -> <n>c hoje                      (git, commits de hoje)
  branch    -> <branch>                       (git)

Default (sem statusline.segments): ["progress","health","commits","branch"].

⚠️ statusLine NAO vai no plugin.json (limite do CC) — use `scripts/wire_statusline.py`
   ou aponte manualmente o settings.json:
  "statusLine": { "type": "command", "command": "python health-kit/statusline/statusline.py --statusline", "padding": 0 }

Modos: --statusline · --panel · --self-test. stdlib + PyYAML (via loader). Nunca crasha no caminho statusline.
v1.0.0 — 2026-07-10 (health-kit · segmento 'health' com detalhe por-servico)
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # .../operator-kit
try:
    from _lib.profile_loader import load_profile, get, profile_path
except Exception:  # noqa: BLE001
    load_profile = None  # type: ignore[assignment]

    def get(_p, _k, default=None):  # type: ignore[misc]
        return default

    def profile_path(_s=None):  # type: ignore[misc]
        return None

_BRT = timezone(timedelta(hours=-3))
_DEF_STATE = "docs/plans/execution/00-STATE.md"
_LEGACY_STATE = "docs/plans/execucao/00-STATE.md"


# Why (rename of the generated names): the modules now write `docs/plans/execution/`. A repo
# scaffolded before that still has the Portuguese directory, and a reader that knows one spelling
# only either misses the state doc or reads nothing and says nothing. New name wins; the legacy is
# accepted for one version, with a single line on stderr; an explicit path from the profile is
# never rewritten.
def _resolve_state(rel: str, root: Path, quem: str) -> str:
    if rel != _DEF_STATE:
        return rel
    if (root / _DEF_STATE).exists():
        return _DEF_STATE
    if (root / _LEGACY_STATE).exists():
        print(f"[{quem}] deprecated: read '{_LEGACY_STATE}'; rename it to '{_DEF_STATE}' — "
              "the old spelling is accepted for one version only.", file=sys.stderr)
        return _LEGACY_STATE
    return _DEF_STATE
_DEF_HEALTH_CACHE = ".claude/health-cache.json"
_DEF_SEGMENTS = ["progress", "health", "commits", "branch"]


def _root() -> Path:
    if load_profile is not None:
        p = profile_path()
        if p is not None:
            d = p.parent
            for cand in (d, *d.parents):
                if (cand / ".git").exists():
                    return cand
            return d
    cur = Path.cwd().resolve()
    for cand in (cur, *cur.parents):
        if (cand / ".git").exists():
            return cand
    return cur


def _prof() -> dict:
    return load_profile() if load_profile is not None else {}


def _read(p: Path | None) -> str:
    if p is None:
        return ""
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _bar(pct: float, width: int = 8) -> str:
    fill = int(round(pct / 100 * width))
    return "█" * fill + "░" * (width - fill)


def _checklist(text: str) -> tuple[int, int]:
    m = re.search(r"<!--\s*CHECKLIST\s*-->(.*?)<!--\s*/CHECKLIST\s*-->", text, re.S)
    scope = m.group(1) if m else text
    done = len(re.findall(r"^\s*[-*]\s*\[[xX]\]", scope, re.M))
    todo = len(re.findall(r"^\s*[-*]\s*\[ \]", scope, re.M))
    return done, done + todo


def _git(root: Path, args: list[str], timeout: int = 6) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=str(root),
                           capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def _health_cache_state(root: Path) -> tuple[str, dict | None, str]:
    """Le o cache que health_probe.py escreve. Retorna (estado, dados, detalhe), estado em
    `absent` (arquivo nao existe: a sonda ainda nao rodou) · `ok` · `error` (existe e nao da
    para ler: OSError, vazio, JSON invalido, JSON que nao e' objeto).
    # Why: erro de leitura devolvido como "sem dado" some da statusline com a mesma cara de
    # "ainda nao rodou" — um cache corrompido ou ilegivel precisa aparecer como tal."""
    path = root / get(_prof(), "paths.health_cache", _DEF_HEALTH_CACHE)
    if not path.exists():
        return "absent", None, ""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return "error", None, f"leitura falhou ({e.__class__.__name__})"
    if not raw.strip():
        return "error", None, "cache vazio"
    try:
        data = json.loads(raw)
    except ValueError:
        return "error", None, "JSON invalido"
    if not isinstance(data, dict):
        return "error", None, "JSON nao e' objeto"
    return "ok", data, ""


def _health_cache(root: Path) -> dict | None:
    return _health_cache_state(root)[1]


def _services(root: Path) -> tuple[int, int]:
    data = _health_cache(root)
    if data is None:
        return (-1, 0)
    h = data.get("health")
    if isinstance(h, dict) and "services_online" in h:
        try:
            return (int(h["services_online"]), int(h.get("services_total", 0)))
        except (TypeError, ValueError):
            pass
    services = data.get("services")
    if isinstance(services, dict):
        vals = [b for b in services.values() if isinstance(b, dict)]
        up = sum(1 for b in vals if b.get("online") is True
                 or str(b.get("status") or "").lower() in ("ok", "up", "online", "healthy"))
        return (up, len(vals))
    return (-1, 0)


def _services_detail(root: Path) -> dict:
    """Retorna {name: online_bool} p/ segmentos que precisam do detalhe por-servico."""
    data = _health_cache(root)
    services = data.get("services") if isinstance(data, dict) else None
    if not isinstance(services, dict):
        return {}
    out = {}
    for name, b in services.items():
        if not isinstance(b, dict):
            continue
        online = b.get("online") is True or str(b.get("status") or "").lower() in ("ok", "up", "online", "healthy")
        out[str(name)] = online
    return out


# ---- SEGMENTOS (cada um retorna str; "" = omitir) ----

def seg_progress(root: Path) -> str:
    prof = _prof()
    label = str(get(prof, "projeto", "proj"))
    tracker = get(prof, "paths.tracker_doc", "")
    src = (_read(root / tracker) if tracker else "") or _read(
        root / _resolve_state(get(prof, "paths.state_ssot", _DEF_STATE), root, "statusline"))
    done, total = _checklist(src)
    pct = (done / total * 100) if total else 0.0
    return f"🧠 {label} {pct:.0f}% {_bar(pct)}"


def seg_health(root: Path) -> str:
    """health-kit: mostra o detalhe POR-SERVICO (ex.: 'api:OK db:DOWN'), nao so o agregado —
    e o produto inteiro deste kit, entao o detalhe e o default. Acima de 6 servicos, degrada p/
    agregado (⚕up/tot) pra nao estourar a largura da statusline. Cache ausente = segmento
    omitido; cache ilegivel/corrompido = `⚕cache:ERR` (estado proprio, nao silencio)."""
    if _health_cache_state(root)[0] == "error":
        return "⚕cache:ERR"
    detail = _services_detail(root)
    if not detail:
        up, tot = _services(root)
        return "" if up < 0 else f"⚕{up}/{tot}"
    if len(detail) > 6:
        up = sum(1 for v in detail.values() if v)
        return f"⚕{up}/{len(detail)}"
    return " ".join(f"{name}:{'OK' if online else 'DOWN'}" for name, online in detail.items())


def seg_commits(root: Path) -> str:
    out = _git(root, ["log", "--since=midnight", "--oneline"])
    n = len([ln for ln in out.splitlines() if ln.strip()])
    return f"{n}c hoje"


def seg_branch(root: Path) -> str:
    b = _git(root, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    return b or ""


def seg_tokens(root: Path) -> str:
    cmd = str(get(_prof(), "statusline.token_cmd", "") or "")
    if not cmd:
        return ""
    try:
        r = subprocess.run(cmd, shell=True, cwd=str(root),
                           capture_output=True, text=True, timeout=3)
        return r.stdout.strip().splitlines()[0][:24] if r.returncode == 0 and r.stdout.strip() else ""
    except Exception:
        return ""


def seg_autonomy(root: Path) -> str:
    lvl = get(_prof(), "statusline.autonomy_level", None)
    try:
        return f"🎚L{int(lvl)}" if lvl is not None else ""
    except (TypeError, ValueError):
        return ""


def seg_donegate(root: Path) -> str:
    cache = str(get(_prof(), "statusline.donegate_cache", "") or "")
    if not cache:
        return ""
    raw = _read(root / cache)
    if not raw:
        return ""
    try:
        d = json.loads(raw)
        if isinstance(d, dict):
            if "done" in d:
                return "✅DoD" if d.get("done") else "❌DoD"
            p, t = d.get("passed"), d.get("total")
            if isinstance(p, int) and isinstance(t, int):
                return f"{'✅' if p == t and t > 0 else '❌'}DoD {p}/{t}"
    except Exception:
        pass
    return "✅DoD" if "DONE" in raw.upper() and "NOT-DONE" not in raw.upper() else "❌DoD"


def seg_gates(root: Path) -> str:
    gs = str(get(_prof(), "paths.gate_sheet", "") or "")
    if not gs:
        return ""
    text = _read(root / gs)
    if not text:
        return ""
    n = len(re.findall(r"^\s*[-*]\s*\[ \]", text, re.M))
    return f"gates:{n}" if n else ""


_SEGMENTS = {
    "progress": seg_progress, "health": seg_health, "commits": seg_commits,
    "branch": seg_branch, "tokens": seg_tokens, "autonomy": seg_autonomy,
    "donegate": seg_donegate, "gates": seg_gates,
}


def _segment_list() -> list[str]:
    cfg = get(_prof(), "statusline.segments", None)
    if isinstance(cfg, list) and cfg:
        return [str(s) for s in cfg if str(s) in _SEGMENTS]
    return list(_DEF_SEGMENTS)


def render_statusline() -> str:
    root = _root()
    parts = []
    for name in _segment_list():
        try:
            v = _SEGMENTS[name](root)
        except Exception:
            v = ""
        if v:
            parts.append(v)
    return " ▸ ".join(parts) if parts else "🧠 statusline"


def render_panel() -> str:
    root = _root()
    ts = datetime.now(_BRT).strftime("%Y-%m-%d %H:%M BRT")
    rows = [f"  {name:<10} {(_SEGMENTS[name](root) or '(vazio)')}" for name in _segment_list()]
    return "\n".join([
        "╔══════════════════════════════════════════════════════════╗",
        "║  🗂️  STATUSLINE — segmentos ao vivo (Operator Kit)        ║",
        "╠══════════════════════════════════════════════════════════╣",
        f"  LIVE @ {ts}",
        *rows,
        "╠══════════════════════════════════════════════════════════╣",
        f"  -> {render_statusline()}",
        "╚══════════════════════════════════════════════════════════╝",
    ])


def _self_test() -> None:
    assert _bar(50, 8) == "████░░░░" and _bar(0, 4) == "░░░░" and _bar(100, 4) == "████"
    # segmentos puros nao dependem de rede; render nunca crasha e sempre retorna str
    sl = render_statusline()
    assert isinstance(sl, str) and sl, "statusline deve retornar string nao-vazia"
    # default segments validos
    assert all(s in _SEGMENTS for s in _DEF_SEGMENTS)
    # autonomy/tokens/donegate omitem quando ausentes (sem profile = "")
    print("self-test OK")
    print(sl)


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else "--statusline"
    if arg == "--statusline":
        try:
            sys.stdin.read()
        except Exception:
            pass
        try:
            print(render_statusline())
        except Exception:
            print("🧠 statusline")
    elif arg == "--panel":
        print(render_panel())
    elif arg in ("--self-test", "-t"):
        _self_test()
    else:
        print(render_statusline())
    sys.exit(0)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    main()
