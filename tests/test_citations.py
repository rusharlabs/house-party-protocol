"""Citation check (`hpp.citation-check/v1`): a claim bigger than its proof becomes an exit code.

`hpp/citations.py` reads an answer and the context it was supposedly built from, and says, without a
model, which sentences cite something that is not in the context (BLOCK), which markers try to cite
several sources at once (BLOCK), and which sentences state a number with no citation at all (WARN).
It does not judge whether a source supports its sentence; that limit is written into the module.

Every finding code below is triggered on purpose and discriminated: the CONTROLE tests prove the
checker is not blocking everything, and that the same instrument flips when one marker breaks.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

import pytest

from hpp.citations import (
    DEFAULT_MARKER,
    SCHEMA,
    CitationError,
    check,
    check_files,
    exit_for,
    split_sentences,
)

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
MODULE = PRODUCT_ROOT / "hpp" / "citations.py"
EXAMPLE = PRODUCT_ROOT / "examples" / "citations"

CONTEXT = [
    {"id": "a", "text": "Revenue grew 12% in 2025."},
    {"id": "b", "text": "The plan costs $40 per seat."},
    {"id": "doc-1", "text": "A hyphenated id is still one id."},
    {"id": "1", "text": "one"},
    {"id": "2", "text": "two"},
    {"id": "3", "text": "three"},
]


def _codes(report):
    return [finding["code"] for finding in report["findings"]]


# --------------------------------------------------------------------------- controls first

def test_CONTROLE_the_shipped_example_is_clean():
    report = check_files(EXAMPLE / "answer.md", EXAMPLE / "context.json")
    assert report["schema"] == SCHEMA
    assert report["findings"] == []
    assert (report["verdict"], report["exit_code"]) == ("ok", 0)
    counts = report["counts"]
    # the example is small enough to count by hand: 2 headings + 5 prose sentences, 5 markers
    assert counts["sentences"] == 7
    assert counts["markers"] == 5
    assert counts["cited_ids"] == 5
    assert counts["unique_cited_ids"] == 4
    assert counts["context_ids"] == 5
    assert counts["unused_context_ids"] == 1


def test_CONTROLE_the_same_example_blocks_when_one_marker_points_nowhere(tmp_path):
    broken = (EXAMPLE / "answer.md").read_text(encoding="utf-8").replace("[ID:glossary]", "[ID:glossary-v2]")
    answer = tmp_path / "answer.md"
    answer.write_text(broken, encoding="utf-8")
    report = check_files(answer, EXAMPLE / "context.json")
    assert _codes(report) == ["UNKNOWN_ID"]
    assert (report["verdict"], report["exit_code"]) == ("block", 2)


def test_CONTROLE_a_cited_number_is_not_an_uncited_claim():
    report = check("Revenue grew 12% in 2025 [ID:a].", CONTEXT)
    assert report["findings"] == [] and report["exit_code"] == 0


# --------------------------------------------------------------------------- BLOCK class

def test_an_unknown_id_blocks_with_the_sentence_and_the_marker():
    report = check("Revenue is fine [ID:a]. Churn fell to zero [ID:z].", CONTEXT)
    assert _codes(report) == ["UNKNOWN_ID"]
    finding = report["findings"][0]
    assert finding["severity"] == "block"
    assert finding["sentence"] == 2 and finding["line"] == 1
    assert finding["marker"] == "[ID:z]"
    assert finding["excerpt"] == "Churn fell to zero [ID:z]."
    assert (report["verdict"], exit_for(report)) == ("block", 2)


@pytest.mark.parametrize("marker", ["[ID:1-3]", "[ID:1,2]", "[ID:1..3]", "[ID:1 - 3]", "[ID:1–3]",
                                    "[ID:a, b]", "[ID:a;b]"])
def test_a_marker_that_cites_a_range_or_a_list_blocks(marker):
    report = check(f"All three agree {marker}.", CONTEXT)
    assert _codes(report) == ["RANGE"], report["findings"]
    assert report["exit_code"] == 2


def test_CONTROLE_a_hyphenated_id_that_exists_is_one_id_not_a_range():
    assert check("One id [ID:doc-1].", CONTEXT)["findings"] == []


def test_CONTROLE_an_unknown_hyphenated_id_is_unknown_not_a_range():
    assert _codes(check("A report [ID:report-final].", CONTEXT)) == ["UNKNOWN_ID"]
    assert _codes(check("A dated note [ID:2026-09-24].", CONTEXT)) == ["UNKNOWN_ID"]


@pytest.mark.parametrize("marker", ["[ID:]", "[ID:   ]"])
def test_an_empty_marker_blocks(marker):
    report = check(f"Something was said {marker}.", CONTEXT)
    assert _codes(report) == ["EMPTY_MARKER"]
    assert report["exit_code"] == 2


def test_block_outranks_warn_and_both_findings_are_kept():
    report = check("Churn fell [ID:z]. Revenue grew 12%.", CONTEXT)
    assert _codes(report) == ["UNKNOWN_ID", "UNCITED_CLAIM"]
    assert (report["verdict"], report["exit_code"]) == ("block", 2)


# --------------------------------------------------------------------------- WARN class

def test_too_many_markers_in_one_sentence_warns_and_the_limit_is_configurable():
    five = "Everyone agrees [ID:a][ID:b][ID:doc-1][ID:1][ID:2]."
    report = check(five, CONTEXT)
    assert _codes(report) == ["TOO_MANY"]
    assert (report["verdict"], report["exit_code"]) == ("warn", 1)
    assert check(five, CONTEXT, max_per_sentence=5)["findings"] == []
    assert check("Everyone agrees [ID:a][ID:b][ID:doc-1][ID:1].", CONTEXT)["findings"] == []


@pytest.mark.parametrize("sentence, token", [
    ("Revenue grew 12% last year.", "12%"),
    ("The plan costs $40 per seat.", "$40"),
    ("O plano custa R$ 1.500,00 por mês.", "R$ 1.500,00"),
    ("The release shipped on 2026-09-24.", "2026-09-24"),
    ("There are 3 lanes on the board.", "3"),
])
def test_a_quantitative_sentence_without_a_marker_warns(sentence, token):
    report = check(sentence, CONTEXT)
    assert _codes(report) == ["UNCITED_CLAIM"]
    finding = report["findings"][0]
    assert finding["severity"] == "warn" and finding["token"] == token
    assert (report["verdict"], report["exit_code"]) == ("warn", 1)
    assert report["counts"]["quantitative_sentences"] == 1


@pytest.mark.parametrize("text", [
    "## 2026 results\n\nNothing numeric follows.",
    "1. Open the file.\n2. Save it.\n10. Close it.",
    "3) Open the file.",
    "Install v2.5.8 before you start.",
    "See https://example.com/2026/report for the source.",
    "Run `make test-42` first.",
    "Plain prose.\n\n```\nport = 8080\nretries = 3. [ID:zz]\n```\n\nMore plain prose.",
])
def test_structure_that_is_not_a_claim_is_not_flagged(text):
    report = check(text, CONTEXT)
    # NO_MARKERS only says the text cites nothing; the point here is that no claim was invented.
    assert _codes(report) in ([], ["NO_MARKERS"]), report["findings"]


def test_a_marker_inside_a_code_block_is_not_parsed():
    report = check("Prose.\n\n```\n[ID:zz] [ID:1-3]\n```\n", CONTEXT)
    assert report["counts"]["markers"] == 0 and _codes(report) == ["NO_MARKERS"]


def test_unused_context_is_a_count_never_a_finding():
    report = check("Revenue grew 12% [ID:a].", CONTEXT)
    assert report["findings"] == []
    assert report["counts"]["context_ids"] == 6
    assert report["counts"]["unique_cited_ids"] == 1
    assert report["counts"]["unused_context_ids"] == 5


# --------------------------------------------------------------------------- the splitter

def test_decimals_are_not_sentence_boundaries():
    assert split_sentences("Latency fell from 3.5 s to 2.1 s [ID:a].") == ["Latency fell from 3.5 s to 2.1 s [ID:a]."]


def test_CONTROLE_the_splitter_does_split_at_a_real_boundary():
    assert split_sentences("Latency fell. It is 2 s now [ID:a]!  Good?") == [
        "Latency fell.", "It is 2 s now [ID:a]!", "Good?"]


def test_a_boundary_inside_a_marker_is_ignored():
    context = [{"id": "Report vol. 2", "text": "a report"}]
    text = "The effect was 4% [ID:Report vol. 2]. It held."
    assert split_sentences(text) == ["The effect was 4% [ID:Report vol. 2].", "It held."]
    assert check(text, context)["findings"] == []


def test_a_marker_after_the_full_stop_belongs_to_the_sentence_that_ended():
    text = "Revenue grew 12%. [ID:a] Costs were flat."
    assert split_sentences(text) == ["Revenue grew 12%. [ID:a]", "Costs were flat."]
    assert check(text, CONTEXT)["findings"] == []


def test_common_abbreviations_do_not_end_a_sentence():
    assert split_sentences("Some ports, e.g. the admin one, are closed.") == [
        "Some ports, e.g. the admin one, are closed."]


def test_headings_list_items_and_blank_lines_are_boundaries():
    text = "# Title\nFirst line\ncontinues here.\n\n- item one\n- item two\n"
    assert split_sentences(text) == ["# Title", "First line\ncontinues here.", "item one", "item two"]


def test_a_table_row_is_one_sentence_and_its_separator_row_is_none():
    text = "| metric | value |\n|---|:-:|\n| churn | 3% [ID:a] |\n| growth | 12% |"
    assert split_sentences(text) == ["| metric | value |", "| churn | 3% [ID:a] |", "| growth | 12% |"]
    report = check(text, CONTEXT)
    # a number in a table row is a claim too; the documented cost is a row cited only in a caption
    assert [(finding["code"], finding["token"]) for finding in report["findings"]] == [("UNCITED_CLAIM", "12%")]


def test_windows_line_endings_split_like_unix_ones():
    unix = "# T\n\nRevenue grew 12% [ID:a].\nCosts fell 3%.\n"
    windows = unix.replace("\n", "\r\n")
    assert split_sentences(windows) == [part.replace("\n", "\r\n") for part in split_sentences(unix)]
    assert _codes(check(windows, CONTEXT)) == _codes(check(unix, CONTEXT)) == ["UNCITED_CLAIM"]


# --------------------------------------------------------------------------- the marker grammar

def test_a_custom_marker_regex_replaces_the_default():
    marker = r"\{cite:([^}]*)\}"
    assert check("Revenue grew 12% {cite:a}.", CONTEXT, marker=marker)["findings"] == []
    # the default syntax is no longer a marker, so the number is uncited
    assert _codes(check("Revenue grew 12% [ID:a].", CONTEXT, marker=marker)) == ["UNCITED_CLAIM"]
    assert _codes(check("Revenue grew 12% {cite:zz}.", CONTEXT, marker=marker)) == ["UNKNOWN_ID"]
    assert check("x [ID:a].", CONTEXT)["marker_pattern"] == DEFAULT_MARKER


@pytest.mark.parametrize("pattern, fragment", [
    ("(", "invalid marker regex"),
    (r"\[ID:\w+\]", "exactly one capture group"),
    (r"\[(ID):(\w+)\]", "exactly one capture group"),
    (r"(\d*)", "matches empty text"),
    ("", "marker regex"),
])
def test_an_unusable_marker_regex_is_refused(pattern, fragment):
    with pytest.raises(CitationError, match=re.escape(fragment)):
        check("x.", CONTEXT, marker=pattern)


# --------------------------------------------------------------------------- refusals

def test_secret_like_text_is_refused_without_echoing_it():
    with pytest.raises(CitationError) as info:
        check("Use api_key=sk-abcdefghijkl to call it [ID:a].", CONTEXT)
    assert "secret" in str(info.value)
    assert "sk-abc" not in str(info.value)


def test_secret_like_context_is_refused_and_named_by_position():
    with pytest.raises(CitationError, match="context item 1") as info:
        check("x [ID:a].", [{"id": "a", "text": "ok"}, {"id": "k", "text": "password: hunter2"}])
    assert "hunter2" not in str(info.value)


@pytest.mark.parametrize("context, fragment", [
    ({"id": "a"}, "must be a list"),
    ([{"id": "a", "text": "x"}, {"id": "a", "text": "y"}], "duplicate context id"),
    ([{"id": "", "text": "x"}], "non-empty"),
    ([{"id": 1, "text": "x"}], "string"),
    ([{"id": " a", "text": "x"}], "whitespace"),
    ([{"id": "a"}], "text"),
    (["a", {"id": "b", "text": "x"}], "mixes"),
    (["a", "a"], "duplicate context id"),
])
def test_a_malformed_context_is_refused(context, fragment):
    with pytest.raises(CitationError, match=re.escape(fragment)):
        check("x [ID:a].", context)


def test_a_context_of_bare_ids_is_accepted():
    report = check("Revenue grew 12% [ID:a].", ["a", "b"])
    assert report["findings"] == [] and report["counts"]["context_ids"] == 2


def test_text_that_is_not_valid_unicode_is_refused_not_crashed():
    # Why: JSON may carry a lone surrogate (`"\ud800"`), which cannot be encoded to hash it; before
    # this test the check raised UnicodeEncodeError, an internal error instead of a refusal.
    with pytest.raises(CitationError, match="Unicode"):
        check("x [ID:a].", [{"id": "a", "text": "\ud800"}])
    with pytest.raises(CitationError, match="Unicode"):
        check("x \ud800 [ID:a].", ["a"])


def test_a_text_that_is_only_code_is_refused():
    with pytest.raises(CitationError, match="nothing to check"):
        check("```\nrevenue = 12\n```\n", CONTEXT)


@pytest.mark.parametrize("text", ["", "   \n\t\n"])
def test_empty_text_is_refused_rather_than_passed(text):
    with pytest.raises(CitationError, match="nothing to check"):
        check(text, CONTEXT)


@pytest.mark.parametrize("value", [0, -1, True, "4", 2.5])
def test_max_per_sentence_must_be_a_positive_integer(value):
    with pytest.raises(CitationError, match="max_per_sentence"):
        check("x [ID:a].", CONTEXT, max_per_sentence=value)


# --------------------------------------------------------------------------- the report

def test_the_report_carries_both_hashes_and_is_deterministic(tmp_path):
    text = (EXAMPLE / "answer.md").read_text(encoding="utf-8")
    context = json.loads((EXAMPLE / "context.json").read_text(encoding="utf-8"))
    report = check(text, context)
    assert report["text_sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()
    canonical = json.dumps(context, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert report["context_sha256"] == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert check(text, context) == report
    # reformatting the context file (indentation, key order) does not change its hash
    reformatted = tmp_path / "context.json"
    reformatted.write_text(json.dumps([dict(reversed(list(item.items()))) for item in context], indent=4),
                           encoding="utf-8")
    assert check_files(EXAMPLE / "answer.md", reformatted)["context_sha256"] == report["context_sha256"]


def test_a_long_sentence_is_truncated_in_the_excerpt():
    sentence = "Revenue grew 12% " + "and kept growing " * 20 + "."
    excerpt = check(sentence, CONTEXT)["findings"][0]["excerpt"]
    assert len(excerpt) <= 120 and excerpt.endswith("...")


@pytest.mark.parametrize("verdict, code", [("ok", 0), ("warn", 1), ("block", 2)])
def test_exit_for_follows_the_contract_0_ok_1_warn_2_block(verdict, code):
    report = check({"ok": "Plain [ID:a].", "warn": "It is 5%.", "block": "It is [ID:zz]."}[verdict], CONTEXT)
    assert report["verdict"] == verdict and exit_for(report) == code


def test_check_files_reads_exactly_the_two_files_given(tmp_path, monkeypatch):
    read = []
    original = Path.read_bytes

    def spy(self):
        read.append(self.resolve())
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", spy)
    check_files(EXAMPLE / "answer.md", EXAMPLE / "context.json")
    assert sorted(read) == sorted([(EXAMPLE / "answer.md").resolve(), (EXAMPLE / "context.json").resolve()])


def test_check_files_refuses_unreadable_inputs(tmp_path):
    bad = tmp_path / "context.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(CitationError, match="context"):
        check_files(EXAMPLE / "answer.md", bad)
    with pytest.raises(CitationError, match="not found"):
        check_files(tmp_path / "missing.md", EXAMPLE / "context.json")


def test_the_module_imports_nothing_that_reaches_the_network_or_spawns_a_process():
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    names = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    names |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not names & {"socket", "urllib", "http", "subprocess", "ssl", "asyncio"}, names


def test_the_example_readmes_carry_identical_code_blocks():
    fence = re.compile(r"^```[^\n]*\n(.*?)^```", re.M | re.S)
    english = fence.findall((EXAMPLE / "README.md").read_text(encoding="utf-8"))
    portuguese = fence.findall((EXAMPLE / "README.pt-BR.md").read_text(encoding="utf-8"))
    assert english and english == portuguese


# --------------------------------------------------------------------------- CLI

def test_cli_cite_check_follows_the_exit_contract(tmp_path, capsys):
    from hpp import cli

    example = Path(__file__).resolve().parent.parent / "examples" / "citations"
    assert cli.main(["cite", "check", "--text", str(example / "answer.md"),
                     "--context", str(example / "context.json")]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "ok"
    broken = tmp_path / "answer.md"
    broken.write_text("Revenue grew 12% [ID:nope].\n", encoding="utf-8")
    assert cli.main(["cite", "check", "--text", str(broken), "--context", str(example / "context.json")]) == 2
    capsys.readouterr()
    assert cli.main(["cite", "check", "--text", str(broken), "--context", str(example / "context.json"),
                     "--marker", "("]) == 2


# --------------------------------------------------------------------------- second review

def test_an_empty_context_is_refused():
    with pytest.raises(CitationError, match="empty"):
        check("Revenue grew 12% [ID:a].", [])


def test_a_text_that_cites_nothing_warns_instead_of_passing():
    report = check("The system is reliable and fast.", [{"id": "a", "text": "x"}])
    assert report["verdict"] == "warn" and [f["code"] for f in report["findings"]] == ["NO_MARKERS"]


def test_CONTROLE_one_resolved_marker_is_enough_to_pass():
    report = check("The system is reliable [ID:a].", [{"id": "a", "text": "x"}])
    assert report["verdict"] == "ok"


def test_a_fence_inside_a_list_item_is_skipped():
    text = "- item:\n\n    ```\n    retries = 3. [ID:zz]\n    ```\n\nIt works [ID:a].\n"
    report = check(text, [{"id": "a", "text": "x"}])
    assert report["verdict"] == "ok", report["findings"]


@pytest.mark.parametrize("title", ["Dr.", "Mr.", "Mrs.", "Ms.", "Prof.", "St.", "Inc.", "et al."])
def test_a_title_or_common_abbreviation_does_not_split_a_cited_sentence(title):
    report = check(f"Revenue rose 12% per {title} Smith [ID:a].", [{"id": "a", "text": "x"}])
    assert report["verdict"] == "ok", report["findings"]
