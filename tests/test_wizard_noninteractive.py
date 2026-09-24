"""Non-interactive mode: zero `input()`; everything through a flag or an answers file.

`builtins.input` is replaced by a function that EXPLODES. If any non-interactive
path called `input`, the test would fail with AssertionError, not with a hung
prompt. The control at the end proves that interactive mode, when actually
turned on, calls the asker -- otherwise "did not call input" would be trivially true.
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
def test_no_non_interactive_path_calls_input(target, flags, capsys):
    """With no TTY (pytest captures stdout) none of the four paths can prompt -- including
    the one with no flag at all, because TTY detection is part of the rule, not an extra."""
    code = cli.main(["init", "--target", str(target), "--no-benchmark", "--no-animation", *flags])
    assert code == 0
    out = capsys.readouterr().out
    if "--json" in flags:
        assert json.loads(out)["interactive"] is False


def test_interactivity_detection_follows_tty_flags_and_ci(manifest, target):
    assert wizard.prepare_options(_args(target=str(target)), manifest, env={}, stdin_tty=True, stdout_tty=True).interactive is True
    assert wizard.prepare_options(_args(target=str(target)), manifest, env={}, stdin_tty=False, stdout_tty=True).interactive is False
    assert wizard.prepare_options(_args(target=str(target)), manifest, env={}, stdin_tty=True, stdout_tty=False).interactive is False
    assert wizard.prepare_options(_args(target=str(target), yes=True), manifest, env={}, stdin_tty=True, stdout_tty=True).interactive is False
    assert wizard.prepare_options(_args(target=str(target), non_interactive=True), manifest, env={}, stdin_tty=True, stdout_tty=True).interactive is False
    assert wizard.prepare_options(_args(target=str(target), json=True), manifest, env={}, stdin_tty=True, stdout_tty=True).interactive is False
    assert wizard.prepare_options(_args(target=str(target)), manifest, env={"CI": "true"}, stdin_tty=True, stdout_tty=True).interactive is False


def test_profile_file_answers_the_questions_and_flag_wins_over_file(manifest, target, capsys):
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


def test_modules_replaces_the_bundle_and_becomes_a_custom_plan(target, capsys):
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
def test_invalid_profile_file_is_a_usage_error(manifest, target, content, fragment):
    answers = target.parent / "answers.json"
    answers.write_text(content, encoding="utf-8")
    with pytest.raises(wizard.InitUsageError, match=fragment):
        wizard.prepare_options(_args(target=str(target), profile=str(answers)), manifest, env={}, stdin_tty=False, stdout_tty=False)


@pytest.mark.parametrize("field,value,fragment", [
    ("host", "vim", "unknown host"),
    ("bundle", "nope", "unknown bundle"),
    ("modules", "operator-kit,ghost-kit", "unknown module"),
])
def test_choice_outside_the_manifest_is_block_like_in_hpp_install(manifest, target, field, value, fragment):
    with pytest.raises(InstallError, match=fragment):
        wizard.prepare_options(_args(target=str(target), **{field: value}), manifest, env={}, stdin_tty=False, stdout_tty=False)


def test_empty_modules_is_a_usage_error(manifest, target):
    with pytest.raises(wizard.InitUsageError, match="at least one module"):
        wizard.prepare_options(_args(target=str(target), modules=" , "), manifest, env={}, stdin_tty=False, stdout_tty=False)


def test_interactive_asker_enter_accepts_default_number_chooses_and_garbage_falls_to_default():
    console = Console(stream=io.StringIO(), tier="none", animate=False, width=80)
    question = {"id": "host", "prompt": "Which host?", "type": "choice", "options": ["claude-code", "codex"], "default": "claude-code"}
    scripted = iter(["", "2", "bogus", "99", "still-wrong"])
    ask = wizard.make_asker(console, input_fn=lambda prompt: next(scripted))
    assert ask(question) == ("claude-code", "default-accepted")
    assert ask(question) == ("codex", "human")
    assert ask(question) == ("claude-code", "default")
    rendered = console.stream.getvalue()
    assert "1) claude-code" in rendered and "(default)" in rendered and "not a valid choice" in rendered


def test_asker_with_eof_on_stdin_falls_back_to_default_without_raising():
    console = Console(stream=io.StringIO(), tier="none", animate=False, width=80)
    question = {"id": "host", "prompt": "Which host?", "type": "choice", "options": ["a", "b"], "default": "b"}

    def eof(prompt: str) -> str:
        raise EOFError

    assert wizard.make_asker(console, input_fn=eof)(question) == ("b", "default")


def test_CONTROLE_interactive_mode_actually_asks(manifest, target):
    """Control: with `interactive=True` and an injected asker, every question is
    asked -- proves that the tests above do not pass through an interactive mode that never turns on."""
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
