[English](SECURITY.md) · [Português](SECURITY.pt-BR.md)

# Segurança

## Versões suportadas

Correções de segurança vão só para a linha minor atual; cada correção sai como uma nova versão
patch com a nota no `CHANGELOG.md`. Confira a sua com `hpp --version`.

| versão | suportada |
|---|---|
| 2.4.x | sim — linha atual |
| 2.0 – 2.3 | não — atualize para 2.4.x |
| 1.x | não |

Os módulos têm versão própria (`plugin.json`, `marketplace.json`); a correção de um módulo sai
como nova versão do módulo, pela mesma release.

## Reportar uma vulnerabilidade

**Não abra issue pública** para falha de segurança. Dois canais, igualmente válidos — use o que
funcionar para você:

1. **GitHub → aba Security → "Report a vulnerability"** (relato privado). Se o botão não
   estiver lá — relato privado é uma configuração do repositório — use o canal de e-mail; ele
   não é um fallback de menor valor.
2. **Canal de contato no site:** `https://rusharlabs.com`. Nenhum endereço cru é publicado aqui de
   propósito: caixa de e-mail em repositório público é colhida, e caixa colhida é canal que deixa
   de ser lido.

Inclua: o módulo e a versão (`.claude-plugin/plugin.json`), como reproduzir, e o impacto que você
mediu. Resposta inicial em até 5 dias úteis por qualquer dos dois canais; correção publicada como
nova versão do módulo, com a nota no `CHANGELOG.md`.

## O que este projeto considera falha de segurança

- Um hook ou script de módulo que **execute** algo que não está no seu próprio código (download,
  `curl | bash`, `eval` sobre entrada externa).
- Um módulo que **leia ou envie** credencial, `.env`, token ou dado do projeto para fora da máquina.
- Um gate que **passe** quando deveria bloquear (o `ip_pii_linter` deixando segredo entrar num
  módulo; o `done_gate` devolvendo verde sem exit 0) — isso é vulnerabilidade, não bug.

## O que já está no desenho

- Cada módulo traz `CHECKSUMS.txt` (sha256 por arquivo) e um `.zip` com os mesmos bytes;
  `kit_doctor.py verify <módulo>` prova a integridade antes de instalar.
- Todo `.py` de módulo tem `--self-test`; o `kit_doctor.py install` roda todos antes de tocar o
  seu projeto.
- Hooks são **WARN-only por padrão** — um hook nunca derruba a ferramenta.
- Nenhum módulo contém credencial. O ruleset real do linter de IP/PII nunca é publicado; só o
  `ip-ruleset.example.yaml` viaja.

## Superfícies oficiais

O projeto é publicado nestes lugares e em nenhum outro. Uma cópia encontrada em outro lugar —
outra conta do GitHub, um índice de pacotes que a lista abaixo não nomeia, um site de download,
um fork que mantém o nome — não é este projeto e não recebe suporte de segurança.

- Fonte, issues, releases: `https://github.com/rushar-labs/house-party-protocol`
- Canal de plugin do Claude Code: `/plugin marketplace add rushar-labs/house-party-protocol`
- pip: `pip install git+https://github.com/rushar-labs/house-party-protocol@<tag>` (uma
  publicação no PyPI, quando existir, é anunciada primeiro no `CHANGELOG.md` e no README)
- Web: `https://rusharlabs.com` (o canal de contato para o que não cabe numa issue pública)

Todo diretório de módulo traz `CHECKSUMS.txt`, e toda GitHub Release traz `SHA256SUMS`; um
arquivo cujo hash não está neles não veio daqui.
