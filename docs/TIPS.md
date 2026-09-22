[English](TIPS.md) · [Português](TIPS.pt-BR.md)

# Tactical patterns

Short commands to operate the kits without relying on implicit memory. Adjust
paths to the emitted directory and read the plan before using `--apply`.

### 1. Inventory before creating

```bash
rg --files | rg '(^|/)(nome|termo)'
```

### 2. Measure the Git tree without confusing untracked files

```bash
git status --short --branch
```

### 3. Separate local change from the last commit

```bash
git diff --stat && git diff --cached --stat
```

### 4. Find the decision, not only the implementation

```bash
rg -n -i 'decisão|decision|rejeitad|supersed' docs . --glob '*.md'
```

### 5. Run the preflight before the done gate

```bash
python scripts/preflight.py --project .
```

### 6. Make the criterion fail before the fix

```bash
python -m pytest caminho/do/teste.py::test_caso -q
```

### 7. Validate Python syntax in isolation

```bash
python -m py_compile caminho/do/script.py
```

### 8. Run the artifact's self-test

```bash
python caminho/do/script.py --self-test
```

### 9. Close multiple criteria with AND

```bash
python scripts/done_gate.py "python -m pytest -q" "python -m py_compile app.py"
```

### 10. Declare a partial without painting it green

```bash
python scripts/done_gate.py "python -m pytest -q" --declare-partial "falta validar o destino externo"
```

### 11. Install a kit in plan mode first

```bash
python installers/kit-forge-*/kit_doctor.py install --kit <kit> --target . --host claude-code
```

### 12. Apply the installation only after reading the plan

```bash
python installers/kit-forge-*/kit_doctor.py install --kit <kit> --target . --host claude-code --apply
```

### 13. Install namespaced skills on Codex

```bash
python installers/kit-forge-*/kit_doctor.py install --kit <kit> --target . --host codex --apply
```

### 14. Verify the integrity of an emitted kit

```bash
python installers/kit-forge-*/kit_doctor.py verify <kit>
```

### 15. List registered installations

```bash
python installers/kit-forge-*/kit_doctor.py registry
```

### 16. Choose a checker from another provider

```bash
python multi-session/lane-kit-*/scripts/checker_router.py --maker claude --require
```

### 17. See the lanes without editing the registry

```bash
python multi-session/lane-kit-*/scripts/lane_board.py --help
```

### 18. Count items with an explicit ruler

```bash
python frameworks/operator-kit-*/scripts/live_count.py --help
```

### 19. Look for common silent errors

```bash
rg -n 'except\s+Exception|catch\s*\(|\.catch\(' --glob '*.py' --glob '*.js' --glob '*.ts'
```

### 20. Confirm the active GitHub account

```bash
gh api user --jq .login
```

### 21. Compare the remote before pushing

```bash
git ls-remote origin refs/heads/main
```

### 22. List MCPs per host

```bash
claude mcp list && codex mcp list
```

### 23. Generate the catalogue from the tree

```bash
python installers/kit-forge-*/tools/catalog_md.py . --write
```

### 24. Validate every published skill

```bash
find . -type d -name skills -exec python installers/kit-forge-*/tools/skill_lint.py --all {} \;
```

## Provenance

The tactical index format was inspired by the repository
`shanraisshan/claude-code-best-practice`, MIT licence, commit
`bde3f03174714fff4145d21cfda41ddd2ffffb28`. The selection, the texts and the commands
on this page are an original implementation of House Party Protocol.
