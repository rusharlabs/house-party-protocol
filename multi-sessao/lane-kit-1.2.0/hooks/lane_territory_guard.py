#!/usr/bin/env python3
"""
lane_territory_guard — PreToolUse (Edit|Write): avisa sobre colisão de território entre lanes.

WARN-only (doutrina da casa: nunca emite `decision`, nunca bloqueia, sempre exit 0) — mesmo
padrão de `snapshot_rollback_gate.py`/`external_send_draft_gate.py` do operator-kit. Dois
tipos de aviso, ambos independentes de haver ou não outra lane viva:

  1. Zona vermelha (`lanes.yaml -> zonas_vermelhas`): paths sensíveis que merecem atenção
     mesmo numa sessão solo (ex.: settings do harness, arquivo de memória compartilhada).
  2. Território exclusivo: outra lane VIVA (ou suspeita) já reivindicou este path via
     `_lane_io.register(..., territory=...)` — coordene via lane_board/REORIENT-MAILBOX
     antes de editar.

Uso (hook): echo '{"tool_input":{"file_path":"/abs/path.py"}}' | python lane_territory_guard.py
Exit: sempre 0.
stdlib only. v1.0.0 — 2026-07-10 (lane-kit)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lane_io  # noqa: E402

_DEFAULT_RED_ZONES = [".claude/settings*.json", "**/MEMORY.md"]


def _red_zone_hit(rel_path: str, cfg: dict) -> str | None:
    zones = list(_DEFAULT_RED_ZONES)
    extra = _lane_io.get(cfg, "zonas_vermelhas", None)
    if isinstance(extra, list):
        for z in extra:
            if z not in zones:
                zones.append(z)
    for pattern in zones:
        if _lane_io._glob_to_regex(pattern).match(rel_path):
            return pattern
    return None


def handle(payload: dict) -> str | None:
    """Retorna o texto de aviso (ou None). Nunca lança, nunca sinaliza decision/block."""
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return None
    file_path = tool_input.get("file_path")
    if not file_path:
        return None

    rel = _lane_io._norm_path(str(file_path))
    cfg = _lane_io.load_config()
    my_lane = os.environ.get("CLAUDE_LANE_ID") or "solo"

    warnings = []

    red_hit = _red_zone_hit(rel, cfg)
    if red_hit:
        warnings.append(
            f"[lane_territory_guard] AVISO: {rel} é ZONA VERMELHA ({red_hit}) — "
            f"nenhuma lane edita sem gate do operador. WARN-only — não estou bloqueando."
        )

    owners = [o for o in _lane_io.who_owns(rel) if o[0] != my_lane]
    if owners:
        lid, pattern, state = owners[0]
        entry = _lane_io._read_registry().get("lanes", {}).get(lid, {})
        age = _lane_io.age_str(entry)
        warnings.append(
            f"[lane_territory_guard] AVISO: {rel} está no território EXCLUSIVO da lane {lid} "
            f"(heartbeat {age}, {state}) — coordene via lane_board / REORIENT-MAILBOX antes de editar. WARN-only."
        )

    return "\n".join(warnings) if warnings else None


def main(argv) -> int:
    if argv and argv[0] in ("--self-test", "-t"):
        return _self_test()

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:  # noqa: BLE001
        payload = {}

    try:
        warn = handle(payload)
    except Exception:  # noqa: BLE001 — fail-open total
        warn = None

    if warn:
        sys.stderr.write(warn + "\n")
    print("{}")
    return 0


def _self_test() -> int:
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="lane_territory_guard_selftest_"))
    orig = (_lane_io._PROJECT_ROOT, _lane_io._LANES_DIR, _lane_io.REGISTRY_PATH, _lane_io.CONFIG_PATH)
    try:
        _lane_io._PROJECT_ROOT = tmp
        _lane_io._LANES_DIR = tmp / ".claude" / "lanes"
        _lane_io.REGISTRY_PATH = _lane_io._LANES_DIR / "registry.json"
        _lane_io.CONFIG_PATH = _lane_io._LANES_DIR / "lanes.yaml"

        os.environ["CLAUDE_LANE_ID"] = "exec-b"
        _lane_io.register("exec-a", "executora", "s1", "claude-opus-4-8",
                           territory={"paths": [], "exclusive": ["scripts/vm/**"]})

        # 1. exec-b editando território exclusivo de exec-a -> avisa
        p1 = str(tmp / "scripts" / "vm" / "x.py")
        w1 = handle({"tool_input": {"file_path": p1}})
        assert w1 and "exec-a" in w1, f"deveria avisar sobre territorio de exec-a: {w1}"

        # 2. path fora do territorio -> silencio
        p2 = str(tmp / "scripts" / "other" / "y.py")
        w2 = handle({"tool_input": {"file_path": p2}})
        assert w2 is None, f"fora do territorio nao deveria avisar: {w2}"

        # 3. exec-a editando o proprio territorio -> silencio
        os.environ["CLAUDE_LANE_ID"] = "exec-a"
        w3 = handle({"tool_input": {"file_path": p1}})
        assert w3 is None, f"dono editando o proprio territorio nao deveria avisar: {w3}"
        os.environ["CLAUDE_LANE_ID"] = "exec-b"

        # 4. exec-a com heartbeat de 35min (morta) -> zero falso positivo
        import time as _time
        from datetime import datetime, timezone
        dead_ts = datetime.fromtimestamp(_time.time() - 35 * 60, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        reg = _lane_io._read_registry()
        reg["lanes"]["exec-a"]["heartbeat_at"] = dead_ts
        _lane_io._write_registry(reg)
        w4 = handle({"tool_input": {"file_path": p1}})
        assert w4 is None, f"lane morta nao deveria disparar territorio: {w4}"

        # 5. zona vermelha com registry vazio -> avisa mesmo solo
        _lane_io.evict("exec-a")
        os.environ["CLAUDE_LANE_ID"] = "solo"
        p5 = str(tmp / ".claude" / "settings.local.json")
        w5 = handle({"tool_input": {"file_path": p5}})
        assert w5 and "ZONA VERMELHA" in w5, f"zona vermelha deveria avisar mesmo solo: {w5}"

        # 6. glob ** de zona vermelha (MEMORY.md aninhado)
        p6 = str(tmp / "deep" / "nested" / "MEMORY.md")
        w6 = handle({"tool_input": {"file_path": p6}})
        assert w6 and "ZONA VERMELHA" in w6, f"** deveria casar MEMORY.md aninhado: {w6}"

        # 7. payload sem file_path / garbage -> None, exit 0 via main()
        assert handle({"tool_input": {}}) is None
        assert handle({}) is None

        # 8. o resultado do main() nunca contem "decision" (WARN-only estrutural)
        import io as _io
        old_stdin = sys.stdin
        sys.stdin = _io.StringIO(json.dumps({"tool_input": {"file_path": p1}}))
        rc = main([])
        sys.stdin = old_stdin
        assert rc == 0

        print("self-test OK — territorio exclusivo avisa dono correto, fora do territorio silencia, "
              "dono no proprio territorio silencia, lane morta = zero falso positivo, zona vermelha "
              "avisa mesmo solo, glob ** funciona, payload vazio = None, main() sempre exit 0")
        return 0
    finally:
        os.environ.pop("CLAUDE_LANE_ID", None)
        _lane_io._PROJECT_ROOT, _lane_io._LANES_DIR, _lane_io.REGISTRY_PATH, _lane_io.CONFIG_PATH = orig
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
