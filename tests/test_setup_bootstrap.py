"""Bootstrap trust and phase boundaries, with no real pip or host activation."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("setup_bootstrap", ROOT / "scripts/setup_hpp.py")
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)
REAL_RUN = subprocess.run


def snapshot(root):
    return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def world(tmp_path, monkeypatch):
    source = tmp_path / "release with spaces"
    target = tmp_path / "consumer & project"
    state = tmp_path / "local-state"
    target.mkdir()
    (source / ".github/requirements").mkdir(parents=True)
    (source / ".github/requirements/setup.txt").write_text("-r build.txt\nPyYAML==6.0.3\n")
    (source / ".github/requirements/build.txt").write_text("setuptools==84.1.0\n")
    (source / "hpp").mkdir()
    (source / "hpp/__init__.py").write_text("__version__='2.14.0'\n")
    (source / "scripts").mkdir()
    (source / "scripts/setup_hpp.py").write_text("# fixture bootstrap\n")
    for name in ("pyproject.toml", "README.md", "LICENSE"):
        (source / name).write_text("fixture\n")
    (source / "hpp.manifest.json").write_text(json.dumps({"modules": [{"id": "lane-kit", "path": "modules/lane"}]}))
    (source / "modules/lane").mkdir(parents=True)
    (source / "modules/lane/CHECKSUMS.txt").write_text("fixture\n")
    plan = {"version": "2.14.0", "selected_modules": ["lane-kit"], "status": "planned", "exit_code": 0,
            "activation_commands": [["claude", "plugin", "marketplace", "add", str(source)]]}
    monkeypatch.setattr(bootstrap, "_probe", lambda *a: plan.copy())
    monkeypatch.setattr(bootstrap, "_untracked_managed", lambda *a: None)
    calls = []

    class Environment:
        def __init__(self, **kwargs):
            assert kwargs == {"with_pip": True, "symlinks": False}

        def create(self, path):
            python = path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            python.parent.mkdir(parents=True)
            python.write_bytes(b"trusted-python-fixture")
            (path / "pyvenv.cfg").write_text("fixture\n")

    def execute(argv, **kwargs):
        # Never expose the caller's entire environment in a failing fixture repr.
        calls.append((argv, {k: v for k, v in kwargs.items() if k != "env"}))
        if "pip" in argv:
            assert "-I" in argv and "-B" in argv
            assert kwargs["stdout"] is sys.stderr
            return subprocess.CompletedProcess(argv, 0)
        assert argv[-2:] == ["--apply", "--json"]
        return subprocess.CompletedProcess(argv, 0, json.dumps({**plan, "status": "prepared"}))

    monkeypatch.setattr(bootstrap.venv, "EnvBuilder", Environment)
    monkeypatch.setattr(bootstrap.subprocess, "run", execute)

    def make_shims(python, directory, env, source):
        directory.mkdir(exist_ok=True)
        for name in ("hpp", "hpp-python", "python", "python3"):
            suffix = ".exe" if os.name == "nt" else ""
            (directory / (name + suffix)).write_bytes(("isolated-launcher:" + name).encode())

    monkeypatch.setattr(bootstrap, "_make_shims", make_shims)
    args = argparse.Namespace(target=str(target), host="claude-code", bundle=None, all_compatible=False,
                              modules=None, apply=False, json=True, state_dir=str(state))
    return source, target, state, args, calls


def test_plan_zero_writes_and_lists_preparation(world):
    source, target, state, args, calls = world
    before = snapshot(source)
    report = bootstrap.run(args, source)
    assert report["status"] == "planned"
    assert not list(target.iterdir()) and not state.exists() and not calls
    assert snapshot(source) == before
    assert "PyYAML==6.0.3" in report["bootstrap_dependencies"]["packages"]
    assert ".hpp/run.py" in report["planned_managed_paths"]


def test_apply_builds_copy_and_rerun_is_zero_write(world):
    source, target, state, args, calls = world
    before = snapshot(source)
    args.apply = True
    first = bootstrap.run(args, source)
    assert first["status"] == "prepared" and first["exit_code"] == 0
    assert len(calls) == 3
    assert calls[1][0][-1] != str(source)
    assert Path(calls[1][0][-1]).is_relative_to(target / ".hpp")
    assert snapshot(source) == before
    target_before, state_before = snapshot(target), snapshot(state)
    calls.clear()
    second = bootstrap.run(args, source)
    assert second["rerun_verified"] and not calls
    assert snapshot(target) == target_before and snapshot(state) == state_before


def test_forged_project_receipt_cannot_adopt_existing_python(world):
    source, target, _, args, calls = world
    identity = bootstrap.run(args, source)["identity"]
    python = target / ".hpp/venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python.parent.mkdir(parents=True)
    python.write_bytes(b"attacker executable")
    (target / ".hpp/bootstrap-receipt.json").write_text(json.dumps({"schema": bootstrap.SCHEMA, "identity": identity, "owned_files": {}}))
    args.apply = True
    with pytest.raises(ValueError, match="trusted local ownership"):
        bootstrap.run(args, source)
    assert not calls


@pytest.mark.parametrize("name", ["evil.pth", "__pycache__/injected.pyc", "pyvenv.cfg"])
def test_extra_or_modified_environment_file_is_refused(world, name):
    source, target, state, args, calls = world
    args.apply = True
    bootstrap.run(args, source)
    path = target / ".hpp/venv" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"untrusted altered bytes")
    before = snapshot(state)
    calls.clear()
    with pytest.raises(ValueError, match="environment changed"):
        bootstrap.run(args, source)
    assert not calls and snapshot(state) == before


def test_missing_prepared_environment_is_not_verified(world):
    source, target, _, args, calls = world
    args.apply = True
    bootstrap.run(args, source)
    environment = target / ".hpp/venv"
    environment.rename(target / ".hpp/preserved-venv")
    calls.clear()
    with pytest.raises(ValueError, match="environment is missing"):
        bootstrap.run(args, source)
    assert not calls


def test_partial_pip_failure_is_recorded_and_can_retry(world, monkeypatch):
    source, target, state, args, calls = world
    normal = bootstrap.subprocess.run
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(argv, 1))
    args.apply = True
    failed = bootstrap.run(args, source)
    assert failed["status"] == "partial" and failed["exit_code"] == 2
    assert list(state.glob("*.json")) and (target / ".hpp/bootstrap-receipt.json").is_file()
    monkeypatch.setattr(bootstrap.subprocess, "run", normal)
    assert bootstrap.run(args, source)["status"] == "prepared"
    assert len(calls) == 3


def test_malformed_owner_and_scope_are_refused(world):
    source, target, _, args, calls = world
    (target / ".hpp").mkdir()
    (target / ".hpp/bootstrap-receipt.json").write_text("[]")
    with pytest.raises(ValueError, match="must be an object"):
        bootstrap.run(args, source)
    assert not calls


def test_owner_relative_traversal_cannot_be_read_even_with_trusted_state(world):
    source, target, state, args, calls = world
    args.apply = True
    bootstrap.run(args, source)
    owner_path = target / ".hpp/bootstrap-receipt.json"
    owner = json.loads(owner_path.read_text())
    owner["owned_files"] = {"../outside": "0" * 64}
    owner_path.write_text(json.dumps(owner))
    trusted_path = next(state.glob("*.json"))
    trusted = json.loads(trusted_path.read_text())
    trusted["receipt_sha256"] = hashlib.sha256(owner_path.read_bytes()).hexdigest()
    trusted_path.write_text(json.dumps(trusted))
    calls.clear()
    with pytest.raises(ValueError, match="invalid bootstrap file ownership"):
        bootstrap.run(args, source)
    assert not calls


def test_source_bytecode_refused_before_import(world):
    source, target, state, args, calls = world
    cache = source / "hpp/__pycache__"
    cache.mkdir()
    (cache / "injected.pyc").write_bytes(b"untrusted")
    with pytest.raises(ValueError, match="untrusted bytecode"):
        bootstrap.run(args, source)
    assert not calls and not list(target.iterdir()) and not state.exists()


def test_managed_files_tracked_by_consumer_are_refused(tmp_path):
    if not shutil.which("git"):
        pytest.skip("Git unavailable")
    REAL_RUN(["git", "init", str(tmp_path)], check=True, capture_output=True)
    path = tmp_path / ".hpp/venv/evil.pth"
    path.parent.mkdir(parents=True)
    path.write_text("untrusted\n")
    REAL_RUN(["git", "-C", str(tmp_path), "add", "--", ".hpp/venv/evil.pth"], check=True)
    with pytest.raises(ValueError, match="must not be tracked"):
        bootstrap._untracked_managed(tmp_path)


def test_generated_launcher_rechecks_data_and_environment(world):
    source, target, _, args, _ = world
    args.apply = True
    bootstrap.run(args, source)
    (target / ".hpp/venv/evil.pth").write_text("untrusted")
    result = REAL_RUN([sys.executable, "-I", "-B", str(target / ".hpp/run.py"), "hpp", "doctor"],
                      capture_output=True, text=True)
    assert result.returncode != 0 and "Environment files changed" in result.stderr


def test_default_console_plan_shows_all_preparation_metadata(world, monkeypatch, capsys):
    source, _, _, args, _ = world
    plan = bootstrap.run(args, source)
    monkeypatch.setattr(bootstrap, "run", lambda *a, **kw: plan)
    assert bootstrap.main(["--target", args.target, "--host", "claude-code"]) == 0
    output = capsys.readouterr().out
    for value in (".hpp/venv", "PyYAML==6.0.3", "setuptools==84.1.0", ".hpp/run.py", plan["ownership_state"], "HOOK CAPABILITIES"):
        assert value in output


def test_host_launcher_preserves_application_environment(world, monkeypatch, tmp_path):
    source, target, _, args, _ = world
    args.apply = True
    bootstrap.run(args, source)
    original_python = str(tmp_path / "application/python.exe")
    application_modules = tmp_path / "application-modules"
    application_modules.mkdir()
    (application_modules / "application_marker.py").write_text("VALUE = 'application-environment-preserved'\n")
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path / "application"))
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "application-modules"))
    monkeypatch.setenv("PATH", str(tmp_path / "application"))
    monkeypatch.setattr(shutil, "which", lambda name, **kw: str(tmp_path / "claude.exe") if name.startswith("claude") else original_python)
    captured = {}

    def capture(argv, **kwargs):
        captured.update(kwargs)
        direct = REAL_RUN([sys.executable, "-B", "-c", "import application_marker;print(application_marker.VALUE)"],
                          env=kwargs["env"], capture_output=True, text=True)
        assert direct.returncode == 0 and direct.stdout.strip() == "application-environment-preserved", direct.stderr
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(subprocess, "run", capture)
    monkeypatch.setattr(sys, "argv", [str(target / ".hpp/run.py"), "host", "--version"])
    original_flags = sys.flags

    class IsolatedFlags:
        isolated = 1

        def __getattr__(self, name):
            return getattr(original_flags, name)

    monkeypatch.setattr(sys, "flags", IsolatedFlags())
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(target / ".hpp/run.py"), run_name="__main__")
    assert stopped.value.code == 0
    assert captured["env"]["VIRTUAL_ENV"] == str(tmp_path / "application")
    assert captured["env"]["PYTHONPATH"] == str(tmp_path / "application-modules")
    original = json.loads(captured["env"]["HPP_APPLICATION_ENV"])
    assert original["PYTHONPATH"] == str(tmp_path / "application-modules")
    assert original["PATH"] == str(tmp_path / "application")


def test_shim_tamper_is_not_adopted(world):
    source, target, _, args, calls = world
    args.apply = True
    bootstrap.run(args, source)
    shim = target / ".hpp/bin" / ("python.exe" if os.name == "nt" else "python")
    shim.write_bytes(b"untrusted shim")
    calls.clear()
    with pytest.raises(ValueError, match="launcher was edited|shim directory changed"):
        bootstrap.run(args, source)
    assert not calls


def test_same_version_changed_core_cannot_reuse_old_environment(world):
    source, _, _, args, calls = world
    args.apply = True
    bootstrap.run(args, source)
    (source / "hpp/new.py").write_text("# changed same-version code\n")
    calls.clear()
    with pytest.raises(ValueError, match="existing bootstrap differs"):
        bootstrap.run(args, source)
    assert not calls


def test_native_entrypoint_isolation_blocks_startup_shadowing(tmp_path):
    maker_class = pytest.importorskip("pip._vendor.distlib.scripts").ScriptMaker
    output = tmp_path / "native launchers"
    output.mkdir()
    poison = tmp_path / "consumer import path"
    (poison / "json").mkdir(parents=True)
    marker = tmp_path / "shadow-executed"
    (poison / "json/__init__.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('unsafe')\nraise RuntimeError('shadow control')\n"
    )
    maker = maker_class(None, str(output))
    maker.executable = sys.executable
    maker.variants = {""}
    maker.make("unsafe = json.tool:main")
    maker.make("isolated = json.tool:main", {"interpreter_args": ["-I"]})
    env = {**os.environ, "PYTHONPATH": str(poison)}
    suffix = ".exe" if os.name == "nt" else ""
    control = REAL_RUN([str(output / ("unsafe" + suffix)), "--help"], env=env, capture_output=True)
    assert control.returncode != 0 and marker.exists()
    marker.rename(tmp_path / "preserved-shadow-control")
    fixed = REAL_RUN([str(output / ("isolated" + suffix)), "--help"], env=env, capture_output=True)
    assert fixed.returncode == 0 and not marker.exists(), fixed.stderr.decode(errors="replace")


def test_caught_partial_shim_build_can_resume(world, monkeypatch):
    source, target, _, args, _ = world
    args.apply = True
    complete = bootstrap._make_shims

    def partial(python, directory, env, source):
        directory.mkdir(exist_ok=True)
        (directory / ("hpp.exe" if os.name == "nt" else "hpp")).write_bytes(b"partial-owned-launcher")
        raise ValueError("controlled launcher failure")

    monkeypatch.setattr(bootstrap, "_make_shims", partial)
    failed = bootstrap.run(args, source)
    assert failed["status"] == "partial"
    assert len(failed["owned_files"]) == 1
    monkeypatch.setattr(bootstrap, "_make_shims", complete)
    assert bootstrap.run(args, source)["status"] == "prepared"
    assert (target / ".hpp/run.py").is_file()


def test_native_posix_shim_retry_replaces_owned_partial_file(tmp_path):
    maker_class = pytest.importorskip("pip._vendor.distlib.scripts").ScriptMaker
    output = tmp_path / "posix-launchers"
    output.mkdir()
    launcher = output / "isolated"
    launcher.write_bytes(b"controlled interrupted write")
    maker = maker_class(None, str(output))
    maker._is_nt = False  # exercise the POSIX writer on every CI OS
    maker.executable = sys.executable
    maker.variants = {""}
    maker.clobber = False
    maker.make("isolated = json.tool:main", {"interpreter_args": ["-I"]})
    assert launcher.read_bytes() == b"controlled interrupted write"
    maker.clobber = True
    maker.make("isolated = json.tool:main", {"interpreter_args": ["-I"]})
    assert launcher.read_bytes().startswith(b"#!") and b"json.tool" in launcher.read_bytes()


def test_posix_shim_quotes_spaced_interpreter_and_keeps_isolation(tmp_path):
    """Execute POSIX-style launcher wrappers on Bash, including real Git Bash."""
    import venv

    scripts = pytest.importorskip("pip._vendor.distlib.scripts")
    if os.name == "nt":
        bash = Path("C:/Program Files/Git/bin/bash.exe")
        if not bash.is_file():
            pytest.skip("real Git Bash is unavailable")
    else:
        binary = shutil.which("bash")
        if not binary:
            pytest.skip("Bash is unavailable")
        bash = Path(binary)
    environment = tmp_path / "Python environment with spaces"
    venv.EnvBuilder(with_pip=False).create(environment)
    interpreter = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    output = tmp_path / "generated commands with spaces"
    output.mkdir()
    poison = tmp_path / "poison import path"
    (poison / "json").mkdir(parents=True)
    marker = tmp_path / "unsafe-import-executed"
    (poison / "json/__init__.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('unsafe')\nraise RuntimeError('startup shadow control')\n"
    )

    def posix_shebang(executable, post_interp):
        # Force only the shell-wrapper writer; do not mutate shared os.name.
        return b"#!/bin/sh\n'''exec' " + executable + post_interp + b' "$0" "$@"\n\' \'\'\'\n'

    maker = scripts.ScriptMaker(None, str(output))
    maker._is_nt = False
    maker._build_shebang = posix_shebang
    maker.variants = {""}
    maker.executable = interpreter.as_posix()
    maker.make("unquoted = json.tool:main", {"interpreter_args": ["-I"]})
    maker.executable = scripts.enquote_executable(interpreter.as_posix())
    maker.make("quoted-unsafe = json.tool:main")
    maker.make("quoted-isolated = json.tool:main", {"interpreter_args": ["-I"]})
    env = {**os.environ, "PYTHONPATH": str(poison)}
    env.pop("PYTHONHOME", None)

    def execute(name):
        return REAL_RUN([str(bash), "--noprofile", "--norc", (output / name).as_posix(), "--help"],
                        env=env, capture_output=True, text=True)

    # Old assignment skips distlib's automatic quoting and fails before Python.
    control = execute("unquoted")
    assert control.returncode != 0 and not marker.exists()
    assert "not found" in control.stderr or "No such file" in control.stderr, control.stderr
    unsafe = execute("quoted-unsafe")
    assert unsafe.returncode != 0 and marker.exists(), unsafe.stderr
    marker.rename(tmp_path / "preserved-unsafe-control")
    fixed = execute("quoted-isolated")
    assert fixed.returncode == 0 and not marker.exists(), fixed.stderr
    assert "usage:" in fixed.stdout.lower()


def test_posix_shims_keep_shell_metacharacters_literal(tmp_path):
    import venv

    if os.name == "nt":
        bash = Path("C:/Program Files/Git/bin/bash.exe")
        if not bash.is_file():
            pytest.skip("real Git Bash is unavailable")
    else:
        binary = shutil.which("bash")
        if not binary:
            pytest.skip("Bash is unavailable")
        bash = Path(binary)
    environment = tmp_path / "Python env $(touch injected-marker) with 'quotes' and spaces"
    venv.EnvBuilder(with_pip=False).create(environment)
    interpreter = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    site = REAL_RUN([str(interpreter), "-I", "-B", "-c", "import sysconfig;print(sysconfig.get_path('purelib'))"],
                    capture_output=True, text=True, check=True)
    package = Path(site.stdout.strip()) / "hpp"
    package.mkdir()
    (package / "__init__.py").write_text("")
    probe = ("import json,sys\n"
             "def report(entry):\n"
             " print(json.dumps({'entry':entry,'argv':sys.argv,'isolated':sys.flags.isolated,"
             "'no_bytecode':sys.dont_write_bytecode,'prefix':sys.prefix}));return 0\n")
    (package / "cli.py").write_text(probe + "def main():return report('hpp')\n")
    (package / "runtime.py").write_text(probe + "def python_main():return report('hpp-python')\ndef router_main():return report('router')\n")
    output = tmp_path / "commands $(touch injected-marker) with 'quotes' and spaces"
    output.mkdir()
    bootstrap._write_posix_shims(interpreter, output)
    poison = tmp_path / "poisoned consumer import path"
    (poison / "hpp").mkdir(parents=True)
    import_marker = tmp_path / "consumer-import-executed"
    (poison / "hpp/__init__.py").write_text(f"from pathlib import Path\nPath({str(import_marker)!r}).write_text('unsafe')\nraise RuntimeError('consumer shadow')\n")
    env = {**os.environ, "PYTHONPATH": str(poison)}
    env.pop("PYTHONHOME", None)
    if os.name == "nt":
        env["PATH"] = "C:/Program Files/Git/usr/bin" + os.pathsep + env.get("PATH", "")
    legacy = output / "legacy-double-quoted"
    legacy.write_text('#!/bin/sh\nexec "' + interpreter.absolute().as_posix() + '" -I -B -c "pass" "$@"\n')

    def execute(name, *arguments):
        return REAL_RUN([str(bash), "--noprofile", "--norc", (output / name).as_posix(), *arguments],
                        cwd=tmp_path, env=env, capture_output=True, text=True)

    injection_marker = tmp_path / "injected-marker"
    control = execute("legacy-double-quoted")
    assert control.returncode != 0 and injection_marker.exists(), control.stderr
    injection_marker.rename(tmp_path / "preserved-legacy-injection-control")
    arguments = ["a b", "$(touch injected-marker)", ";", "single ' quote"]
    for name, entry in [("hpp", "hpp"), ("hpp-python", "hpp-python"), ("python", "router"), ("python3", "router")]:
        result = execute(name, *arguments)
        assert result.returncode == 0, result.stderr
        measured = json.loads(result.stdout)
        assert measured["entry"] == entry
        assert Path(measured["argv"][0]).name == name
        assert measured["argv"][1:] == arguments
        assert measured["isolated"] == 1 and measured["no_bytecode"]
        assert Path(measured["prefix"]) == environment
        assert not injection_marker.exists() and not import_marker.exists()
