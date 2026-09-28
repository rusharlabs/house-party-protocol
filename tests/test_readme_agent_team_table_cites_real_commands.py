"""Every `hpp` command the README's agent-team table cites exists in the argument parser.

Why this file exists: the section "Agent teams, under evidence" binds every word about a team to
a command that shows the contract holding. That binding is the only thing that separates the
section from a feature list -- and a table drifts: a verb is renamed, a flag is dropped, a
subcommand moves, and the sentence next to it keeps reading as if the command still existed.
Nothing else in the suite reads that table. This file extracts every backticked
`hpp <verb> [<subverb>] [--flag ...]` from its command column, in both languages, and checks
verb, subverb, every flag and every flag value with declared choices against `hpp.cli.build_parser()`
-- introspected in-process, not read from `--help` output, so the check is against the parser
itself and costs no subprocess.

Commands that belong to modules (`lane_board.py ...`, the lane-kit mailbox eval, the roles
directory) are not part of the product source this suite runs on; they are listed in
`KNOWN_MODULE_COMMANDS` and not checked here. A backticked span in the command column that is
neither an `hpp` command, a known module command nor a known token FAILS the test: the table
may not grow a new unchecked kind of command in silence.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pytest

from hpp import cli
from hpp.graph import build_graph
from hpp.manifest import load_manifest

PRODUCT_ROOT = Path(__file__).resolve().parent.parent

SECTION = {
    "README.md": "## Agent teams, under evidence",
    "README.pt-BR.md": "## Times de agentes, sob evidência",
}
# Why: these run from an installed module directory, not from `python -m hpp`; the lane module's
# own self-test and the monorepo's lane-kit tests measure them.
KNOWN_MODULE_COMMANDS = ("lane_board.py", "evals/mailbox-e2e.sh", "ls frameworks/dev-squad-kit-")
# Why: `agent-roles` is not a command but a node of the capability graph, cited beside the graph
# command that lists it; it is checked against that graph below.
KNOWN_TOKENS = {"agent-roles"}
# Why (LC-1b): a control against the vacuous pass. The table cites more than twenty command spans;
# a parser that reported nothing, or a section heading that moved, would read as "all valid".
MINIMUM_DISTINCT_HPP_COMMANDS = 15

_SPAN = re.compile(r"`([^`]+)`")


# --------------------------------------------------------------------------- extraction

def _split_row(line: str) -> list[str]:
    """Cells of one pipe-table row; a `|` inside backticks does not split a cell."""
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    cells, current, in_code = [], "", False
    for char in text:
        if char == "`":
            in_code = not in_code
        if char == "|" and not in_code:
            cells.append(current.strip())
            current = ""
        else:
            current += char
    cells.append(current.strip())
    return cells


def table_rows(markdown: str, heading: str) -> list[list[str]]:
    """The body rows of the first pipe table under `heading`, without header and delimiter."""
    lines = markdown.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == heading)
    except StopIteration:
        return []
    rows: list[list[str]] = []
    i = start + 1
    while i < len(lines) and not lines[i].startswith("|"):
        if lines[i].startswith("## "):
            return []
        i += 1
    while i < len(lines) and lines[i].startswith("|"):
        rows.append(_split_row(lines[i]))
        i += 1
    return rows[2:] if len(rows) > 2 else []


def command_spans(rows: list[list[str]]) -> list[str]:
    """Every backticked span in the LAST column of every row, in table order."""
    spans: list[str] = []
    for row in rows:
        if not row or not row[-1]:
            continue
        spans.extend(_SPAN.findall(row[-1]))
    return spans


def classify(span: str) -> str:
    if span.startswith("hpp "):
        return "hpp"
    if span.startswith(KNOWN_MODULE_COMMANDS):
        return "module"
    if span in KNOWN_TOKENS:
        return "token"
    return "unknown"


# --------------------------------------------------------------------------- the check

def _subparsers(parser: argparse.ArgumentParser) -> argparse._SubParsersAction | None:
    return next((a for a in parser._actions if isinstance(a, argparse._SubParsersAction)), None)


def check_hpp_command(span: str, parser: argparse.ArgumentParser) -> list[str]:
    """Findings for one `hpp ...` span against the real parser; an empty list means it exists.

    Verb, then a subverb when the verb has subparsers, then every `-x` / `--flag` against the
    option strings of the innermost parser, and the word after a flag against that flag's
    declared choices when it has any. A `<placeholder>` is never judged."""
    tokens = span.split()
    if len(tokens) < 2:
        return [f"{span!r}: no verb"]
    top = _subparsers(parser)
    verb = tokens[1]
    if verb not in top.choices:
        return [f"{span!r}: unknown verb {verb!r}"]
    current = top.choices[verb]
    position = 2
    nested = _subparsers(current)
    if nested is not None:
        if position >= len(tokens) or tokens[position].startswith("-"):
            return [f"{span!r}: {verb!r} needs a subverb, one of {sorted(nested.choices)}"]
        subverb = tokens[position]
        if subverb not in nested.choices:
            return [f"{span!r}: unknown subverb {subverb!r} under {verb!r}"]
        current = nested.choices[subverb]
        position += 1
    options = {flag: action for action in current._actions for flag in action.option_strings}
    findings: list[str] = []
    while position < len(tokens):
        token = tokens[position]
        position += 1
        if not token.startswith("-"):
            continue  # a positional or a value that no flag claimed
        if token not in options:
            findings.append(f"{span!r}: unknown flag {token!r} for {' '.join(tokens[1:position - 1])!r}")
            continue
        action = options[token]
        if action.nargs == 0:
            continue  # store_true: the next token is not its value
        if position < len(tokens) and not tokens[position].startswith(("-", "<")):
            value = tokens[position]
            position += 1
            if action.choices is not None and value not in action.choices:
                findings.append(f"{span!r}: {token} does not accept {value!r}; choices {sorted(action.choices)}")
    return findings


def check_table(markdown: str, heading: str, parser: argparse.ArgumentParser) -> dict:
    spans = command_spans(table_rows(markdown, heading))
    findings: list[str] = []
    hpp_spans: list[str] = []
    for span in spans:
        kind = classify(span)
        if kind == "hpp":
            hpp_spans.append(span)
            findings.extend(check_hpp_command(span, parser))
        elif kind == "unknown":
            findings.append(f"{span!r}: neither an hpp command, a known module command nor a known token")
    return {"spans": spans, "hpp": hpp_spans, "findings": findings}


def _readme(name: str) -> str:
    return (PRODUCT_ROOT / name).read_text(encoding="utf-8")


def _normalised(span: str) -> str:
    return re.sub(r"<[^>]+>", "<>", span)


# --------------------------------------------------------------------------- real tests

@pytest.mark.parametrize("name", sorted(SECTION))
def test_every_hpp_command_in_the_agent_team_table_exists_in_the_parser(name: str):
    report = check_table(_readme(name), SECTION[name], cli.build_parser())
    assert report["findings"] == [], "\n".join(report["findings"])


@pytest.mark.parametrize("name", sorted(SECTION))
def test_CONTROLE_the_table_was_read_and_cites_a_non_trivial_number_of_commands(name: str):
    """LC-1b: `no findings` over an empty table is indistinguishable from `every command exists`."""
    report = check_table(_readme(name), SECTION[name], cli.build_parser())
    distinct = {_normalised(span) for span in report["hpp"]}
    assert len(distinct) >= MINIMUM_DISTINCT_HPP_COMMANDS, (
        f"{name}: {len(distinct)} distinct hpp commands read under {SECTION[name]!r} "
        f"(floor {MINIMUM_DISTINCT_HPP_COMMANDS}); the section or its table moved")
    assert any(classify(span) == "module" for span in report["spans"]), (
        f"{name}: no module command in the table; KNOWN_MODULE_COMMANDS excuses nothing")


def test_the_two_languages_cite_the_same_hpp_commands():
    """The bilingual gate compares headings and code fences; a table cell is prose to it.

    Here the command column is what must not diverge: the same hpp commands, in the same order,
    with only the `<placeholder>` translated."""
    parser = cli.build_parser()
    english = [_normalised(s) for s in check_table(_readme("README.md"), SECTION["README.md"], parser)["hpp"]]
    portuguese = [_normalised(s) for s in check_table(_readme("README.pt-BR.md"), SECTION["README.pt-BR.md"], parser)["hpp"]]
    assert english == portuguese


def test_the_known_token_is_a_node_of_the_capability_graph():
    """`agent-roles` is cited beside `hpp graph --view capability`; the graph must carry it."""
    manifest, _ = load_manifest()
    ids = {node["id"] for node in build_graph(manifest, "capability")["nodes"]}
    for token in KNOWN_TOKENS:
        assert f"capability:{token}" in ids, sorted(ids)


# --------------------------------------------------------------------------- controls

_TABLE_HEAD = (
    "## Agent teams, under evidence\n\nprose\n\n"
    "| what the team does | what HPP holds it to | the command that shows it |\n"
    "|---|---|---|\n"
    "| **split the work** | | |\n"
    "| says done | verified needs evidence | `hpp evidence verify` · `hpp status --json` |\n"
    "| reviews | refused | `lane_board.py --self-test` · `hpp attest create --maker a --checker a` → exit 2 |\n"
    "| passes once | `pass@k` apart | `hpp eval run -k 3 --gate both` |\n"
    "| routes | by tier | `hpp route --maker-family <family>` |\n"
)
_TAIL = "\nAfter the table `hpp bogus` is not in the table.\n"
_TABLE = _TABLE_HEAD + _TAIL


def test_CONTROLE_a_planted_command_that_does_not_exist_is_rejected():
    """The check must be able to say no, or `no findings` on the real table proves nothing.

    The planted row goes INSIDE the table (before the blank line that ends it); a row planted
    after the table is prose, and the control below proves prose is not read."""
    parser = cli.build_parser()
    for planted, expected in (
        ("| loops | budget | `hpp verdict accept --force-green` |", "unknown verb 'verdict'"),
        ("| loops | budget | `hpp work fly` |", "unknown subverb 'fly'"),
        ("| loops | budget | `hpp status --all` |", "unknown flag '--all'"),
        ("| loops | budget | `hpp eval run --gate maybe` |", "does not accept 'maybe'"),
        ("| loops | budget | `hpp work` |", "needs a subverb"),
        ("| loops | budget | `some_other_tool.py run` |", "neither an hpp command"),
    ):
        report = check_table(_TABLE_HEAD + planted + "\n" + _TAIL, "## Agent teams, under evidence", parser)
        assert len(report["findings"]) == 1, (planted, report["findings"])
        assert expected in report["findings"][0], (planted, report["findings"])


def test_CONTROLE_the_clean_planted_table_passes_and_is_read_in_full():
    parser = cli.build_parser()
    report = check_table(_TABLE, "## Agent teams, under evidence", parser)
    assert report["findings"] == []
    assert report["hpp"] == ["hpp evidence verify", "hpp status --json", "hpp attest create --maker a --checker a",
                             "hpp eval run -k 3 --gate both", "hpp route --maker-family <family>"]
    assert "lane_board.py --self-test" in report["spans"]
    # the prose after the table is not read: `hpp bogus` produced no finding above
    assert table_rows(_TABLE, "## A heading that is not there") == []


def test_CONTROLE_a_pipe_inside_backticks_does_not_split_the_command_cell():
    row = "| a | b | `hpp route --policy economy\\|balanced\\|frontier` |"
    assert _split_row(row)[-1] == "`hpp route --policy economy\\|balanced\\|frontier`"
    assert len(_split_row(row)) == 3
