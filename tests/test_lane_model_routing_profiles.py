"""Declared models and opt-in profiles reach CLI arguments without weakening independent review."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


MODEL_IDS = (
    ("codex", "gpt-6.1-sol", "gpt"),
    ("codex", "gpt-6.1-terra", "gpt"),
    ("codex", "gpt-6-luna", "gpt"),
    ("codex", "gpt-6-astra", "gpt"),
    ("codex", "gpt-6-sol", "gpt"),
    ("claude", "claude-sonnet-5-5", "claude"),
    ("claude", "claude-opus-5-5", "claude"),
    ("claude", "claude-haiku-5-5", "claude"),
    ("claude", "claude-fable-5-2", "claude"),
)

PROFILE_MODELS = {
    "balanced": {
        "codex": ("gpt-6.1-sol", "gpt-6-astra", "gpt-6.1-sol"),
        "claude": ("claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-2"),
    },
    "economy": {
        "codex": ("gpt-6-luna", "gpt-6.1-sol", "gpt-6.1-sol"),
        "claude": ("claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"),
    },
    "visual": {
        "codex": ("gpt-6.1-terra", "gpt-6.1-sol", "gpt-6.1-sol"),
        "claude": ("claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-2"),
    },
}


@pytest.fixture(scope="module")
def dashboard():
    product = Path(__file__).resolve().parents[1]
    kits = sorted(product.glob("multi-session/lane-kit-*/scripts/lane_dashboard.py"))
    if not kits:
        source = product.parents[2] / "staging/lane-kit/scripts/lane_dashboard.py"
        if not source.is_file():
            pytest.skip("requires the emitted lane-kit or a source checkout")
        kits = [source]
    assert len(kits) == 1
    spec = importlib.util.spec_from_file_location("hpp_lane_model_profiles", kits[0])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def settings(project, value):
    target = project / ".claude" / "lanes" / "dashboard.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value), encoding="utf-8")


def which(name):
    return "/fake/" + name if name in ("codex", "claude") else None


@pytest.mark.parametrize("agent,model,family", MODEL_IDS)
def test_exact_declared_id_reaches_cli_argv(dashboard, tmp_path, agent, model, family):
    settings(tmp_path, {"agents": {agent: {"model": model}}})
    profile = dashboard.agent_profile(tmp_path, agent, "executor", which)
    assert profile["available"] and not profile["identity_problem"]
    assert profile["declared_model"] == profile["model"] == model
    assert profile["family"] == family
    argv = dashboard._argv(profile["headless"], profile["command"], "read prompt", profile)
    expected = ["codex", "exec", "--model", model, "read prompt"] if agent == "codex" else [
        "claude", "--model", model, "-p", "read prompt"]
    assert argv == expected


@pytest.mark.parametrize("name", PROFILE_MODELS)
def test_shipped_profile_overrides_are_consumed_by_real_roles(dashboard, tmp_path, name):
    kit = Path(dashboard.__file__).resolve().parents[1]
    template = kit / "templates" / f"dashboard.models-{name}.example.json"
    value = json.loads(template.read_text(encoding="utf-8"))
    settings(tmp_path, value)
    for agent, (default, reviewer, analyst) in PROFILE_MODELS[name].items():
        for role, expected in (("executor", default), ("planner", default),
                               ("reviewer", reviewer), ("analyst", analyst)):
            profile = dashboard.agent_profile(tmp_path, agent, role, which)
            assert not profile["identity_problem"]
            assert profile["declared_model"] == expected
            argv = dashboard._argv(profile["headless"], profile["command"], "task", profile)
            assert argv[argv.index("--model") + 1] == expected
    assert dashboard.brief_order({"gpt"}, which, tmp_path) == ["claude"]
    assert dashboard.brief_order({"claude"}, which, tmp_path) == ["codex"]


def review_history(builder):
    return [
        {"item_id": "TASK", "state": state, "lane_id": "build", "role": "executor", "model": builder}
        for state in ("CLAIMED", "BUILDING", "CHECKPOINT-READY")
    ]


@pytest.mark.parametrize("builder,reviewer", [
    ("gpt-6.1-sol", "gpt-6-luna"),
    ("gpt-6.1-sol", "gpt-6-astra"),
    ("gpt-6.1-sol", "gpt-6.1-terra"),
    ("gpt-6.1-sol", "gpt-6-sol"),
    ("claude-sonnet-5-5", "claude-opus-5-5"),
    ("claude-sonnet-5-5", "claude-haiku-5-5"),
    ("claude-opus-5-5", "claude-fable-5-2"),
])
def test_changing_model_inside_a_vendor_cannot_launch_a_review(dashboard, tmp_path, monkeypatch,
                                                              builder, reviewer):
    agent = "codex" if reviewer.startswith("gpt-") else "claude"
    settings(tmp_path, {"agents": {agent: {"model": reviewer}}})
    history = review_history(builder)
    monkeypatch.setattr(dashboard, "_latest", lambda *_args: (history[-1], history))
    launched = []

    def launch(*_args, **_kwargs):
        launched.append(True)
        return 200, {}

    monkeypatch.setattr(dashboard, "launch_lane", launch)
    status, value = dashboard.launch_review(tmp_path, {"item_id": "TASK", "agent": agent}, which=which)
    assert status == 409 and "maker≠checker" in value["error"]
    assert launched == []


@pytest.mark.parametrize("builder,reviewer", [("gpt-6.1-sol", "claude-opus-5-5"),
                                             ("claude-sonnet-5-5", "gpt-6-astra")])
def test_another_vendor_reaches_the_review_launcher(dashboard, tmp_path, monkeypatch, builder, reviewer):
    agent = "codex" if reviewer.startswith("gpt-") else "claude"
    settings(tmp_path, {"agents": {agent: {"model": reviewer}}})
    history = review_history(builder)
    monkeypatch.setattr(dashboard, "_latest", lambda *_args: (history[-1], history))
    launched = []

    def launch(*_args, **kwargs):
        launched.append(kwargs)
        return 200, {"model": reviewer}

    monkeypatch.setattr(dashboard, "launch_lane", launch)
    status, value = dashboard.launch_review(tmp_path, {"item_id": "TASK", "agent": agent}, which=which)
    assert status == 200 and value["model"] == reviewer
    assert len(launched) == 1 and launched[0]["role"] == "reviewer"
