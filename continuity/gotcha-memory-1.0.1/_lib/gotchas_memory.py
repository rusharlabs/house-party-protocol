"""
gotchas_memory (portable) -- operational learning loop: failure becomes knowledge.

Versioned, DEPERSONALIZED copy of `core/intelligence/gotchas_memory.py`
(origin repo) for the distributable `gotcha-memory` kit. Differences from the origin:

  1. The `error_strategy` import is from the SIBLING `_lib/` (vendored), not from `core.*`.
  2. The store is resolved DYNAMICALLY per call: profile (`paths.gotcha_store`)
     -> env `GOTCHA_STORE_DIR` -> `.claude/gotchas/` under the project's cwd.
  3. The origin owner's hardcoded guardrail seed was REMOVED (it was
     personal content/PII -- forbidden in a distributable kit). In its place:
     `seed_from_file(path)` reads curated lessons from a YAML/JSONL of YOUR OWN
     (see `curated.seed.example.yaml` at the kit's root).

PRINCIPLE: when a task fails, the event is recorded and classified (via
error_strategy). When the SAME kind of failure recurs >= N times within a time
window, it becomes a GOTCHA -- an ACTIONABLE lesson injected as a preamble BEFORE
the next run of the same task, so the agent/cron doesn't repeat the error.
"Curated" gotchas (seeded by you) are always-on when the key matches.

FLOW:
    record_failure(task_key, error)  ->  failures.jsonl  (append, classified)
    recurring_gotchas()              ->  groups by (task_key, family); >=min_count in the window
    gotchas_for_task(task_key)       ->  curated(match) + recurring(match); top-N by severity
    inject_preamble(task_key)        ->  "⚠️ GOTCHAS" string to paste into the pre-task prompt

I/O: only append/read JSONL in the store. stdlib only (+ vendored error_strategy;
PyYAML is OPTIONAL -- only for seeding from YAML and for the profile). Deterministic: `now` is
injectable (tests). NEVER raises in normal use: reading a missing/corrupted store
degrades to an empty list (honesty > crash).

v1.0.0 -- 2026-07-11 (gotcha-memory kit -- standalone extraction)
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from error_strategy import select_strategy  # noqa: E402  (vendored sibling)

try:
    import profile_loader  # sibling -- optional config via operator-profile.yaml
except ImportError:  # degrade: no profile, defaults
    profile_loader = None  # type: ignore[assignment]

# Base severity by error family (0-100). Families come from error_strategy.
_FAMILY_SEVERITY = {
    "fatal": 100,
    # Why: the instrument and lock families were born in error_strategy and the consumer
    # didn't know them -- they fell into the default 35 and the "unknown" lesson. instrument
    # is the most expensive: the number lies and nobody repeats it.
    "instrument": 85,
    "lock": 50,
    "dependency": 75,
    "state": 70,
    "config": 65,
    "ratelimit": 55,
    "transient": 40,
    "unknown": 35,
    "manual": 90,  # owner's curated = high weight by design
}

# Preventive lesson derived from the family (the "how to avoid it"). Merged with the strategy.
_FAMILY_PREVENTION = {
    "transient": "Recurring transient failure: retry with backoff/jitter before escalating; check upstream health.",
    "ratelimit": "Recurring rate limit: throttle preemptively (stop at ~80% of the cap) + honour Retry-After.",
    "dependency": "Missing/broken dependency: check the service/module is ALIVE before calling it; do not assume.",
    "state": "Recurring inconsistent state: rollback + re-sync before retrying; never operate on dirty state.",
    "config": "Missing config/env: validate the env at boot (fail-fast); do not run with a credential/port missing.",
    "fatal": "Recurring fatal error: ESCALATE to the human — no blind retry; capture the root cause.",
    "instrument": "The instrument answered and the number does not measure what it seems: DO NOT repeat the command — run a known-good control and change the ruler.",
    "lock": "Another process holds the resource (lock/index): wait or identify the owner — never remove the lock without proving the owner died.",
    "unknown": "Recurring unclassified failure: investigate the root cause by hand before retrying.",
}

_STRATEGY_HINT = {
    "retry": "→ retry",
    "rollback_and_retry": "→ rollback+retry",
    "skip": "→ skip (non-critical)",
    "escalate": "→ ESCALATE to the human",
    "recovery_workflow": "→ recovery workflow",
    "remeasure": "→ RE-MEASURE with another instrument (do not repeat the command)",
}


@dataclass(frozen=True)
class Gotcha:
    """An actionable lesson, learned (recurring) or imposed (curated)."""
    key: str            # task_key (recurring) or tag/substring (curated; "*" = always-on)
    family: str
    prevention: str
    severity: int       # 0-100
    source: str         # "recurring" | "curated"
    count: int = 0      # how many failures within the window (0 for curated)
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
    """The kit's effective config: profile (`gotchas.*`) layered over the defaults. Never raises."""
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
    """Resolves the store: argument > profile > env GOTCHA_STORE_DIR > .claude/gotchas/ in the cwd."""
    if store_dir:
        return Path(store_dir)
    cfg_dir = config().get("store_dir")
    if cfg_dir:
        return Path(cfg_dir)
    env = os.environ.get("GOTCHA_STORE_DIR")
    if env:
        return Path(env)
    return Path.cwd() / ".claude" / "gotchas"


# ─────────────────────────── internal helpers ───────────────────────────

def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Reads JSONL. Missing file -> []. Corrupted lines are skipped (degrades, doesn't crash)."""
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
                    continue  # corrupted line -- skip it
    except OSError:
        return []
    return out


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _matches(gotcha_key: str, task_key: str) -> bool:
    """Curated key matches task_key if it's '*' (always-on) or a substring (either direction)."""
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


# ─────────────────────────── redaction (before persisting) ───────────────────────────
# Why: the error and the command that failed go to disk and come back into the transcript on
# the next hook; a token echoed by a 401 would end up written in the clear. Redaction is by
# SHAPE (provider prefix, authorization header, key=value, credential in a URL, high-entropy
# blob) and records only the TYPE and the LENGTH -- never the value.

_REDACTED = "[REDACTED:{kind}:{n}]"
_KEYWORDS = (
    r"(?:api[_-]?key|access[_-]?key|secret(?:[_-]?key)?|client[_-]?secret|password|passwd"
    r"|token|auth[_-]?token|private[_-]?key)"
)
_VALUE = r"[^\s\"'&;,]"
# (type, regex, group that carries the value to redact)
_REDACT_RULES: list[tuple[str, re.Pattern[str], int]] = [
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.DOTALL), 0),
    ("url-credential", re.compile(r"(?<=://)([^/\s@:]+:[^@\s/]+)(?=@)"), 1),
    ("basic-credential", re.compile(r"(?:^|\s)(?:-u|--user|--proxy-user)[ =]\s*[\"']?([^\s\"'@:]+:[^\s\"']+)"), 1),
    ("auth-header", re.compile(r"(?i)\b(bearer|basic)\s+([A-Za-z0-9_\-.=+/]{16,})"), 2),
    ("provider-token", re.compile(
        r"\b(?:sk-ant-[A-Za-z0-9_\-]{8,}|sk-[A-Za-z0-9_\-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}"
        r"|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_\-]{20,}|xox[baprs]-[A-Za-z0-9\-]{8,}"
        r"|AKIA[0-9A-Z]{12,}|AIza[0-9A-Za-z_\-]{20,})"), 0),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"), 0),
    ("assignment", re.compile(r"(?i)\b" + _KEYWORDS + r"[\"']?\s*=\s*[\"']?(" + _VALUE + r"{4,})"), 1),
    # the `key: value` shape only when the value looks like a credential (digit/symbol, >= 8),
    # so it doesn't erase prose like "token: expired".
    ("assignment", re.compile(r"(?i)\b" + _KEYWORDS + r"[\"']?\s*:\s*[\"']?((?=" + _VALUE + r"*[0-9_\-+/=.!@#$%^*~])" + _VALUE + r"{8,})"), 1),
    ("high-entropy", re.compile(r"(?<![A-Za-z0-9+=_\-])[A-Za-z0-9+=_\-]{32,}(?![A-Za-z0-9+=_\-])"), 0),
]


def _shannon_bits(s: str) -> float:
    n = len(s)
    counts: dict[str, int] = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def _looks_random(tok: str) -> bool:
    """High-entropy blob: uppercase + lowercase + digit and >= 4 bits/char. A hex hash
    (lowercase only) and a camelCase identifier are left out."""
    return (
        any(c.islower() for c in tok) and any(c.isupper() for c in tok)
        and any(c.isdigit() for c in tok) and _shannon_bits(tok) >= 4.0
    )


def redact_secrets(text: str) -> str:
    """Replaces secrets with `[REDACTED:<type>:<length>]`. Text without a secret comes back unchanged."""
    if not text:
        return text
    out = text
    for kind, rx, grp in _REDACT_RULES:
        def _sub(m: re.Match[str], kind: str = kind, grp: int = grp) -> str:
            val = m.group(grp)
            if val.startswith("[REDACTED:") or (kind == "high-entropy" and not _looks_random(val)):
                return m.group(0)
            tag = _REDACTED.format(kind=kind, n=len(val))
            s, e = m.start(grp) - m.start(0), m.end(grp) - m.start(0)
            return m.group(0)[:s] + tag + m.group(0)[e:]
        out = rx.sub(_sub, out)
    return out


def _redact_obj(obj: Any) -> Any:
    if isinstance(obj, str):
        return redact_secrets(obj)
    if isinstance(obj, dict):
        return {k: _redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_redact_obj(v) for v in obj]
    return obj


# ─────────────────────────── public API ───────────────────────────

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
    dedupe_key: str | None = None,
) -> dict[str, Any]:
    """Records a failure (classified via error_strategy) into failures.jsonl. Returns the event.

    Secrets in task_key/error/context are redacted BEFORE truncating and persisting.

    `dedupe_key`: the failure's identity at the origin (e.g. the host's tool_use_id). If an event
    with the same key exists in failures.jsonl, nothing is written and the existing one is returned.
    # Why: the same failure can reach the hook via more than one host event; without the key, each
    # arrival becomes a record and the recurrence (min_count) is reached without truly recurring."""
    ts = time.time() if now is None else now
    dec = select_strategy(error_message, attempt=attempt, max_retries=max_retries, is_critical=is_critical)
    event = {
        "task_key": redact_secrets(str(task_key)),
        "error": redact_secrets(str(error_message or ""))[:500],
        "family": dec.family,
        "strategy": dec.strategy,
        "terminal": dec.terminal,
        "context": _redact_obj(context or {}),
        "ts": ts,
    }
    path = _store(store_dir) / "failures.jsonl"
    if dedupe_key:
        event["dedupe_key"] = str(dedupe_key)
        for prev in _read_jsonl(path):
            if prev.get("dedupe_key") == event["dedupe_key"]:
                return prev
    _append_jsonl(path, event)
    return event


def rotate_failures(
    *,
    max_lines: int = 5000,
    keep_days: float = 45,
    store_dir: str | Path | None = None,
    now: float | None = None,
) -> dict[str, int]:
    """Rotates failures.jsonl: the overflow goes to failures.archive.jsonl.

    # Why: the append had no ceiling (1.9 MB / 1,744 lines in a month) and the preflight
    # re-reads the WHOLE file on every Bash command -- growing the store is latency in every
    # session. keep_days=45 covers the review window (30d) with slack; max_lines=5000 ~= 3
    # months of the worst month measured. Best-effort and idempotent: with no overflow, it's a
    # no-op. Atomic rewrite (tmp+replace) so the store is never corrupted if it dies midway.
    """
    store = _store(store_dir)
    failures_path = store / "failures.jsonl"
    events = _read_jsonl(failures_path)
    n = len(events)
    if n == 0:
        return {"kept": 0, "archived": 0}

    cutoff = (time.time() if now is None else now) - keep_days * 86400
    in_window = sum(1 for e in events if float(e.get("ts", 0) or 0) >= cutoff)
    # append-order == time-order (record_failure uses time.time()); keeps the trailing ones
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
    """Groups failures by (task_key, family) within the window; those recurring >= min_count become a Gotcha."""
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
    """Reads the curated gotchas (always-on when the key matches; seeded by you)."""
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
    """Adds a curated gotcha (idempotent by (key, prevention)). Returns True if it added one."""
    path = _store(store_dir) / "curated.jsonl"
    existing = _read_jsonl(path)
    for c in existing:
        if c.get("key") == key and c.get("prevention") == prevention:
            return False  # already exists -- don't duplicate
    _append_jsonl(path, {"key": key, "prevention": prevention, "family": family, "severity": int(severity)})
    return True


def seed_from_file(seed_path: str | Path, *, store_dir: str | Path | None = None) -> int:
    """Seeds curated gotchas from a file of YOUR OWN (.yaml list of {key, prevention, severity?, family?}
    or .jsonl with the same fields). Idempotent. Returns the number added. -1 if unreadable."""
    p = Path(seed_path)
    if not p.exists():
        return -1
    entries: list[dict[str, Any]] = []
    if p.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml  # PyYAML -- optional
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
    """Gotchas relevant to a task: curated(match) + recurring(match), top-N by severity."""
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
    """Renders the top-N gotchas as a preamble to paste into the pre-task prompt. '' if none."""
    gs = gotchas_for_task(task_key, top=top, window_hours=window_hours, min_count=min_count, store_dir=store_dir, now=now)
    if not gs:
        return ""
    lines = ["⚠️ GOTCHAS (do not repeat these — learned from earlier failures):"]
    for g in gs:
        tag = f"[{g.count}x]" if g.source == "recurring" else "[rule]"
        lines.append(f"  • {tag} {g.prevention}")
    return "\n".join(lines)


# ─────────────────────────── CLI / self-test / demo ───────────────────────────

def _demo() -> None:
    """VISIBLE demo: uses a temporary store, simulates 3 failures, shows the learning."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        store = Path(d)
        print("═" * 70)
        print("DEMO gotcha-memory — the system learning from its own failure")
        print("═" * 70)
        add_curated_gotcha("deploy", "Check that the BACKEND changed (a route exclusive to the new one), not just the auth gate.", store_dir=store)
        print("\n[1] 1 curated gotcha added (your rule, always-on when it matches)\n")

        # Example task: a cron that repeatedly hits a rate limit
        t0 = 1_000_000.0
        ev: dict[str, Any] = {}
        for i in range(3):
            ev = record_failure(
                "cron:ingest",
                "upstream: overloaded (429 rate limit)",
                store_dir=store, now=t0 + i * 60,
            )
        print(f"[2] cron:ingest failed 3x in 3min — classified: family={ev['family']} strategy={ev['strategy']}")

        rec = recurring_gotchas(store_dir=store, now=t0 + 200)
        print(f"\n[3] recurring_gotchas detected {len(rec)} pattern(s):")
        for g in rec:
            print(f"    • [{g.count}x] family={g.family} sev={g.severity}: {g.prevention}")

        print("\n[4] PREAMBLE injected BEFORE the next cron:ingest (what the agent sees):")
        print("-" * 70)
        print(inject_preamble("cron:ingest", store_dir=store, now=t0 + 200))
        print("-" * 70)

        print("\n[5] PREAMBLE on a deploy task (curated fires by substring):")
        print("-" * 70)
        print(inject_preamble("run the deploy of service X", store_dir=store, now=t0 + 200))
        print("-" * 70)
        print("\nDEMO OK — failure→knowledge→prevention, in code, verifiable.\n")


def _self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        store = Path(d)
        t0 = 5_000_000.0
        # 2 failures do NOT become a gotcha; 3 do
        record_failure("task:x", "ETIMEDOUT", store_dir=store, now=t0)
        record_failure("task:x", "ETIMEDOUT", store_dir=store, now=t0 + 10)
        assert recurring_gotchas(store_dir=store, now=t0 + 20, min_count=3) == [], "2 failures should not become a gotcha"
        record_failure("task:x", "ETIMEDOUT", store_dir=store, now=t0 + 20)
        rec = recurring_gotchas(store_dir=store, now=t0 + 30, min_count=3)
        assert len(rec) == 1 and rec[0].count == 3, "3 failures should become 1 gotcha with count=3"
        assert rec[0].family == "transient", f"expected transient, got {rec[0].family}"
        # Window: an old failure outside the window doesn't count
        assert recurring_gotchas(store_dir=store, now=t0 + 30 + 25 * 3600, window_hours=24, min_count=3) == [], "failures outside the window do not count"
        # Curated is idempotent
        assert add_curated_gotcha("deploy", "check the backend", store_dir=store) is True
        assert add_curated_gotcha("deploy", "check the backend", store_dir=store) is False, "re-add must be idempotent"
        # Curated match by substring
        pre = inject_preamble("touch the deploy of the service", store_dir=store, now=t0 + 30)
        assert "backend" in pre.lower(), "the deploy curated rule should fire"
        # Seed from a JSONL file (stdlib) -- idempotent
        seed = store / "seed.jsonl"
        seed.write_text(
            json.dumps({"key": "migration", "prevention": "back it up first", "severity": 95}) + "\n",
            encoding="utf-8",
        )
        assert seed_from_file(seed, store_dir=store) == 1, "seed should add 1"
        assert seed_from_file(seed, store_dir=store) == 0, "re-seed must be idempotent (0)"
        assert seed_from_file(store / "does-not-exist.jsonl", store_dir=store) == -1, "missing file = -1"
        # Missing store degrades to empty (doesn't crash)
        assert curated_gotchas(store_dir=store / "sub" / "that-does-not-exist") == []
        # Redaction before persisting: the value never reaches disk; type + length do
        record_failure(
            "task:auth", "401 Bearer " + "sk-" + "ant-EXEMPLO0000000000000000 token=" + "ghp" + "_EXEMPLOEXEMPLOEXEMPLOEXEMPLO12",
            context={"cmd": "curl -u user:SENHA-EXEMPLO-1 https://x"}, store_dir=store, now=t0,
        )
        raw = (store / "failures.jsonl").read_text(encoding="utf-8")
        assert "EXEMPLO" not in raw, "secret was persisted in the clear"
        assert "[REDACTED:auth-header:30]" in raw and "[REDACTED:basic-credential:20]" in raw, raw
        assert redact_secrets("ETIMEDOUT em api.example.com:443") == "ETIMEDOUT em api.example.com:443"
        print("self-test OK ✓")


if __name__ == "__main__":
    # Windows console is cp1252 -- force utf-8 so it doesn't break on the special chars below.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

    arg = sys.argv[1] if len(sys.argv) > 1 else "--demo"
    if arg in ("--self-test", "-t"):
        _self_test()
    elif arg == "--seed" and len(sys.argv) > 2:
        n = seed_from_file(sys.argv[2])
        print(f"Seeded {n} curated gotchas into {_store(None) / 'curated.jsonl'}" if n >= 0
              else f"seed unreadable/missing: {sys.argv[2]} (YAML needs PyYAML; alternative: .jsonl)")
    elif arg == "--preamble" and len(sys.argv) > 2:
        print(inject_preamble(" ".join(sys.argv[2:])) or "(no gotcha for that task)")
    else:
        _demo()
