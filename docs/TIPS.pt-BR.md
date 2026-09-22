[English](TIPS.md) · [Português](TIPS.pt-BR.md)

# Padrões táticos

Comandos curtos para operar os kits sem depender de memória implícita. Ajuste
caminhos ao diretório emitido e leia o plano antes de usar `--apply`.

### 1. Inventarie antes de criar

```bash
rg --files | rg '(^|/)(name|termo)'
```

### 2. Meça a árvore Git sem confundir não rastreado

```bash
git status --short --branch
```

### 3. Separe mudança local do último commit

```bash
git diff --stat && git diff --cached --stat
```

### 4. Encontre a decisão, não só a implementação

```bash
rg -n -i 'decisão|decision|rejeitad|supersed' docs . --glob '*.md'
```

### 5. Execute o preflight antes do done gate

```bash
python scripts/preflight.py --project .
```

### 6. Faça o critério falhar antes da correção

```bash
python -m pytest caminho/do/teste.py::test_caso -q
```

### 7. Valide sintaxe Python isoladamente

```bash
python -m py_compile caminho/do/script.py
```

### 8. Rode o self-test do artefato

```bash
python caminho/do/script.py --self-test
```

### 9. Feche múltiplos critérios com AND

```bash
python scripts/done_gate.py "python -m pytest -q" "python -m py_compile app.py"
```

### 10. Declare parcial sem pintar de verde

```bash
python scripts/done_gate.py "python -m pytest -q" --declare-partial "falta validar o destino externo"
```

### 11. Instale um kit primeiro em modo plano

```bash
python installers/kit-forge-*/kit_doctor.py install --kit <kit> --target . --host claude-code
```

### 12. Aplique a instalação somente após ler o plano

```bash
python installers/kit-forge-*/kit_doctor.py install --kit <kit> --target . --host claude-code --apply
```

### 13. Instale skills namespaced no Codex

```bash
python installers/kit-forge-*/kit_doctor.py install --kit <kit> --target . --host codex --apply
```

### 14. Verifique integridade de um kit emitido

```bash
python installers/kit-forge-*/kit_doctor.py verify <kit>
```

### 15. Liste instalações registradas

```bash
python installers/kit-forge-*/kit_doctor.py registry
```

### 16. Escolha checker de outro provider

```bash
python multi-session/lane-kit-*/scripts/checker_router.py --maker claude --require
```

### 17. Veja as lanes sem editar o registry

```bash
python multi-session/lane-kit-*/scripts/lane_board.py --help
```

### 18. Conte itens com uma régua explícita

```bash
python frameworks/operator-kit-*/scripts/live_count.py --help
```

### 19. Procure erros silenciosos comuns

```bash
rg -n 'except\s+Exception|catch\s*\(|\.catch\(' --glob '*.py' --glob '*.js' --glob '*.ts'
```

### 20. Confirme a conta GitHub ativa

```bash
gh api user --jq .login
```

### 21. Compare o remoto antes de enviar

```bash
git ls-remote origin refs/heads/main
```

### 22. Liste MCPs por host

```bash
claude mcp list && codex mcp list
```

### 23. Gere o catálogo a partir da árvore

```bash
python installers/kit-forge-*/tools/catalog_md.py . --write
```

### 24. Valide todas as skills publicadas

```bash
find . -type d -name skills -exec python installers/kit-forge-*/tools/skill_lint.py --all {} \;
```

## Proveniência

O formato de índice tático foi inspirado no repositório
`shanraisshan/claude-code-best-practice`, licença MIT, commit
`bde3f03174714fff4145d21cfda41ddd2ffffb28`. A seleção, os textos e os comandos
desta página são uma implementação original do House Party Protocol.
