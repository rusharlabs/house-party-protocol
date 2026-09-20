# REORIENT-MAILBOX — {{lane_id}}

> Gerado a partir do template do lane-kit. Substitua os `{{placeholders}}` — nunca deixe
> um `{{...}}` sem preencher no arquivo final. Este mailbox é a caixa de correio ASSÍNCRONA
> entre lanes (planejadora → executora, revisora → executora) quando o board sozinho não
> basta para transmitir contexto rico (ex.: uma reorientação de escopo no meio do trabalho).

## Para: {{lane_id_destino}}
## De: {{lane_id_origem}} ({{role_origem}})
## Quando: {{timestamp}}
## Item(ns) afetado(s): {{item_ids}}

### O que mudou
{{descricao_da_reorientacao}}

### Por quê
{{motivo}}

### O que a lane destino deve fazer
- [ ] {{acao_1}}
- [ ] {{acao_2}}

### Evidência/contexto
{{evidencia_ou_link}}

---
*Consumo: a lane destino LÊ este arquivo no próximo `lane_register.py` heartbeat/register
e marca como lido movendo para `.claude/lanes/mailbox/_read/{{filename}}` (convenção —
nunca editar in-place; mailbox é write-once, read-and-archive).*
