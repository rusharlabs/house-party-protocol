"""Contrato de linha de comando: `--version`/`--help` funcionam, todo subcomando
do parser tem uma funcao correspondente (e vice-versa), e o contrato de saida
(0 ok / 1 warn / 2 block / 3 erro) e respeitado nos comandos que de fato o
produzem.

Os testes de superficie externa (--version, --help, subcomando inexistente) vao
por `subprocess` + `python -m hpp`, exatamente como um usuario real invocaria o
pacote. O resto chama `hpp.cli.main()` em processo (mais rapido, mesmo
comportamento) porque o que se quer testar e' a logica de despacho e os exit
codes, nao o entrypoint do interpretador em si -- ja coberto pelos primeiros.
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
# Superficie externa: python -m hpp, de verdade, fora de processo.
# ---------------------------------------------------------------------------


def test_version_via_python_dash_m_hpp():
    result = _run_subprocess(["--version"])
    assert result.returncode == 0
    assert result.stdout.strip() == __version__


def test_help_lista_uso_e_sai_zero():
    result = _run_subprocess(["--help"])
    assert result.returncode == 0
    assert "usage" in result.stdout.lower()


def test_CONTROLE_subcomando_inexistente_e_rejeitado_pelo_parser():
    """Controle: prova que o parser de fato distingue um nome valido de um
    invalido -- sem isto, 'todo subcomando existe' seria uma afirmacao vazia."""
    result = _run_subprocess(["bogus-command-that-does-not-exist"])
    assert result.returncode == 2
    assert "invalid choice" in result.stderr.lower()


# ---------------------------------------------------------------------------
# Todo subcomando do parser <-> toda funcao command_* do modulo (introspeccao,
# sem lista hardcoded de nomes dos dois lados).
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


def test_todo_subcomando_tem_funcao_command_e_toda_funcao_command_tem_subcomando():
    """
    O manifesto publico (hpp.manifest.json) nao declara uma lista de subcomandos
    de CLI -- ele descreve modulos, capacidades e o loop de eventos, nao a forma
    do parser. O contrato real e' entre o parser (`build_parser`) e as funcoes
    `command_*` do proprio `hpp/cli.py`: as duas listas abaixo vem de
    introspeccao, nenhuma foi digitada a mao aqui -- entao um subcomando
    adicionado sem sua funcao (ou vice-versa) derruba este teste.
    """
    subcommands = _top_level_subcommand_names()
    functions = _command_function_names()
    assert subcommands == functions, (
        f"subcomandos sem funcao command_*: {subcommands - functions}; "
        f"funcoes command_* sem subcomando: {functions - subcommands}"
    )


def test_CONTROLE_lista_de_subcomandos_nao_esta_vazia():
    """Controle: a comparacao acima passaria trivialmente (conjunto vazio ==
    conjunto vazio) se `build_parser` quebrasse silenciosamente."""
    assert len(_top_level_subcommand_names()) >= 10


# ---------------------------------------------------------------------------
# Cross-checks derivados do manifesto (nao hardcoded): o que o manifesto
# declara sobre routing/maps bate com o que o parser de fato expõe.
# ---------------------------------------------------------------------------


def test_tiers_de_routing_do_manifesto_batem_com_as_escolhas_de_policy_no_parser():
    manifest, _ = load_manifest()
    parser = cli.build_parser()
    route_subparser = next(
        action.choices["route"]
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction) and "route" in action.choices
    )
    policy_action = next(action for action in route_subparser._actions if action.dest == "policy")
    assert list(policy_action.choices) == manifest["routing"]["tiers"]


def test_maps_do_manifesto_cobrem_as_views_de_graph_e_de_map_expostas_no_parser():
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
# Contrato de exit code: 0 ok, 1 warn, 2 block, 3 erro interno.
# ---------------------------------------------------------------------------


def test_exit_ok_via_doctor_e_via_benchmark(capsys):
    manifest, _ = load_manifest()
    assert cli.main(["doctor"]) == manifest["exit_codes"]["ok"]
    capsys.readouterr()
    assert cli.main(["benchmark", "-k", "3"]) == manifest["exit_codes"]["ok"]


def test_exit_warn_via_policy_check_manual(capsys):
    manifest, _ = load_manifest()
    code = cli.main(["policy", "check", "--mode", "enforce", "--command", "curl https://example.com/data"])
    assert code == manifest["exit_codes"]["warn"]


def test_exit_block_via_policy_check_destrutivo(capsys):
    manifest, _ = load_manifest()
    code = cli.main(["policy", "check", "--mode", "enforce", "--command", "rm -rf /tmp/example"])
    assert code == manifest["exit_codes"]["block"]


def test_exit_error_e_produzido_pelo_ramo_defensivo_do_main(monkeypatch, capsys):
    """
    Nao existe, hoje, um argv 'legitimo' (sintaxe valida, contrato respeitado)
    que alcance o exit 3: todo erro de dominio no harness (AttestationError,
    ManifestError, InstallError, StateError, EvalError, RoutingError, MapError,
    WorkGraphError, ContextError) herda de ValueError e cai no ramo que devolve
    2 -- ver `except (...) as exc: return 2` em hpp/cli.py. O ramo
    `except Exception -> 3` e puramente defensivo (contra um bug futuro que
    escape das excecoes de dominio conhecidas).

    Isto prova que o ramo, quando alcancado, se comporta como o contrato promete
    -- injetando uma falha real via monkeypatch (a unica forma de exercitar um
    caminho que nenhum argv real alcanca hoje). NAO e' um teste de um argv
    especifico; e' um teste do proprio `except Exception` em `main()`.
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


def test_CONTROLE_erro_de_dominio_normal_continua_caindo_no_exit_block_nao_no_error(capsys):
    """Controle: um ValueError de dominio real (comando sem manifesto valido)
    continua caindo em 2, nao em 3 -- prova que o monkeypatch acima testou o
    ramo certo, e nao acidentalmente os dois."""
    manifest, _ = load_manifest()
    code = cli.main(["work", "waves", str(PRODUCT_ROOT / "this-file-does-not-exist.json")])
    assert code == manifest["exit_codes"]["block"]
