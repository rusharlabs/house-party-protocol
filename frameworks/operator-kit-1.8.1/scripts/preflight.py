#!/usr/bin/env python3
"""Validates local pre-conditions before done_gate.

Exit: 0 ready -- 2 blocking pre-condition -- 3 usage error.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _git_repo(project: Path) -> tuple[bool, str]:
    try:
        probe = subprocess.run(
            ["git", "-C", str(project), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    detail = (probe.stdout or probe.stderr).strip()
    return probe.returncode == 0 and probe.stdout.strip() == "true", detail


def _settings_writable(project: Path) -> tuple[bool, str]:
    settings = project / ".claude" / "settings.local.json"
    probe = settings if settings.exists() else settings.parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    writable = probe.exists() and os.access(probe, os.W_OK)
    return writable, f"destino={settings}; base_testada={probe}"


def inspect(project: Path) -> dict:
    git_ok, git_detail = _git_repo(project)
    settings_ok, settings_detail = _settings_writable(project)
    checks = {
        "python": {
            "ok": sys.version_info >= (3, 10),
            "detail": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        },
        "pyyaml": {
            "ok": importlib.util.find_spec("yaml") is not None,
            "detail": "módulo yaml importável" if importlib.util.find_spec("yaml") else "módulo yaml ausente",
        },
        "git_repo": {"ok": git_ok, "detail": git_detail},
        "settings_writable": {"ok": settings_ok, "detail": settings_detail},
    }
    return {"status": "ok" if all(item["ok"] for item in checks.values()) else "block", "project": str(project), "checks": checks}


def _self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="hpp_preflight_") as tmp:
        root = Path(tmp)
        before = inspect(root)
        assert before["checks"]["git_repo"]["ok"] is False
        (root / ".claude").mkdir()
        init = subprocess.run(["git", "init", str(root)], capture_output=True, text=True, encoding="utf-8", timeout=10)
        assert init.returncode == 0, init.stderr
        after = inspect(root)
        assert after["checks"]["python"]["ok"]
        assert after["checks"]["pyyaml"]["ok"]
        assert after["checks"]["git_repo"]["ok"]
        assert after["checks"]["settings_writable"]["ok"]
        assert after["status"] == "ok"
    print("self-test OK — bloqueia fora de git e aprova Python/PyYAML/git/settings gravável")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=".")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    project = Path(args.project).resolve()
    if not project.is_dir():
        print(json.dumps({"status": "error", "detail": f"diretório ausente: {project}"}, ensure_ascii=False))
        return 3
    report = inspect(project)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
