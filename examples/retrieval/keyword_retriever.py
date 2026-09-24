"""A keyword retriever over a small synthetic corpus: the baseline a real retriever has to beat.

Reads {"query": ..., "k": ...} on stdin (what `hpp retrieval eval` sends) and prints
{"results": [{"id": ..., "score": ...}, ...]}, best first, at most k of them. The score is the
number of distinct query words a document contains. There is no stemming and no synonym, so a
paraphrase finds nothing: that is the point of a baseline. It imports only the standard library
and never imports hpp, so it runs from a checkout with nothing installed.

    echo '{"query": "how do I restore a backup", "k": 3}' | python examples/retrieval/keyword_retriever.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CORPUS = Path(__file__).resolve().parent / "corpus.json"
WORD = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset({
    "a", "all", "an", "and", "are", "as", "at", "by", "do", "does", "for", "from", "how", "i", "in",
    "is", "it", "my", "of", "on", "so", "the", "to", "why", "with",
})


def words(text: str) -> set[str]:
    return {word for word in WORD.findall(text.lower()) if word not in STOPWORDS}


def retrieve(query: str, k: int, documents: list[dict]) -> list[dict]:
    wanted = words(query)
    scored = [(len(wanted & words(document["text"])), document["id"]) for document in documents]
    ranked = sorted((item for item in scored if item[0] > 0), key=lambda item: (-item[0], item[1]))
    return [{"id": document_id, "score": score} for score, document_id in ranked[:k]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Keyword retriever for the retrieval example.")
    parser.add_argument("--corpus", type=Path, default=CORPUS, help="corpus JSON with a 'documents' list")
    args = parser.parse_args(argv)
    request = json.loads(sys.stdin.read())
    documents = json.loads(args.corpus.read_text(encoding="utf-8"))["documents"]
    print(json.dumps({"results": retrieve(request["query"], int(request["k"]), documents)}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
