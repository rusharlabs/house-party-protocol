"""The installer offers an OPTIONAL typed-decision advisor and prints how to integrate it.

The product's refusals stay intact: hpp calls no model, stores no key and writes nothing but the
profile. What the wizard adds is a declared choice (`off` by default) and, when a provider is
declared, the instructions a person follows to wire their own key and their own decider.
"""
from __future__ import annotations

import builtins
import json

import pytest

from hpp import cli, wizard
from hpp.manifest import load_manifest

ADVISORS = ("typesafe", "openrouter", "compatible")


@pytest.fixture()
def target(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    return workspace


@pytest.fixture(autouse=True)
def no_input(monkeypatch):
    def explode(prompt=""):
        raise AssertionError(f"input() called in non-interactive mode: {prompt!r}")
    monkeypatch.setattr(builtins, "input", explode)


def _report(target, capsys, *extra):
    code = cli.main(["init", "--target", str(target), "--no-benchmark", "--no-animation", "--json", *extra])
    return code, json.loads(capsys.readouterr().out)


def _stage(report, name):
    return next(stage for stage in report["stages"] if stage["stage"] == name)["detail"]


def test_the_advisor_is_a_question_and_its_default_is_off():
    manifest, _ = load_manifest()
    question = next(item for item in wizard.questions(manifest) if item["id"] == "decision_advisor")
    assert question["default"] == "off"
    assert question["options"][0] == "off" and set(ADVISORS) <= set(question["options"])


def test_off_by_default_changes_neither_the_profile_nor_the_pending_defaults(target, capsys):
    code, report = _report(target, capsys, "--host", "claude-code", "--policy-mode", "audit")
    profile = _stage(report, "profile")
    assert code == 0
    assert "decision_advisor" not in profile["profile"]
    assert "decision_advisor" not in profile["pending_defaults"]
    lines = "\n".join(_stage(report, "wire-suggest")["lines"])
    assert "decide.py" not in lines


@pytest.mark.parametrize("advisor", ADVISORS)
def test_a_declared_advisor_is_recorded_and_its_integration_is_printed_not_performed(target, capsys, advisor):
    code, report = _report(target, capsys, "--decision-advisor", advisor)
    assert code == 0
    profile = _stage(report, "profile")["profile"]
    assert profile["decision_advisor"] == advisor
    wire = _stage(report, "wire-suggest")
    text = "\n".join(wire["lines"])
    assert wire["writes"] == 0
    assert "examples/typed-decisions/decide.py" in text
    assert "hpp decide eval" in text and "hpp decide validate" in text
    assert "never" in text.lower()
    if advisor == "typesafe":
        assert "TYPESAFE_API_KEY" in text
    if advisor == "openrouter":
        assert "OPENROUTER_API_KEY" in text
    if advisor == "compatible":
        assert "--endpoint" in text


def test_the_apply_writes_the_declared_advisor_and_never_the_key_in_the_shell(target, capsys, monkeypatch):
    sentinel = "sentinel-key-value-0123456789"
    monkeypatch.setenv("TYPESAFE_API_KEY", sentinel)
    code = cli.main(["init", "--target", str(target), "--apply", "--no-benchmark", "--no-animation", "--json",
                     "--decision-advisor", "typesafe"])
    printed = capsys.readouterr().out
    assert code == 0
    written = (target / ".hpp" / "profile.json").read_text(encoding="utf-8")
    assert json.loads(written)["decision_advisor"] == "typesafe"
    assert sentinel not in written and sentinel not in printed
    assert sorted(path.name for path in (target / ".hpp").iterdir()) == ["profile.json"]


def test_the_advisor_block_is_not_counted_as_commands_to_paste(target, capsys):
    _, plain = _report(target, capsys)
    _, advised = _report(target, capsys, "--decision-advisor", "compatible")
    summary = lambda report: next(stage for stage in report["stages"] if stage["stage"] == "wire-suggest")["summary"]
    assert summary(plain) == summary(advised)
    assert len(_stage(advised, "wire-suggest")["lines"]) > len(_stage(plain, "wire-suggest")["lines"])


def test_the_profile_file_may_declare_the_advisor(target, capsys, tmp_path):
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({"decision_advisor": "compatible"}), encoding="utf-8")
    code, report = _report(target, capsys, "--profile", str(answers))
    assert code == 0
    assert _stage(report, "profile")["sources"]["decision_advisor"] == "file"


def test_CONTROLE_an_unknown_advisor_is_refused(target, capsys, tmp_path):
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({"decision_advisor": "whatever-vendor"}), encoding="utf-8")
    code = cli.main(["init", "--target", str(target), "--no-benchmark", "--no-animation", "--json",
                     "--profile", str(answers)])
    assert code == 2


def test_the_suggested_apply_keeps_the_declared_advisor(target, capsys):
    """The NEXT line is what a person copies; dropping the advisor there silently undoes the choice."""
    _, report = _report(target, capsys, "--decision-advisor", "openrouter")
    assert any("--decision-advisor openrouter" in step and "--apply" in step for step in report["next"])


def test_CONTROLE_off_adds_no_advisor_flag_to_the_suggested_apply(target, capsys):
    _, report = _report(target, capsys)
    assert not any("--decision-advisor" in step for step in report["next"])
