"""Modo nao-interativo: zero `input()`; tudo por flag ou por arquivo de respostas.

`builtins.input` e' substituido por uma funcao que EXPLODE. Se qualquer caminho
nao-interativo chamasse `input`, o teste cairia com AssertionError, nao com um
prompt pendurado. O controle no fim prova que o modo interativo, quando de fato
ligado, chama o perguntador -- senao "nao chamou input" seria trivialmente verdade.
"""
from __future__ import annotations

import argparse
import builtins
import io
import json
from pathlib import Path

import pytest

from hpp import cli, wizard
from hpp.install import InstallError
from hpp.manifest import load_manifest
from hpp.term import Console


def _explode(prompt: str = "") -> str:
    raise AssertionError(f"input() was called in non-interactive mode with prompt {prompt!r}")


def _args(**overrides) -> argparse.Namespace:
    base = {"target": ".", "apply": False, "host": None, "bundle": None, "modules": None, "policy_mode": None,
            "profile": None, "yes": False, "non_interactive": False, "json": False, "no_benchmark": True,
            "marketplace": None, "no_animation": True, "manifest": None}
    base.update(overrides)
    return argparse.Namespace(**base)


@pytest.fixture()
def manifest():
    data, _ = load_manifest()
    return data


@pytest.fixture()
def target(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    return workspace


@pytest.fixture(autouse=True)
def no_input(monkeypatch):
    monkeypatch.setattr(builtins, "input", _explode)


@pytest.mark.parametrize("flags", [["--non-interactive"], ["--yes"], ["--json"], []])
def test_nenhum_caminho_nao_interativo_chama_input(target, flags, capsys):
    """Sem TTY (pytest captura stdout) nenhum dos quatro caminhos pode perguntar -- inclusive
    o sem flag nenhuma, porque a deteccao de TTY e' parte da regra, nao um extra."""
    code = cli.main(["init", "--target", str(target), "--no-benchmark", "--no-animation", *flags])
    assert code == 0
    out = capsys.readouterr().out
    if "--json" in flags:
        assert json.loads(out)["interactive"] is False


def test_deteccao_de_interatividade_segue_tty_flags_e_ci(manifest, target):
    assert wizard.prepare_options(_args(target=str(target)), manifest, env={}, stdin_tty=True, stdout_tty=True).interactive is True
    assert wizard.prepare_options(_args(target=str(target)), manifest, env={}, stdin_tty=False, stdout_tty=True).interactive is False
    assert wizard.prepare_options(_args(target=str(target)), manifest, env={}, stdin_tty=True, stdout_tty=False).interactive is False
    assert wizard.prepare_options(_args(target=str(target), yes=True), manifest, env={}, stdin_tty=True, stdout_tty=True).interactive is False
    assert wizard.prepare_options(_args(target=str(target), non_interactive=True), manifest, env={}, stdin_tty=True, stdout_tty=True).interactive is False
    assert wizard.prepare_options(_args(target=str(target), json=True), manifest, env={}, stdin_tty=True, stdout_tty=True).interactive is False
    assert wizard.prepare_options(_args(target=str(target)), manifest, env={"CI": "true"}, stdin_tty=True, stdout_tty=True).interactive is False


def test_arquivo_de_profile_responde_as_perguntas_e_flag_vence_arquivo(manifest, target, capsys):
    answers = target.parent / "answers.json"
    answers.write_text(json.dumps({"host": "codex", "policy_mode": "enforce"}), encoding="utf-8")
    code = cli.main(["init", "--target", str(target), "--profile", str(answers), "--policy-mode", "audit",
                     "--no-benchmark", "--json"])
    report = json.loads(capsys.readouterr().out)
    assert code == 0
    profile = next(stage for stage in report["stages"] if stage["stage"] == "profile")["detail"]
    assert profile["answers"]["host"] == "codex" and profile["sources"]["host"] == "file"
    assert profile["answers"]["policy_mode"] == "audit" and profile["sources"]["policy_mode"] == "flag"
    assert profile["pending_defaults"] == ["bundle"]


def test_modules_substitui_o_bundle_e_vira_plano_custom(target, capsys):
    code = cli.main(["init", "--target", str(target), "--modules", "operator-kit, lane-kit", "--no-benchmark", "--json"])
    report = json.loads(capsys.readouterr().out)
    assert code == 0
    configure = next(stage for stage in report["stages"] if stage["stage"] == "configure")["detail"]
    assert configure["bundle"] == "custom"
    assert [module["id"] for module in configure["modules"]] == ["operator-kit", "lane-kit"]
    assert any("--modules operator-kit,lane-kit" in step for step in report["next"])


@pytest.mark.parametrize("content,fragment", [
    ('{"host": "codex", "colour": "orange"}', "unknown keys"),
    ('["codex"]', "must be a JSON object"),
    ('{"modules": []}', "non-empty list"),
    ('{"host": 3}', "must be a string"),
])
def test_arquivo_de_profile_invalido_e_erro_de_uso(manifest, target, content, fragment):
    answers = target.parent / "answers.json"
    answers.write_text(content, encoding="utf-8")
    with pytest.raises(wizard.InitUsageError, match=fragment):
        wizard.prepare_options(_args(target=str(target), profile=str(answers)), manifest, env={}, stdin_tty=False, stdout_tty=False)


@pytest.mark.parametrize("field,value,fragment", [
    ("host", "vim", "unknown host"),
    ("bundle", "nope", "unknown bundle"),
    ("modules", "operator-kit,ghost-kit", "unknown module"),
])
def test_escolha_fora_do_manifesto_e_block_como_no_hpp_install(manifest, target, field, value, fragment):
    with pytest.raises(InstallError, match=fragment):
        wizard.prepare_options(_args(target=str(target), **{field: value}), manifest, env={}, stdin_tty=False, stdout_tty=False)


def test_modules_vazio_e_erro_de_uso(manifest, target):
    with pytest.raises(wizard.InitUsageError, match="at least one module"):
        wizard.prepare_options(_args(target=str(target), modules=" , "), manifest, env={}, stdin_tty=False, stdout_tty=False)


def test_perguntador_interativo_enter_aceita_default_numero_escolhe_e_lixo_cai_no_default():
    console = Console(stream=io.StringIO(), tier="none", animate=False, width=80)
    question = {"id": "host", "prompt": "Which host?", "type": "choice", "options": ["claude-code", "codex"], "default": "claude-code"}
    scripted = iter(["", "2", "bogus", "99", "still-wrong"])
    ask = wizard.make_asker(console, input_fn=lambda prompt: next(scripted))
    assert ask(question) == ("claude-code", "default-accepted")
    assert ask(question) == ("codex", "human")
    assert ask(question) == ("claude-code", "default")
    rendered = console.stream.getvalue()
    assert "1) claude-code" in rendered and "(default)" in rendered and "not a valid choice" in rendered


def test_perguntador_com_eof_no_stdin_volta_o_default_sem_estourar():
    console = Console(stream=io.StringIO(), tier="none", animate=False, width=80)
    question = {"id": "host", "prompt": "Which host?", "type": "choice", "options": ["a", "b"], "default": "b"}

    def eof(prompt: str) -> str:
        raise EOFError

    assert wizard.make_asker(console, input_fn=eof)(question) == ("b", "default")


def test_CONTROLE_modo_interativo_de_fato_pergunta(manifest, target):
    """Controle: com `interactive=True` e um perguntador injetado, as tres perguntas sao
    feitas -- prova que os testes acima nao passam por um modo interativo que nunca liga."""
    manifest_data, manifest_path = load_manifest()
    calls: list[str] = []

    def ask(question):
        calls.append(question["id"])
        return question["default"], "human"

    options = wizard.InitOptions(target=target, target_label=str(target), interactive=True, benchmark_k=0)
    report = wizard.run_init(options, manifest_data, manifest_path, ask=ask)
    assert calls == [question["id"] for question in wizard.questions(manifest_data)]
    profile = next(stage for stage in report["stages"] if stage["stage"] == "profile")["detail"]
    assert profile["pending_defaults"] == []
    assert set(profile["sources"].values()) == {"human"}
