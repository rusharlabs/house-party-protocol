"""Route HPP Python commands without replacing an application's environment.

The bootstrap writes the routing document and binds its bytes to a SHA256 in
the host process environment. This module never creates environments, changes
PATH, imports project code, or interprets shell command text.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Mapping


ROUTER_SCHEMA = "hpp.runtime-router/v1"
DATA_ENV = "HPP_RUNTIME_ROUTER_DATA"
HASH_ENV = "HPP_RUNTIME_ROUTER_SHA256"
APPLICATION_ENV_KEYS = {"PATH", "VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP",
                        "PYTHONUSERBASE", "PYTHONINSPECT", "PYTHONWARNINGS", "PYTHONDONTWRITEBYTECODE"}


class RuntimeRouteError(ValueError):
    """Routing cannot continue without risking the wrong interpreter."""


def _absolute(value: object, label: str, *, canonical: bool = True) -> Path:
    if not isinstance(value, str) or not value or not Path(value).is_absolute():
        raise RuntimeRouteError(f"{label} must be an absolute path; re-run HPP setup from the application's original shell")
    # Executable spelling is significant for venv discovery: resolving
    # <venv>/bin/python to the base interpreter discards pyvenv.cfg context.
    # Canonical paths remain useful for metadata, containment and recursion.
    path = Path(value)
    return path.resolve() if canonical else path


def _read_router(env: Mapping[str, str]) -> tuple[dict, Path, list[Path], Path]:
    metadata = _absolute(env.get(DATA_ENV), DATA_ENV)
    expected = env.get(HASH_ENV, "")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
        raise RuntimeRouteError(f"missing or invalid {HASH_ENV}; launch the host through its HPP project launcher")
    try:
        raw = metadata.read_bytes()
    except OSError as exc:
        raise RuntimeRouteError("router metadata is unavailable; re-run HPP setup") from exc
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), expected.lower()):
        raise RuntimeRouteError("router metadata SHA256 mismatch; preserve it and re-run HPP setup")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise RuntimeRouteError("router metadata must be a UTF-8 JSON object") from exc
    allowed = {"schema", "source", "hpp_runtime_roots", "managed_python"}
    if not isinstance(data, dict) or set(data) - allowed:
        raise RuntimeRouteError("router metadata contains unknown fields or is not an object")
    if data.get("schema", ROUTER_SCHEMA) != ROUTER_SCHEMA:
        raise RuntimeRouteError("unknown router metadata schema; re-run HPP setup with this CLI version")
    source = _absolute(data.get("source"), "router source")
    if not source.is_dir() or source.parent == source:
        raise RuntimeRouteError("router source must be an existing HPP checkout directory")
    raw_roots = data.get("hpp_runtime_roots")
    if not isinstance(raw_roots, list) or not raw_roots:
        raise RuntimeRouteError("hpp_runtime_roots must be a non-empty list of HPP directories")
    roots = []
    for item in raw_roots:
        if not isinstance(item, str) or not item:
            raise RuntimeRouteError("every HPP runtime root must be a path string")
        root = Path(item)
        if not root.is_absolute():
            if ".." in root.parts or "\\" in item:
                raise RuntimeRouteError("source-relative HPP roots cannot traverse outside the checkout")
            root = source / root
        root = root.resolve()
        if root.parent == root:
            raise RuntimeRouteError("an HPP runtime root cannot be a filesystem root")
        roots.append(root)
    managed = _absolute(data.get("managed_python"), "managed_python", canonical=False)
    if not managed.is_file():
        raise RuntimeRouteError("managed HPP Python is unavailable; re-run HPP setup")
    return data, metadata, roots, managed


def _command_target(argv: list[str]) -> tuple[str, str | None]:
    """Read Python's interpreter options only; never parse or evaluate code."""
    index = 0
    simple = set("bBdEiIOPqRsSuvx")
    while index < len(argv):
        arg = argv[index]
        if arg == "--":
            return ("script", argv[index + 1]) if index + 1 < len(argv) else ("application", None)
        if arg == "-" or not arg:
            return "application", None
        if not arg.startswith("-"):
            return "script", arg
        if arg == "--check-hash-based-pycs":
            if index + 1 >= len(argv):
                return "application", None
            index += 2
            continue
        if arg.startswith("--check-hash-based-pycs="):
            index += 1
            continue
        if arg.startswith("--"):
            return "application", None  # help/version/unknown option: native Python handles it
        position = 1
        while position < len(arg):
            option = arg[position]
            remainder = arg[position + 1:]
            if option == "c":
                return "application", None
            if option == "m":
                module = remainder or (argv[index + 1] if index + 1 < len(argv) else "")
                return "module", module
            if option in {"X", "W"}:
                if not remainder:
                    if index + 1 >= len(argv):
                        return "application", None
                    index += 1
                break
            if option not in simple:
                return "application", None
            position += 1
        index += 1
    return "application", None


def _is_router(path: Path, metadata: Path, program: str) -> bool:
    canonical = path.resolve()
    for candidate in (path, canonical):
        name = candidate.name.lower().removesuffix(".exe")
        if name in {"hpp-python-router", "hpp-python"}:
            return True
        # Keep lexical and canonical guards: aliases can themselves be links.
        if candidate.parent.name.lower() == "bin" and candidate.parent.parent.name.lower() == ".hpp":
            return True
        if candidate.parent == (metadata.parent / "bin").resolve():
            return True
    called = Path(program)
    return called.is_absolute() and canonical == called.resolve()


def _hpp_module(argv: list[str]) -> bool:
    kind, value = _command_target(argv)
    return kind == "module" and (value == "hpp" or bool(value and value.startswith("hpp.")))


def _managed_environment(env: Mapping[str, str]) -> dict[str, str]:
    startup = APPLICATION_ENV_KEYS - {"PATH", "VIRTUAL_ENV"}
    result = {key: value for key, value in env.items() if key.upper() not in startup}
    result.update(PYTHONDONTWRITEBYTECODE="1")
    return result


def _application_environment(env: Mapping[str, str]) -> dict[str, str]:
    try:
        original = json.loads(env.get("HPP_APPLICATION_ENV", ""))
    except ValueError as exc:
        raise RuntimeRouteError("missing or invalid HPP_APPLICATION_ENV; relaunch from the application's original shell") from exc
    if not isinstance(original, dict) or any(
            not isinstance(key, str) or key not in APPLICATION_ENV_KEYS
            or (value is not None and not isinstance(value, str)) for key, value in original.items()):
        raise RuntimeRouteError("HPP_APPLICATION_ENV must contain only original PATH/PYTHON*/VIRTUAL_ENV strings or null")
    if "PATH" not in original:
        raise RuntimeRouteError("HPP_APPLICATION_ENV omits original PATH; relaunch through the HPP project launcher")
    result = dict(env)
    for key, value in original.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = value
    return result


def route_argv(argv: list[str], *, env: Mapping[str, str] | None = None,
               program: str | None = None, cwd: Path | None = None) -> list[str]:
    """Pure, read-only routing decision; argv and caller environment are preserved."""
    environment = os.environ if env is None else env
    program = sys.argv[0] if program is None else program
    _, metadata, roots, managed = _read_router(environment)
    kind, value = _command_target(argv)
    is_hpp = _hpp_module(argv)
    if kind == "script" and value:
        script = Path(value)
        if not script.is_absolute():
            script = (cwd or Path.cwd()) / script
        script = script.resolve()
        is_hpp = any(script == root or root in script.parents for root in roots)
    if is_hpp:
        if _is_router(managed, metadata, program):
            raise RuntimeRouteError("managed_python points to an HPP router; repair the HPP environment before launching")
        return [str(managed), *(["-I"] if kind == "module" else []), "-B", *argv]
    basename = Path(program).name.lower().removesuffix(".exe")
    variable = "HPP_APPLICATION_PYTHON3" if basename == "python3" else "HPP_APPLICATION_PYTHON"
    application = _absolute(environment.get(variable), variable, canonical=False)
    if _is_router(application, metadata, program):
        raise RuntimeRouteError(f"{variable} points to an HPP router; restart from the application's original shell and re-run setup")
    if not application.is_file():
        raise RuntimeRouteError(f"{variable} is unavailable; activate the application environment and re-run HPP setup")
    return [str(application), *argv]


def python_main(argv: list[str] | None = None) -> int:
    """Dedicated HPP interpreter launcher; the native entry point binds sys.executable."""
    args = sys.argv[1:] if argv is None else argv
    command = [sys.executable, *(["-I"] if _hpp_module(args) else []), "-B", *args]
    return subprocess.run(command, env=_managed_environment(os.environ), shell=False).returncode


def router_main(argv: list[str] | None = None) -> int:
    """Console entry point copied as python/python3 in the project shim directory."""
    args = sys.argv[1:] if argv is None else argv
    try:
        command = route_argv(args)
        # route_argv adds -B only for managed routes; application argv is exact.
        # Compare against metadata as well so an application legitimately using
        # the same executable still receives its original application env.
        kind, value = _command_target(args)
        managed_route = _hpp_module(args)
        if kind == "script" and value:
            _, _, roots, _ = _read_router(os.environ)
            script = Path(value).resolve()
            managed_route = any(script == root or root in script.parents for root in roots)
        env = _managed_environment(os.environ) if managed_route else _application_environment(os.environ)
        return subprocess.run(command, env=env, shell=False).returncode
    except (RuntimeRouteError, OSError) as exc:
        print(f"hpp-python-router: {exc}", file=sys.stderr)
        return 2
