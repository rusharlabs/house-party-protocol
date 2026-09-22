[English](MCP-RUNBOOK.md) · [Português](MCP-RUNBOOK.pt-BR.md)

# Runbook MCP

Roteiro para descobrir, testar e diagnosticar servidores MCP sem confundir
"configurado" com "operacional". Execute o preflight antes do done gate:

```bash
python scripts/preflight.py --project .
python scripts/done_gate.py "<verifiable criterion>"
```

## 1. Inventário por host

```bash
claude mcp list
codex mcp list
```

Registre host, escopo da configuração, nome do servidor e transporte. Uma
entrada na lista comprova configuração, não autenticação nem resposta útil.

## 2. Identidade e segredo

Leia qual conta ou workspace está ativo antes de chamar uma ferramenta. Segredo
fica em variável de ambiente ou cofre do host; nunca cole valor em JSON, comando,
documento ou log.

```bash
python -c "import os; print('CONFIGURADA' if os.getenv('SERVICE_API_KEY') else 'AUSENTE')"
```

Esse comando prova somente presença da variável de ambiente, não validade da
credencial.

## 3. Controle positivo

Escolha uma operação read-only conhecida como viva, por exemplo listar um
recurso público ou ler um item estável. Anote request, exit code, tempo e
resposta. Só depois teste o caso investigado com o mesmo instrumento.

```bash
claude --debug
codex --help
```

Se o controle também falhar, classifique o instrumento como não discriminante;
não declare o serviço morto.

## 4. Diagnóstico em camadas

```bash
python -c "import socket; print(socket.getaddrinfo('example.com', 443)[0][4])"
```

Verifique, nesta ordem: processo/CLI, resolução DNS, transporte, autenticação,
autorização, schema da ferramenta e resultado no destino. Preserve o primeiro
erro causal; não o substitua por um fallback vazio.

## 5. Fechamento

Reporte `configurado · conectado · autorizado · operação positiva · caso alvo`
como cinco estados separados. Inclua gaps que dependam de conta, credencial ou
gate humano.

## Proveniência

Estrutura inspirada no inventário de práticas do repositório
`shanraisshan/claude-code-best-practice`, licença MIT, commit
`bde3f03174714fff4145d21cfda41ddd2ffffb28`. O procedimento e os comandos acima
são uma implementação original do House Party Protocol.
