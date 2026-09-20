"""error_strategy — o que uma falha de Bash QUER DIZER, e o que fazer com ela.

Classifica a mensagem de erro numa FAMILIA e escolhe a ESTRATEGIA de recuperacao. E o
primeiro degrau do gotcha-memory: sem familia, nao ha recorrencia a contar, e sem
recorrencia nao ha licao a injetar.

== ORIGEM =====================================================================

Escrito do zero a partir de falhas observadas em transcripts e documentadas como regras —
cada familia abaixo cita o incidente que a justificou. Substitui, por reescrita clean-room,
uma versao anterior adaptada de
um repositorio de terceiro sem licenca declarada (`NOASSERTION` = todos os direitos
reservados). Nem renomear nem atribuir resolve codigo sem licenca; reescrever a partir
do proprio dado resolve — e produz uma taxonomia melhor para quem opera Claude Code,
porque e a taxonomia de quem opera Claude Code.

== A TAXONOMIA, e por que ela e diferente ======================================

Sete familias sao o contrato que o `gotchas_memory` le (severidade e prevencao por
familia). Duas nasceram aqui e nao existem em tabela generica nenhuma:

  instrument   o INSTRUMENTO mentiu: o comando devolveu zero, vazio ou parcial e saiu
               com exit 0 — ou saiu com exit 1 sobre um resultado legitimo. E a familia
               mais cara, porque o numero PARECE medicao. Casos medidos:
               `grep -c` devolvendo exit 1 quando a contagem e 0 · o MSYS convertendo
               todo argumento iniciado por barra em caminho Windows (`/health` vira
               `C:/Program Files/Git/health`, zero hits) · `tar` lendo `X:/` como host
               remoto · `tee ARQ | head` truncando ARQ por SIGPIPE.
  lock         outro processo segura o recurso: `index.lock`, "another git process",
               "resource busy". Nao e `state` (o dado esta integro) nem `transient` (nao
               resolve sozinho) — resolve quando o DONO do lock solta ou morre.

As outras cinco sao as familias que qualquer operador reconhece — e o contrato do
consumidor exige exatamente estes nomes:

  ratelimit    429, overloaded, quota, too many requests
  transient    timeout, conexao recusada/resetada, 502/503, DNS
  state        dado inconsistente, corrompido, fora de sincronia, conflito de merge
  config       env ausente, chave nao encontrada, 401/403, arquivo de config invalido
  dependency   modulo/pacote/comando nao encontrado, import que falha
  fatal        OOM, segfault, stack overflow, "unrecoverable"
  unknown      nada casou — e o default e RETRY, porque um erro desconhecido raramente
               e permanente, e escalar cedo demais e o que faz o operador ignorar o gate

== AS ESTRATEGIAS =============================================================

  retry                tente de novo (o chamador cuida do backoff)
  rollback_and_retry   volte ao ultimo estado bom ANTES de tentar de novo
  skip                 pule — so em tarefa nao-critica
  escalate             pare e chame o humano — terminal
  recovery_workflow    rode o fluxo de recuperacao (reinstalar, reconstruir)
  remeasure            NAO repita o comando: troque o instrumento e meca de novo.
                       Exclusiva da familia `instrument`. Repetir o mesmo comando
                       devolve o mesmo zero com a mesma cara de verdade.

API publica (contrato mantido para o consumidor):
  classify_error(msg) -> familia
  select_strategy(msg, *, attempt=1, max_retries=3, is_critical=True) -> StrategyDecision
  StrategyDecision(family, strategy, rationale, terminal)

stdlib only.
"""
from __future__ import annotations

import re
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
    sinais: tuple          # substrings simples, comparadas em minusculas
    padroes: tuple         # regexes compiladas, para o que substring nao expressa
    estrategia: str
    porque: str            # o incidente que comprou esta familia


def _rx(*ps: str) -> tuple:
    return tuple(re.compile(p, re.I) for p in ps)


# A ORDEM IMPORTA: a primeira familia que casar vence. As mais ESPECIFICAS vem
# primeiro, e `instrument` vem antes de tudo porque os sinais dela sao mensagens
# que as outras familias leriam errado ("No such file" de um tar que na verdade
# tentou abrir um host remoto; "0" de um grep que na verdade funcionou).
_FAMILIAS: tuple = (
    Familia(
        nome="instrument",
        sinais=(
            # Why: "cannot connect to" e "resolve failed" soltos casavam falha de REDE (docker daemon,
            # postgres) e, como instrument nunca escala por teto, o max_retries virava bypass. O caso
            # do GNU tar lendo `X:/caminho` como host ("Cannot connect to P: resolve failed") foi para
            # os PADROES, com a letra de unidade como host — e o que o distingue de uma conexao de verdade.
            "unexpected end of file",     # gzip: stdin truncado pelo SIGPIPE
            "broken pipe",
            "sigpipe",
            "msys2_arg_conv",
            "not in sorted order",        # comm com collation divergente
        ),
        padroes=_rx(
            r"tar \(child\):",                    # a assinatura do tar remoto
            r"cannot connect to [a-z]:\s*resolve failed",  # tar lendo X:/ como host rsh
            r"grep: .*: (No such file|Is a directory)",  # grep que nao chegou no alvo
            r"\btee\b.*\bhead\b",                 # o pipeline que trunca
        ),
        estrategia=REMEASURE,
        porque=(
            "o comando responde, o numero e real, e nao mede o que parece. Repetir "
            "devolve o mesmo zero. Troque o instrumento."
        ),
    ),
    Familia(
        nome="lock",
        sinais=(
            "index.lock",
            "another git process",
            "resource busy",
            "resource temporarily unavailable",
            "is being used by another process",   # Windows: arquivo aberto
            "could not lock",
            "lock file",
        ),
        padroes=_rx(r"\block(ed)?\b.*\b(held|exists|busy)\b"),
        estrategia=RETRY,
        porque=(
            "index.lock orfao por 11h no repo compartilhado (2026-09-19): nao e "
            "estado corrompido, e um dono que nao soltou. Espera e retenta; se "
            "persistir, o humano decide se o dono morreu."
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
            # Why: " 429" era substring crua e casava "42900ms" e "4296 bytes". O padrao 429 logo
            # abaixo ja cobre o codigo HTTP.
        ),
        padroes=_rx(r"\b429\b", r"limit(e)?\s+(semanal|weekly|diario|daily)"),
        estrategia=RETRY,
        porque=(
            "loop-cost-budget LC-5 e feedback_throttled_workflows_beat_ratelimit: "
            "o teto e do provedor; backoff e do chamador. Nunca trocar de provedor "
            "pago para furar o limite."
        ),
    ),
    Familia(
        nome="transient",
        sinais=(
            "timeout", "timed out", "etimedout",
            "econnrefused", "connection refused", "conexao recusada", "cannot connect to",
            "could not resolve host", "resolve failed",   # Why: falha de DNS pertence a rede.
            "econnreset", "connection reset",
            "socket hang up",
            "network is unreachable", "temporary failure in name resolution",
            "eai_again", "enotfound",
            "bad gateway", "service unavailable", "gateway timeout",
        ),
        padroes=_rx(r"\b50[234]\b", r"fetch.*failed"),
        estrategia=RETRY,
        porque=(
            "health-kit: 'health de SERVICO != health de DADO'. Servico fora responde "
            "assim; o dado continua onde estava. Retenta."
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
            "continuity-kit: o dado esta errado, nao o canal. Voltar ao ultimo "
            "estado bom ANTES de tentar de novo, ou a retentativa grava em cima do "
            "corrompido."
        ),
    ),
    Familia(
        nome="config",
        sinais=(
            "not set", "nao definida", "nao definido", "não definida", "não definido", "undefined environment",
            "missing config", "config missing", "invalid config",
            "no such key", "key not found", "keyerror",
            "unauthorized", "forbidden", "permission denied", "access denied",
            "invalid api key", "authentication failed",
        ),
        padroes=_rx(r"\b40[13]\b", r"env(ironment)?\s*(var(iable)?)?\s*\w*\s*(not set|missing|ausente)"),
        estrategia=ESCALATE,
        porque=(
            "shell-secret-guardrail R3: segredo vazio grava com exit 0. Config errada "
            "exige a MAO do humano — retentar so repete o erro com mais confianca."
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
            "claude-dev-kit: a peca nao esta la. Tem fluxo para isso (instalar, "
            "reconstruir, religar) — e o fluxo, nao a retentativa, que resolve."
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
            "o processo morreu por dentro. Retentar sem mudar nada reproduz a morte; "
            "o humano decide o que mudar."
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
    terminal: bool  # True quando nao ha o que retentar (escalate / skip)


def _compila_sinal(sinal: str):
    """Sinal que comeca E termina em alfanumerico ganha fronteira de palavra;
    o resto (com espaco, ponto, dois-pontos) casa por substring.

    # Why: `enotfound` casava dentro de `modulENOTFOUNDerror` e classificava um import quebrado
    # como rede. Substring crua de token curto nao e opcao: a fronteira olha as PONTAS e o
    # miolo pode ter espaco.
    """
    s = sinal.lower()
    if s and s[0].isalnum() and s[-1].isalnum():
        return re.compile("(?<![0-9a-z])" + re.escape(s) + "(?![0-9a-z])")
    return None  # None = substring cru (sinais com pontuacao nas pontas, ex.: "tar (child):")


_SINAIS_COMPILADOS = {
    fam.nome: tuple((s.lower(), _compila_sinal(s)) for s in fam.sinais) for fam in _FAMILIAS
}


def _casa(sinal_lower: str, rx, low: str) -> bool:
    return rx.search(low) is not None if rx is not None else sinal_lower in low


def classify_error(error_message: str) -> str:
    """Devolve a familia da mensagem. `unknown` quando nada casa — nunca inventa."""
    msg = str(error_message or "")
    if not msg.strip():
        return "unknown"
    low = msg.lower()
    for fam in _FAMILIAS:
        if any(_casa(s, rx, low) for s, rx in _SINAIS_COMPILADOS[fam.nome]):
            return fam.nome
        if any(p.search(msg) for p in fam.padroes):
            return fam.nome
    return "unknown"


def familia_info(nome: str) -> Familia | None:
    """A entrada completa da familia (sinais, estrategia, porque) — para quem
    quiser mostrar ao operador POR QUE a licao existe."""
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
    """Decide o que fazer com este erro, nesta tentativa.

    attempt      tentativa atual, 1-based
    max_retries  teto; ao atingir, escala independente da familia
    is_critical  False permite SKIP em erro de config de tarefa nao-critica
    """
    family = classify_error(error_message)

    # Teto de tentativas vence tudo — menos `instrument`, porque ali repetir nunca
    # foi a resposta: a estrategia ja e trocar o instrumento na PRIMEIRA vez.
    if family != "instrument" and attempt >= max_retries:
        return StrategyDecision(
            family=family,
            strategy=ESCALATE,
            rationale=f"{attempt}/{max_retries} tentativas esgotadas — escalar",
            terminal=True,
        )

    strategy = _ESTRATEGIA_POR_FAMILIA.get(family, RETRY)

    if family == "config" and not is_critical:
        strategy = SKIP

    terminal = strategy in (ESCALATE, SKIP)
    if family == "instrument":
        rationale = (
            "o instrumento respondeu e nao mediu o que parece — NAO repita o comando, "
            "troque a regua e meca de novo (remeasure)"
        )
    else:
        rationale = f"erro classificado como '{family}' -> {strategy}"
    return StrategyDecision(family=family, strategy=strategy, rationale=rationale, terminal=terminal)


def _self_test() -> None:
    # familias classicas
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

    # as duas familias que nasceram aqui
    assert classify_error("fatal: Unable to create '.git/index.lock': File exists.") == "lock", \
        "index.lock tem de vencer o 'fatal' generico"
    assert classify_error("Another git process seems to be running") == "lock"
    assert classify_error("tar (child): Cannot connect to P: resolve failed") == "instrument"
    assert classify_error("gzip: stdin: unexpected end of file") == "instrument"

    # estrategias
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

    # contrato com o consumidor: as 7 familias classicas continuam existindo
    for f in ("fatal", "dependency", "state", "config", "ratelimit", "transient", "unknown"):
        assert f in FAMILIAS, f

    # fronteira de palavra: um sinal curto NAO casa dentro de outra palavra
    assert classify_error("ModuleNotFoundError: No module named yaml") == "dependency", \
        "enotfound casou dentro de modulENOTFOUNDerror — a fronteira de palavra caiu"
    assert classify_error("getaddrinfo ENOTFOUND api.example.com") == "transient", \
        "e o sinal isolado tem de continuar casando (controle)"
    assert classify_error("the room was overloaded with people") == "ratelimit", \
        "controle: palavra inteira casa mesmo em prosa"
    assert classify_error("preloaded assets") == "unknown", \
        "'loaded' nao e 'overloaded' — substring cru casaria"

    # o instrumento discrimina: nem tudo cai na mesma familia
    assert len({classify_error(m) for m in (
        "ETIMEDOUT", "overloaded", "no module named x", "state corrupt",
        "env not set", "out of memory", "index.lock",
        "tar (child): Cannot connect to P: resolve failed", "xyz",
    )}) == 9
    # Why: conexao recusada e falha de rede; a estrategia escala ate o teto de tentativas.
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
