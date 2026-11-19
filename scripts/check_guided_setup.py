#!/usr/bin/env python3
"""Exercise real bootstrap preparation for both hosts without activating either host."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def files(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", help="dedicated empty directory; artifacts are preserved")
    args = parser.parse_args()
    source = Path(__file__).resolve().parent.parent
    base = Path(args.workdir).resolve() if args.workdir else Path(tempfile.mkdtemp(prefix="hpp-guided-setup-")).resolve()
    base.mkdir(parents=True, exist_ok=True)
    if list(base.iterdir()):
        raise SystemExit("Use an empty workdir; no previous artifacts were changed.")
    manifest = json.loads((source / "hpp.manifest.json").read_text(encoding="utf-8"))
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    results = []
    source_before = subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"], env=env)
    for host in ["claude-code", "codex"]:
        target = base / (host + " project with spaces")
        target.mkdir()
        command = [sys.executable, "-I", "-B", str(source / "scripts/setup_hpp.py"), "--host", host,
                   "--target", str(target), "--all-compatible", "--state-dir", str(base / "trusted-state"), "--json"]
        plan = subprocess.run(command, env=env, capture_output=True, text=True, encoding="utf-8", timeout=300)
        assert plan.returncode == 0, plan.stdout + plan.stderr
        assert not list(target.iterdir()), "Plan wrote into target"
        for phase, argv in [("apply", [*command, "--apply"]), ("rerun", [*command, "--apply"])]:
            before = files(target)
            result = subprocess.run(argv, env=env, capture_output=True, text=True, encoding="utf-8", timeout=1800)
            (base / f"{host}-{phase}.stdout.json").write_text(result.stdout, encoding="utf-8")
            (base / f"{host}-{phase}.stderr.log").write_text(result.stderr, encoding="utf-8")
            assert result.returncode == 0, result.stdout + result.stderr[-2500:]
            report = json.loads(result.stdout)
            assert report["status"] == "prepared"
            expected = [m["id"] for m in manifest["modules"] if m["hosts"][host] != "unsupported"]
            assert report["setup"]["selected_modules"] == expected
            if phase == "rerun":
                assert report["rerun_verified"] and files(target) == before
        # No host or native activation command is invoked: this checks the installed CLI/environment.
        doctor = subprocess.run([sys.executable, "-I", "-B", str(target / ".hpp/run.py"), "hpp", "doctor"],
                                cwd=target, env=env, capture_output=True, text=True, encoding="utf-8", timeout=120)
        (base / f"{host}-doctor.log").write_text(doctor.stdout + doctor.stderr, encoding="utf-8")
        assert doctor.returncode == 0, doctor.stdout + doctor.stderr
        # Exercise the actual native launchers, not only their Python functions.
        suffix = ".exe" if os.name == "nt" else ""
        managed = target / ".hpp"
        native = subprocess.run([str(managed / "bin" / ("hpp" + suffix)), "doctor"], cwd=target,
                                env=env, capture_output=True, text=True, encoding="utf-8", timeout=120)
        assert native.returncode == 0, native.stdout + native.stderr
        router_file = managed / "runtime-router.json"
        routed_env = {**env, "HPP_RUNTIME_ROUTER_DATA": str(router_file),
                      "HPP_RUNTIME_ROUTER_SHA256": hashlib.sha256(router_file.read_bytes()).hexdigest(),
                      "HPP_APPLICATION_PYTHON": sys.executable, "HPP_APPLICATION_PYTHON3": sys.executable,
                      "HPP_APPLICATION_ENV": json.dumps({"PATH": env.get("PATH"), "PYTHONPATH": None,
                                                         "PYTHONHOME": None, "VIRTUAL_ENV": env.get("VIRTUAL_ENV")})}
        for name in ["python", "python3"]:
            routed = subprocess.run([str(managed / "bin" / (name + suffix)), "-m", "hpp", "doctor"],
                                    cwd=target, env=routed_env, capture_output=True, text=True, encoding="utf-8", timeout=120)
            assert routed.returncode == 0, routed.stdout + routed.stderr
            application = subprocess.run([str(managed / "bin" / (name + suffix)), "-c",
                                          "import sys;print(sys.executable);print(sys.prefix)"],
                                         cwd=target, env=routed_env, capture_output=True, text=True, encoding="utf-8", timeout=120)
            assert application.returncode == 0, application.stderr
            assert Path(application.stdout.splitlines()[0]).absolute() == Path(sys.executable).absolute()
            assert Path(application.stdout.splitlines()[1]).absolute() == Path(sys.prefix).absolute()
        dedicated = subprocess.run([str(managed / "bin" / ("hpp-python" + suffix)), "-c",
                                    "import yaml,sys;print(sys.prefix)"], cwd=target, env=env,
                                   capture_output=True, text=True, encoding="utf-8", timeout=120)
        assert dedicated.returncode == 0, dedicated.stderr
        assert Path(dedicated.stdout.strip()).absolute() == (managed / "venv").absolute()
        verified = subprocess.run([*command, "--apply"], env=env, capture_output=True, text=True, encoding="utf-8", timeout=300)
        assert verified.returncode == 0, verified.stdout + verified.stderr
        assert json.loads(verified.stdout)["rerun_verified"]
        assert not (target / ".claude/settings.json").exists()
        assert not (target / ".claude/settings.local.json").exists()
        assert not (target / ".codex/config.toml").exists()
        results.append({"host": host, "modules": len(expected), "plan_zero_target_writes": True,
                        "bootstrap_prepared": True, "rerun_no_changes": True, "installed_doctor_exit": 0,
                        "native_launchers_verified": True, "application_interpreter_preserved": True,
                        "host_activation_executed": False})
    assert subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"], env=env) == source_before
    summary = {"version": manifest["product_version"], "python": sys.version, "results": results,
               "source_status_unchanged": True, "evidence": str(base)}
    (base / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
