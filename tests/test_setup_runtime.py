"""The HPP router must not replace a consumer application's Python environment."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path
from types import SimpleNamespace

import pytest

from hpp import runtime


@pytest.fixture
def routing(tmp_path):
    source = tmp_path / "HPP checkout with spaces"
    module = source / "frameworks/health-kit"
    module.mkdir(parents=True)
    target = tmp_path / "application project"
    target.mkdir()
    metadata = target / ".hpp/runtime-router.json"
    metadata.parent.mkdir()
    managed = tmp_path / "managed environment/python.exe"
    application = target / ".venv/python.exe"
    application3 = target / ".venv/python3.exe"
    for path in (managed, application, application3):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"interpreter placeholder")
    data = {
        "schema": runtime.ROUTER_SCHEMA,
        "source": str(source),
        "hpp_runtime_roots": [str(module), str(target / ".agents/hpp")],
        "managed_python": str(managed),
    }
    metadata.write_text(json.dumps(data), encoding="utf-8")
    env = {
        runtime.DATA_ENV: str(metadata),
        runtime.HASH_ENV: hashlib.sha256(metadata.read_bytes()).hexdigest(),
        "HPP_APPLICATION_PYTHON": str(application),
        "HPP_APPLICATION_PYTHON3": str(application3),
        "VIRTUAL_ENV": str(target / ".venv"),
        "PATH": "original application path",
        "APP_SETTING": "kept unchanged",
        "HPP_APPLICATION_ENV": json.dumps(
            {
                "PATH": "original application path",
                "PYTHONPATH": None,
                "PYTHONHOME": None,
            }
        ),
    }
    return SimpleNamespace(
        source=source,
        module=module,
        target=target,
        metadata=metadata,
        managed=managed,
        application=application,
        application3=application3,
        data=data,
        env=env,
        program=str(target / ".hpp/bin/python.exe"),
    )


def rewrite(route, **updates):
    route.data.update(updates)
    route.metadata.write_text(json.dumps(route.data), encoding="utf-8")
    route.env[runtime.HASH_ENV] = hashlib.sha256(
        route.metadata.read_bytes()
    ).hexdigest()


@pytest.mark.parametrize(
    "prefix",
    [
        [],
        ["-I", "-B"],
        ["-IB", "-X", "utf8"],
        ["-W", "ignore"],
        ["-Wignore", "-Xutf8"],
        ["--check-hash-based-pycs", "always"],
        ["--check-hash-based-pycs=always"],
        ["-u", "-OO", "-P"],
        ["--"],
    ],
)
def test_selected_hpp_script_uses_managed_interpreter(routing, prefix):
    script = routing.module / "scripts/health probe.py"
    argv = [*prefix, str(script), "--literal", "a;$(not a shell)"]
    before = dict(routing.env)
    result = runtime.route_argv(argv, env=routing.env, program=routing.program)
    assert result == [str(routing.managed), "-B", *argv]
    assert routing.env == before


@pytest.mark.parametrize(
    "argv,managed",
    [
        (["-m", "hpp"], True),
        (["-I", "-m", "hpp.status"], True),
        (["-mhpp"], True),
        (["-Imhpp"], True),
        (["-m", "pytest", "-q"], False),
        (["-m", "hppy"], False),
        (["-c", "print('hpp')"], False),
        (["-Icprint('hpp')"], False),
        (["--version"], False),
        (["-VV"], False),
        (["--help"], False),
        (["--unknown", "ignored.py"], False),
        (["-X"], False),
        (["-m"], False),
        (["-"], False),
        ([], False),
    ],
)
def test_module_code_and_interpreter_flags(routing, argv, managed):
    result = runtime.route_argv(argv, env=routing.env, program=routing.program)
    assert result == (
        [str(routing.managed), "-I", "-B", *argv]
        if managed
        else [str(routing.application), *argv]
    )


def test_application_script_and_python3_preserve_original_selection(routing):
    argv = ["-X", "utf8", str(routing.target / "app.py"), "arg with spaces"]
    result = runtime.route_argv(argv, env=routing.env, program="python3.exe")
    assert result == [str(routing.application3), *argv]
    result = runtime.route_argv(argv, env=routing.env, program="python")
    assert result == [str(routing.application), *argv]


def test_relative_roots_and_containment_are_resolved(routing):
    rewrite(
        routing,
        hpp_runtime_roots=[
            "frameworks/health-kit",
            str(routing.target / ".agents/hpp"),
        ],
    )
    managed = runtime.route_argv(
        ["scripts/probe.py"], env=routing.env, program="python", cwd=routing.module
    )
    assert managed[0] == str(routing.managed)
    copied = runtime.route_argv(
        [".agents/hpp/health-kit/probe.py"],
        env=routing.env,
        program="python",
        cwd=routing.target,
    )
    assert copied[0] == str(routing.managed)
    sibling = runtime.route_argv(
        [str(routing.source / "frameworks/health-kit-extra/app.py")],
        env=routing.env,
        program="python",
    )
    assert sibling[0] == str(routing.application)
    traversal = runtime.route_argv(
        ["../app.py"], env=routing.env, program="python", cwd=routing.module
    )
    assert traversal[0] == str(routing.application)


@pytest.mark.parametrize(
    "mode",
    [
        "missing-hash",
        "tampered",
        "unknown-field",
        "unknown-schema",
        "not-object",
        "invalid-json",
        "traversal-root",
        "missing-application",
        "recursive-application",
        "other-project-router",
        "recursive-managed",
    ],
)
def test_bad_routing_data_refuses_before_execution(routing, monkeypatch, mode, capsys):
    argv = ["--version"]
    if mode == "missing-hash":
        routing.env.pop(runtime.HASH_ENV)
    elif mode == "tampered":
        routing.metadata.write_text("tampered", encoding="utf-8")
    elif mode == "unknown-field":
        rewrite(routing, unexpected="not accepted")
    elif mode == "unknown-schema":
        rewrite(routing, schema="unknown/v99")
    elif mode in {"not-object", "invalid-json"}:
        routing.metadata.write_text(
            "[]" if mode == "not-object" else "{", encoding="utf-8"
        )
        routing.env[runtime.HASH_ENV] = hashlib.sha256(
            routing.metadata.read_bytes()
        ).hexdigest()
    elif mode == "traversal-root":
        rewrite(routing, hpp_runtime_roots=["../../outside"])
    elif mode == "missing-application":
        routing.env.pop("HPP_APPLICATION_PYTHON")
    elif mode in {"recursive-application", "other-project-router"}:
        path = routing.target / ".hpp/bin/python.exe"
        if mode == "other-project-router":
            path = routing.target / "another-project/.hpp/bin/python.exe"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"router")
        routing.env["HPP_APPLICATION_PYTHON"] = str(path)
    else:
        path = routing.target / ".hpp/bin/python.exe"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"router")
        rewrite(routing, managed_python=str(path))
        argv = ["-m", "hpp"]
    monkeypatch.setattr(runtime.os, "environ", routing.env)
    monkeypatch.setattr(runtime.sys, "argv", [routing.program])
    monkeypatch.setattr(
        runtime.subprocess,
        "run",
        lambda *a, **kw: pytest.fail("invalid route executed"),
    )
    assert runtime.router_main(argv) == 2
    assert "hpp-python-router:" in capsys.readouterr().err


def test_router_and_direct_launcher_use_literal_argv_and_inherited_environment(
    routing, monkeypatch
):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs, dict(os.environ)))
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(runtime.os, "environ", routing.env)
    monkeypatch.setattr(runtime.sys, "argv", [routing.program])
    monkeypatch.setattr(runtime.subprocess, "run", run)
    args = ["-c", "import sys; print(sys.argv)", "$(literal)", ";", "a b", '"quote"']
    before = dict(routing.env)
    assert runtime.router_main(args) == 7
    assert calls[0] == (
        [str(routing.application), *args],
        {"shell": False, "env": before},
        before,
    )
    assert runtime.python_main(args) == 7
    expected_managed = {**before, "PYTHONDONTWRITEBYTECODE": "1"}
    assert calls[1] == (
        [sys.executable, "-B", *args],
        {"shell": False, "env": expected_managed},
        before,
    )
    assert routing.env == before


def test_causal_real_application_and_hpp_venvs_remain_distinct(tmp_path, routing):
    app_env = tmp_path / "real application venv"
    hpp_env = tmp_path / "real HPP venv"
    for path in (app_env, hpp_env):
        venv.EnvBuilder(with_pip=False).create(path)
    executable = "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    application = app_env / executable
    managed = hpp_env / executable
    rewrite(routing, managed_python=str(managed))
    routing.env.update(
        HPP_APPLICATION_PYTHON=str(application),
        HPP_APPLICATION_PYTHON3=str(application),
        VIRTUAL_ENV=str(app_env),
    )
    payload = "import json,os,sys; print(json.dumps({'prefix':sys.prefix,'virtual_env':os.environ.get('VIRTUAL_ENV'),'argv':sys.argv[1:]}))"
    hpp_script = routing.module / "probe with spaces.py"
    app_script = routing.target / "app with spaces.py"
    for path in (hpp_script, app_script):
        path.write_text(payload, encoding="utf-8")
    literal = ["a b", "$(must remain literal)", ";", '"quoted"']
    env = {**os.environ, **routing.env}
    before = dict(env)
    for path, expected in ((hpp_script, hpp_env), (app_script, app_env)):
        args = [str(path), *literal]
        command = runtime.route_argv(args, env=env, program=routing.program)
        result = subprocess.run(
            command, env=env, capture_output=True, text=True, check=True, shell=False
        )
        measured = json.loads(result.stdout)
        assert Path(measured["prefix"]).resolve() == expected.resolve()
        assert measured["virtual_env"] == str(app_env)
        assert measured["argv"] == literal
    assert env == before


def test_application_environment_restored_and_managed_startup_sanitized(
    routing, monkeypatch
):
    routing.env.update(
        PATH="project shim path",
        PYTHONPATH="must not affect HPP",
        PYTHONHOME="also unsafe",
    )
    routing.env["HPP_APPLICATION_ENV"] = json.dumps(
        {
            "PATH": "application path",
            "PYTHONPATH": "application modules",
            "PYTHONHOME": None,
            "PYTHONINSPECT": None,
        }
    )
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runtime.os, "environ", routing.env)
    monkeypatch.setattr(runtime.sys, "argv", [routing.program])
    monkeypatch.setattr(runtime.subprocess, "run", run)
    before = dict(routing.env)
    assert runtime.router_main(["-m", "pytest"]) == 0
    app = calls[-1][1]["env"]
    assert app["PATH"] == "application path"
    assert app["PYTHONPATH"] == "application modules"
    assert "PYTHONHOME" not in app
    assert app["VIRTUAL_ENV"] == before["VIRTUAL_ENV"]
    assert runtime.router_main([str(routing.module / "probe.py")]) == 0
    managed = calls[-1][1]["env"]
    assert "PYTHONPATH" not in managed and "PYTHONHOME" not in managed
    assert managed["VIRTUAL_ENV"] == before["VIRTUAL_ENV"]
    assert calls[-1][0][1] == "-B"  # file imports retain their script directory
    assert runtime.python_main(["-m", "hpp", "--version"]) == 0
    assert calls[-1][0][1:3] == ["-I", "-B"]
    assert routing.env == before


@pytest.mark.parametrize(
    "value", ["not-json", "[]", '{"UNKNOWN":"bad"}', '{"PATH":42}', "{}"]
)
def test_invalid_application_environment_refuses_without_running(
    routing, monkeypatch, value
):
    routing.env["HPP_APPLICATION_ENV"] = value
    monkeypatch.setattr(runtime.os, "environ", routing.env)
    monkeypatch.setattr(runtime.sys, "argv", [routing.program])
    monkeypatch.setattr(
        runtime.subprocess,
        "run",
        lambda *a, **kw: pytest.fail("malformed application environment executed"),
    )
    assert runtime.router_main(["-c", "pass"]) == 2


def test_managed_hpp_module_ignores_consumer_shadow_module(tmp_path, routing):
    managed_env = tmp_path / "managed isolated venv"
    venv.EnvBuilder(with_pip=False).create(managed_env)
    executable = managed_env / (
        "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    )
    rewrite(routing, managed_python=str(executable))
    site_result = subprocess.run(
        [
            str(executable),
            "-I",
            "-c",
            "import site,json; print(json.dumps(site.getsitepackages()))",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    site_packages = Path(json.loads(site_result.stdout)[0])
    site_packages.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        Path(runtime.__file__).parent,
        site_packages / "hpp",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    shadow = routing.target / "hpp.py"
    shadow.write_text(
        'import os\nfrom pathlib import Path\nPath(os.environ["ROUTE_TEST_MARKER"]).write_text("shadow executed")\n',
        encoding="utf-8",
    )
    control_marker = tmp_path / "control-shadow-ran"
    subprocess.run(
        [str(executable), "-B", "-m", "hpp", "--version"],
        cwd=routing.target,
        env={**os.environ, "ROUTE_TEST_MARKER": str(control_marker)},
        check=True,
    )
    assert control_marker.exists()
    marker = tmp_path / "managed-must-not-load-shadow"
    command = runtime.route_argv(
        ["-m", "hpp", "--version"], env=routing.env, program=routing.program
    )
    result = subprocess.run(
        command,
        cwd=routing.target,
        env={**os.environ, "ROUTE_TEST_MARKER": str(marker)},
        capture_output=True,
        text=True,
        check=True,
    )
    from hpp import __version__

    assert result.stdout.strip() == __version__
    assert not marker.exists()


def test_module_smoke_inner_python_precedes_router_aliases(tmp_path, monkeypatch):
    from hpp import setup

    shim = tmp_path / ".hpp/bin"
    shim.mkdir(parents=True)
    (shim / ("python.exe" if sys.platform == "win32" else "python")).write_bytes(
        b"router cannot run without HPP metadata"
    )
    monkeypatch.setenv("PATH", str(shim))
    monkeypatch.setenv("HPP_RUNTIME_ROUTER_DATA", "must not escape to module smoke")
    script = "import json,sys,shutil,os; print(json.dumps({'status':'ok','selected_python':sys.executable,'discovered_python':shutil.which('python'),'router_data':os.environ.get('HPP_RUNTIME_ROUTER_DATA')}))"
    result = setup._execute([sys.executable, "-I", "-B", "-c", script], tmp_path)
    assert Path(result["selected_python"]).resolve() == Path(sys.executable).resolve()
    assert Path(result["discovered_python"]).resolve() == Path(sys.executable).resolve()
    assert result["router_data"] is None


def test_module_smoke_rejects_python_directory_with_real_host_cli(tmp_path):
    from hpp import setup

    interpreter = tmp_path / "python.exe"
    interpreter.write_bytes(b"interpreter")
    (tmp_path / "claude.cmd").write_text("must not execute")
    with pytest.raises(setup.SetupError, match="contains a host CLI"):
        setup._module_environment(str(interpreter))


@pytest.mark.parametrize("managed", [False, True])
def test_executable_argv_keeps_venv_path_when_resolve_points_to_base(
    routing, tmp_path, monkeypatch, managed
):
    """Deterministic RT01 regression, including Windows without symlink privileges."""
    lexical = routing.managed if managed else routing.application
    base = tmp_path / "base interpreter/python.exe"
    base.parent.mkdir()
    base.write_bytes(b"base interpreter")
    original = Path.resolve

    def resolve(path, *args, **kwargs):
        return base if path == lexical else original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    args = [str(routing.module / "probe.py")] if managed else ["-c", "pass"]
    command = runtime.route_argv(args, env=routing.env, program=routing.program)
    assert command[0] == str(lexical)
    assert command[0] != str(base)


def test_linked_application_router_still_refuses_canonical_recursion(
    routing, monkeypatch
):
    original = Path.resolve
    canonical_router = Path(routing.program)

    def resolve(path, *args, **kwargs):
        if path == routing.application:
            return canonical_router
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    with pytest.raises(runtime.RuntimeRouteError, match="points to an HPP router"):
        runtime.route_argv(["--version"], env=routing.env, program=routing.program)


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX symlink venv semantics; deterministic RT01 tests also run on Windows",
)
def test_causal_posix_symlink_venvs_keep_application_only_imports_and_prefix(
    tmp_path, routing
):
    app_env = tmp_path / "application symlink venv"
    managed_env = tmp_path / "HPP symlink venv"
    app_python, managed_python = app_env / "bin/python", managed_env / "bin/python"
    env = runtime._managed_environment(os.environ)
    for directory, interpreter, module in [
        (app_env, app_python, "hpp_rt01_application_only_marker"),
        (managed_env, managed_python, "hpp_rt01_managed_only_marker"),
    ]:
        venv.EnvBuilder(with_pip=False, symlinks=True).create(directory)
        assert interpreter.is_symlink()
        purelib = subprocess.run(
            [
                str(interpreter),
                "-I",
                "-c",
                "import sysconfig; print(sysconfig.get_path('purelib'))",
            ],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        (Path(purelib.stdout.strip()) / (module + ".py")).write_text(
            'VALUE = "venv-only marker"\n', encoding="utf-8"
        )
        # Control: the dereferenced base interpreter cannot import this marker.
        control = subprocess.run(
            [str(interpreter.resolve()), "-I", "-c", "import " + module],
            env=env,
            capture_output=True,
            text=True,
        )
        assert control.returncode != 0 and "ModuleNotFoundError" in control.stderr
    rewrite(routing, managed_python=str(managed_python))
    routing.env.update(
        HPP_APPLICATION_PYTHON=str(app_python), HPP_APPLICATION_PYTHON3=str(app_python)
    )
    for script, interpreter, prefix, module in [
        (
            routing.target / "app probe.py",
            app_python,
            app_env,
            "hpp_rt01_application_only_marker",
        ),
        (
            routing.module / "HPP probe.py",
            managed_python,
            managed_env,
            "hpp_rt01_managed_only_marker",
        ),
    ]:
        script.write_text(
            "import json,sys\nimport "
            + module
            + " as marker\nprint(json.dumps({'prefix':sys.prefix,'marker':marker.VALUE}))\n",
            encoding="utf-8",
        )
        command = runtime.route_argv(
            [str(script)], env=routing.env, program=routing.program
        )
        assert command[0] == str(interpreter)
        measured = subprocess.run(
            command, env=env, capture_output=True, text=True, check=True
        )
        result = json.loads(measured.stdout)
        assert Path(result["prefix"]) == prefix
        assert result["marker"] == "venv-only marker"
