"""`hpp doctor --report` prints the feedback link and the report to paste, locally and offline.

The harness sends nothing: it prints the URL of the feedback form (the issue template that already
ships in `.github/`) with the title filled in, the address of the support page (`SUPPORT.md`, which
lists every other channel), and the doctor JSON below them, with no machine path in it. Opening a
link is the person's act; the CONTROLE tests prove the command opens no socket.
"""
from __future__ import annotations

import json
import re
import socket
import urllib.parse
import urllib.request
from pathlib import Path

from hpp import __version__, cli

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
FORM = "https://github.com/rusharlabs/house-party-protocol/issues/new?template=feedback.yml&title="
SUPPORT = "https://github.com/rusharlabs/house-party-protocol/blob/main/SUPPORT.md"
PERSONAL_PATH = re.compile(r"[A-Za-z]:[\\/]|(?<![A-Za-z0-9_])/(?:Users|home)/")


def _no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("hpp opened a network connection")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(urllib.request, "urlopen", refuse)


def _split(text: str) -> tuple[str, dict]:
    url = next(line.strip() for line in text.splitlines() if line.strip().startswith(FORM))
    body = text[text.index("{"):]
    return url, json.loads(body)


def test_report_prints_the_form_link_and_the_json_to_paste(monkeypatch, capsys):
    _no_network(monkeypatch)
    assert cli.main(["doctor", "--report"]) == 0
    out = capsys.readouterr().out
    url, report = _split(out)
    assert url.startswith(FORM)
    assert report["schema"] == "hpp.doctor-report/v1"
    assert report["version"] == __version__
    assert report["python"] and report["platform"]
    assert report["modules"] == 10 and report["hosts"] == ["claude-code", "codex"]
    assert report["hooks"]["declared"] >= 15
    assert "manifest" not in report


def test_the_title_is_percent_encoded_and_names_the_version(monkeypatch, capsys):
    _no_network(monkeypatch)
    cli.main(["doctor", "--report"])
    url, _ = _split(capsys.readouterr().out)
    title = url[len(FORM):]
    assert " " not in title and "&" not in title
    decoded = urllib.parse.unquote(title)
    assert decoded.startswith("[feedback]") and __version__ in decoded


def test_the_report_carries_no_machine_path(monkeypatch, capsys):
    _no_network(monkeypatch)
    cli.main(["doctor", "--report"])
    _, report = _split(capsys.readouterr().out)
    assert not PERSONAL_PATH.search(json.dumps(report)), report


def test_report_with_json_is_one_object(monkeypatch, capsys):
    _no_network(monkeypatch)
    assert cli.main(["doctor", "--report", "--json"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["feedback_url"].startswith(FORM)
    assert document["report"]["schema"] == "hpp.doctor-report/v1"


def test_the_link_targets_the_issue_tracker_the_package_declares():
    pyproject = (PRODUCT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    issues = re.search(r'^Issues = "([^"]+)"', pyproject, re.M).group(1)
    assert FORM.startswith(issues + "/new?")
    assert (PRODUCT_ROOT / ".github" / "ISSUE_TEMPLATE" / "feedback.yml").is_file()


def test_report_prints_the_support_page_above_the_report_to_paste(monkeypatch, capsys):
    _no_network(monkeypatch)
    assert cli.main(["doctor", "--report"]) == 0
    out = capsys.readouterr().out
    assert SUPPORT in [line.strip() for line in out.splitlines()], out
    # Why above the JSON: everything from the first `{` on is what the person pastes into the form.
    assert out.index(SUPPORT) < out.index("{"), "the support link landed inside the report to paste"
    _, report = _split(out)
    assert "SUPPORT.md" not in json.dumps(report)


def test_report_with_json_carries_the_support_url(monkeypatch, capsys):
    _no_network(monkeypatch)
    assert cli.main(["doctor", "--report", "--json"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert sorted(document) == ["feedback_url", "report", "support_url"]
    assert document["support_url"] == SUPPORT


def test_the_support_link_names_a_page_that_ships_in_the_product_root(monkeypatch, capsys):
    # Why: the address is printed, never fetched, so nothing at run time would notice a page that
    # was renamed or never shipped; this ties the printed URL to the file beside pyproject.toml.
    _no_network(monkeypatch)
    cli.main(["doctor", "--report", "--json"])
    url = json.loads(capsys.readouterr().out)["support_url"]
    pyproject = (PRODUCT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    repository = re.search(r'^Repository = "([^"]+)"', pyproject, re.M).group(1)
    prefix = f"{repository}/blob/main/"
    assert url.startswith(prefix), url
    page = PRODUCT_ROOT / urllib.parse.unquote(url[len(prefix):])
    assert page.is_file(), f"the support link names {page.name}, which is not in the product root"


def test_CONTROLE_doctor_without_report_prints_no_link(capsys):
    assert cli.main(["doctor"]) == 0
    assert "issues/new" not in capsys.readouterr().out


def test_CONTROLE_doctor_without_report_prints_no_support_link(capsys):
    assert cli.main(["doctor"]) == 0
    assert "SUPPORT.md" not in capsys.readouterr().out
