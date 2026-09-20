# LEARNED-CORRECTIONS — regras destiladas de correções recorrentes

> **Auto-Trigger:** Antes de reportar números/contagens/status; quando o operador autoriza execução ampla (auto/goal/100%/máxima capacidade); antes de criar script novo ou marcar item como pendente/órfão.
> **Keywords:** "quantos", "contagem", "quantas", "status", "health", "métricas", "número", "stale", "onde estamos", "auto mode", "faça tudo", "faz tudo", "máxima capacidade", "100%", "goal", "criar script", "novo script", "pendente", "órfão", "nao implementado", "não implementado", "TODO", "falta"
> **Prioridade:** ALTA
> **Versão:** 1.0.0 (generalizada para o operator-kit)
> **Origem:** destilado de um workflow adversarial de correções recorrentes num projeto real — padrões que se repetiram em ≥3 sessões distintas, não-duplicatas de outras regras, e acionáveis.

---

## LC-1 · Auditar a fonte AO VIVO antes de citar QUALQUER número/métrica/status

Audite a fonte AO VIVO antes de citar qualquer número, métrica ou status — trate dados de
STATE.json, handoffs, docs, snapshots ou de outro agente como SUSPEITOS até confirmar.

Aplica-se a: contagens (arquivos, módulos, testes, hooks), health scores, deliverables,
status de item/tarefa, completude de plano/feature, **e deploy/routing** (verificar que o
BACKEND trocou — rota/conteúdo exclusivo do novo — NÃO só o gate de auth nem o status do
processo).

**Caso deploy/routing (lição real, generalizada):** declarar um deploy "no ar" só porque a
resposta HTTP de nível de rede (ex.: um redirect de autenticação) é idêntica ao backend
antigo é um erro comum — o proxy/tunnel pode estar apontando ainda para o build velho. **Verify
de deploy = curl numa rota EXCLUSIVA do novo + marca de build no backend real, não no gate.**
Cadeia de proxy/tunnel: confirme CADA hop, não assuma.

ANTES de reportar:
- Counts de filesystem: `grep`/`ls`/`find` no diretório real (não confie em "eu lembro que eram N").
- Status operacional/serviço: consulte o endpoint ou health-check real do seu `health.probes` (ver `health-kit` do marketplace, se instalado).
- Completude de plano/feature: `git log --grep` + checar arquivos no disco.

Se um número veio de sessão anterior, de outro agente, ou de doc com >1 semana: NÃO repita
como fato — re-verifique na fonte viva e, ao reportar, indique que é ao vivo.

**PORQUE:** relatar dado obsoleto como fato destrói a confiança do operador no que você diz —
isso já aconteceu dezenas de vezes num projeto real antes desta regra existir.

---

## LC-2 · Quando autorizado, executar de verdade — 100% em batch, sem enrolar

Quando o operador autorizar execução ampla (auto mode / "faça tudo" / "máxima capacidade" /
"100%" / um comando de goal), EXECUTAR a ação por completo e em batch — todo o escopo de uma
vez, NUNCA "1 por sessão", nunca parar em preparar/prometer/hedge. Uma instrução explícita de
"concluir tudo 100%" SOBREPÕE qualquer cadência sugerida em runbook. Atacar tudo que NÃO quebra
o sistema de forma autônoma; o que de fato depender do operador (teste manual de GUI, decisão,
acesso) vira doc/formulário objetivo — nunca desculpa para não agir. Manter profundidade e
qualidade técnica; reportar gaps reais ao final.

**PORQUE:** meias-execuções e preparação-sem-ação são a reclamação mais frequente de operadores
exigentes. Executar sem pedir confirmação (quando já autorizado) e sempre reportar gaps
remanescentes ao finalizar são o par que resolve isso.

---

## LC-3 · grep/ls ANTES de criar script novo OU marcar item como pendente/órfão

ANTES de criar qualquer script/ferramenta novo OU de marcar um item como pendente/órfão/
não-implementado: rodar grep + ls/Glob para confirmar que ele não existe já. Tratar
"pendente"/"órfão" como HIPÓTESE a refutar, não verdade. Comandos: grep do nome/feature no
código-fonte, nos scripts, nos hooks; grep por classificações anteriores em docs de plano
antes de reclassificar arquivos.

**PORQUE:** verificar evita retrabalho e duplicatas — um script "novo" que já existia desde
antes, ou um item "pendente" que já foi entregue, são erros de sessão anterior se repetindo.

---

*Destilado de correções recorrentes de operador. Aplica a qualquer LLM que use este kit.*
