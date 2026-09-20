#!/usr/bin/env python3
"""Detecta CLIs alternativas e escolhe um checker cross-provider sem executá-lo.

Inspiração conceitual: shanraisshan/claude-code-best-practice, MIT, commit
bde3f03174714fff4145d21cfda41ddd2ffffb28. Implementação original do HPP.

Exit: 0 rota encontrada · 1 nenhuma rota (warn) · 2 rota obrigatória ausente · 3 erro.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Callable


PROVIDERS = {
    "codex": ("codex",),
    "cursor": ("agent", "cursor-agent", "cursor"),
    "gemini": ("gemini",),
    "claude": ("claude",),
}
DEFAULT_ORDER = ("codex", "gemini", "cursor", "claude")


def detect(which: Callable[[str], str | None] = shutil.which) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for provider, commands in PROVIDERS.items():
        resolved = next(((name, which(name)) for name in commands if which(name)), None)
        result[provider] = {
            "available": resolved is not None,
            "command": resolved[0] if resolved else None,
            "path": resolved[1] if resolved else None,
        }
    return result


def choose(maker: str, available: dict[str, dict], order: tuple[str, ...]) -> str | None:
    return next((name for name in order if name != maker and available.get(name, {}).get("available")), None)


def route(maker: str, prefer: tuple[str, ...]) -> dict:
    available = detect()
    selected = choose(maker, available, prefer)
    return {
        "status": "ok" if selected else "warn",
        "maker": maker,
        "checker": selected,
        "command": available[selected]["command"] if selected else None,
        "available": available,
        "note": "o roteador só seleciona; permissões e prompt read-only continuam explícitos no chamador",
    }


def _self_test() -> int:
    paths = {"codex": "/bin/codex", "agent": "/bin/agent", "gemini": "/bin/gemini", "claude": "/bin/claude"}
    available = detect(paths.get)
    assert all(available[name]["available"] for name in ("codex", "cursor", "gemini", "claude"))
    assert choose("claude", available, DEFAULT_ORDER) == "codex"
    assert choose("codex", available, ("codex", "gemini")) == "gemini"
    assert choose("claude", detect(lambda _name: None), DEFAULT_ORDER) is None
    print("self-test OK — detecta Codex/Cursor/Gemini e nunca escolhe o maker como checker")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maker", default="claude", choices=tuple(PROVIDERS))
    parser.add_argument("--prefer", default=",".join(DEFAULT_ORDER))
    parser.add_argument("--require", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    prefer = tuple(item.strip() for item in args.prefer.split(",") if item.strip())
    unknown = [item for item in prefer if item not in PROVIDERS]
    if not prefer or unknown:
        print(json.dumps({"status": "error", "unknown": unknown}, ensure_ascii=False))
        return 3
    report = route(args.maker, prefer)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["checker"]:
        return 0
    return 2 if args.require else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
