#!/usr/bin/env python3
"""
wire_statusline (health-kit) — arma a statusLine deste kit em settings.json/settings.local.json,
de forma IDEMPOTENTE e REVERSÍVEL.

Vendoriza o mecanismo provado de wire_settings.py (kit-forge): NUNCA sobrescreve um
statusLine alheio sem --force. Backup automático antes de escrever, validação do JSON
depois (rollback automático se quebrar), e undo-state gravado para `--undo` funcionar
sem precisar lembrar o timestamp do backup.

Por que um script novo em vez do `scripts/system/wire_statusline.py` legado da casa:
aquele script tinha o defeito de sobrescrever um statusLine já configurado por outra
ferramenta sem perguntar. Este NUNCA faz isso (ver `apply_spec`).

Uso:
    python wire_statusline.py --target <settings.json> [--force]
    python wire_statusline.py --undo [--target <settings.json>]
    python wire_statusline.py --self-test

O comando wired chama `statusline/statusline.py --statusline` (path resolvido a
partir da localização deste script — funciona com ou sem `${CLAUDE_PLUGIN_ROOT}`).

Exit: 0 ok (wired ou no-op) · 1 warn (conflito sem --force, nada sobrescrito) · 3 erro.
stdlib apenas (sem PyYAML — a spec de wiring é fixa, nao vem de YAML externo).
v1.0.0 — 2026-07-10 (health-kit · idempotente/--undo, modelado em kit-forge/wire_settings.py)
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import sys
from pathlib import Path

_MARKER = "--kit=health-kit"


def _statusline_cmd() -> str:
    # marca a origem com um TOKEN FIXO como argumento extra (ignorado por statusline.py,
    # que so olha sys.argv[1]) — nao usar o path do script como marcador: a pasta emitida
    # e versionada (health-kit-1.0.0), pode ser renomeada pelo usuario, e um
    # path-substring colidiria com o statusline de outro kit que tambem termine em
    # ".../statusline/statusline.py" (ex.: operator-kit). Um argv extra funciona igual
    # em cmd.exe e em shells POSIX — sem depender de sintaxe de env-var-prefix (que
    # cmd.exe nao entende).
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        target = f"{Path(plugin_root).as_posix()}/statusline/statusline.py"
    else:
        script_dir = Path(__file__).resolve().parent.parent  # .../health-kit(-X.Y.Z)
        target = (script_dir / "statusline" / "statusline.py").as_posix()
    return f"python {target} --statusline {_MARKER}"


def _wiring_spec() -> dict:
    return {
        "match_substring": _MARKER,
        "value": {"type": "command", "command": _statusline_cmd(), "padding": 0},
    }


def apply_spec(data: dict, spec: dict, force: bool):
    """Retorna (data, changed:bool, warning:str|None). Só toca 'statusLine' (sem hooks)."""
    marker = spec["match_substring"]
    cur = data.get("statusLine")
    cur_cmd = (cur or {}).get("command", "") if isinstance(cur, dict) else ""
    if isinstance(cur, dict) and marker in cur_cmd:
        return data, False, None  # já wired — idempotente
    if not cur or force:
        data["statusLine"] = dict(spec["value"])
        return data, True, None
    return data, False, f"statusLine já ocupado por outra config; use --force para sobrescrever (atual: {cur_cmd!r})"


def _write_json_atomic(target: Path, data: dict, backup: Path) -> bool:
    out = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    target.write_text(out, encoding="utf-8")
    try:
        json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        shutil.copy2(backup, target)
        return False
    return True


def wire(target: Path, force: bool) -> tuple:
    if not target.exists():
        return 3, {"status": "error", "errors": [f"target não existe: {target}"]}

    raw = target.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return 3, {"status": "error", "errors": [f"JSON inválido em {target}: {e}"]}

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S%f")
    backup = target.with_name(target.name + f".bak-{stamp}")
    shutil.copy2(target, backup)

    new_data, changed, warning = apply_spec(data, _wiring_spec(), force)

    if not changed:
        backup.unlink(missing_ok=True)
        status = "warn" if warning else "no-op"
        return (1 if warning else 0), {"status": status, "warnings": [warning] if warning else []}

    ok = _write_json_atomic(target, new_data, backup)
    if not ok:
        return 3, {"status": "error", "errors": ["JSON ficou inválido após escrita — restaurado do backup"]}

    undo_state = target.with_name(target.name + ".wire-undo.json")
    undo_state.write_text(json.dumps({"target": str(target), "backup": str(backup)}), encoding="utf-8")

    return 0, {"status": "wired", "command": new_data["statusLine"]["command"], "backup": str(backup)}


def undo(target: Path | None) -> tuple:
    if target is None:
        return 3, {"status": "error", "errors": ["--undo requer --target"]}

    undo_state_path = target.with_name(target.name + ".wire-undo.json")
    if not undo_state_path.exists():
        return 3, {"status": "error", "errors": [f"nenhum estado de undo encontrado: {undo_state_path}"]}

    state = json.loads(undo_state_path.read_text(encoding="utf-8"))
    backup = Path(state["backup"])
    tgt = Path(state["target"])
    if not backup.exists():
        return 3, {"status": "error", "errors": [f"backup não existe mais: {backup}"]}

    shutil.copy2(backup, tgt)
    undo_state_path.unlink(missing_ok=True)
    return 0, {"status": "restored", "target": str(tgt), "from_backup": str(backup)}


def _self_test() -> int:
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="wire_statusline_selftest_"))
    try:
        target = tmp / "settings-copy.json"
        target.write_text(json.dumps({"hooks": {}}, indent=2), encoding="utf-8")
        original_bytes = target.read_bytes()

        code1, report1 = wire(target, force=False)
        assert code1 == 0 and report1["status"] == "wired", f"1a run deveria wired: {report1}"
        assert _MARKER in report1["command"]
        bytes_after_run1 = target.read_bytes()
        assert bytes_after_run1 != original_bytes, "1a run deveria mudar o arquivo"

        code2, report2 = wire(target, force=False)
        assert code2 == 0 and report2["status"] == "no-op", f"2a run deveria ser no-op: {report2}"
        assert target.read_bytes() == bytes_after_run1, "2a run deveria ser byte-estável"

        conflict_target = tmp / "conflict.json"
        conflict_target.write_text(json.dumps({"statusLine": {"command": "outro_dono"}, "hooks": {}}), encoding="utf-8")
        code3, report3 = wire(conflict_target, force=False)
        assert code3 == 1 and report3["warnings"], f"conflito sem --force deveria warn: {report3}"
        conflict_data = json.loads(conflict_target.read_text(encoding="utf-8"))
        assert conflict_data["statusLine"]["command"] == "outro_dono", "sobrescreveu statusLine alheio sem --force!"

        code4, report4 = wire(conflict_target, force=True)
        assert code4 == 0 and report4["status"] == "wired", f"--force deveria sobrescrever: {report4}"
        conflict_data2 = json.loads(conflict_target.read_text(encoding="utf-8"))
        assert _MARKER in conflict_data2["statusLine"]["command"]

        undo_code, undo_report = undo(target)
        assert undo_code == 0 and undo_report["status"] == "restored", f"undo falhou: {undo_report}"
        assert target.read_bytes() == original_bytes, "undo não restaurou byte-idêntico ao original"

        print("self-test OK — wire idempotente, conflito sem --force preservado, --force sobrescreve, --undo byte-idêntico")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wire_statusline.py")
    p.add_argument("--target", default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--undo", action="store_true")
    p.add_argument("--self-test", action="store_true")
    return p


def main(argv) -> int:
    args = build_parser().parse_args(argv)

    if args.self_test:
        return _self_test()

    if args.undo:
        target = Path(args.target) if args.target else None
        code, report = undo(target)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return code

    if not args.target:
        print("uso: wire_statusline.py --target <settings.json> [--force]", file=sys.stderr)
        return 3

    code, report = wire(Path(args.target), args.force)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
