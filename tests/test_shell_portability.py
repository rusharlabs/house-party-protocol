"""The shell portability lint catches what breaks on a stock Mac, and only that.

Every rule has a snippet it must REJECT and a portable twin it must pass: a lint whose rules
only ever pass would look the same as no lint at all. The emitted-copy test then holds every
shipped `.sh` at zero findings; in the source tree there are no modules and it skips, out loud.

# Why (2026-09-27): all seven module evals called a bare `python`, and a stock Mac has only
# `python3`; they failed there with "command not found" before checking anything, and no test
# noticed because nothing ran the evals outside the machines that have `python`.
"""
from __future__ import annotations

import importlib.util
import sys
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    """Load a maintainer script by path (the scripts are not a package; see test_terminal_animation)."""
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Why: on Python 3.14 a dataclass looks its module up in sys.modules while the class is built;
    # a module loaded by path and not registered there fails collection with an AttributeError.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sp = _load("shell_portability")

EMITTED_COPY = Path(os.environ.get("HPP_EMITTED_COPY") or ROOT)

# rule id -> (a line that breaks on a stock Mac, the portable twin)
CASES = {
    "assoc-or-nameref": ("declare -A seen", "declare -a seen"),
    "mapfile": ("mapfile -t lines < list.txt", "while IFS= read -r line; do :; done < list.txt"),
    "case-modification": ('lower="${name,,}"', 'lower="$(printf %s "$name" | tr A-Z a-z)"'),
    "parameter-transform": ('echo "${value@Q}"', "printf '%q' \"$value\""),
    "pipe-stderr": ("make |& tee log", "make 2>&1 | tee log"),
    "append-both": ("make &>> log", "make >> log 2>&1"),
    "coproc": ("coproc worker { cat; }", "worker &"),
    "bash4-shopt": ("shopt -s globstar", "shopt -s nullglob"),
    "wait-n": ("wait -n", 'wait "$pid"'),
    "test-v": ("[[ -v HOME ]] && echo set", '[ -n "${HOME+x}" ] && echo set'),
    "negative-index": ('last="${items[-1]}"', 'last="${items[0]}"'),
    "epoch-vars": ('now="$EPOCHSECONDS"', "now=$(date +%s)"),
    "brace-step": ("for i in {1..9..2}; do :; done", "for i in 1 3 5 7 9; do :; done"),
    "sed-inplace": ("sed -i 's/a/b/' notes.txt", "sed -i.bak 's/a/b/' notes.txt"),
    "sed-r": ("sed -r 's/(a)/b/' notes.txt", "sed -E 's/(a)/b/' notes.txt"),
    "grep-P": ("grep -P '\\d+' notes.txt", "grep -E '[0-9]+' notes.txt"),
    "date-gnu": ('when="$(date -d yesterday +%F)"', "when=$(date +%F)"),
    "stat-gnu": ("size=$(stat -c %s notes.txt)", "size=$(wc -c < notes.txt)"),
    "readlink-f": ('real="$(readlink -f "$p")"', 'real="$(readlink -f "$p" 2>/dev/null || echo "$p")"'),
    "find-printf": ("find . -printf '%p\\n'", "find . -type f -print"),
    "head-negative": ("head -n -2 notes.txt", "head -n 2 notes.txt"),
    "timeout": ("timeout 5 ./slow.sh", "./slow.sh --timeout 5"),
    "gnu-checksum": ("sha256sum dist.zip", "shasum -a 256 dist.zip"),
    "gnu-flags": ("base64 -w0 key.bin", "base64 key.bin"),
    "gnu-tools": ("tac notes.txt", "tail -n 1 notes.txt"),
}


def _rules(text: str) -> set[str]:
    return {f.rule for f in sp.lint_text(text, "case.sh")}


def test_every_rule_has_a_case():
    """A rule without a case would be a rule nobody ever saw fail."""
    assert set(CASES) == {rid for rid, *_ in sp.RULES}


@pytest.mark.parametrize("rule", sorted(CASES))
def test_each_rule_rejects_the_breaking_form(rule):
    bad, _ = CASES[rule]
    assert rule in _rules(bad + "\n"), f"{rule} did not flag: {bad}"


@pytest.mark.parametrize("rule", sorted(CASES))
def test_each_rule_passes_the_portable_twin(rule):
    _, good = CASES[rule]
    assert rule not in _rules(good + "\n"), f"{rule} flagged the portable form: {good}"


def test_expansions_inside_double_quotes_are_code():
    """`"$(...)"` and `"${...}"` are the usual shapes; the lint must see inside them."""
    assert "date-gnu" in _rules('x="$(date -d yesterday)"\n')
    assert "case-modification" in _rules('echo "value: ${name^^}"\n')
    assert "epoch-vars" in _rules('echo "at $EPOCHREALTIME"\n')


def test_comments_heredocs_and_embedded_programs_are_not_shell():
    text = (
        "# timeout 5 and sed -i are named here only as prose\n"
        "echo ok  # mapfile, in a trailing comment\n"
        "cat <<'EOF'\n"
        "sed -i 's/x/y/' f   (inside a heredoc body)\n"
        "EOF\n"
        'python3 -c "\n'
        "import subprocess\n"
        "subprocess.run(['x'], timeout=5)\n"
        '"\n'
    )
    assert _rules(text) - {"bare-python"} == set()


def test_a_waiver_needs_a_reason():
    assert "timeout" not in _rules("timeout 5 ./x.sh  # portable: coreutils is a declared prerequisite\n")
    assert "timeout" in _rules("timeout 5 ./x.sh  # portable:\n")


def test_bare_python_is_rejected_unless_the_script_resolves_it():
    assert "bare-python" in _rules('python "$SCRIPT" --self-test\n')
    assert "bare-python" in _rules('out=$(echo x | python3 "$HOOK")\n')
    resolved = 'PY=python3\npython() { command "$PY" "$@"; }\npython "$SCRIPT" --self-test\n'
    assert "bare-python" not in _rules(resolved)
    assert "bare-python" not in _rules('"$PY" "$SCRIPT"\ncommand -v python3 >/dev/null\n')
    assert "bare-python" not in _rules('order="python python3"\n')


def _marketplace(root: Path, *sources: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    plugins = [{"name": Path(source).name, "source": source} for source in sources]
    (root / "marketplace.json").write_text(json.dumps({"plugins": plugins}), encoding="utf-8")
    return root


def test_the_modules_are_the_directories_marketplace_declares(tmp_path):
    root = _marketplace(tmp_path / "emitted", "./frameworks/a-kit-1.0.0", "./frameworks/b-kit-1.0.0")
    for name in ("a-kit-1.0.0", "b-kit-1.0.0"):
        (root / "frameworks" / name).mkdir(parents=True)
    assert [p.name for p in sp.module_dirs(root)] == ["a-kit-1.0.0", "b-kit-1.0.0"]


def test_a_declared_module_whose_directory_is_missing_is_an_error(tmp_path, capsys, monkeypatch):
    """Dropping it would scan one module fewer and pass; with all of them gone the lint would pass on
    nothing, exactly like the source tree it is not."""
    root = _marketplace(tmp_path / "emitted", "./frameworks/a-kit-1.0.0", "./frameworks/b-kit-1.0.0")
    monkeypatch.setattr(sp, "ROOT", root)
    assert sp.main([]) == 3, "every declared module is missing and the lint passed on nothing"
    assert "a-kit-1.0.0" in capsys.readouterr().err
    (root / "frameworks" / "a-kit-1.0.0").mkdir(parents=True)
    assert sp.main([]) == 3, "a declared module is missing and the lint scanned the others only"
    assert "b-kit-1.0.0" in capsys.readouterr().err
    with pytest.raises(sp.MissingModules, match="b-kit-1.0.0"):
        sp.module_dirs(root)


def test_CONTROLE_without_marketplace_json_there_is_nothing_to_scan_and_it_says_so(tmp_path, capsys, monkeypatch):
    assert sp.module_dirs(tmp_path) == []
    monkeypatch.setattr(sp, "ROOT", tmp_path)
    assert sp.main([]) == 0
    assert "nothing to scan" in capsys.readouterr().out


def _shipped_shell_files() -> list[Path]:
    modules = sp.module_dirs(EMITTED_COPY)
    if not modules:
        pytest.skip(f"no marketplace.json with modules at {EMITTED_COPY} (source tree): nothing shipped to scan")
    return sp.discover(modules)


def test_every_shipped_shell_script_is_portable():
    files = _shipped_shell_files()
    # LC-1b: a scan that found no files would pass by construction
    assert len(files) >= 6, [str(f) for f in files]
    findings = [f for path in files for f in sp.lint_text(path.read_text(encoding="utf-8"), str(path))]
    assert not findings, "\n".join(f"{f.file}:{f.line} [{f.rule}] {f.text}" for f in findings)
