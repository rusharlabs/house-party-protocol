"""Every example README and its Portuguese twin run the same commands.

The prose is translated; the fenced code blocks are what a reader copies, so they must be
byte-identical between the two languages.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
FENCE = re.compile(r"^```.*?^```", re.S | re.M)
PAIRS = sorted(path.parent for path in EXAMPLES.glob("*/README.pt-BR.md"))


def test_CONTROLE_the_examples_have_bilingual_readmes_with_code():
    assert len(PAIRS) >= 4
    assert all(FENCE.findall((pair / "README.md").read_text(encoding="utf-8")) for pair in PAIRS)


@pytest.mark.parametrize("example", PAIRS, ids=lambda path: path.name)
def test_the_two_languages_share_their_code_blocks(example):
    english = FENCE.findall((example / "README.md").read_text(encoding="utf-8"))
    portuguese = FENCE.findall((example / "README.pt-BR.md").read_text(encoding="utf-8"))
    assert english == portuguese
