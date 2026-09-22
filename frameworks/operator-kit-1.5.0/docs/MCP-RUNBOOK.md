[English](MCP-RUNBOOK.md) · [Português](MCP-RUNBOOK.pt-BR.md)

# MCP Runbook

A script for discovering, testing and diagnosing MCP servers without confusing
"configured" with "operational". Run the preflight before the done gate:

```bash
python scripts/preflight.py --project .
python scripts/done_gate.py "<verifiable criterion>"
```

## 1. Inventory per host

```bash
claude mcp list
codex mcp list
```

Record host, configuration scope, server name and transport. An entry
in the list proves configuration, not authentication nor a useful response.

## 2. Identity and secret

Read which account or workspace is active before calling a tool. A secret
lives in an environment variable or the host's vault; never paste a value into JSON, a command,
a document or a log.

```bash
python -c "import os; print('CONFIGURADA' if os.getenv('SERVICE_API_KEY') else 'AUSENTE')"
```

That command proves only the presence of the environment variable, not the validity of the
credential.

## 3. Positive control

Pick a read-only operation known to be alive, for example listing a
public resource or reading a stable item. Note request, exit code, time and
response. Only then test the case under investigation with the same instrument.

```bash
claude --debug
codex --help
```

If the control also fails, classify the instrument as non-discriminating;
do not declare the service dead.

## 4. Layered diagnosis

```bash
python -c "import socket; print(socket.getaddrinfo('example.com', 443)[0][4])"
```

Check, in this order: process/CLI, DNS resolution, transport, authentication,
authorization, tool schema and result at the destination. Preserve the first
causal error; do not replace it with an empty fallback.

## 5. Closure

Report `configured · connected · authorized · positive operation · target case`
as five separate states. Include gaps that depend on an account, a credential or
a human gate.

## Provenance

Structure inspired by the practice inventory of the repository
`shanraisshan/claude-code-best-practice`, MIT license, commit
`bde3f03174714fff4145d21cfda41ddd2ffffb28`. The procedure and the commands above
are an original implementation of House Party Protocol.
