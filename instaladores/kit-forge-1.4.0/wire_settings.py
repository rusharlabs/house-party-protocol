#!/usr/bin/env python3
"""
wire_settings — patcher idempotente e reversível para settings.json/settings.local.json.

Generaliza o padrão provado de scripts/system/wire_statusline.py, corrigindo o defeito
conhecido (linhas 47-49 daquele script): NUNCA sobrescreve um statusLine ou hook alheio sem
--force. Hooks são sempre aditivos (append numa lista); statusLine é um escalar único — só
é sobrescrito se: (a) já contém o marcador esperado (idempotente, não conta como mudança),
(b) está vazio, ou (c) --force foi passado.

Uso:
    python wire_settings.py --target <settings.json> --spec <wiring-spec.yaml> [--force]
    python wire_settings.py --undo [--target <settings.json>]
    python wire_settings.py --self-test

wiring-spec.yaml:
    statusLine:
      match_substring: "meu_marcador"
      value: {type: command, command: "...", padding: 0}
    hooks:
      Stop:
        matcher: "*"
        match_substring: "meu_marcador"
        value: {type: command, command: "...", timeout: 30}

Toda escrita gera backup `<target>.bak-<timestamp>` ANTES, valida o JSON DEPOIS (rollback
automático se quebrar) e grava `<target>.wire-undo.json` apontando pro backup mais recente,
para o --undo funcionar sem precisar lembrar o timestamp.

Exit: 0 ok (wired ou no-op) · 1 warn (conflito sem --force, nada sobrescrito) · 3 erro.
stdlib + PyYAML. v1.0.0 — 2026-07-10 (FASE 1 · kit-forge)
"""
from __future__ import annotations

import argparse
import datetime
import json
import shutil
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


def _has_marker(hook_list, marker):
    return any(marker in (h.get("command") or "") for entry in hook_list for h in entry.get("hooks", []))


def apply_spec(data: dict, spec: dict, force: bool):
    """Retorna (data, changed_keys, warnings)."""
    changed = []
    warnings = []
    data.setdefault("hooks", {})

    status_spec = spec.get("statusLine")
    if status_spec:
        marker = status_spec["match_substring"]
        cur = data.get("statusLine")
        cur_cmd = (cur or {}).get("command", "") if isinstance(cur, dict) else ""
        if isinstance(cur, dict) and marker in cur_cmd:
            pass  # já wired — idempotente
        elif not cur or force:
            data["statusLine"] = dict(status_spec["value"])
            changed.append("statusLine")
        else:
            warnings.append(f"statusLine já ocupado por outra config; use --force para sobrescrever (atual: {cur_cmd!r})")

    for event, hook_spec in (spec.get("hooks") or {}).items():
        marker = hook_spec["match_substring"]
        arr = data["hooks"].setdefault(event, [])
        if _has_marker(arr, marker):
            continue  # idempotente
        matcher = hook_spec.get("matcher", "*")
        group = next((e for e in arr if e.get("matcher") == matcher), None)
        if group is None:
            group = {"matcher": matcher, "hooks": []}
            arr.append(group)
        group["hooks"].append(dict(hook_spec["value"]))
        changed.append(f"{event}:{marker}")

    return data, changed, warnings


def _write_json_atomic(target: Path, data: dict, backup: Path):
    out = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    target.write_text(out, encoding="utf-8")
    try:
        json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        shutil.copy2(backup, target)
        return False
    return True


def wire(target: Path, spec: dict, force: bool) -> tuple:
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

    new_data, changed, warnings = apply_spec(data, spec, force)

    if not changed:
        backup.unlink(missing_ok=True)
        status = "warn" if warnings else "no-op"
        return (1 if warnings else 0), {"status": status, "changed": [], "warnings": warnings}

    ok = _write_json_atomic(target, new_data, backup)
    if not ok:
        return 3, {"status": "error", "errors": ["JSON ficou inválido após escrita — restaurado do backup"]}

    undo_state = target.with_name(target.name + ".wire-undo.json")
    undo_state.write_text(json.dumps({"target": str(target), "backup": str(backup)}), encoding="utf-8")

    return (1 if warnings else 0), {"status": "wired", "changed": changed, "warnings": warnings, "backup": str(backup)}


def undo(target: Path | None) -> tuple:
    if target is not None:
        undo_state_path = target.with_name(target.name + ".wire-undo.json")
    else:
        return 3, {"status": "error", "errors": ["--undo requer --target"]}

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

    tmp = Path(tempfile.mkdtemp(prefix="wire_settings_selftest_"))
    try:
        target = tmp / "settings-copy.json"
        target.write_text(json.dumps({"hooks": {}}, indent=2), encoding="utf-8")
        original_bytes = target.read_bytes()

        spec = {
            "statusLine": {"match_substring": "kitforge_marker", "value": {"type": "command", "command": "kitforge_marker_cmd", "padding": 0}},
            "hooks": {
                "Stop": {"matcher": "*", "match_substring": "kitforge_marker", "value": {"type": "command", "command": "kitforge_marker_hook", "timeout": 30}},
            },
        }

        code1, report1 = wire(target, spec, force=False)
        assert code1 == 0 and report1["status"] == "wired", f"1a run deveria wired: {report1}"
        bytes_after_run1 = target.read_bytes()
        assert bytes_after_run1 != original_bytes, "1a run deveria mudar o arquivo"

        code2, report2 = wire(target, spec, force=False)
        assert code2 == 0 and report2["status"] == "no-op", f"2a run deveria ser no-op: {report2}"
        bytes_after_run2 = target.read_bytes()
        assert bytes_after_run2 == bytes_after_run1, "2a run deveria ser byte-estável"

        code3, report3 = wire(target, spec, force=False)
        assert code3 == 0 and report3["status"] == "no-op"
        bytes_after_run3 = target.read_bytes()
        assert bytes_after_run3 == bytes_after_run1, "3a run deveria ser byte-estável"

        conflict_target = tmp / "conflict.json"
        conflict_target.write_text(json.dumps({"statusLine": {"command": "outro_dono"}, "hooks": {}}), encoding="utf-8")
        code4, report4 = wire(conflict_target, spec, force=False)
        assert code4 == 1 and report4["warnings"], f"conflito sem --force deveria reportar warning: {report4}"
        conflict_data = json.loads(conflict_target.read_text(encoding="utf-8"))
        assert conflict_data["statusLine"]["command"] == "outro_dono", "sobrescreveu statusLine alheio sem --force!"

        code5, report5 = wire(conflict_target, spec, force=True)
        assert code5 == 0 and report5["status"] == "wired", f"--force deveria sobrescrever: {report5}"
        conflict_data2 = json.loads(conflict_target.read_text(encoding="utf-8"))
        assert conflict_data2["statusLine"]["command"] == "kitforge_marker_cmd"

        undo_code, undo_report = undo(target)
        assert undo_code == 0 and undo_report["status"] == "restored", f"undo falhou: {undo_report}"
        assert target.read_bytes() == original_bytes, "undo não restaurou byte-idêntico ao original"

        print("self-test OK — wire idempotente, conflito sem --force preservado, --force sobrescreve, --undo byte-idêntico")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wire_settings.py")
    p.add_argument("--target", default=None)
    p.add_argument("--spec", default=None)
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

    if not args.target or not args.spec:
        print("uso: wire_settings.py --target <settings.json> --spec <wiring-spec.yaml> [--force]", file=sys.stderr)
        return 3

    if yaml is None:
        print("wire_settings: PyYAML ausente", file=sys.stderr)
        return 3

    spec_path = Path(args.spec)
    if not spec_path.exists():
        print(f"wire_settings: spec não encontrado: {spec_path}", file=sys.stderr)
        return 3
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}

    code, report = wire(Path(args.target), spec, args.force)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
