#!/usr/bin/env python3
"""
statusline (Operator Kit) -- live progress bar in the CLI/IDE footer, PORTABLE and COMPOSABLE.

The bar is assembled from configurable SEGMENTS (statusline.segments in
operator-profile.yaml); each segment is best-effort and DEGRADES to empty if its
source does not exist (it never hangs).

Built-in segments (all optional, order defined by the profile):
  progress  -> 🧠 <project> <pct>% ████░░   (checklist from tracker_doc/state_ssot)
  health    -> ⚕<up>/<tot>                   (health cache -- paths.health_cache; see health_probe.py)
  tokens    -> <stdout of statusline.token_cmd>  (e.g. "◔41% $63/100"; empty = omit)
  autonomy  -> 🎚L<n>                         (statusline.autonomy_level 0-5; omits if null)
  donegate  -> ✅DoD / ❌DoD                  (cache in statusline.donegate_cache; omits if absent)
  gates     -> gates:<n>                      (open '- [ ]' items in paths.gate_sheet)
  commits   -> <n>c today                     (git, commits made today)
  branch    -> <branch>                       (git)

Default (without statusline.segments): ["progress","health","commits","branch"].

⚠️ statusLine does NOT go in plugin.json (CC limitation) -- point settings.json to it:
  "statusLine": { "type": "command", "command": "python operator-kit/statusline/statusline.py --statusline", "padding": 0 }

Modes: --statusline - --panel - --self-test. stdlib + PyYAML (via loader). Never crashes on the statusline path.
v2.1.0 -- 2026-07-10 (Operator Kit - Tier 2 - 'health' segment)
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
except Exception:  # noqa: BLE001 -- Why: a statusline that raises replaces the bar with an error on every prompt. A partial install, a hand-edited loader or a missing PyYAML must degrade to the defaults below, silently.
    load_profile = None  # type: ignore[assignment]

    def get(_p, _k, default=None):  # type: ignore[misc]
        return default

    def profile_path(_s=None):  # type: ignore[misc]
        return None

_BRT = timezone(timedelta(hours=-3))
_DEF_STATE = "docs/plans/execution/00-STATE.md"
_LEGACY_STATE = "docs/plans/execucao/00-STATE.md"
# A statusline renders on every prompt: the fallback works, it just does not shout about it.
_QUIET_FALLBACK = True
# Same reasoning for the profile keys renamed in 2.6.0: the loader's dual read keeps working here,
# and the once-per-session notice belongs to the hooks, not to a bar that redraws every prompt.
try:
    from _lib import profile_loader as _profile_loader  # type: ignore[import-not-found]

    _profile_loader.QUIET_DEPRECATION = _QUIET_FALLBACK
except Exception:  # noqa: BLE001 -- Why: with no loader there is nothing to mute, and raising here would kill the prompt line over a cosmetic setting.
    pass


# Why (rename of the generated names): the modules now write `docs/plans/execution/`. A repo
# scaffolded before that still has the Portuguese directory, and a reader that knows one spelling
# only either misses the state doc or reads nothing and says nothing. New name wins; the legacy is
# accepted for one version, with a single line on stderr; an explicit path from the profile is
# never rewritten.
def _resolve_state(rel: str, root: Path, who: str) -> str:
    if rel != _DEF_STATE:
        return rel
    if (root / _DEF_STATE).exists():
        return _DEF_STATE
    if (root / _LEGACY_STATE).exists():
        # Why (adversarial review of 2.5.0): a statusline re-renders on every prompt, so this line
        # printed on EVERY refresh — a deprecation notice that repeats forever is noise the operator
        # learns to scroll past, and it competes with the status bar it sits next to. The hooks
        # (`autoprompt_resume`, `session_boot`) already say it once per session, which is where a
        # notice belongs; here the fallback stays silent and simply works.
        if not _QUIET_FALLBACK:
            print(f"[{who}] deprecated: read '{_LEGACY_STATE}'; rename it to '{_DEF_STATE}' — "
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


def _health_cache(root: Path) -> dict | None:
    raw = _read(root / get(_prof(), "paths.health_cache", _DEF_HEALTH_CACHE))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


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
    """Returns {name: online_bool} for segments that need the per-service detail."""
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


# ---- SEGMENTS (each one returns str; "" = omit) ----

def seg_progress(root: Path) -> str:
    prof = _prof()
    label = str(get(prof, "project", "proj"))
    tracker = get(prof, "paths.tracker_doc", "")
    src = (_read(root / tracker) if tracker else "") or _read(
        root / _resolve_state(get(prof, "paths.state_ssot", _DEF_STATE), root, "statusline"))
    done, total = _checklist(src)
    pct = (done / total * 100) if total else 0.0
    return f"🧠 {label} {pct:.0f}% {_bar(pct)}"


def seg_health(root: Path) -> str:
    up, tot = _services(root)
    return "" if up < 0 else f"⚕{up}/{tot}"


def seg_commits(root: Path) -> str:
    out = _git(root, ["log", "--since=midnight", "--oneline"])
    n = len([ln for ln in out.splitlines() if ln.strip()])
    return f"{n}c today"


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
    # Why: the done_gate's text output carries "DONE-GATE: PARCIAL-DECLARADO" -- it contains "DONE" and
    # does not contain "NOT-DONE", so a substring fallback painted ✅ a state that by
    # contract is not green; and searching the whole text for "PARCIAL" painted ⚠️ a real NOT-DONE,
    # because the hint "If this is PARTIAL, declare what is missing" contains that word. The rule is the
    # state TOKEN on the line "DONE-GATE: <ESTADO>", never the surrounding text.
    up = raw.upper()
    m = re.search(r"DONE-GATE:\s*([A-Z\-]+)", up)
    state_token = m.group(1) if m else ""
    if state_token.startswith("PARCIAL") or state_token.startswith("PARTIAL"):
        return "⚠️DoD partial"
    if state_token == "DONE":
        return "✅DoD"
    if state_token:
        return "❌DoD"
    # without the state line (cache from another tool): the old rule, without the false positive
    return "✅DoD" if "DONE" in up and "NOT-DONE" not in up else "❌DoD"


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
    # pure segments do not depend on network; render never crashes and always returns str
    sl = render_statusline()
    assert isinstance(sl, str) and sl, "the statusline must return a non-empty string"
    # default segments are valid
    assert all(s in _SEGMENTS for s in _DEF_SEGMENTS)
    # autonomy/tokens/donegate omit when absent (no profile = "")
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
