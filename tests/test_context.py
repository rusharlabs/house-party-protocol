"""Context compilation: budget never overflows, the published number matches the
real size of the produced text, and secret-like material is refused.
"""
from __future__ import annotations

import pytest

from hpp.context import ContextError, compile_context


def _item(source, priority, content):
    return {"source": source, "priority": priority, "content": content}


def test_every_input_that_fits_is_included_whole_and_the_budget_never_overflows():
    inputs = [_item("a", 10, "x" * 50), _item("b", 5, "y" * 50)]
    result = compile_context(inputs, budget=200)
    assert result["used"] <= result["budget"]
    assert result["used"] + result["remaining"] == result["budget"]
    assert [record["source"] for record in result["included"]] == ["a", "b"]
    assert result["omitted"] == []


def test_item_that_does_not_fit_is_omitted_whole_never_sliced():
    big = _item("big", 10, "x" * 100)
    small = _item("small", 5, "y" * 10)
    result = compile_context([big, small], budget=50)
    included_sources = {record["source"] for record in result["included"]}
    omitted_sources = {record["source"] for record in result["omitted"]}
    assert included_sources | omitted_sources == {"big", "small"}
    assert included_sources.isdisjoint(omitted_sources)
    for record in result["included"]:
        assert record["chars"] <= result["budget"]


def test_higher_priority_goes_in_first_when_the_budget_is_tight():
    high = _item("high", 100, "x" * 30)
    low = _item("low", 1, "y" * 30)
    result = compile_context([low, high], budget=30)  # only one of the two fits
    assert [record["source"] for record in result["included"]] == ["high"]
    assert [record["source"] for record in result["omitted"]] == ["low"]


def test_char_count_and_final_text_match_the_real_content():
    inputs = [_item("a", 10, "abc"), _item("b", 5, "defgh")]
    result = compile_context(inputs, budget=1000)
    by_source = {record["source"]: record["content"] for record in inputs}
    for record in result["included"]:
        assert record["chars"] == len(by_source[record["source"]])
    expected_text = "\n\n".join(by_source[record["source"]] for record in result["included"])
    assert result["text"] == expected_text
    # "used" is the number PUBLISHED as the budget cost -- it has to match the
    # REAL size of the produced text (including the separators between blocks),
    # not just the sum of each item's isolated "chars": it is this number that
    # decides whether a next item still fits, so it cannot underestimate the
    # real text.
    assert result["used"] == len(result["text"])
    assert result["used"] >= sum(record["chars"] for record in result["included"])


def test_separator_between_blocks_is_charged_to_the_budget_not_just_the_content():
    """
    Two 5-char items each fit in budget=10 looking only at the content, but the
    final text carries a 2-char separator between them ("\\n\\n") -- if that
    cost were not charged, the produced text would overflow the declared
    budget without "used"/"remaining" flagging it.
    """
    inputs = [_item("a", 10, "12345"), _item("b", 5, "67890")]
    result = compile_context(inputs, budget=10)
    assert [record["source"] for record in result["included"]] == ["a"]
    assert [record["source"] for record in result["omitted"]] == ["b"]
    assert result["used"] == len(result["text"]) == 5
    assert result["used"] <= result["budget"]


SECRET_LIKE_CONTENT = [
    "api_key: sk-ABCDEFGH12345678",
    "access_token=abcd1234efgh5678",
    "password: hunter2-secret-value",
    "-----BEGIN " + "PRIVATE KEY-----\nMIIB...\n-----END PRIVATE KEY-----",
    "SECRET=abcdefghijklmnop",
]


@pytest.mark.parametrize("content", SECRET_LIKE_CONTENT)
def test_secret_like_material_is_refused(content):
    with pytest.raises(ContextError, match="secret-like material"):
        compile_context([_item("leak", 1, content)], budget=10_000)


def test_CONTROLE_common_prose_mentioning_the_same_words_is_not_a_false_positive():
    """Control: the refusal is by SHAPE (key=value, PEM block, sk- prefix), not
    by containing the word 'secret'/'password' in common prose."""
    content = "This document explains our secret sauce for onboarding; no password involved."
    result = compile_context([_item("prosa", 1, content)], budget=10_000)
    assert [record["source"] for record in result["included"]] == ["prosa"]


def test_negative_budget_is_rejected():
    with pytest.raises(ContextError):
        compile_context([_item("a", 1, "x")], budget=-1)


def test_duplicate_source_is_rejected():
    with pytest.raises(ContextError, match="duplicate context source"):
        compile_context([_item("dup", 1, "a"), _item("dup", 2, "b")], budget=100)


def test_zero_budget_omits_everything_without_raising_an_error():
    result = compile_context([_item("a", 1, "x")], budget=0)
    assert result["included"] == []
    assert [record["source"] for record in result["omitted"]] == ["a"]
    assert result["used"] == 0
    assert result["text"] == ""


def test_input_without_a_list_is_rejected():
    with pytest.raises(ContextError):
        compile_context({"source": "a"}, budget=100)  # dict, not list
