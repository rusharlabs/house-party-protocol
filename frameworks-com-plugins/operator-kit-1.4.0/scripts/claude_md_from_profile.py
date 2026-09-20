#!/usr/bin/env python3
"""
claude_md_from_profile (Operator Kit) — gera o bloco do CLAUDE.md a partir do operator-profile.yaml.

O CLAUDE.md nasce do MODELO, nao da memoria: le o `operator-profile.yaml` e escreve quatro
secoes que ensinam qualquer agente a operar ESTE projeto — e a calar onde a decisao nao e
dele. O piso vem PRIMEIRO, por cruzamento de campos, nunca por opiniao: cada linha sai de
um campo do perfil; se o campo nao esta la, a linha nao existe.

    ## O QUE VOCE NAO DECIDE      <- autonomia · guardrails · loop.fronteiras_proibidas
    ## ONDE AS COISAS MORAM       <- paths.*
    ## AS REGRAS DO PRONTO        <- verificacao.done_criterios · ladder
    ## O FLUXO                    <- concorrencia · loop · autonomia.default

O script governa SOMENTE o bloco entre os marcadores:

    <!-- operator-kit:claude-md:begin -->
    ...
    <!-- operator-kit:claude-md:end -->

O que esta fora dos marcadores e da pessoa e nunca e tocado. Dentro, a ultima linha e a
ASSINATURA (hash do perfil + data). Se o bloco foi editado a mao — a assinatura nao bate
com o conteudo — o script RECUSA sobrescrever, mostra o que mudaria e para.

Uso:
    python claude_md_from_profile.py                       # acha o perfil, grava ./CLAUDE.md
    python claude_md_from_profile.py --profile p.yaml --out CLAUDE.md
    python claude_md_from_profile.py --dry-run             # imprime o bloco, nao grava
    python claude_md_from_profile.py --force               # sobrescreve bloco editado a mao
    python claude_md_from_profile.py --self-test

Exit: 0 gravado ou no-op · 1 bloco editado a mao, recusado (use --force) ·
      2 uso/perfil invalido · 3 escrita recusada pela maquina (ver INSTRUCOES-DO-CLAUDE.md)

# Why: nenhum dos kits gerava CLAUDE.md a partir de um modelo estruturado — o perfil do
# operador era lido por scripts e nunca escrito para o agente ler. A geracao e CODIGO, nao
# prosa: "todo campo citado existe" tem de ser verdade por construcao, nao por disciplina.

stdlib + PyYAML. v1.0.0 — 2026-09-20 (Operator Kit · A14)
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from _lib.profile_loader import profile_path as find_profile  # type: ignore[import-not-found]
except Exception:  # noqa: BLE001 -- Why: sem o loader, --profile explicito continua funcionando; so a descoberta automatica cai
    find_profile = None  # type: ignore[assignment]

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

BEGIN = "<!-- operator-kit:claude-md:begin -->"
END = "<!-- operator-kit:claude-md:end -->"
FALLBACK_NAME = "INSTRUCOES-DO-CLAUDE.md"  # literal: e este nome que a pessoa vai procurar

# Why: a assinatura e o que separa "gerado" (pode sobrescrever) de "editado a mao" (nao pode).
# Ela carrega o hash do CONTEUDO gerado, entao qualquer edicao dentro do bloco a invalida.
# Why: a assinatura aponta para a skill (que resolve o caminho por ${CLAUDE_PLUGIN_ROOT}), nao
# para `python <script>`: o script mora no plugin, nao na raiz do projeto, e `python` a seco
# nao existe no macOS.
_ASSINATURA = "*Bloco gerado do `{perfil}` em {data} - assinatura {hash} - para regerar: skill `claude-md-from-profile` (operator-kit; script {script}). Se editar este bloco a mao, a assinatura deixa de bater e eu paro de sobrescrever.*"


def _get(d: dict, dotted: str, default=None):
    cur = d
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _lista(x) -> list:
    return [str(i) for i in x] if isinstance(x, list) else []


# --------------------------------------------------------------------------
# as quatro secoes — cada linha rastreia a UM campo do perfil
# --------------------------------------------------------------------------
def secao_nao_decide(p: dict) -> list:
    """O piso. Nunca sai vazia: se nada cruzou, uma linha honesta."""
    out = []
    por_acao = _get(p, "autonomia.por_acao", {}) or {}
    if isinstance(por_acao, dict):
        for acao, nivel in por_acao.items():
            try:
                n = int(nivel)
            except (TypeError, ValueError):
                continue
            if n <= 1:
                out.append(f"- **{acao}**: nivel {n} (`autonomia.por_acao.{acao}`). Voce PROPOE, nao executa. Quem autoriza e a pessoa.")
    for pth in _lista(_get(p, "autonomia.paths_sensiveis_auto_gate")):
        out.append(f"- Qualquer escrita em `{pth}` cai em gate humano automatico (`autonomia.paths_sensiveis_auto_gate`). Nao contorne por outro caminho.")
    for pth in _lista(_get(p, "guardrails.protected_paths")):
        out.append(f"- `{pth}` e protegido (`guardrails.protected_paths`): nao apague, nao mova, nao reescreva em massa.")
    for br in _lista(_get(p, "guardrails.protected_branches")):
        out.append(f"- Branch `{br}` e protegida (`guardrails.protected_branches`): nunca push direto, nunca force.")
    for fam in _lista(_get(p, "guardrails.block_families")):
        out.append(f"- A familia de comando **{fam}** e BLOQUEADA (`guardrails.block_families`). Nao ha excecao por urgencia.")
    ext = _lista(_get(p, "guardrails.external_send_tools"))
    if ext:
        out.append(f"- Enviar para fora ({', '.join(ext)}) e gate humano (`guardrails.external_send_tools`): prepare, mostre, nao dispare.")
    for fr in _lista(_get(p, "loop.fronteiras_proibidas")):
        out.append(f"- Fronteira proibida do loop: `{fr}` (`loop.fronteiras_proibidas`). Se a tarefa parecer exigir isto, a tarefa esta errada.")
    for sc in _lista(_get(p, "loop.stop_conditions")):
        out.append(f"- Condicao de PARADA: **{sc}** (`loop.stop_conditions`). Parar aqui e sucesso, nao falha.")
    if not out:
        out.append("- Este perfil ainda nao registrou nenhum limite. Isso quer dizer que ele esta no comeco, nao que voce esta livre. Pergunte antes de qualquer acao irreversivel.")
    return out


def secao_onde_moram(p: dict) -> list:
    paths = _get(p, "paths", {}) or {}
    if not isinstance(paths, dict) or not paths:
        return ["- `paths` nao esta preenchido no perfil. Nao assuma caminho nenhum - pergunte."]
    out = []
    for k, v in paths.items():
        if v is None or str(v).strip() == "":
            out.append(f"- **{k}**: *nao configurado* (`paths.{k}` vazio). Nao invente um caminho.")
        else:
            out.append(f"- **{k}** mora em `{v}` (`paths.{k}`).")
    return out


def secao_regras_do_pronto(p: dict) -> list:
    out = []
    crit = _get(p, "verificacao.done_criterios", {}) or {}
    if isinstance(crit, dict) and crit:
        out.append("\"Pronto\" so existe depois do gate. Por tipo de tarefa (`verificacao.done_criterios`):")
        for tipo, cmds in crit.items():
            cmds_l = _lista(cmds)
            if cmds_l:
                out.append(f"- **{tipo}**: " + " | ".join(f"`{c}`" for c in cmds_l))
            else:
                out.append(f"- **{tipo}**: *sem criterio* - lista vazia NUNCA passa por omissao (done_gate).")
    else:
        out.append("- `verificacao.done_criterios` nao esta preenchido. Sem criterio, nenhuma tarefa e \"pronta\" - o done_gate reprova lista vazia por desenho.")
    ladder = _get(p, "verificacao.ladder", {}) or {}
    obrig = _lista(_get(p, "verificacao.ladder_obrigatorios"))
    minimo = _get(p, "verificacao.ladder_score_minimo")
    if isinstance(ladder, dict) and ladder:
        out.append(f"- Escada de verificacao (`verificacao.ladder`): {', '.join(str(k) for k in ladder.keys())}."
                   + (f" Obrigatorios: {', '.join(obrig)}." if obrig else "")
                   + (f" Score minimo: {minimo}." if minimo is not None else ""))
    out.append("- Tres estados, e so um e proibido: **DONE** | **PARCIAL-DECLARADO** (diga o que falta) | ~~parcial silencioso~~. Se nao terminou, declare - silencio nao e estado.")
    return out


def secao_fluxo(p: dict) -> list:
    out = []
    default = _get(p, "autonomia.default")
    inten = _get(p, "intensidade.default")
    if default is not None:
        out.append(f"- Autonomia padrao: **nivel {default}** (`autonomia.default`)" + (f", intensidade **{inten}** (`intensidade.default`)." if inten else "."))
    teto = _get(p, "concorrencia.teto")
    wave = _get(p, "concorrencia.wave_size")
    fb = _get(p, "concorrencia.fallback")
    if teto is not None or wave is not None:
        out.append(f"- Paralelismo: teto **{teto}** (`concorrencia.teto`), ondas de **{wave}** (`concorrencia.wave_size`)" + (f", fallback `{fb}`." if fb else "."))
    charter = _get(p, "loop.charter")
    work = _get(p, "loop.work_list")
    if charter or work:
        out.append(f"- O loop le o charter em `{charter}` e a fila em `{work}` (`loop.charter` / `loop.work_list`).")
    gat = _lista(_get(p, "loop.gatilho_autorizacao"))
    if gat:
        out.append(f"- Execucao AMPLA so quando a pessoa disser uma destas: {', '.join(repr(g) for g in gat)} (`loop.gatilho_autorizacao`). Fora disso, uma acao por vez.")
    kw = _lista(_get(p, "guardrails.approval_keywords"))
    if kw:
        out.append(f"- Palavras que valem como aprovacao humana: {', '.join(repr(k) for k in kw)} (`guardrails.approval_keywords`). Nada mais vale.")
    if not out:
        out.append("- O perfil nao configurou autonomia nem concorrencia. Opere no nivel mais baixo ate alguem preencher `autonomia.default`.")
    return out


def gerar_bloco(perfil: dict, perfil_nome: str, script_nome: str, hoje: str | None = None) -> str:
    hoje = hoje or _dt.date.today().isoformat()
    exemplo = bool(perfil.get("_exemplo")) or perfil.get("projeto") in ("nome-do-projeto", "", None)
    linhas = [BEGIN]
    if exemplo:
        linhas.append("> AVISO: ESTE BLOCO FOI GERADO DE UM PERFIL DE EXEMPLO. O projeto abaixo nao existe. Preencha o `operator-profile.yaml` e regere.")
    linhas += [
        f"# Como operar `{perfil.get('projeto', '?')}`",
        "",
        "Este bloco foi gerado do `operator-profile.yaml`. Ele diz o que voce pode fazer, o que",
        "voce nao decide, e onde as coisas moram. **Leia o piso antes dos inventarios.**",
        "",
        "## O QUE VOCE NAO DECIDE", *secao_nao_decide(perfil), "",
        "## ONDE AS COISAS MORAM", *secao_onde_moram(perfil), "",
        "## AS REGRAS DO PRONTO", *secao_regras_do_pronto(perfil), "",
        "## O FLUXO", *secao_fluxo(perfil), "",
    ]
    corpo = "\n".join(linhas)
    h = hashlib.sha256(corpo.encode("utf-8")).hexdigest()[:12]
    linhas.append(_ASSINATURA.format(perfil=perfil_nome, data=hoje, hash=h, script=script_nome))
    linhas.append(END)
    return "\n".join(linhas) + "\n"


# --------------------------------------------------------------------------
# o bloco dentro do arquivo
# --------------------------------------------------------------------------
def _extrai_bloco(texto: str):
    i = texto.find(BEGIN)
    j = texto.find(END)
    if i < 0 or j < 0 or j < i:
        return None
    return texto[i: j + len(END) + (1 if texto[j + len(END): j + len(END) + 1] == "\n" else 0)]


def _bloco_foi_editado(bloco: str) -> bool:
    """True se a assinatura nao bate com o conteudo — alguem mexeu dentro do bloco."""
    linhas = bloco.rstrip("\n").split("\n")
    if len(linhas) < 3 or linhas[-1] != END:
        return True
    assin = linhas[-2]
    if "assinatura " not in assin:
        return True
    h_decl = assin.split("assinatura ")[1].split(" ")[0]
    corpo = "\n".join(linhas[:-2])
    return hashlib.sha256(corpo.encode("utf-8")).hexdigest()[:12] != h_decl


def aplicar(alvo: Path, bloco: str, force: bool = False) -> tuple:
    """Devolve (status, texto_final). status: novo | substituido | no-op | recusado."""
    if not alvo.exists():
        return "novo", bloco
    bruto = io.open(alvo, encoding="utf-8", newline="").read()
    # Why: um CLAUDE.md salvo em CRLF faria a assinatura nunca bater (o hash e do texto LF) e o
    # arquivo seria "editado a mao" para sempre. Trabalha-se em LF e devolve-se no EOL original.
    eol = "\r\n" if "\r\n" in bruto else "\n"
    atual = bruto.replace("\r\n", "\n")
    antigo = _extrai_bloco(atual)
    if antigo is None:
        # o bloco vai no TOPO: o piso e a primeira coisa que a IA le, antes do texto da pessoa
        status, texto = "novo", bloco + "\n" + atual
    elif _sem_assinatura_igual(antigo, bloco):
        return "no-op", bruto
    elif _bloco_foi_editado(antigo) and not force:
        return "recusado", bruto
    else:
        status, texto = "substituido", atual.replace(antigo, bloco, 1)
    return status, (texto.replace("\n", eol) if eol != "\n" else texto)


def _sem_assinatura_igual(a: str, b: str) -> bool:
    """Compara os blocos IGNORANDO a linha de assinatura (que carrega a data)."""
    def miolo(x):
        ls = x.rstrip("\n").split("\n")
        return "\n".join(l for l in ls if "assinatura " not in l)
    return miolo(a) == miolo(b)


def gravar(alvo: Path, texto: str) -> Path:
    """Grava; se a maquina recusar, cai no nome literal de fallback e devolve ELE."""
    try:
        with open(alvo, "w", encoding="utf-8", newline="") as fh:
            fh.write(texto)
        return alvo
    except OSError:
        # Why: algumas maquinas recusam a escrita de CLAUDE.md em silencio. Nao contornar por shell
        # nem por outro caminho — a recusa e protecao da maquina. O nome de fallback e LITERAL:
        # e ele que a pessoa vai procurar.
        fb = alvo.parent / FALLBACK_NAME
        cab = ("<!-- Este arquivo deveria se chamar CLAUDE.md. A gravacao com esse nome foi\n"
               "     recusada por esta maquina. RENOMEIE PARA CLAUDE.md e apague este bloco -->\n\n")
        with open(fb, "w", encoding="utf-8", newline="") as fh:
            fh.write(cab + texto)
        return fb


# --------------------------------------------------------------------------
def _self_test() -> None:
    import tempfile
    assert yaml is not None, "PyYAML necessario para o self-test"
    exemplo = Path(__file__).resolve().parents[1] / "profile.example.yaml"
    perfil = yaml.safe_load(io.open(exemplo, encoding="utf-8"))
    bloco = gerar_bloco(perfil, "profile.example.yaml", "x.py", hoje="2026-09-20")

    # forma
    assert "{{" not in bloco, "placeholder nao substituido"
    for sec in ("## O QUE VOCE NAO DECIDE", "## ONDE AS COISAS MORAM", "## AS REGRAS DO PRONTO", "## O FLUXO"):
        assert sec in bloco, sec
    assert bloco.index("## O QUE VOCE NAO DECIDE") < bloco.index("## ONDE AS COISAS MORAM"), "o piso vem PRIMEIRO"
    assert "PERFIL DE EXEMPLO" in bloco, "profile.example tem de vir carimbado como exemplo"
    assert bloco.startswith(BEGIN) and bloco.rstrip("\n").endswith(END)

    # todo campo citado existe: cada `chave.sub` citada esta no perfil
    import re
    for ref in set(re.findall(r"\(`([a-z_]+(?:\.[a-z_]+)+)`", bloco)):
        assert _get(perfil, ref, "__AUSENTE__") != "__AUSENTE__", f"citou campo que nao existe: {ref}"

    # piso nunca vazio, mesmo com perfil vazio
    vazio = gerar_bloco({"projeto": "x"}, "p.yaml", "x.py", hoje="2026-09-20")
    assert "ainda nao registrou nenhum limite" in vazio
    assert "nao esta preenchido" in vazio

    with tempfile.TemporaryDirectory() as td:
        alvo = Path(td) / "CLAUDE.md"
        # 1a vez: novo
        st, txt = aplicar(alvo, bloco); assert st == "novo"; gravar(alvo, txt)
        # 2a vez: no-op (idempotente)
        st, _ = aplicar(alvo, bloco); assert st == "no-op", st
        # arquivo com conteudo da pessoa FORA do bloco: preservado
        alvo.write_text("# Meu projeto\n\nminhas notas\n", encoding="utf-8")
        st, txt = aplicar(alvo, bloco)
        assert st == "novo" and txt.startswith(BEGIN) and txt.rstrip("\r\n").endswith("minhas notas"), "bloco no TOPO, pessoa INTEIRA depois"
        gravar(alvo, txt)
        assert "minhas notas" in alvo.read_text(encoding="utf-8")
        # perfil muda -> bloco substituido, e o de fora continua la
        bloco2 = gerar_bloco({**perfil, "projeto": "outro"}, "p.yaml", "x.py", hoje="2026-09-20")
        st, txt = aplicar(alvo, bloco2); assert st == "substituido"; gravar(alvo, txt)
        t = alvo.read_text(encoding="utf-8")
        assert "minhas notas" in t and "outro" in t and t.count(BEGIN) == 1
        # edicao A MAO dentro do bloco -> recusado; --force -> substitui
        t2 = t.replace("## O FLUXO", "## O FLUXO (editei)")
        alvo.write_text(t2, encoding="utf-8")
        st, _ = aplicar(alvo, bloco2); assert st == "recusado", "edicao a mao tem de ser recusada"
        st, txt = aplicar(alvo, bloco2, force=True); assert st == "substituido"
        # o instrumento discrimina: bloco intacto NAO e "editado"
        assert not _bloco_foi_editado(bloco2)
        assert _bloco_foi_editado(bloco2.replace("## O FLUXO", "## O FLUXO x"))
        # recusa de escrita -> fallback literal
        ro = Path(td) / "ro"; ro.mkdir()
        alvo_ro = ro / "CLAUDE.md"; alvo_ro.mkdir()   # um DIRETORIO com esse nome: open() falha
        dest = gravar(alvo_ro, bloco)
        assert dest.name == FALLBACK_NAME and dest.exists()
        assert "RENOMEIE PARA CLAUDE.md" in dest.read_text(encoding="utf-8")
    print("self-test OK")


def main(argv) -> int:
    if argv and argv[0] in ("--self-test", "-t"):
        _self_test()
        return 0
    dry = "--dry-run" in argv
    force = "--force" in argv
    args = [a for a in argv if a not in ("--dry-run", "--force")]
    prof_path = None
    out_path = Path("CLAUDE.md")
    i = 0
    while i < len(args):
        if args[i] == "--profile" and i + 1 < len(args):
            prof_path = Path(args[i + 1]); i += 2; continue
        if args[i] == "--out" and i + 1 < len(args):
            out_path = Path(args[i + 1]); i += 2; continue
        print(__doc__.split("Uso:")[1].split("Exit:")[0], file=sys.stderr)
        return 2

    if yaml is None:
        print("claude_md_from_profile: PyYAML ausente — instale pyyaml", file=sys.stderr)
        return 2
    if prof_path is None:
        if find_profile is None:
            print("claude_md_from_profile: passe --profile <operator-profile.yaml>", file=sys.stderr)
            return 2
        prof_path = find_profile()
        if prof_path is None:
            print("claude_md_from_profile: nenhum operator-profile.yaml encontrado a partir da cwd. "
                  "O CLAUDE.md nasce do perfil, nao do contrario — crie o perfil primeiro "
                  "(cp profile.example.yaml operator-profile.yaml).", file=sys.stderr)
            return 2
    prof_path = Path(prof_path)
    try:
        perfil = yaml.safe_load(io.open(prof_path, encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001 -- Why: YAML quebrado vira exit 2 com a mensagem do parser, nunca um bloco gerado pela metade
        print(f"claude_md_from_profile: perfil ilegivel ({exc}). Nao conserto as cegas — corrija o YAML.", file=sys.stderr)
        return 2
    if not isinstance(perfil, dict):
        print("claude_md_from_profile: o perfil nao e um mapeamento YAML", file=sys.stderr)
        return 2

    bloco = gerar_bloco(perfil, prof_path.name, Path(__file__).name)
    if dry:
        sys.stdout.write(bloco)
        return 0

    status, texto = aplicar(out_path, bloco, force=force)
    if status == "recusado":
        print(f"claude_md_from_profile: o bloco em {out_path} foi EDITADO A MAO (a assinatura nao bate). "
              "Nao sobrescrevo. Veja o que mudaria com --dry-run; para sobrescrever mesmo assim, --force.",
              file=sys.stderr)
        return 1
    if status == "no-op":
        print(f"claude_md_from_profile: {out_path} ja esta em dia com {prof_path.name} (no-op)")
        return 0
    dest = gravar(out_path, texto)
    if dest.name == FALLBACK_NAME:
        print(f"claude_md_from_profile: esta maquina nao me deixou gravar {out_path.name}. O conteudo esta "
              f"inteiro em {dest} — renomeie para {out_path.name} e esta resolvido.", file=sys.stderr)
        return 3
    print(f"claude_md_from_profile: bloco {status} em {dest} (fonte: {prof_path.name})")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
