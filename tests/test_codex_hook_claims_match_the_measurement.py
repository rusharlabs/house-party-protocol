"""No document says Codex CLI has no lifecycle hooks: it has them, and HPP does not load its own there.

Measured with Codex CLI 0.153.4 and recorded in docs/CONCEPTS.md (section "host"): `codex features list`
prints `hooks  stable  true`, and with no `hooks` key the Codex plugin loader registers a module's
`hooks/hooks.json` (16 hooks without the override, 0 with it). HPP's hooks are written and tested for
Claude Code, so each Codex plugin manifest carries the empty object `{"hooks": {}}` and on Codex the
same capabilities run as explicit commands. The honest sentence is "HPP does not wire its hooks on
Codex", never "Codex has no hooks".

The scan covers every Markdown and HTML file of the tree this test runs in (HTML with its tags
stripped): the product source, or the emitted tree, where the modules' documents sit under their
family directories. CHANGELOG files are history and are not scanned.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "__pycache__", "node_modules", "tests", ".venv"}

# Each form was a live sentence in the 2.10.0 documents. Matched on text whose whitespace and
# emphasis markers are collapsed, so a line break or ** inside the sentence does not hide it.
FORBIDDEN = (
    re.compile(r"Codex CLI (?:there are|has) no lifecycle hooks", re.IGNORECASE),
    re.compile(r"There are no lifecycle hooks", re.IGNORECASE),
    re.compile(r"Não há lifecycle hooks", re.IGNORECASE),
    re.compile(r"no lifecycle hooks on this host", re.IGNORECASE),
    re.compile(r"runs lifecycle hooks; Codex CLI does not", re.IGNORECASE),
    re.compile(r"host without lifecycle hooks", re.IGNORECASE),
    re.compile(r"native once wired by a person \| none", re.IGNORECASE),
    re.compile(r"No Codex CLI não há hooks de lifecycle", re.IGNORECASE),
    re.compile(r"Codex CLI também não tem hooks de ciclo de vida", re.IGNORECASE),
    re.compile(r"sem hooks de ciclo de vida neste host", re.IGNORECASE),
    re.compile(r"hooks de lifecycle; o Codex CLI não\b", re.IGNORECASE),
    re.compile(r"host sem lifecycle hook", re.IGNORECASE),
    re.compile(r"nativos depois que uma pessoa faz o wiring \| nenhum", re.IGNORECASE),
)


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("**", "").replace("`", ""))


def _offenders(text: str) -> list[str]:
    flat = _normalized(text)
    return [pattern.pattern for pattern in FORBIDDEN if pattern.search(flat)]


def _text(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".html":
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return text


def _documents(root: Path) -> list[Path]:
    found = []
    for path in [*root.rglob("*.md"), *root.rglob("*.html")]:
        relative = path.relative_to(root)
        if SKIP_DIRS.intersection(relative.parts[:-1]) or path.name.startswith("CHANGELOG"):
            continue
        found.append(path)
    return sorted(found)


def test_no_document_says_codex_has_no_lifecycle_hooks():
    documents = _documents(PRODUCT_ROOT)
    assert len(documents) >= 10, f"the scan found only {len(documents)} documents under {PRODUCT_ROOT}"
    hits = {}
    for path in documents:
        offenders = _offenders(_text(path))
        if offenders:
            hits[path.relative_to(PRODUCT_ROOT).as_posix()] = offenders
    assert not hits, f"documents that deny Codex its hooks: {hits}"


def test_CONTROLE_every_form_catches_the_sentence_it_was_written_for():
    old = (
        "On Codex CLI there are no\n  lifecycle hooks; the same capabilities are explicit commands.",
        "Codex CLI has no lifecycle hooks either, so a Codex lane hears",
        "| Codex CLI | no lifecycle hooks on this host: the lane hears about mail",
        "Claude Code runs lifecycle hooks; Codex CLI does not. Coverage",
        "does not turn a host without lifecycle hooks into automatic enforcement",
        "| lifecycle hooks (`Stop`, ...) | native once wired by a person | none; the same scripts |",
        "No Codex CLI não\n  há hooks de lifecycle; as mesmas capacidades",
        "O Codex CLI também não tem hooks de ciclo de vida, então",
        "| Codex CLI | sem hooks de ciclo de vida neste host: a lane",
        "O Claude Code executa hooks de lifecycle; o Codex CLI\n  não. A cobertura",
        "não transforma um host sem lifecycle hook em enforcement automático",
        "| hooks de lifecycle | nativos depois que uma pessoa faz o wiring | nenhum; os mesmos |",
        "AGENTS.md read by the host. There are no lifecycle hooks; the same capabilities",
        "AGENTS.md lido pelo host. Não há lifecycle hooks; as mesmas capacidades",
    )
    for sentence in old:
        assert _offenders(sentence), f"no form catches: {sentence!r}"


def test_CONTROLE_the_measured_sentence_passes():
    measured = (
        "Codex CLI has its own lifecycle hooks, but HPP does not load its hooks there: each Codex plugin "
        "manifest carries an empty hooks object, and the same capabilities are explicit commands.",
        "O Codex CLI tem hooks de lifecycle próprios, mas o HPP não carrega os seus lá.",
        "A module installed by file copy cannot wire its own hooks on that host.",
    )
    for sentence in measured:
        assert not _offenders(sentence), f"a true sentence was flagged: {sentence!r}"
