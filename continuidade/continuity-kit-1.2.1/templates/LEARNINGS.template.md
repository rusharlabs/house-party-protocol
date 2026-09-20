# LEARNINGS — {{project_name}}

> Lições CURADAS, com evidência-fonte OBRIGATÓRIA — diferente de um MEMORY.md em prosa
> livre. Cada entrada aqui foi promovida por um HUMANO a partir de um candidato (ver
> ponte com `instinct-pack`/ECC, se instalado: instinct captura candidatos automaticamente
> via hook; LEARNINGS é onde o humano os aceita como regra durável).

## Formato de entrada (obrigatório)

```
### {{data}} — {{titulo_da_licao}}
**Contexto:** {{o_que_aconteceu}}
**Evidência:** {{commit_ou_arquivo_ou_output_colado}}
**Regra destilada:** {{o_que_fazer_diferente_a_partir_de_agora}}
**Aplica quando:** {{condicao_de_gatilho}}
```

## Exemplo real (formato provado — genérico, sem dado de cliente)

### 2026-07-05 — verify de deploy precisa ser rota exclusiva, não gate de auth
**Contexto:** deploy declarado "no ar" após ver um 302 do gate de autenticação — idêntico
entre o backend antigo e o novo. O tunnel apontava pro alvo errado; o site seguiu servindo
a versão antiga por dias sem que ninguém percebesse.
**Evidência:** commit `abc1234` (fix do tunnel) + `curl` numa rota exclusiva do novo backend
mostrando o marker de build correto.
**Regra destilada:** verify de deploy = curl numa rota EXCLUSIVA do novo (com marca de build),
nunca só o gate de auth/status do processo. Confirmar cada hop de proxy/tunnel.
**Aplica quando:** qualquer deploy/rollback com proxy ou tunnel no caminho.

---

*(Entradas novas vão ACIMA desta linha, mais recente primeiro. Nunca editar entradas
existentes — se uma lição precisar de correção, adicione uma NOVA entrada referenciando
a antiga.)*
