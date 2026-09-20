# 00-ISOLAMENTO-E-RECUPERAÇÃO — {{project_name}}

> Responde a pergunta que nenhum doc de handoff sozinho responde: **"outra sessão vai
> sobrescrever isto enquanto eu trabalho?"** Se você não sabe a resposta antes de editar
> um arquivo compartilhado, pare e confira aqui primeiro.

## Isolamento — quem pode tocar o quê, AGORA

1. **Confira o registry de lanes vivas** (se o lane-kit estiver instalado):
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/lane_board.py status
   ```
2. **Sem lane-kit instalado** — heurística mínima antes de editar arquivo compartilhado:
   - `git status --porcelain` — há trabalho não-commitado de outra sessão?
   - mtime do arquivo-alvo — mudou nos últimos {{janela_minutos}} minutos por outra fonte?
3. **Território exclusivo** (se declarado): `{{lista_de_paths_exclusivos_desta_lane}}` — fora
   disso, presuma compartilhado e confirme antes de editar.

## Recuperação — se algo foi sobrescrito/perdido

1. **Durabilidade primeiro**: `docs/_state-mirror/` (ou o `mirror_dir` deste projeto) guarda
   cópias dos arquivos gitignored críticos — `state_mirror.py` os regenera, não os garante
   originais perdidos, mas evita a perda TOTAL.
2. **Git é a rede real**: `git log --all --oneline -- <path>` acha versões anteriores mesmo
   de arquivo tracked sobrescrito.
3. **Handoff/ledger**: `.claude/handoff/HANDOFF-LEDGER.jsonl` tem o histórico de o que cada
   lane deixou — útil para reconstruir a timeline de quem tocou o quê.

## Gap conhecido (herdado, honesto)

Backup/isolamento cobre arquivos DENTRO do repo. Se a fonte-de-verdade vive fora dele (ex.:
uma VM, um banco de dados externo), este template NÃO cobre isso — declare explicitamente
o mecanismo de backup daquele sistema externo aqui: {{backup_externo_ou_gap_declarado}}.
