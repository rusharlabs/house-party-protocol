[English](SECURITY.md) · [Português](SECURITY.pt-BR.md)

# Segurança

## Reportar uma vulnerabilidade

**Não abra issue pública** para falha de segurança. Use um dos dois canais:

1. **GitHub → aba Security → "Report a vulnerability"** (relato privado, o preferido).
2. E-mail: `atendimento@rushar.com.br` com o assunto `[house-party-protocol] security`.

Inclua: o módulo e a versão (`.claude-plugin/plugin.json`), como reproduzir, e o impacto que você
mediu. Resposta inicial em até 5 dias úteis; correção publicada como nova versão do módulo, com a
nota no `CHANGELOG.md`.

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
