#!/usr/bin/env python3
"""
lane_board — quadro-branco com máquina de estados p/ N sessões (lanes) sem colisão.

Único writer do board.jsonl (append-only, lock por diretório). Enforcement EM CÓDIGO
(não disciplina textual): CHECKPOINT-READY só quem claimou + evidência; VERIFIED/NEEDS-FIX
só revisora de OUTRA lane E OUTRA família de modelo que o builder (maker≠checker); checker
indisponível → só DEFERRED; MERGED exige VERIFIED prévio (+ gate humano para itens 🔴, via
--tag red exigindo --human-approved).

Estados: CLAIMED -> BUILDING -> CHECKPOINT-READY -> UNDER-REVIEW -> VERIFIED|NEEDS-FIX -> MERGED
                                                                   -> DEFERRED (checker indisponível)

Uso:
    python lane_board.py claim <item_id> --lane <id> --role <role> --model <model> [--tag green|red]
    python lane_board.py --set <item_id> <estado> --lane <id> --role <role> --model <model>
                          [--evidencia "..."] [--verdict-by-lane <id>] [--verdict-by-model <m>]
                          [--checker-indisponivel] [--human-approved]
    python lane_board.py status [<item_id>]
    python lane_board.py render
    python lane_board.py --self-test

Exit: 0 ok · 1 transição inválida/enforcement recusou · 2 uso inválido/lock não obtido.
stdlib only. v1.0.0 — 2026-07-10 (lane-kit)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
_LANES_DIR = _PROJECT_ROOT / ".claude" / "lanes"
BOARD_PATH = _LANES_DIR / "board.jsonl"
RENDER_PATH = _PROJECT_ROOT / "docs" / "plans" / "execucao" / "LANE-BOARD.md"

_LOCK_SPIN_SECONDS = 2.0

_TRANSITIONS = {
    None: {"CLAIMED"},
    "CLAIMED": {"BUILDING", "CLAIMED"},
    "BUILDING": {"CHECKPOINT-READY", "BUILDING"},
    "CHECKPOINT-READY": {"UNDER-REVIEW"},
    "UNDER-REVIEW": {"VERIFIED", "NEEDS-FIX", "DEFERRED"},
    "NEEDS-FIX": {"BUILDING"},
    "VERIFIED": {"MERGED"},
    "DEFERRED": {"UNDER-REVIEW"},
    "MERGED": set(),
}


class LockError(Exception):
    pass


class _Lock:
    def __init__(self, lanes_dir: Path, timeout: float = _LOCK_SPIN_SECONDS):
        self.path = lanes_dir / ".lock"
        self.timeout = timeout
        self._acquired = False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                os.mkdir(self.path)
                self._acquired = True
                return self
            except FileExistsError:
                if time.monotonic() > deadline:
                    raise LockError(f"lock não obtido em {self.timeout}s: {self.path}")
                time.sleep(0.01)

    def __exit__(self, *exc):
        if self._acquired:
            try:
                os.rmdir(self.path)
            except OSError:
                pass


def _model_family(model: str) -> str:
    """Extrai a família de um id de modelo (heurística): 'claude-opus-4-8' -> 'claude'."""
    if not model:
        return ""
    m = re.match(r"^([a-zA-Z]+)", model)
    return m.group(1).lower() if m else model.lower()


def _read_events(item_id: str | None = None) -> list:
    if not BOARD_PATH.exists():
        return []
    events = []
    for line in BOARD_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue  # linha corrompida (nunca deveria ocorrer com o lock) — ignora, não crasha
        if item_id is None or e.get("item_id") == item_id:
            events.append(e)
    return events


def _latest_state(item_id: str) -> dict | None:
    events = _read_events(item_id)
    return events[-1] if events else None


def _append_event(event: dict) -> None:
    BOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BOARD_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _validate_transition(item_id: str, new_state: str, lane_id: str, role: str, model: str,
                          evidencia: str = "", verdict_by_lane: str = "", verdict_by_model: str = "",
                          checker_indisponivel: bool = False, human_approved: bool = False, tag: str = "green") -> str | None:
    """Retorna None se válido, ou a mensagem de erro."""
    current = _latest_state(item_id)
    cur_state = current["estado"] if current else None

    allowed = _TRANSITIONS.get(cur_state, set())
    if new_state not in allowed:
        return f"transição inválida: {cur_state} -> {new_state} (permitido: {sorted(allowed)})"

    if new_state == "CLAIMED" and current and cur_state not in (None,):
        if cur_state in ("MERGED",):
            return f"item já MERGED — não pode reabrir com CLAIMED"

    if new_state == "CHECKPOINT-READY":
        builder = current  # o evento BUILDING/CLAIMED mais recente é o "dono"
        if role != "executora":
            return f"CHECKPOINT-READY só por role=executora (veio: {role})"
        if not builder or builder.get("lane_id") != lane_id:
            return f"CHECKPOINT-READY só pela lane que claimou o item (dono: {builder.get('lane_id') if builder else '?'}, veio: {lane_id})"
        if not evidencia:
            return "CHECKPOINT-READY exige evidência não-vazia (hash/exit-code colado, nunca 'rodei')"

    if new_state in ("VERIFIED", "NEEDS-FIX"):
        if role != "revisora":
            return f"{new_state} só por role=revisora (veio: {role})"
        # acha o builder original (evento CLAIMED)
        claimed = next((e for e in reversed(_read_events(item_id)) if e["estado"] == "CLAIMED"), None)
        builder_lane = claimed.get("lane_id") if claimed else None
        builder_model = claimed.get("model") if claimed else None
        if checker_indisponivel:
            return f"checker indisponível — só DEFERRED é aceito, não {new_state}"
        if verdict_by_lane == builder_lane:
            return f"maker≠checker violado: revisora ({verdict_by_lane}) é a MESMA lane do builder ({builder_lane})"
        if _model_family(verdict_by_model) == _model_family(builder_model):
            return f"maker≠checker violado: revisora e builder são da MESMA família de modelo ({_model_family(verdict_by_model)})"

    if new_state == "DEFERRED" and not checker_indisponivel:
        return "DEFERRED só quando --checker-indisponivel"

    if new_state == "MERGED":
        verified = next((e for e in reversed(_read_events(item_id)) if e["estado"] == "VERIFIED"), None)
        if not verified:
            return "MERGED exige um VERIFIED prévio no histórico do item"
        if tag == "red" and not human_approved:
            return "item 🔴 (tag=red) exige --human-approved para MERGED (gate humano)"

    return None


def set_state(item_id: str, new_state: str, lane_id: str, role: str, model: str, **kwargs) -> tuple:
    """Retorna (ok, message_or_error). Grava sob lock."""
    try:
        with _Lock(_LANES_DIR):
            err = _validate_transition(item_id, new_state, lane_id, role, model, **kwargs)
            if err:
                return False, err
            event = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "item_id": item_id,
                "estado": new_state,
                "lane_id": lane_id,
                "role": role,
                "model": model,
            }
            if kwargs.get("evidencia"):
                event["evidencia"] = kwargs["evidencia"]
            if kwargs.get("verdict_by_lane"):
                event["verdict_by"] = {"lane": kwargs["verdict_by_lane"], "model": kwargs.get("verdict_by_model", "")}
            if kwargs.get("tag"):
                event["tag"] = kwargs["tag"]
            _append_event(event)
            return True, event
    except LockError as e:
        return False, str(e)


def render() -> str:
    items: dict = {}
    for e in _read_events():
        items.setdefault(e["item_id"], []).append(e)
    lines = ["# LANE-BOARD.md (gerado por lane_board.py render — não editar à mão)", ""]
    for item_id, events in sorted(items.items()):
        last = events[-1]
        lines.append(f"## {item_id} — {last['estado']}")
        for e in events:
            evid = f" · evidência: {e['evidencia']}" if e.get("evidencia") else ""
            verdict = f" · verdict_by: {e['verdict_by']}" if e.get("verdict_by") else ""
            lines.append(f"- {e['ts']} · {e['estado']} · lane={e['lane_id']} role={e['role']}{evid}{verdict}")
        lines.append("")
    return "\n".join(lines)


def _self_test() -> int:
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="lane_board_selftest_"))
    global _PROJECT_ROOT, _LANES_DIR, BOARD_PATH, RENDER_PATH
    orig = (_PROJECT_ROOT, _LANES_DIR, BOARD_PATH, RENDER_PATH)
    try:
        _PROJECT_ROOT = tmp
        _LANES_DIR = tmp / ".claude" / "lanes"
        BOARD_PATH = _LANES_DIR / "board.jsonl"
        RENDER_PATH = tmp / "LANE-BOARD.md"

        ok1, r1 = set_state("ITEM-1", "CLAIMED", "exec-a", "executora", "claude-opus-4-8")
        assert ok1, f"CLAIMED deveria passar: {r1}"

        ok2, r2 = set_state("ITEM-1", "BUILDING", "exec-a", "executora", "claude-opus-4-8")
        assert ok2, f"BUILDING deveria passar: {r2}"

        ok3, r3 = set_state("ITEM-1", "CHECKPOINT-READY", "exec-b", "executora", "claude-opus-4-8", evidencia="exit=0")
        assert not ok3 and "dono" in r3, f"CHECKPOINT-READY por lane errada deveria recusar: {r3}"

        ok4, r4 = set_state("ITEM-1", "CHECKPOINT-READY", "exec-a", "executora", "claude-opus-4-8")
        assert not ok4 and "evidência" in r4, f"CHECKPOINT-READY sem evidência deveria recusar: {r4}"

        ok5, r5 = set_state("ITEM-1", "CHECKPOINT-READY", "exec-a", "executora", "claude-opus-4-8", evidencia="exit=0 sha=abc")
        assert ok5, f"CHECKPOINT-READY válido deveria passar: {r5}"

        ok6, r6 = set_state("ITEM-1", "UNDER-REVIEW", "exec-a", "executora", "claude-opus-4-8")
        assert ok6, f"UNDER-REVIEW deveria passar: {r6}"

        ok7, r7 = set_state("ITEM-1", "VERIFIED", "exec-a", "revisora", "claude-opus-4-8", verdict_by_lane="exec-a", verdict_by_model="claude-opus-4-8")
        assert not ok7 and "MESMA lane" in r7, f"maker=checker (mesma lane) deveria recusar: {r7}"

        ok8, r8 = set_state("ITEM-1", "VERIFIED", "exec-a", "revisora", "claude-opus-4-8", verdict_by_lane="rev-a", verdict_by_model="claude-opus-4-8")
        assert not ok8 and "MESMA família" in r8, f"maker=checker (mesma família modelo) deveria recusar: {r8}"

        ok9, r9 = set_state("ITEM-1", "VERIFIED", "exec-a", "revisora", "claude-opus-4-8", verdict_by_lane="rev-a", verdict_by_model="gpt-5.5")
        assert ok9, f"revisora outra lane+outra família deveria passar: {r9}"

        ok10, r10 = set_state("ITEM-1", "MERGED", "rev-a", "revisora", "gpt-5.5")
        assert ok10, f"MERGED após VERIFIED (tag green default) deveria passar: {r10}"

        ok11, r11 = set_state("ITEM-2", "CLAIMED", "exec-a", "executora", "claude-opus-4-8", tag="red")
        set_state("ITEM-2", "BUILDING", "exec-a", "executora", "claude-opus-4-8")
        set_state("ITEM-2", "CHECKPOINT-READY", "exec-a", "executora", "claude-opus-4-8", evidencia="exit=0")
        set_state("ITEM-2", "UNDER-REVIEW", "exec-a", "executora", "claude-opus-4-8")
        set_state("ITEM-2", "VERIFIED", "exec-a", "revisora", "gpt-5.5", verdict_by_lane="rev-a", verdict_by_model="gpt-5.5")
        ok12, r12 = set_state("ITEM-2", "MERGED", "rev-a", "revisora", "gpt-5.5", tag="red")
        assert not ok12 and "gate humano" in r12, f"item red sem --human-approved deveria recusar MERGED: {r12}"
        ok13, r13 = set_state("ITEM-2", "MERGED", "rev-a", "revisora", "gpt-5.5", tag="red", human_approved=True)
        assert ok13, f"item red com --human-approved deveria passar: {r13}"

        ok14, r14 = set_state("ITEM-3", "CLAIMED", "exec-a", "executora", "claude-opus-4-8")
        set_state("ITEM-3", "BUILDING", "exec-a", "executora", "claude-opus-4-8")
        set_state("ITEM-3", "CHECKPOINT-READY", "exec-a", "executora", "claude-opus-4-8", evidencia="x")
        set_state("ITEM-3", "UNDER-REVIEW", "exec-a", "executora", "claude-opus-4-8")
        ok15, r15 = set_state("ITEM-3", "VERIFIED", "exec-a", "revisora", "claude-opus-4-8", checker_indisponivel=True, verdict_by_lane="rev-a", verdict_by_model="gpt-5.5")
        assert not ok15 and "DEFERRED" in r15, f"checker indisponível só aceita DEFERRED: {r15}"
        ok16, r16 = set_state("ITEM-3", "DEFERRED", "exec-a", "revisora", "claude-opus-4-8", checker_indisponivel=True)
        assert ok16, f"DEFERRED com checker indisponível deveria passar: {r16}"

        rendered = render()
        assert "ITEM-1" in rendered and "MERGED" in rendered

        print("self-test OK — CLAIMED->BUILDING->CHECKPOINT-READY->UNDER-REVIEW->VERIFIED->MERGED, "
              "maker=checker recusado (mesma lane / mesma família), tag=red exige --human-approved, "
              "checker indisponível só aceita DEFERRED, render ok")
        return 0
    finally:
        _PROJECT_ROOT, _LANES_DIR, BOARD_PATH, RENDER_PATH = orig
        shutil.rmtree(tmp, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lane_board.py")
    sub = p.add_subparsers(dest="cmd")

    c = sub.add_parser("claim")
    c.add_argument("item_id")
    c.add_argument("--lane", required=True)
    c.add_argument("--role", default="executora")
    c.add_argument("--model", required=True)
    c.add_argument("--tag", default="green", choices=["green", "red"])

    s = sub.add_parser("set")
    s.add_argument("item_id")
    s.add_argument("estado")
    s.add_argument("--lane", required=True)
    s.add_argument("--role", required=True)
    s.add_argument("--model", required=True)
    s.add_argument("--evidencia", default="")
    s.add_argument("--verdict-by-lane", default="")
    s.add_argument("--verdict-by-model", default="")
    s.add_argument("--checker-indisponivel", action="store_true")
    s.add_argument("--human-approved", action="store_true")
    s.add_argument("--tag", default="green", choices=["green", "red"])

    st = sub.add_parser("status")
    st.add_argument("item_id", nargs="?")

    sub.add_parser("render")
    p.add_argument("--self-test", action="store_true")
    return p


def main(argv) -> int:
    args = build_parser().parse_args(argv)

    if args.self_test:
        return _self_test()

    if args.cmd == "claim":
        ok, result = set_state(args.item_id, "CLAIMED", args.lane, args.role, args.model, tag=args.tag)
    elif args.cmd == "set":
        ok, result = set_state(
            args.item_id, args.estado, args.lane, args.role, args.model,
            evidencia=args.evidencia, verdict_by_lane=args.verdict_by_lane, verdict_by_model=args.verdict_by_model,
            checker_indisponivel=args.checker_indisponivel, human_approved=args.human_approved, tag=args.tag,
        )
    elif args.cmd == "status":
        events = _read_events(args.item_id)
        print(json.dumps(events, ensure_ascii=False, indent=2))
        return 0
    elif args.cmd == "render":
        text = render()
        RENDER_PATH.parent.mkdir(parents=True, exist_ok=True)
        RENDER_PATH.write_text(text, encoding="utf-8")
        print(text)
        return 0
    else:
        print("uso: claim|set|status|render [...] ou --self-test", file=sys.stderr)
        return 2

    if ok:
        print(json.dumps(result, ensure_ascii=False))
        return 0
    print(f"lane_board: recusado — {result}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
