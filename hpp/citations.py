"""Citation check: a claim bigger than its proof becomes an exit code.

An answer written from sources marks each claim with the id of the source it rests on (`[ID:<id>]`
by default). `check` reads the answer and the list of sources it was given (`[{"id", "text"}]`, or
a list of bare ids) and reports, deterministically and without a model, what the answer claims that
its sources cannot back:

BLOCK (exit 2)
  UNKNOWN_ID     a marker names an id that is not in the context: a source the answer was never given.
  RANGE          one marker names a range or a list (`1-3`, `1,2`, `1..3`). One id per marker, so every
                 cited source can be looked up on its own.
  EMPTY_MARKER   a marker with no id in it.
WARN (exit 1)
  TOO_MANY       more than `max_per_sentence` markers (default 4) in one sentence: a sentence that needs
                 that many sources is several claims.
  UNCITED_CLAIM  a sentence states a number, a percentage, a currency amount or a date and carries no
                 marker at all. Quantitative claims must carry a citation.

Context the answer never cites is not a finding (the sources may be larger than the answer); it is
published as a count. A text that is empty, or has no sentence outside code, is refused rather than
passed: there is nothing to measure. Secret-like text, in the answer or in the context, is refused
before anything is hashed, so a report can never echo one in an excerpt.

What this check does NOT do: it never reads a cited source to see whether it supports the sentence.
A marker that resolves proves the id exists, not that the source says what the sentence says. That
judgement needs a reader; this is the part that does not.

Heuristics, stated so nobody mistakes them for parsing:
- Sentences end at `.`, `?` or `!` (a run of them, plus closing quotes or brackets) followed by
  whitespace or the end of a block. `3.5` does not end a sentence, a boundary inside a marker or
  inside `inline code` is ignored, and common abbreviations (`e.g.`, `Dr.`, `Inc.`, `et al.`,
  month names) do not end one. An abbreviation outside that list does, and splits a sentence.
- Markers that follow the full stop on the same line (`It grew 12%. [ID:a]`) belong to the sentence
  that just ended. A marker on the next line belongs to the next sentence.
- Blocks come from Markdown shape: a blank line, a heading, a list item and a table row each start a
  new block (a heading or a table row is one sentence, and a table's separator row is none); other
  consecutive lines are one paragraph. Fenced code blocks are skipped entirely:
  no sentences and no markers are read inside them (an unclosed fence runs to the end of the text),
  and markers inside `inline code` are not markers.
- A quantitative token is a digit not glued to a letter on its left, with an optional currency sign
  (`$`, `R$`, `US$`, `€`, `£`, `¥`) and an optional `%`. Not scanned: headings, the numbering of a
  list item, inline code, URLs, footnote references (`[^1]`), and versions written with a `v`
  (`v2.5.8`). A bare `2.5.8` IS flagged: it cannot be told apart from a dotted date like
  `24.09.2026`, so write versions with a `v` or in code.
- Known false positives: ordinals (`1st`), labels (`Step 2`, `RFC 2119`, `COVID-19`), a number in a
  table row whose citation sits in a caption, and a citation written in another syntax (`[1]`).
  Known false negatives: numbers written as words (`twelve percent`) and digits glued to a letter on
  their left (`Q3`, `H2O`); a digit with a letter on its right (`3x`, `5k`) is caught. These are
  warnings, never blocks.
- A marker is `[ID:<id>]` unless another regex with exactly one capture group is given. Whitespace
  around the captured id is ignored. A marker id that is not in the context is a RANGE when it
  splits on `,` or `;` into parts of which one is a known id or all are numbers, or when it splits
  once on `-`, an en/em dash or `..` into two known ids or two numbers; otherwise it is UNKNOWN_ID.
  So `doc-1` in the context is one id, and `2026-09-24` outside it is unknown, not a range.

`check` returns the report (`hpp.citation-check/v1`); `exit_for` maps it to 0/1/2. Invalid input
raises `CitationError`, which a command line reports as a refusal (exit 2).
"""
from __future__ import annotations

import bisect
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterator, Union

from hpp.context import _SECRET_PATTERN

SCHEMA = "hpp.citation-check/v1"
DEFAULT_MARKER = r"\[ID:([^\]\n]*)\]"
DEFAULT_MAX_PER_SENTENCE = 4
EXCERPT_CHARS = 120
BLOCK_CODES = ("UNKNOWN_ID", "RANGE", "EMPTY_MARKER")
WARN_CODES = ("TOO_MANY", "UNCITED_CLAIM", "NO_MARKERS")
EXIT_CODES = {"ok": 0, "warn": 1, "block": 2}

# Why: a fence inside a list item is indented by the item's content offset, so any leading
# whitespace is accepted; otherwise the code in it is judged as prose.
_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
_HEADING = re.compile(r"^ {0,3}#{1,6}(?:[ \t]|$)")
_LIST_ITEM = re.compile(r"^[ \t]*(?:[-*+]|\d{1,9}[.)])[ \t]+")
_TABLE_ROW = re.compile(r"^[ \t]*\|")
_INLINE_CODE = re.compile(r"`[^`\n]+`")
_TERMINAL = ".?!"
_CLOSERS = "\"')]}»”’"
_OPENERS = "\"'([{«“‘"
_ABBREVIATIONS = frozenset({
    "e.g.", "i.e.", "cf.", "vs.", "al.", "approx.", "fig.", "no.",
    "dr.", "mr.", "mrs.", "ms.", "prof.", "st.", "jr.", "sr.", "inc.", "ltd.", "co.", "corp.",
    "jan.", "feb.", "mar.", "apr.", "jun.", "jul.", "aug.", "sep.", "sept.", "oct.", "nov.", "dec.",
})
_NOT_CLAIMS = (
    re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE),
    re.compile(r"\[\^[^\]\s]+\]"),
    re.compile(r"(?<![\w.])v\d+(?:\.\d+)+(?:[-+][0-9A-Za-z.]+)?", re.IGNORECASE),
)
_CLAIM = re.compile(r"(?:(?:R|US)\$|[$€£¥])?\s?(?<!\w)\d(?:[\d.,:/-]*\d)?(?:\s?%)?")
_LIST_SEPARATOR = re.compile(r"[,;]")
_RANGE_SEPARATOR = re.compile(r"\s*(?:\.{2,3}|…|[-–—])\s*")
_NUMBER = re.compile(r"\d+")


class CitationError(ValueError):
    """The answer, the context or an option cannot be checked as given."""


# --------------------------------------------------------------------------- inputs

def compile_marker(pattern: str) -> re.Pattern[str]:
    """The marker regex, or CitationError: it must compile, capture exactly one id, never match ''."""
    if not isinstance(pattern, str) or not pattern:
        raise CitationError("marker regex must be a non-empty string")
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise CitationError(f"invalid marker regex: {exc}") from exc
    if compiled.groups != 1:
        raise CitationError(f"marker regex needs exactly one capture group (the id); it has {compiled.groups}")
    # Why: a pattern that matches empty text finds a "marker" between every two characters.
    if compiled.search("") is not None:
        raise CitationError("marker regex matches empty text; a marker must consume at least one character")
    return compiled


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def context_ids(context: Any) -> list[str]:
    """The ids of a context (objects with id and text, or bare ids), or CitationError."""
    if not isinstance(context, list):
        raise CitationError('context must be a list of {"id", "text"} objects or a list of ids')
    if not context:
        raise CitationError("context is empty: there is nothing to cite against")
    bare = [isinstance(item, str) for item in context]
    if any(bare) and not all(bare):
        raise CitationError("context mixes bare ids and objects; use one form")
    ids: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(context):
        if isinstance(item, dict):
            ident = item.get("id")
            if not isinstance(item.get("text"), str):
                raise CitationError(f"context item {index} needs a text string")
        elif isinstance(item, str):
            ident = item
        else:
            raise CitationError(f"context item {index} must be an object or an id string")
        if not isinstance(ident, str):
            raise CitationError(f'context item {index}: ids must be strings (write "1", not 1)')
        if not ident:
            raise CitationError(f"context item {index} needs a non-empty id")
        if any(_SECRET_PATTERN.search(text) for text in _strings(item)):
            raise CitationError(f"context item {index} looks like it carries a secret; it is never hashed into a report")
        if ident != ident.strip() or "\n" in ident or "\r" in ident:
            raise CitationError(f"context item {index}: an id cannot start or end with whitespace or span lines")
        if ident in seen:
            raise CitationError(f"duplicate context id: {ident!r}")
        seen.add(ident)
        ids.append(ident)
    return ids


# --------------------------------------------------------------------------- structure

def _structure(text: str) -> tuple[list[list[Any]], list[tuple[int, int]], list[int]]:
    """Blocks as [start, end, kind] offsets, fenced-code spans, and the offset of each line."""
    blocks: list[list[Any]] = []
    fenced: list[tuple[int, int]] = []
    line_starts: list[int] = []
    current: Any = None
    fence: Any = None
    offset = 0
    for raw in text.splitlines(keepends=True):
        start = offset
        offset += len(raw)
        line_starts.append(start)
        line = raw.rstrip("\r\n")
        if start == 0 and line.startswith("﻿"):
            line, start = line[1:], 1
        end = start + len(line)
        opener = _FENCE.match(line)
        if fence is not None:
            fenced.append((start, offset))
            if opener and opener.group(1)[0] == fence[0] and len(opener.group(1)) >= fence[1] \
                    and not line[opener.end():].strip():
                fence = None
            continue
        if opener:
            current, fence = None, (opener.group(1)[0], len(opener.group(1)))
            fenced.append((start, offset))
            continue
        if not line.strip():
            current = None
            continue
        indent = len(line) - len(line.lstrip())
        heading, table = _HEADING.match(line), _TABLE_ROW.match(line)
        if heading or table:
            current = None
            # Why: `|---|:-:|` only draws the table; counting it would inflate the sentence count.
            if not (table and not line.strip(" \t|-:")):
                blocks.append([start + indent, start + len(line.rstrip()), "heading" if heading else "table"])
            continue
        item = _LIST_ITEM.match(line)
        if item:
            current = [start + item.end(), end, "text"]
            blocks.append(current)
        elif current is not None:
            current[1] = end
        else:
            current = [start + indent, end, "text"]
            blocks.append(current)
    return blocks, fenced, line_starts


def _abbreviation(text: str, begin: int, stop: int) -> bool:
    words = text[begin:stop].split()
    return bool(words) and words[-1].lstrip(_OPENERS).lower() in _ABBREVIATIONS


def _pieces(text: str, start: int, end: int, skip: dict[int, int], markers_at: dict[int, int]) -> list[tuple[int, int]]:
    pieces: list[tuple[int, int]] = []
    begin = i = start
    while i < end:
        jump = skip.get(i)
        if jump is not None:
            i = max(jump, i + 1)
            continue
        if text[i] not in _TERMINAL:
            i += 1
            continue
        j = i + 1
        while j < end and text[j] in _TERMINAL:
            j += 1
        while j < end and text[j] in _CLOSERS:
            j += 1
        if (j < end and not text[j].isspace()) or (text[i] == "." and _abbreviation(text, begin, i + 1)):
            i = j
            continue
        # Why: `It grew 12%. [ID:a]` is a common way to cite; the marker after the full stop
        # belongs to the sentence that just ended, not to the next one.
        k = j
        while True:
            m = k
            while m < end and text[m] in " \t":
                m += 1
            stop = markers_at.get(m)
            if stop is None or stop > end:
                break
            k = stop
        while k < end and text[k] in _TERMINAL + _CLOSERS:
            k += 1
        pieces.append((begin, k))
        begin = i = k
    pieces.append((begin, end))
    trimmed = []
    for a, b in pieces:
        while a < b and text[a].isspace():
            a += 1
        while b > a and text[b - 1].isspace():
            b -= 1
        if a < b:
            trimmed.append((a, b))
    return trimmed


def _parse(text: str, marker: re.Pattern[str]) -> tuple[list[tuple[int, int, str]], list[tuple[int, int, str]], list[int], list[tuple[int, int]]]:
    """Sentences (start, end, kind), markers (start, end, raw id), line starts, inline-code spans."""
    blocks, fenced, line_starts = _structure(text)
    fenced_starts = [a for a, _ in fenced]

    def in_fence(position: int) -> bool:
        index = bisect.bisect_right(fenced_starts, position) - 1
        return index >= 0 and position < fenced[index][1]

    code = [(m.start(), m.end()) for m in _INLINE_CODE.finditer(text) if not in_fence(m.start())]
    code_starts = [a for a, _ in code]

    def in_code(position: int) -> bool:
        index = bisect.bisect_right(code_starts, position) - 1
        return index >= 0 and position < code[index][1]

    markers = [(m.start(), m.end(), m.group(1) or "") for m in marker.finditer(text)
               if m.end() > m.start() and not in_fence(m.start()) and not in_code(m.start())]
    markers_at = {a: b for a, b, _ in markers}
    skip = dict(markers_at)
    skip.update({a: b for a, b in code})
    sentences: list[tuple[int, int, str]] = []
    for start, end, kind in blocks:
        if kind == "text":
            sentences.extend((a, b, kind) for a, b in _pieces(text, start, end, skip, markers_at))
        elif start < end:
            sentences.append((start, end, kind))
    return sentences, markers, line_starts, code


def split_sentences(text: str, marker: str = DEFAULT_MARKER) -> list[str]:
    """The sentences `check` would judge, as the original text of each (the heuristic is documented above)."""
    if not isinstance(text, str):
        raise CitationError("text must be a string")
    sentences, _, _, _ = _parse(text, compile_marker(marker))
    return [text[start:end] for start, end, _ in sentences]


# --------------------------------------------------------------------------- classification

def _is_number(value: str) -> bool:
    return _NUMBER.fullmatch(value) is not None


def _classify(raw: str, known: set[str]) -> Union[str, None]:
    ident = raw.strip()
    if not ident:
        return "EMPTY_MARKER"
    if ident in known:
        return None
    parts = [part.strip() for part in _LIST_SEPARATOR.split(ident) if part.strip()]
    if len(parts) >= 2 and (any(part in known for part in parts) or all(_is_number(part) for part in parts)):
        return "RANGE"
    for separator in _RANGE_SEPARATOR.finditer(ident):
        left, right = ident[:separator.start()], ident[separator.end():]
        if left and right and ((left in known and right in known) or (_is_number(left) and _is_number(right))):
            return "RANGE"
    return "UNKNOWN_ID"


def _claim(text: str, start: int, end: int, markers: list[tuple[int, int, str]],
           code: list[tuple[int, int]]) -> Union[str, None]:
    chars = list(text[start:end])
    for a, b in [(a, b) for a, b, _ in markers] + code:
        for position in range(max(a, start), min(b, end)):
            chars[position - start] = " "
    scanned = "".join(chars)
    for pattern in _NOT_CLAIMS:
        scanned = pattern.sub(lambda m: " " * len(m.group(0)), scanned)
    found = _CLAIM.search(scanned)
    return found.group(0).strip() if found else None


def _excerpt(value: str) -> str:
    flat = " ".join(value.split())
    return flat if len(flat) <= EXCERPT_CHARS else flat[:EXCERPT_CHARS - 3].rstrip() + "..."


def _sha256(value: str, label: str) -> str:
    # Why: JSON can carry a lone surrogate ("\ud800"); encoding it raised UnicodeEncodeError, an
    # internal error where the input is simply not text that can be hashed or reported.
    try:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
    except UnicodeEncodeError as exc:
        raise CitationError(f"{label} is not valid Unicode text (character {exc.start})") from exc


# --------------------------------------------------------------------------- the check

def check(text: str, context: Any, max_per_sentence: int = DEFAULT_MAX_PER_SENTENCE,
          marker: str = DEFAULT_MARKER) -> dict[str, Any]:
    """Judge `text` against `context`. Returns `hpp.citation-check/v1`; raises CitationError on bad input."""
    if isinstance(max_per_sentence, bool) or not isinstance(max_per_sentence, int) or max_per_sentence < 1:
        raise CitationError("max_per_sentence must be a positive integer")
    pattern = compile_marker(marker)
    if not isinstance(text, str):
        raise CitationError("text must be a string")
    if not text.strip():
        raise CitationError("text is empty: there is nothing to check")
    if _SECRET_PATTERN.search(text):
        raise CitationError("text looks like it carries a secret; it is never checked, hashed or echoed into a report")
    text_sha256 = _sha256(text, "text")
    ids = context_ids(context)
    try:
        canonical = json.dumps(context, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise CitationError(f"context is not JSON data: {exc}") from exc
    context_sha256 = _sha256(canonical, "context")
    known = set(ids)
    sentences, markers, line_starts, code = _parse(text, pattern)
    if not sentences:
        raise CitationError("text has no sentence outside code blocks: there is nothing to check")

    starts = [start for start, _, _ in sentences]
    by_sentence: dict[int, list[tuple[int, int, str]]] = {}
    for item in markers:
        by_sentence.setdefault(max(bisect.bisect_right(starts, item[0]) - 1, 0), []).append(item)

    findings: list[dict[str, Any]] = []
    cited: list[str] = []
    quantitative = 0
    for index, (start, end, kind) in enumerate(sentences):
        own = by_sentence.get(index, [])
        where = {"sentence": index + 1, "line": bisect.bisect_right(line_starts, start),
                 "excerpt": _excerpt(text[start:end])}
        for a, b, raw in own:
            ident = raw.strip()
            code_name = _classify(raw, known)
            if code_name is None:
                cited.append(ident)
                continue
            message = {
                "EMPTY_MARKER": "marker has no id",
                "RANGE": f"marker cites {_excerpt(ident)!r} as a range or a list; write one id per marker",
                "UNKNOWN_ID": f"marker cites {_excerpt(ident)!r}, which is not in the context",
            }[code_name]
            findings.append({"code": code_name, "severity": "block", **where, "marker": _excerpt(text[a:b]),
                             "message": message})
        if len(own) > max_per_sentence:
            findings.append({"code": "TOO_MANY", "severity": "warn", **where, "count": len(own),
                             "message": f"{len(own)} markers in one sentence (limit {max_per_sentence}); "
                                        "a sentence that needs this many sources is several claims"})
        if kind == "heading":
            continue
        token = _claim(text, start, end, own, code)
        if token is None:
            continue
        quantitative += 1
        if not own:
            findings.append({"code": "UNCITED_CLAIM", "severity": "warn", **where, "token": token,
                             "message": f"quantitative claim {token!r} carries no citation"})

    if not markers and not findings:
        # Why: with no marker and no uncited number, every check above passed vacuously; "ok" would
        # certify a text that cites nothing.
        findings.append({"code": "NO_MARKERS", "severity": "warn", "sentence": None, "line": None,
                         "excerpt": "", "message": "the text cites nothing, so no citation was checked"})
    severities = {finding["severity"] for finding in findings}
    verdict = "block" if "block" in severities else "warn" if "warn" in severities else "ok"
    unique = set(cited)
    return {
        "schema": SCHEMA,
        "text_sha256": text_sha256,
        "context_sha256": context_sha256,
        "marker_pattern": marker,
        "max_per_sentence": max_per_sentence,
        "counts": {
            "sentences": len(sentences),
            "quantitative_sentences": quantitative,
            "markers": len(markers),
            "cited_ids": len(cited),
            "unique_cited_ids": len(unique),
            "context_ids": len(ids),
            "unused_context_ids": len(known - unique),
        },
        "findings": findings,
        "verdict": verdict,
        "exit_code": EXIT_CODES[verdict],
    }


def check_files(text_path: Union[str, Path], context_path: Union[str, Path],
                max_per_sentence: int = DEFAULT_MAX_PER_SENTENCE, marker: str = DEFAULT_MARKER) -> dict[str, Any]:
    """Read exactly the two files given (UTF-8 text, JSON context) and `check` them. Nothing else is read."""
    text_path, context_path = Path(text_path), Path(context_path)
    for label, path in (("text", text_path), ("context", context_path)):
        if not path.is_file():
            raise CitationError(f"{label} file not found: {path}")
    try:
        text = text_path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CitationError(f"text file is not UTF-8: {exc.reason}") from exc
    try:
        context = json.loads(context_path.read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CitationError(f"invalid context JSON: {exc}") from exc
    return check(text, context, max_per_sentence=max_per_sentence, marker=marker)


def exit_for(report: dict[str, Any]) -> int:
    """0 ok · 1 warn · 2 block. A refused input never produces a report; the caller exits 2 for it."""
    return EXIT_CODES[report["verdict"]]
