"""Command-line contract: `--version`/`--help` work, every subcommand of the
parser has a matching function (and vice versa), and the exit contract
(0 ok / 1 warn / 2 block / 3 error) is honored by the commands that actually
produce it.

The external-surface tests (--version, --help, nonexistent subcommand) go
through `subprocess` + `python -m hpp`, exactly as a real user would invoke
the package. The rest call `hpp.cli.main()` in-process (faster, same
behavior) because what we want to test is the dispatch logic and the exit
codes, not the interpreter entrypoint itself -- already covered by the first ones.
"""
from __future__ import annotations

import argparse
import inspect
import subprocess
import sys
from pathlib import Path

import pytest

from hpp import __version__, cli
from hpp.manifest import load_manifest

PRODUCT_ROOT = Path(__file__).resolve().parent.parent


def _run_subprocess(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "hpp", *argv],
        cwd=PRODUCT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )


# ---------------------------------------------------------------------------
# External surface: python -m hpp, for real, out of process.
# ---------------------------------------------------------------------------


def test_version_via_python_dash_m_hpp():
    result = _run_subprocess(["--version"])
    assert result.returncode == 0
    assert result.stdout.strip() == __version__


def test_help_lists_usage_and_exits_zero():
    result = _run_subprocess(["--help"])
    assert result.returncode == 0
    assert "usage" in result.stdout.lower()


def test_CONTROLE_nonexistent_subcommand_is_rejected_by_the_parser():
    """Control: proves that the parser actually distinguishes a valid name from
    an invalid one -- without this, 'every subcommand exists' would be vacuous."""
    result = _run_subprocess(["bogus-command-that-does-not-exist"])
    assert result.returncode == 2
    assert "invalid choice" in result.stderr.lower()


# ---------------------------------------------------------------------------
# Every parser subcommand <-> every command_* function of the module
# (introspection, no hardcoded list of names on either side).
# ---------------------------------------------------------------------------


def _top_level_subcommand_names() -> set[str]:
    parser = cli.build_parser()
    subparsers_action = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    return set(subparsers_action.choices)


def _command_function_names() -> set[str]:
    names = set()
    for name, _ in inspect.getmembers(cli, inspect.isfunction):
        if name.startswith("command_"):
            names.add(name[len("command_"):])
    return names


def test_every_subcommand_has_a_command_function_and_vice_versa():
    """
    The public manifest (hpp.manifest.json) does not declare a list of CLI
    subcommands -- it describes modules, capabilities and the event loop, not
    the shape of the parser. The real contract is between the parser
    (`build_parser`) and the `command_*` functions of `hpp/cli.py` itself: the
    two lists below come from introspection, neither was typed by hand here --
    so a subcommand added without its function (or vice versa) fails this test.
    """
    subcommands = _top_level_subcommand_names()
    functions = _command_function_names()
    assert subcommands == functions, (
        f"subcomandos sem funcao command_*: {subcommands - functions}; "
        f"funcoes command_* sem subcomando: {functions - subcommands}"
    )


def test_CONTROLE_the_subcommand_list_is_not_empty():
    """Control: the comparison above would pass trivially (empty set ==
    empty set) if `build_parser` broke silently."""
    assert len(_top_level_subcommand_names()) >= 10


# ---------------------------------------------------------------------------
# Cross-checks derived from the manifest (not hardcoded): what the manifest
# declares about routing/maps matches what the parser actually exposes.
# ---------------------------------------------------------------------------


def test_manifest_routing_tiers_match_the_policy_choices_in_the_parser():
    manifest, _ = load_manifest()
    parser = cli.build_parser()
    route_subparser = next(
        action.choices["route"]
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction) and "route" in action.choices
    )
    policy_action = next(action for action in route_subparser._actions if action.dest == "policy")
    assert list(policy_action.choices) == manifest["routing"]["tiers"]


def test_manifest_maps_cover_the_graph_and_map_views_exposed_in_the_parser():
    manifest, _ = load_manifest()
    declared_maps = set(manifest["maps"])
    parser = cli.build_parser()
    top_level = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    graph_view_action = next(
        action for action in top_level.choices["graph"]._actions if action.dest == "view"
    )
    map_subparsers = next(
        action for action in top_level.choices["map"]._actions if isinstance(action, argparse._SubParsersAction)
    )
    assert set(graph_view_action.choices) <= declared_maps, (
        "graph --view expoe uma visao que o manifesto nao promete em 'maps'"
    )
    assert set(map_subparsers.choices) <= declared_maps, (
        "map expoe uma visao que o manifesto nao promete em 'maps'"
    )


# ---------------------------------------------------------------------------
# Exit code contract: 0 ok, 1 warn, 2 block, 3 internal error.
# ---------------------------------------------------------------------------


def test_exit_ok_via_doctor_and_via_benchmark(capsys):
    manifest, _ = load_manifest()
    assert cli.main(["doctor"]) == manifest["exit_codes"]["ok"]
    capsys.readouterr()
    assert cli.main(["benchmark", "-k", "3"]) == manifest["exit_codes"]["ok"]


def test_exit_warn_via_policy_check_manual(capsys):
    manifest, _ = load_manifest()
    code = cli.main(["policy", "check", "--mode", "enforce", "--command", "curl https://example.com/data"])
    assert code == manifest["exit_codes"]["warn"]


def test_exit_block_via_policy_check_destructive(capsys):
    manifest, _ = load_manifest()
    code = cli.main(["policy", "check", "--mode", "enforce", "--command", "rm -rf /tmp/example"])
    assert code == manifest["exit_codes"]["block"]


def test_exit_error_is_produced_by_the_defensive_branch_of_main(monkeypatch, capsys):
    """
    There is no, today, a 'legitimate' argv (valid syntax, contract honored)
    that reaches exit 3: every domain error in the harness (AttestationError,
    ManifestError, InstallError, StateError, EvalError, RoutingError, MapError,
    WorkGraphError, ContextError) inherits from ValueError and falls into the
    branch that returns 2 -- see `except (...) as exc: return 2` in hpp/cli.py.
    The `except Exception -> 3` branch is purely defensive (against a future
    bug that escapes the known domain exceptions).

    This proves that the branch, when reached, behaves as the contract promises
    -- injecting a real failure via monkeypatch (the only way to exercise a
    path that no real argv reaches today). It is NOT a test of a specific
    argv; it is a test of `except Exception` itself in `main()`.
    """
    manifest, _ = load_manifest()

    def _boom(_args):
        raise RuntimeError("synthetic failure to exercise the internal-error branch")

    monkeypatch.setattr(cli, "command_doctor", _boom)
    code = cli.main(["doctor"])
    assert code == manifest["exit_codes"]["error"]
    captured = capsys.readouterr()
    assert "internal error" in captured.err
    assert "RuntimeError" in captured.err


def test_CONTROLE_a_normal_domain_error_still_falls_into_exit_block_not_error(capsys):
    """Control: a real domain ValueError (command with no valid manifest)
    still falls into 2, not 3 -- proves that the monkeypatch above tested the
    right branch, and not accidentally both."""
    manifest, _ = load_manifest()
    code = cli.main(["work", "waves", str(PRODUCT_ROOT / "this-file-does-not-exist.json")])
    assert code == manifest["exit_codes"]["block"]
