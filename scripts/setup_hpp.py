#!/usr/bin/env python3
"""Prepare a project-local Python environment and invoke the offline HPP setup.

Run from a full, versioned HPP checkout. The default is a read-only plan;
--apply installs hash-pinned bootstrap dependencies and the local CLI, then
delegates module installation to ``hpp setup``. Host activation is separate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any
import venv

SCHEMA = "hpp.bootstrap/v1"
APP_ENV_KEYS = ("PATH", "VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE", "PYTHONINSPECT", "PYTHONWARNINGS", "PYTHONDONTWRITEBYTECODE")
RUNNER = r'''"""Use the setup environment; activation remains an explicit user invocation."""
import sys
if not sys.flags.isolated:
    raise SystemExit("Use python -I -B .hpp/run.py (python3 on macOS).")
# Do not import modules from the consumer's .hpp directory.
launcher_dir = __file__.replace("\\", "/").rsplit("/", 1)[0]
sys.path = [p for p in sys.path if p and p.replace("\\", "/").rstrip("/") != launcher_dir]
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess

root = Path(__file__).resolve().parent
data = json.loads((root / "bootstrap-runner.json").read_text(encoding="utf-8"))
if hashlib.sha256((root / "bootstrap-runner.json").read_bytes()).hexdigest() != EXPECTED_DATA:
    raise SystemExit("Setup launcher data changed; review and rerun setup.")
if Path(data["target"]).resolve() != root.parent:
    raise SystemExit("Setup launcher belongs to a different project.")
python = root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
trusted = json.loads(Path(data["ownership_state"]).read_text(encoding="utf-8"))
if (trusted.get("identity") != data["identity"] or
        trusted.get("receipt_sha256") != hashlib.sha256((root / "bootstrap-receipt.json").read_bytes()).hexdigest()):
    raise SystemExit("Bootstrap ownership state differs; review and rerun setup.")
inventory = {}
stack = [root / "venv"]
while stack:
    directory = stack.pop()
    for path in directory.iterdir():
        info = path.lstat()
        name = path.relative_to(root / "venv").as_posix()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            if not path.resolve().is_relative_to((root / "venv").resolve()):
                raise SystemExit("Environment has an external link.")
            inventory[name] = "link:" + os.readlink(path)
        elif stat.S_ISDIR(info.st_mode):
            stack.append(path)
        elif stat.S_ISREG(info.st_mode):
            inventory[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            raise SystemExit("Environment has a special file.")
if inventory != trusted.get("environment_files"):
    raise SystemExit("Environment files changed; existing Python was not executed.")
for name, digest in trusted.get("owned_files", {}).items():
    if Path(name).is_absolute() or ".." in Path(name).parts:
        raise SystemExit("Invalid launcher ownership path.")
    path = root / name
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise SystemExit("A managed launcher changed; it was not executed.")
shim_inventory = {}
for path in (root / "bin").iterdir():
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise SystemExit("Shim directory contains an unexpected entry.")
    shim_inventory[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
if shim_inventory != trusted.get("shim_files"):
    raise SystemExit("Shim directory changed; it was not executed.")
env = dict(os.environ)
app_keys = ("PATH", "VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE", "PYTHONINSPECT", "PYTHONWARNINGS", "PYTHONDONTWRITEBYTECODE")
if env.get("HPP_RUNTIME_ROUTER_DATA") == str(root / "runtime-router.json") and env.get("HPP_APPLICATION_ENV"):
    original = json.loads(env["HPP_APPLICATION_ENV"])
    if not isinstance(original, dict) or set(original) - set(app_keys):
        raise SystemExit("Invalid application environment snapshot.")
    for key, value in original.items():
        if value is None:
            env.pop(key, None)
        elif isinstance(value, str):
            env[key] = value
        else:
            raise SystemExit("Invalid application environment value.")
original = {key: env.get(key) for key in app_keys}
for name in ("python", "python3"):
    executable = shutil.which(name, path=env.get("PATH", "")) or sys.executable
    env["HPP_APPLICATION_PYTHON" + ("3" if name == "python3" else "")] = str(Path(executable).absolute())
env["HPP_APPLICATION_ENV"] = json.dumps(original)
env["PATH"] = str(root / "bin") + os.pathsep + env.get("PATH", "")
env["HPP_RUNTIME_ROUTER_DATA"] = str(root / "runtime-router.json")
env["HPP_RUNTIME_ROUTER_SHA256"] = data["router_sha256"]
env["HPP_PYRUN_NO_VENV"] = "1"

def host_command(name):
    # Prefer native executables. Known npm shims are run through Node, never cmd.exe.
    executable = shutil.which(name + ".exe", path=env["PATH"]) if os.name == "nt" else None
    executable = executable or shutil.which(name, path=env["PATH"])
    if not executable:
        raise SystemExit("Host CLI is missing: " + name)
    if os.name == "nt" and Path(executable).suffix.lower() in {".cmd", ".bat", ".ps1"}:
        package = "@openai/codex/bin/codex.js" if name == "codex" else "@anthropic-ai/claude-code/cli.js"
        entry = Path(executable).parent / "node_modules" / package
        node = shutil.which("node.exe", path=env["PATH"])
        if not node or not entry.is_file():
            raise SystemExit("Use a native host executable or its standard npm installation.")
        return [node, str(entry)]
    return [executable]

mode = sys.argv[1] if len(sys.argv) > 1 else "host"
if mode == "hpp":
    command = [str(python), "-I", "-B", "-m", "hpp", *sys.argv[2:]]
elif mode == "host":
    command = [*host_command("claude" if data["host"] == "claude-code" else "codex"), *sys.argv[2:]]
elif mode == "activate":
    if data["host"] != "claude-code":
        raise SystemExit("Codex skills/runtime are installed locally; Claude hooks remain off.")
    for item in data["source_fingerprints"]:
        path = Path(data["source"]) / item["path"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise SystemExit("Distribution changed; review and rerun setup before activation.")
    # Recheck module bytes without executing any host command first.
    probe = subprocess.run([str(python), "-I", "-B", "-m", "hpp", *data["setup_args"], "--json"],
                           cwd=root.parent, env=env, capture_output=True, text=True, encoding="utf-8")
    if probe.returncode:
        print(probe.stdout)
        raise SystemExit("Module verification refused activation.")
    for argv in data["activation_commands"]:
        if not argv or argv[0] != "claude" or argv[1:2] != ["plugin"] or any(x in argv for x in ["--yes", "-y"]):
            raise SystemExit("Invalid activation command.")
        result = subprocess.run([*host_command("claude"), *argv[1:]], cwd=root.parent, env=env)
        if result.returncode:
            raise SystemExit(result.returncode)
    print("Native plugin commands succeeded. Restart the host and verify its plugin/hook state.")
    raise SystemExit(0)
else:
    raise SystemExit("Usage: python -I -B .hpp/run.py [host|hpp <args>|activate] (python3 on macOS)")
raise SystemExit(subprocess.run(command, cwd=root.parent, env=env).returncode)
'''


def _safe_path(path: Path) -> None:
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("setup refuses symbolic links or reparse points in managed paths")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, data: dict[str, Any]) -> None:
    _safe_path(path)
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent,
                                     prefix=".hpp-setup-", delete=False) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)


def _environment(python: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PIP_") and k not in {"PYTHONPATH", "PYTHONHOME"}}
    env.update(PIP_CONFIG_FILE=os.devnull, PIP_DISABLE_PIP_VERSION_CHECK="1", PYTHONDONTWRITEBYTECODE="1",
               VIRTUAL_ENV=str(python.parent.parent))
    env["PATH"] = str(python.parent) + os.pathsep + env.get("PATH", "")
    return env


def _inventory(root: Path) -> dict[str, str]:
    """Hash a managed environment without following links or accepting special files."""
    result = {}
    stack = [root]
    while stack:
        directory = stack.pop()
        for path in directory.iterdir():
            info = path.lstat()
            name = path.relative_to(root).as_posix()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                if not path.resolve().is_relative_to(root.resolve()):
                    raise ValueError("environment contains an external link")
                result[name] = "link:" + os.readlink(path)
            elif stat.S_ISDIR(info.st_mode):
                stack.append(path)
            elif stat.S_ISREG(info.st_mode):
                result[name] = _digest(path)
            else:
                raise ValueError("environment contains a special file")
            if len(result) > 30000:
                raise ValueError("environment inventory is too large")
    return result


def _read_object(path: Path) -> dict[str, Any]:
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("setup receipt is too large")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("setup receipt must be an object")
    return value


def _untracked_managed(target: Path) -> None:
    """Never execute a Python environment delivered as consumer repository content."""
    git = shutil.which("git")
    if not git:
        raise ValueError("Git must be installed before running the bootstrapper")
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    result = subprocess.run([git, "--no-optional-locks", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=",
                             "-C", str(target), "ls-files", "-z", "--", ".hpp/venv", ".hpp/run.py", ".hpp/bootstrap*", ".hpp/bin", ".hpp/runtime-router.json"],
                            env=env, capture_output=True, timeout=30)
    if result.returncode == 0 and result.stdout:
        raise ValueError("bootstrap environment, launchers and receipts must not be tracked by the consumer repository")


def _build_input(source: Path, managed: Path) -> Path:
    """Build the CLI from a disposable copy, keeping the release checkout unchanged."""
    build = Path(tempfile.mkdtemp(prefix="bootstrap-build-", dir=managed))
    for name in ("pyproject.toml", "README.md", "LICENSE"):
        path = source / name
        _safe_path(path)
        shutil.copyfile(path, build / name)
    stack = [source / "hpp"]
    while stack:
        directory = stack.pop()
        _safe_path(directory)
        for path in directory.iterdir():
            _safe_path(path)
            if path.name in {"__pycache__", ".pytest_cache"}:
                continue
            if path.is_dir():
                stack.append(path)
            elif path.is_file():
                rel = path.relative_to(source)
                if path.suffix == ".py" or rel.as_posix() == "hpp/hpp.manifest.json" or rel.parts[:3] == ("hpp", "examples", "reliable-coding"):
                    destination = build / rel
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, destination)
    return build


def _no_core_bytecode(source: Path) -> None:
    stack = [source / "hpp"]
    while stack:
        directory = stack.pop()
        _safe_path(directory)
        for path in directory.iterdir():
            _safe_path(path)
            if path.is_file() and path.suffix.lower() in {".pyc", ".pyo"}:
                raise ValueError("remove untrusted bytecode from the release copy before setup (nothing was deleted)")
            if path.is_dir():
                stack.append(path)


def _write_posix_shims(python: Path, directory: Path) -> None:
    """Quote literal paths before the shell sees interpreter or launcher names."""
    interpreter = shlex.quote(python.absolute().as_posix())
    entries = [("hpp", "hpp.cli", "main"), ("hpp-python", "hpp.runtime", "python_main"),
               ("python", "hpp.runtime", "router_main"), ("python3", "hpp.runtime", "router_main")]
    for name, module, function in entries:
        launcher = directory / name
        code = f"import sys;sys.argv=sys.argv[1:];from {module} import {function};sys.exit({function}())"
        script = f'#!/bin/sh\nexec {interpreter} -I -B -c {shlex.quote(code)} {shlex.quote(launcher.absolute().as_posix())} "$@"\n'
        launcher.write_text(script, encoding="utf-8", newline="\n")
        launcher.chmod(0o755)


def _make_shims(python: Path, directory: Path, env: dict[str, str], source: Path) -> None:
    directory.mkdir(exist_ok=True)
    if os.name != "nt":
        _write_posix_shims(python, directory)
        return
    code = ("from pip._vendor.distlib.scripts import ScriptMaker,enquote_executable;import sys;"
            "m=ScriptMaker(None,sys.argv[1]);m.executable=enquote_executable(sys.executable);m.variants={''};m.clobber=True;"
            "[m.make(s,{'interpreter_args':['-I']}) for s in "
            "['hpp = hpp.cli:main','hpp-python = hpp.runtime:python_main',"
            "'python = hpp.runtime:router_main','python3 = hpp.runtime:router_main']]")
    result = subprocess.run([str(python), "-I", "-B", "-c", code, str(directory)], cwd=source, env=env,
                            stdin=subprocess.DEVNULL, stdout=sys.stderr, stderr=sys.stderr, timeout=60)
    if result.returncode:
        raise ValueError("isolated command launchers could not be created")


def _core_fingerprint(source: Path) -> str:
    paths = [source / "pyproject.toml", source / "scripts/setup_hpp.py"]
    paths += [p for p in (source / "hpp").rglob("*") if p.is_file()]
    return hashlib.sha256(json.dumps({p.relative_to(source).as_posix(): _digest(p) for p in sorted(paths)}, sort_keys=True).encode()).hexdigest()


def _setup_args(args: argparse.Namespace, source: Path, target: Path) -> list[str]:
    result = ["setup", "--source", str(source), "--target", str(target), "--host", args.host]
    if args.all_compatible:
        result.append("--all-compatible")
    elif args.modules:
        result += ["--modules", args.modules]
    else:
        result += ["--bundle", args.bundle or "reliable-coding"]
    return result


def _probe(source: Path, arguments: list[str]) -> dict[str, Any]:
    # -I avoids consumer/PYTHONPATH shadowing; only this explicit trusted release is imported.
    code = "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('hpp',run_name='__main__')"
    result = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(source), *arguments, "--json"],
                            cwd=source, capture_output=True, text=True, encoding="utf-8", timeout=180)
    try:
        report = json.loads(result.stdout)
    except ValueError:
        raise ValueError("offline setup did not return a readable plan") from None
    if result.returncode:
        raise ValueError("offline setup refused the plan: " + str(report.get("error", report.get("status", "error"))))
    return report


def run(args: argparse.Namespace, source: Path | None = None) -> dict[str, Any]:
    source = (source or Path(__file__).resolve().parent.parent).absolute()
    target = Path(args.target).expanduser().absolute()
    _safe_path(source)
    _safe_path(target)
    if not target.is_dir() or target == source or source in target.parents:
        raise ValueError("choose an existing consumer project outside the HPP distribution")
    if sys.version_info < (3, 10):
        raise ValueError("Python 3.10 or newer is required")
    managed = target / ".hpp"
    environment = managed / "venv"
    owner_path = managed / "bootstrap-receipt.json"
    runner_path = managed / "run.py"
    data_path = managed / "bootstrap-runner.json"
    router_path = managed / "runtime-router.json"
    shim_dir = managed / "bin"
    shim_names = [name + (".exe" if os.name == "nt" else "") for name in ["hpp", "hpp-python", "python", "python3"]]
    owned_names = {"run.py", "bootstrap-runner.json", "runtime-router.json", *("bin/" + name for name in shim_names)}
    for path in (managed, environment, owner_path, runner_path, data_path, router_path, shim_dir):
        _safe_path(path)
    _untracked_managed(target)
    for path in (source / "pyproject.toml", source / ".github/requirements/setup.txt", source / ".github/requirements/build.txt"):
        _safe_path(path)
        if not path.is_file():
            raise ValueError("use a complete HPP checkout, including bootstrap requirements")
    arguments = _setup_args(args, source, target)
    _no_core_bytecode(source)
    plan = _probe(source, arguments)
    identity = hashlib.sha256(json.dumps({"version": plan.get("product_version", plan.get("version")),
                                        "host": args.host, "modules": plan["selected_modules"],
                                        "requirements": _digest(source / ".github/requirements/setup.txt"),
                                        "core": _core_fingerprint(source),
                                        "build": _digest(source / ".github/requirements/build.txt")}, sort_keys=True).encode()).hexdigest()
    state_dir = Path(args.state_dir).expanduser().absolute() if getattr(args, "state_dir", None) else Path.home() / ".hpp-setup-state"
    _safe_path(state_dir)
    if state_dir == target or target in state_dir.parents:
        raise ValueError("ownership state must live outside the consumer project")
    state_path = state_dir / (hashlib.sha256(str(target).encode()).hexdigest() + ".json")
    _safe_path(state_path)
    trusted = _read_object(state_path) if state_path.exists() else None
    owner = None
    if owner_path.exists():
        owner = _read_object(owner_path)
        if owner.get("schema") != SCHEMA or owner.get("identity") != identity:
            raise ValueError("existing bootstrap differs; review its receipt before changing the environment")
        if (not trusted or trusted.get("schema") != SCHEMA or trusted.get("identity") != identity
                or trusted.get("receipt_sha256") != _digest(owner_path)):
            raise ValueError("project receipt has no matching trusted local ownership state; existing files were not adopted")
        owned_files = owner.get("owned_files", {})
        if not isinstance(owned_files, dict) or set(owned_files) - owned_names:
            raise ValueError("invalid bootstrap file ownership")
        if owner.get("status") == "prepared" and set(owned_files) != owned_names:
            raise ValueError("prepared launcher inventory is incomplete")
        for name, digest in owner.get("owned_files", {}).items():
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("invalid bootstrap file digest")
            path = managed / name
            if not path.is_file() or _digest(path) != digest:
                raise ValueError("a managed launcher was edited; nothing was overwritten")
        if owner.get("status") == "prepared" and not (environment.is_dir() and (environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")).is_file()):
            raise ValueError("prepared environment is missing; it was not declared verified")
        if environment.exists() and _inventory(environment) != trusted.get("environment_files"):
            raise ValueError("managed environment changed; existing Python was not executed")
        if shim_dir.exists() and _inventory(shim_dir) != trusted.get("shim_files"):
            raise ValueError("managed shim directory changed; nothing was executed")
        for name in owned_names:
            if (managed / name).exists() and name not in owned_files:
                raise ValueError("setup refuses an unowned launcher file")
    elif environment.exists() or runner_path.exists() or data_path.exists() or router_path.exists() or shim_dir.exists():
        raise ValueError("setup will not adopt an existing unowned environment or launcher")
    report: dict[str, Any] = {"schema": SCHEMA, "status": "planned", "exit_code": 0, "identity": identity,
                              "host": args.host, "setup": plan, "network_on_apply": "public PyPI, hash-pinned bootstrap wheels",
                              "environment": ".hpp/venv", "ownership_state": str(state_path),
                              "planned_managed_paths": [".hpp/venv", ".hpp/bin", ".hpp/runtime-router.json", ".hpp/bootstrap-build-<unique>/", ".hpp/bootstrap-receipt.json", ".hpp/bootstrap-runner.json", ".hpp/run.py"],
                              "bootstrap_dependencies": {"packages": ["setuptools==84.1.0", "PyYAML==6.0.3", "local HPP CLI (no dependencies)"],
                                "setup_requirements_sha256": _digest(source / ".github/requirements/setup.txt"),
                                "build_requirements_sha256": _digest(source / ".github/requirements/build.txt")},
                              "host_activation": "manual", "owned_files": {}}
    if not args.apply:
        return report
    if owner and owner.get("status") == "prepared":
        return {**owner, "setup": plan, "rerun_verified": True}
    managed.mkdir(exist_ok=True)
    # Record ownership before creating the environment so a failed preparation can resume.
    report.update(status="preparing", exit_code=2, owned_files=(owner or {}).get("owned_files", {}))
    _write(owner_path, report)
    state_dir.mkdir(parents=True, exist_ok=True)
    _write(state_path, {"schema": SCHEMA, "identity": identity, "receipt_sha256": _digest(owner_path),
                        "environment_files": trusted.get("environment_files", {}) if trusted else {}})
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    try:
        if not python.is_file():
            venv.EnvBuilder(with_pip=True, symlinks=False).create(environment)
        env = _environment(python)
        build = _build_input(source, managed)
        report["build_input"] = build.name
        steps = [
            [str(python), "-I", "-B", "-m", "pip", "install", "--no-cache-dir", "--index-url", "https://pypi.org/simple",
             "--require-hashes", "--only-binary=:all:", "-r", str(source / ".github/requirements/setup.txt")],
            [str(python), "-I", "-B", "-m", "pip", "install", "--no-deps", "--no-build-isolation", str(build)],
        ]
        for command in steps:
            result = subprocess.run(command, cwd=source, env=env, stdin=subprocess.DEVNULL,
                                    stdout=sys.stderr, stderr=sys.stderr, timeout=600)
            if result.returncode:
                raise ValueError("environment preparation failed; receipt preserved for inspection and retry")
        result = subprocess.run([str(python), "-I", "-B", "-m", "hpp", *arguments, "--apply", "--json"],
                                cwd=source, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, encoding="utf-8", timeout=1800)
        setup = json.loads(result.stdout)
        report["setup"] = setup
        if result.returncode or setup.get("status") != "prepared" or setup.get("exit_code") != 0 or setup.get("selected_modules") != plan["selected_modules"]:
            raise ValueError("module setup did not complete; inspect the module receipt before retrying")
        try:
            _make_shims(python, shim_dir, env, source)
        finally:
            # Preserve ownership of a caught partial launcher build for retry.
            for name in shim_names:
                path = shim_dir / name
                _safe_path(path)
                if path.is_file():
                    report["owned_files"]["bin/" + name] = _digest(path)
        if set(_inventory(shim_dir)) != set(shim_names):
            raise ValueError("isolated launcher inventory is incomplete or contains unexpected files")
        fingerprints = []
        manifest = json.loads((source / "hpp.manifest.json").read_text(encoding="utf-8"))
        selected = set(setup["selected_modules"])
        paths = ["hpp.manifest.json", "marketplace.json", ".claude-plugin/marketplace.json"]
        paths += [module["path"] + "/CHECKSUMS.txt" for module in manifest["modules"] if module["id"] in selected]
        for name in paths:
            path = source / name
            if path.is_file():
                fingerprints.append({"path": name, "sha256": _digest(path)})
        router = {"schema": "hpp.runtime-router/v1", "source": str(source), "managed_python": str(python),
                  "hpp_runtime_roots": [str(target / ".agents/hpp"), *[str(source / m["path"]) for m in manifest["modules"] if m["id"] in selected]]}
        _write(router_path, router)
        report["owned_files"]["runtime-router.json"] = _digest(router_path)
        data = {"host": args.host, "source": str(source), "target": str(target), "source_fingerprints": fingerprints,
                "setup_args": arguments, "activation_commands": setup.get("activation_commands", []),
                "ownership_state": str(state_path), "identity": identity, "router_sha256": _digest(router_path)}
        _write(data_path, data)
        report["owned_files"]["bootstrap-runner.json"] = _digest(data_path)
        runner = "EXPECTED_DATA = " + repr(_digest(data_path)) + "\n" + RUNNER
        runner_path.write_text(runner, encoding="utf-8", newline="\n")
        report["owned_files"]["run.py"] = _digest(runner_path)
        command_python = "python" if os.name == "nt" else "python3"
        report.update(status="prepared", exit_code=0,
                      next=[f"{command_python} -I -B .hpp/run.py hpp doctor", f"{command_python} -I -B .hpp/run.py host"])
        if args.host == "claude-code":
            report["next"].insert(0, f"Review hook capabilities, then: {command_python} -I -B .hpp/run.py activate")
    except (OSError, ValueError, RecursionError, subprocess.SubprocessError) as exc:
        report.update(status="partial", exit_code=2, error=str(exc))
    _write(owner_path, report)
    _write(state_path, {"schema": SCHEMA, "identity": identity, "receipt_sha256": _digest(owner_path),
                        "environment_files": _inventory(environment) if environment.is_dir() else {},
                        "owned_files": report["owned_files"], "shim_files": _inventory(shim_dir) if shim_dir.is_dir() else {}})
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default=".", help="existing consumer project")
    parser.add_argument("--host", required=True, choices=["claude-code", "codex"])
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--bundle", default=None)
    selection.add_argument("--all-compatible", action="store_true")
    selection.add_argument("--modules", help="comma-separated module ids")
    parser.add_argument("--apply", action="store_true", help="prepare the environment and install the reviewed selection")
    parser.add_argument("--json", action="store_true", help="print the structured result")
    parser.add_argument("--state-dir", help="local ownership state outside the consumer project (default: ~/.hpp-setup-state)")
    args = parser.parse_args(argv)
    try:
        report = run(args)
    except (OSError, ValueError, RecursionError, subprocess.SubprocessError) as exc:
        report = {"schema": SCHEMA, "status": "error", "exit_code": 2, "error": str(exc)}
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"HPP setup: {report['status']} - host={args.host}")
        if "setup" in report:
            setup = report["setup"]
            print("Environment: " + report["environment"])
            print("Local ownership state: " + report["ownership_state"])
            print("Dependencies: " + ", ".join(report["bootstrap_dependencies"]["packages"]))
            print("Apply network: " + report["network_on_apply"])
            print("Managed paths: " + ", ".join(report["planned_managed_paths"]))
            print("Selected modules: " + ", ".join(setup["selected_modules"]))
            for item in setup.get("skipped_modules", []):
                print(f"  skipped {item['id']}: {item['reason']}")
            print(f"Module destination files: {len(setup.get('planned_files', []))}; full map: --json")
            for item in setup.get("planned_files", []):
                if item["kind"] in {"project-profile", "module-profile", "setup-receipt"}:
                    print(f"  {item['destination']}: {item['action']}")
            for item in setup.get("planned_actions", []):
                print(f"  {item['destination']}/: {item['action']}")
            print("HOOK CAPABILITIES (not activated by setup):")
            for item in setup.get("hook_capabilities", []):
                print(f"  {item['id']} [{item['module']}]: {item['exit_policy']} - " + ", ".join(item["capabilities"]))
            for argv in setup.get("activation_commands", []):
                print("  manual native command: " + json.dumps(argv))
            if setup.get("error"):
                print(setup["error"], file=sys.stderr)
        if report.get("error"):
            print(report["error"], file=sys.stderr)
        for command in report.get("next", []):
            print(command)
        if not args.apply and report["exit_code"] == 0:
            print("Review the module and hook plan; repeat this command with --apply to prepare files. Host activation stays manual.")
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
