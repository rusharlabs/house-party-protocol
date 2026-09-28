"""The problem form asks for output a person can paste without saying where they work.

Measured 2026-09-27: the optional field asked for `python -m hpp doctor --json`, whose `manifest`
value is the absolute path of the manifest, under the reporter's home folder, with their account
name in it, and the field said nothing about it. `hpp doctor --report` was written to be pasted:
versions, platform and the doctor's counts, with no path from the machine, so the field asks for
that. The absolute path stays in `--json` on purpose (tests and callers locate the manifest through
it), which is exactly why the form must not ask for that output; the CONTROLE tests prove the
detector sees the shape the form no longer requests.
"""
from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

from hpp import cli

ROOT = Path(__file__).resolve().parent.parent
FORM = ROOT / ".github" / "ISSUE_TEMPLATE" / "problem.yml"
# A drive-letter path (`C:\` or `D:/`, not the `s:/` of `https://`), a macOS home or a Linux home.
MACHINE_PATH = re.compile(r"[A-Za-z]:\\|[A-Za-z]:/(?!/)|(?<![A-Za-z0-9_])/(?:Users|home)/")


def _doctor_field() -> tuple[str, str]:
    """(label, description) of the textarea with `id: doctor`."""
    text = FORM.read_text(encoding="utf-8")
    block = re.search(r"(?ms)^  - type: textarea\n    id: doctor\n(.*?)(?=^  - type: |\Z)", text)
    assert block, "problem.yml has no textarea with id `doctor`"
    label = re.search(r"(?m)^      label: (.+)$", block.group(1))
    assert label, "the doctor field has no label"
    description = re.search(r"(?m)^      description: (.+)$", block.group(1))
    return label.group(1), description.group(1) if description else ""


def _argv(label: str) -> list[str]:
    """The `hpp` arguments the label asks the reporter to run, without the interpreter prefix."""
    quoted = re.search(r"`([^`]+)`", label)
    assert quoted, f"the label names no command: {label!r}"
    argv = shlex.split(quoted.group(1))
    if argv[:3] == ["python", "-m", "hpp"]:
        return argv[3:]
    if argv[:1] == ["hpp"]:
        return argv[1:]
    raise AssertionError(f"the label names a command that is not hpp: {argv}")


def test_the_output_the_form_asks_for_carries_no_machine_path(capsys):
    label, _ = _doctor_field()
    argv = _argv(label)
    assert cli.main(argv) == 0, argv
    out = capsys.readouterr().out
    assert not MACHINE_PATH.search(out), f"`hpp {' '.join(argv)}` prints a path from this machine:\n{out}"


def test_the_field_says_what_to_leave_out_of_older_output():
    # Why: a reporter on a version without `--report` will paste what they have; the field has to
    # name the key that carries the machine path, or the note is a reassurance with no instruction.
    _, description = _doctor_field()
    assert "`manifest`" in description, description


def test_CONTROLE_doctor_json_still_carries_the_absolute_manifest_path(capsys):
    # Why: this is the output the form used to ask for. It stays absolute, because callers locate
    # the manifest through it, and that is the reason the form asks for the report instead.
    assert cli.main(["doctor", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    manifest = Path(report["manifest"])
    assert manifest.is_absolute() and manifest.name == "hpp.manifest.json", report["manifest"]


def test_CONTROLE_the_detector_fires_on_each_home_shape_and_not_on_a_url():
    # The strings are assembled at run time so this file carries no personal path of its own.
    for planted in ("C:" + "\\Users\\" + "alice\\repo", "D:/work/repo", "/Users/" + "bob/code", "/home/" + "carol/code"):
        assert MACHINE_PATH.search(json.dumps({"manifest": planted})), planted
    clean = json.dumps({"platform": "Linux x86_64", "python": "3.12.6", "url": "https://example.invalid/x"})
    assert not MACHINE_PATH.search(clean), clean
