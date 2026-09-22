"""error_strategy -- what a Bash failure MEANS, and what to do about it.

Classifies the error message into a FAMILY and picks the recovery STRATEGY.
It's the first rung of gotcha-memory: without a family there's no
recurrence to count, and without recurrence there's no lesson to inject.

== ORIGIN =====================================================================

Written from scratch out of failures observed in transcripts and documented
as rules -- each family below cites the incident that justified it. Replaces,
via clean-room rewrite, an earlier version adapted from a third-party
repository with no declared license (`NOASSERTION` = all rights reserved).
Neither renaming nor attributing fixes unlicensed code; rewriting from your
own data does -- and it produces a better taxonomy for whoever operates
Claude Code, because it IS the taxonomy of whoever operates Claude Code.

== THE TAXONOMY, and why it is different ======================================

Seven families are the contract that `gotchas_memory` reads (severity and
prevention per family). Two were born here and don't exist in any generic table.

  instrument   The INSTRUMENT lied: the command returned zero, empty or partial and exited
               with exit 0 -- or exited with exit 1 over a legitimate result. It's the
               most expensive family, because the number LOOKS like a measurement.
               Measured cases: `grep -c` returning exit 1 when the count is 0; MSYS
               converting every argument that starts with a slash into a Windows path
               (`/health` becomes `C:/Program Files/Git/health`, zero hits); `tar` reading
               `X:/` as a remote host; `tee ARQ | head` truncating ARQ via SIGPIPE.
  lock         Another process holds the resource: `index.lock`, "another git process", "resource
               busy". It's not `state` (the data is intact) nor `transient` (it doesn't resolve
               on its own) -- it resolves when the lock's OWNER releases it or dies.

The other five are the families any operator recognizes --
and the consumer's contract requires exactly these names:

  ratelimit    429, overloaded, quota, too many requests
  transient    timeout, connection refused/reset, 502/503, DNS
  state        inconsistent data, corrupted, out of sync, merge conflict
  config       missing env, key not found, 401/403, invalid config file
  dependency   module/package/command not found, import that fails
  fatal        OOM, segfault, stack overflow, "unrecoverable"
  unknown      nothing matched -- and the default is RETRY, because an unknown error is rarely
               permanent, and escalating too early is what makes the operator ignore the gate

== THE STRATEGIES =============================================================

  retry                try again (the caller handles the backoff)
  rollback_and_retry   go back to the last good state BEFORE trying again
  skip                 skip it -- only for a non-critical task
  escalate             stop and call the human -- terminal
  recovery_workflow    run the recovery flow (reinstall, rebuild)
  remeasure            DO NOT repeat the command: change the instrument and measure
                       again. Exclusive to the `instrument` family. Repeating the same
                       command returns the same zero with the same appearance of truth.

Public API (contract kept for the consumer):
  classify_error(msg) -> family
  select_strategy(msg, *, attempt=1, max_retries=3, is_critical=True) -> StrategyDecision
  StrategyDecision(family, strategy, rationale, terminal)

stdlib only.
"""
from __future__ import annotations

import re
import unicodedata
from typing import NamedTuple

# --- estrategias -------------------------------------------------------------
RETRY = "retry"
ROLLBACK_AND_RETRY = "rollback_and_retry"
SKIP = "skip"
ESCALATE = "escalate"
RECOVERY_WORKFLOW = "recovery_workflow"
REMEASURE = "remeasure"


class Familia(NamedTuple):
    nome: str
    sinais: tuple          # simple substrings, compared lowercase
    padroes: tuple         # compiled regexes, for what a substring can't express
    estrategia: str
    porque: str            # the incident that bought this family


def _rx(*ps: str) -> tuple:
    return tuple(re.compile(p, re.I) for p in ps)


# THE ORDER MATTERS: the first family that matches wins. The most SPECIFIC ones come
# first, and `instrument` comes before everything because its signals are messages
# the other families would read wrong ("No such file" from a tar that actually
# tried to open a remote host; "0" from a grep that actually worked).
_FAMILIAS: tuple = (
    Familia(
        nome="instrument",
        sinais=(
            # Why: bare "cannot connect to" and "resolve failed" matched NETWORK failure (docker daemon,
            # postgres) and, since instrument never escalates by ceiling, max_retries became a bypass. The
            # case of GNU tar reading `X:/path` as a host ("Cannot connect to P: resolve failed") went to
            # PATTERNS, with the drive letter as host -- what distinguishes it from a real connection.
            "unexpected end of file",     # gzip: stdin truncated by SIGPIPE
            "broken pipe",
            "sigpipe",
            "msys2_arg_conv",
            "not in sorted order",        # comm with diverging collation
        ),
        padroes=_rx(
            r"tar \(child\):",                    # the remote tar's signature
            r"cannot connect to [a-z]:\s*resolve failed",  # tar reading X:/ as an rsh host
            r"grep: .*: (No such file|Is a directory)",  # grep that never reached its target
            r"\btee\b.*\bhead\b",                 # the pipeline that truncates
        ),
        estrategia=REMEASURE,
        porque=(
            "the command answers, the number is real, and it does not measure what it "
            "seems to. Repeating gives back the same zero. Change the instrument."
        ),
    ),
    Familia(
        nome="lock",
        sinais=(
            "index.lock",
            "another git process",
            "resource busy",
            "resource temporarily unavailable",
            "is being used by another process",   # Windows: file open
            "could not lock",
            "lock file",
        ),
        padroes=_rx(r"\block(ed)?\b.*\b(held|exists|busy)\b"),
        estrategia=RETRY,
        porque=(
            "an index.lock orphaned for 11h in a shared repo (2026-09-19): this is not "
            "corrupted state, it is an owner that never let go. Wait and retry; if it "
            "persists, a human decides whether the owner died."
        ),
    ),
    Familia(
        nome="ratelimit",
        sinais=(
            "rate limit", "rate-limit", "ratelimit",
            "overloaded",
            "quota exceeded", "quota",
            "too many requests",
            "retry-after",
            # Why: " 429" was a raw substring and matched "42900ms" and "4296 bytes". The 429
            # pattern right below already covers the HTTP code.
        ),
        padroes=_rx(r"\b429\b", r"limit(e)?\s+(semanal|weekly|diario|daily)"),
        estrategia=RETRY,
        porque=(
            "loop-cost-budget LC-5 and feedback_throttled_workflows_beat_ratelimit: "
            "the ceiling belongs to the provider, the backoff belongs to the caller. "
            "Never switch to a paid provider to punch through the limit."
        ),
    ),
    Familia(
        nome="transient",
        sinais=(
            "timeout", "timed out", "etimedout",
            "econnrefused", "connection refused", "conexao recusada", "cannot connect to",
            "could not resolve host", "resolve failed",   # Why: a DNS failure belongs to the network.
            "econnreset", "connection reset",
            "socket hang up",
            "network is unreachable", "temporary failure in name resolution",
            "eai_again", "enotfound",
            "bad gateway", "service unavailable", "gateway timeout",
        ),
        padroes=_rx(r"\b50[234]\b", r"fetch.*failed"),
        estrategia=RETRY,
        porque=(
            "health-kit: 'the health of a SERVICE is not the health of the DATA'. A "
            "service that is down answers like this; the data is still where it was. Retry."
        ),
    ),
    Familia(
        nome="state",
        sinais=(
            "corrupt", "inconsistent", "out of sync", "out-of-sync",
            "invalid state", "stale",
            "merge conflict", "conflict",
            "integrity check failed", "checksum mismatch", "crc",
        ),
        padroes=_rx(r"state.*(corrupt|invalid|inconsistent)"),
        estrategia=ROLLBACK_AND_RETRY,
        porque=(
            "continuity-kit: the data is wrong, not the channel. Go back to the last "
            "good state BEFORE trying again, or the retry writes on top of the corrupted "
            "one."
        ),
    ),
    Familia(
        nome="config",
        sinais=(
            "not set", "nao definida", "nao definido", "undefined environment",
            "missing config", "config missing", "invalid config",
            "no such key", "key not found", "keyerror",
            "unauthorized", "forbidden", "permission denied", "access denied",
            "invalid api key", "authentication failed",
        ),
        padroes=_rx(r"\b40[13]\b", r"env(ironment)?\s*(var(iable)?)?\s*\w*\s*(not set|missing|ausente)"),
        estrategia=ESCALATE,
        porque=(
            "shell-secret-guardrail R3: an empty secret is written with exit 0. Bad "
            "config needs a human HAND - retrying only repeats the error with more "
            "confidence."
        ),
    ),
    Familia(
        nome="dependency",
        sinais=(
            "cannot find module", "module not found", "modulenotfounderror",
            "no module named",
            "package not found", "could not find a version",
            "command not found", "nao encontrado", "not recognized as",
            "importerror", "import error",
            "enoent",
        ),
        padroes=_rx(r"no such file or directory", r"\bdependenc(y|ies)\b"),
        estrategia=RECOVERY_WORKFLOW,
        porque=(
            "claude-dev-kit: the part is not there. There is a flow for that (install, "
            "rebuild, reconnect) - and it is the flow, not the retry, that fixes it."
        ),
    ),
    Familia(
        nome="fatal",
        sinais=(
            "fatal", "unrecoverable",
            "out of memory", "oom", "oomkilled", "heap out of memory", "memoryerror",
            "segmentation fault", "segfault",
            "maximum call stack", "recursionerror", "stack overflow",
            "killed",
        ),
        padroes=_rx(r"\bexit code 13[7-9]\b"),   # 137 SIGKILL · 139 SIGSEGV
        estrategia=ESCALATE,
        porque=(
            "the process died from the inside. Retrying without changing anything "
            "reproduces the death; a human decides what to change."
        ),
    ),
)

_ESTRATEGIA_POR_FAMILIA = {f.nome: f.estrategia for f in _FAMILIAS}
_ESTRATEGIA_POR_FAMILIA["unknown"] = RETRY

FAMILIAS = tuple(f.nome for f in _FAMILIAS) + ("unknown",)


class StrategyDecision(NamedTuple):
    family: str
    strategy: str
    rationale: str
    terminal: bool  # True when there's nothing left to retry (escalate / skip)


def _compila_sinal(sinal: str):
    """A signal that starts AND ends with an alphanumeric gets a word boundary;
    the rest (with a space, dot, colon) matches by substring.

    # Why: `enotfound` used to match inside `modulENOTFOUNDerror` and classified a broken import
    # as network. A raw substring for a short token isn't an option: the boundary looks at the
    # ENDS, and the middle can have a space.
    """
    s = sinal.lower()
    if s and s[0].isalnum() and s[-1].isalnum():
        return re.compile("(?<![0-9a-z])" + re.escape(s) + "(?![0-9a-z])")
    return None  # None = raw substring (signals with punctuation at the ends, e.g.: "tar (child):")


_SINAIS_COMPILADOS = {
    fam.nome: tuple((s.lower(), _compila_sinal(s)) for s in fam.sinais) for fam in _FAMILIAS
}


def _casa(sinal_lower: str, rx, low: str) -> bool:
    return rx.search(low) is not None if rx is not None else sinal_lower in low


def _sem_acento(text: str) -> str:
    """Drop combining marks so a localized message matches the ASCII signal.

    # Why: a localized tool emits the same signal with and without the accent, and the table
    # listed BOTH spellings. Folding at match time keeps the coverage (and extends it to every
    # accented spelling) with one ASCII entry per signal.
    """
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def classify_error(error_message: str) -> str:
    """Returns the message's family. `unknown` when nothing matches -- it never invents one."""
    msg = str(error_message or "")
    if not msg.strip():
        return "unknown"
    low = _sem_acento(msg.lower())
    for fam in _FAMILIAS:
        if any(_casa(s, rx, low) for s, rx in _SINAIS_COMPILADOS[fam.nome]):
            return fam.nome
        if any(p.search(msg) for p in fam.padroes):
            return fam.nome
    return "unknown"


def familia_info(nome: str) -> Familia | None:
    """The family's full entry (sinais, estrategia, porque) -- for whoever
    wants to show the operator WHY the lesson exists."""
    for fam in _FAMILIAS:
        if fam.nome == nome:
            return fam
    return None


def select_strategy(
    error_message: str,
    *,
    attempt: int = 1,
    max_retries: int = 3,
    is_critical: bool = True,
) -> StrategyDecision:
    """Decides what to do with this error, on this attempt.

    attempt      current attempt, 1-based
    max_retries  ceiling; on reaching it, escalates regardless of family
    is_critical  False allows SKIP on a config error for a non-critical task
    """
    family = classify_error(error_message)

    # The retry ceiling beats everything -- except `instrument`, because there repeating was
    # never the answer: the strategy is already to change the instrument on the FIRST try.
    if family != "instrument" and attempt >= max_retries:
        return StrategyDecision(
            family=family,
            strategy=ESCALATE,
            rationale=f"{attempt}/{max_retries} attempts exhausted - escalate",
            terminal=True,
        )

    strategy = _ESTRATEGIA_POR_FAMILIA.get(family, RETRY)

    if family == "config" and not is_critical:
        strategy = SKIP

    terminal = strategy in (ESCALATE, SKIP)
    if family == "instrument":
        rationale = (
            "the instrument answered and did not measure what it seems to - do NOT repeat "
            "the command, change the ruler and measure again (remeasure)"
        )
    else:
        rationale = f"error classified as '{family}' -> {strategy}"
    return StrategyDecision(family=family, strategy=strategy, rationale=rationale, terminal=terminal)


def _self_test() -> None:
    # classic families
    assert classify_error("ETIMEDOUT connecting to host") == "transient"
    assert classify_error("Anthropic: overloaded") == "ratelimit"
    assert classify_error("HTTP 429 Too Many Requests") == "ratelimit"
    assert classify_error("Cannot find module 'foo'") == "dependency"
    assert classify_error("ModuleNotFoundError: No module named yaml") == "dependency"
    assert classify_error("invalid state: out of sync") == "state"
    assert classify_error("CONFLICT (content): Merge conflict in x.py") == "state"
    assert classify_error("ENV not set: API_KEY") == "config"
    assert classify_error("HTTP 403 Forbidden") == "config"
    assert classify_error("FATAL: out of memory") == "fatal"
    assert classify_error("Error: Exit code 137") == "fatal"
    assert classify_error("weird thing happened") == "unknown"
    assert classify_error("") == "unknown"

    # the two families born here
    assert classify_error("fatal: Unable to create '.git/index.lock': File exists.") == "lock", \
        "index.lock tem de vencer o 'fatal' generico"
    assert classify_error("Another git process seems to be running") == "lock"
    assert classify_error("tar (child): Cannot connect to P: resolve failed") == "instrument"
    assert classify_error("gzip: stdin: unexpected end of file") == "instrument"

    # strategies
    d1 = select_strategy("ETIMEDOUT", attempt=1, max_retries=3)
    assert d1.strategy == RETRY and not d1.terminal, d1
    d2 = select_strategy("ETIMEDOUT", attempt=3, max_retries=3)
    assert d2.strategy == ESCALATE and d2.terminal, d2
    d3 = select_strategy("missing config", attempt=1, is_critical=False)
    assert d3.strategy == SKIP and d3.terminal, d3
    d4 = select_strategy("state corrupt", attempt=1)
    assert d4.strategy == ROLLBACK_AND_RETRY, d4
    d5 = select_strategy("tar (child): Cannot connect to X: resolve failed", attempt=5, max_retries=3)
    assert d5.strategy == REMEASURE and not d5.terminal, \
        "instrument nunca vira 'escalate por teto' — repetir nunca foi a resposta"

    # contract with the consumer: the 7 classic families still exist
    for f in ("fatal", "dependency", "state", "config", "ratelimit", "transient", "unknown"):
        assert f in FAMILIAS, f

    # word boundary: a short signal does NOT match inside another word
    assert classify_error("ModuleNotFoundError: No module named yaml") == "dependency", \
        "enotfound casou dentro de modulENOTFOUNDerror — a fronteira de palavra caiu"
    assert classify_error("getaddrinfo ENOTFOUND api.example.com") == "transient", \
        "e o sinal isolado tem de continuar casando (controle)"
    assert classify_error("the room was overloaded with people") == "ratelimit", \
        "controle: palavra inteira casa mesmo em prosa"
    assert classify_error("preloaded assets") == "unknown", \
        "'loaded' nao e 'overloaded' — substring cru casaria"

    # the instrument discriminates: not everything falls into the same family
    assert len({classify_error(m) for m in (
        "ETIMEDOUT", "overloaded", "no module named x", "state corrupt",
        "env not set", "out of memory", "index.lock",
        "tar (child): Cannot connect to P: resolve failed", "xyz",
    )}) == 9
    # Why: connection refused is a network failure; the strategy escalates up to the retry ceiling.
    assert classify_error("Cannot connect to the Docker daemon") == "transient"
    assert select_strategy("Cannot connect to the Docker daemon", attempt=3, max_retries=3).terminal
    assert classify_error("timeout after 42900ms") != "ratelimit", "429 dentro de 42900 nao e rate limit"
    assert classify_error("container terminated: OOMKilled") == "fatal"
    assert classify_error("API_KEY nao definida") == "config"

    print("self-test OK")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] not in ("--self-test", "-t"):
        d = select_strategy(" ".join(sys.argv[1:]))
        print(f"family={d.family} strategy={d.strategy} terminal={d.terminal}\n  {d.rationale}")
        info = familia_info(d.family)
        if info:
            print(f"  porque: {info.porque}")
        sys.exit(0)
    _self_test()
