"""The module runner fails when a self-test or an eval fails, and never passes on nothing.

A fake emitted copy stands in for the real one: its kit doctor reports the smoke results the
case needs, and its evals are two-line bash scripts. The real modules are exercised by CI
(`python scripts/module_checks.py` in the published repository).
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    """Load a maintainer script by path (the scripts are not a package; see test_terminal_animation)."""
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mc = _load("module_checks")

BASH = shutil.which("bash")
needs_bash = pytest.mark.skipif(BASH is None, reason="no bash on this machine")

# The flag and the markers are spelled in pieces so this fake doctor does not itself look like a
# script that answers --self-test (the runner's LC-1b control would count it).
FAKE_DOCTOR = '''\
import json, sys
from pathlib import Path
kit = Path(sys.argv[sys.argv.index("--kit") + 1])
flag, hidden, broken = "--self" + "-test", "HID" + "DEN", "BRO" + "KEN"
results = []
for py in sorted(kit.rglob("*.py")):
    text = py.read_text(encoding="utf-8")
    if flag in text and hidden not in text:
        results.append({"file": py.name, "status": "fail" if broken in text else "ok"})
print(json.dumps({"stages": [{"stage": "smoke", "results": results}]}))
'''


def _tree(tmp_path: Path, *, broken_self_test=False, failing_eval=False, hidden_self_test=False) -> Path:
    root = tmp_path / "emitted"
    forge = root / "installers" / "kit-forge-1.0.0"
    forge.mkdir(parents=True)
    (forge / "kit_doctor.py").write_text(FAKE_DOCTOR, encoding="utf-8")
    mod = root / "frameworks" / "demo-kit-1.0.0"
    (mod / "evals").mkdir(parents=True)
    marker = "BROKEN" if broken_self_test else ("HIDDEN" if hidden_self_test else "")
    (mod / "tool.py").write_text(f"# --self-test {marker}\n", encoding="utf-8")
    (mod / "evals" / "roundtrip.sh").write_text(
        "echo 'roundtrip: 3/3 checks green'\nexit {}\n".format(1 if failing_eval else 0), encoding="utf-8")
    (root / "marketplace.json").write_text(json.dumps({"plugins": [
        {"name": "kit-forge", "source": "./installers/kit-forge-1.0.0"},
        {"name": "demo-kit", "source": "./frameworks/demo-kit-1.0.0"},
    ]}), encoding="utf-8")
    return root


def test_source_tree_has_nothing_to_run_and_says_so(tmp_path, capsys):
    assert mc.main(["--root", str(tmp_path)]) == 0
    assert "nothing to run" in capsys.readouterr().out


def test_a_declared_module_whose_directory_is_missing_is_an_error(tmp_path, capsys):
    """marketplace.json declares it and the copy does not carry it: an incomplete distribution, not
    one module fewer to check."""
    root = _tree(tmp_path)
    shutil.rmtree(root / "frameworks" / "demo-kit-1.0.0")
    assert mc.main(["--root", str(root), "--skip-evals"]) == 3
    assert "demo-kit" in capsys.readouterr().err


def test_every_declared_module_missing_is_an_error_not_a_source_tree(tmp_path, capsys):
    root = _tree(tmp_path)
    shutil.rmtree(root / "frameworks")
    shutil.rmtree(root / "installers")
    assert mc.main(["--root", str(root), "--skip-evals"]) == 3
    captured = capsys.readouterr()
    assert "nothing to run" not in captured.out and "kit-forge" in captured.err


@needs_bash
def test_green_tree_passes(tmp_path, capsys):
    assert mc.main(["--root", str(_tree(tmp_path)), "--bash", BASH]) == 0
    out = capsys.readouterr().out
    assert "1 self-test(s), 1/1 eval(s)" in out and "0 failure(s)" in out


@needs_bash
def test_a_failing_eval_fails_the_run(tmp_path, capsys):
    assert mc.main(["--root", str(_tree(tmp_path, failing_eval=True)), "--bash", BASH]) == 1
    out = capsys.readouterr().out
    assert "roundtrip.sh  exit 1" in out


def test_a_failing_self_test_fails_the_run(tmp_path, capsys):
    assert mc.main(["--root", str(_tree(tmp_path, broken_self_test=True)), "--skip-evals"]) == 1
    assert "self-test  tool.py: fail" in capsys.readouterr().out


def test_zero_self_tests_run_is_not_a_pass(tmp_path, capsys):
    """LC-1b: scripts that answer --self-test and a smoke stage that ran none is a failure."""
    assert mc.main(["--root", str(_tree(tmp_path, hidden_self_test=True)), "--skip-evals"]) == 1
    assert "ran none" in capsys.readouterr().out


@pytest.mark.skipif(os.name == "nt", reason="--without-python is for macOS and Linux")
def test_without_python_leaves_only_this_interpreter_as_python3(tmp_path):
    shim = tmp_path / "shim"
    shim.mkdir()
    env = mc._without_python_env(shim)
    dirs = env["PATH"].split(os.pathsep)
    assert dirs[0] == str(shim)
    assert (shim / "python3").resolve() == Path(sys.executable).resolve()
    assert not any((Path(d) / "python").exists() for d in dirs)
