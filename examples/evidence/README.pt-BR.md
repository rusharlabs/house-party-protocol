[English](README.md) · [Português](README.pt-BR.md)

# Pacotes de evidência — uma checagem ponta a ponta que se re-deriva depois

> Novo na 2.6.0.

Um teste de navegador prova alguma coisa só quando três coisas valem: o comando que o rodou tem
nome, o código de saída foi medido fora do modelo, e os arquivos que ele deixou podem ser
re-hasheados amanhã. O `hpp evidence` registra exatamente isso. Ele não dirige navegador e não
chama modelo — o critério é o que você declarar.

| campo | o que guarda |
|---|---|
| `command` | o argv que rodou, como declarado |
| `exit_code` · `verdict` | `passed` só quando o comando saiu com 0 **e** todo artefato declarado existe |
| `artifacts` | por glob declarado: caminho (relativo), tamanho e sha256 de cada arquivo |
| `stdout` · `stderr` | contagem de bytes e sha256 — nunca o texto |
| `record_sha256` | hash do próprio registro, então um registro editado é pego |

## Rode o demo (sem navegador)

```bash
python -m hpp evidence run --id smoke-page --artifact out/report.html --artifact out/smoke.log \
  -- python examples/evidence/smoke_page.py
python -m hpp evidence verify .hpp/evidence/<the record path it printed>
```

Acrescente `--break` depois do script para ver um critério falhando: os artefatos são escritos e
o veredito continua `failed`, porque uma página que reprova na checagem não é evidência.

## Com um runner ponta a ponta de verdade

O padrão é o mesmo para qualquer runner que saia com código diferente de zero na falha e escreva
arquivos. No Playwright, mantenha traces e screenshots ligados e declare onde eles caem:

```bash
python -m hpp evidence run --id e2e-login --artifact "test-results/**/trace.zip" \
  --artifact "test-results/**/*.png" -- npx playwright test tests/login.spec.ts --trace on
```

Grave o teste uma vez (`npx playwright codegen`, ou um agente dirigindo o Playwright MCP enquanto
constrói) e versione o spec. O modelo pode ajudar a escrever o teste; ele nunca roda na verificação.

## Amarre ao loop

`--record-event` acrescenta `evidence_recorded` ao `.hpp/events.jsonl` quando, e só quando, o
pacote passou — uma execução que falhou é medição, não evidência, então nunca move o loop:

```bash
python -m hpp event append --type work_started
python -m hpp evidence run --id smoke-page --artifact out/report.html --record-event \
  -- python examples/evidence/smoke_page.py
python -m hpp status
```

## Limites

- No timeout, a árvore inteira de processos que o comando iniciou é parada. Quando o comando termina
  sozinho, um filho que ele deixou rodando não é esperado nem parado: ponha servidores de longa
  duração sob o ciclo de vida do próprio runner (`webServer` do Playwright).
- Um artefato só conta quando esta execução o escreveu. Um arquivo que casa com o glob mas está
  exatamente como estava antes da execução sai como `unchanged` e não satisfaz o padrão.
- No Windows, um nome de comando sem caminho, como `npx`, é resolvido por `PATH` e `PATHEXT`
  (`npx.cmd`), do jeito que um terminal resolve.
- Uma linha de comando com cara de carregar segredo é recusada; passe segredos pelo ambiente, nunca
  como argumento.
- Os globs de artefato são relativos ao workspace e não podem sair dele.
