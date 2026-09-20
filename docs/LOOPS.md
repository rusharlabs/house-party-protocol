# Loops, autoprompt e waves

## Loop governado

Um loop HPP possui:

1. objetivo e spec;
2. estado observável;
3. próxima ação;
4. budget de tempo/iterações;
5. gate de evidência;
6. stop conditions;
7. escalonamento humano;
8. feedback persistido.

`ralph_gate.py` implementa o stop gate: uma marca textual de conclusão não libera o loop sem que
o `done_gate` correspondente passe. `autoprompt_resume.py` produz retomada; não altera o veredito.

## Autoloop e LoopGraph

Autoloop é o ciclo finito `observe → choose → act → verify → record → stop/continue`. No HPP ele
não significa autonomia sem teto. O `loop` de `hpp.manifest.json` é o LoopGraph mínimo: estados,
eventos, gates e transições permitidas. Repetição intencional fica no charter com budget e saída;
ciclo acidental no WorkGraph é erro.

## Spec-driven

A spec é compilada em WorkGraph. Acceptance criteria viajam com cada unidade. Dependências viram
waves topológicas e cada wave fecha testes e review antes de liberar a próxima.

## Autoprompt

Autoprompt responde “qual é o próximo passo derivável do estado?”. Ele não decide risco, não
aprova mudança sensível e não substitui checker. Se o estado é insuficiente, a saída correta é
declarar o dado faltante.

## Memória de falhas

Gotcha Memory classifica falhas, mede recorrência e propõe uma lição. A promoção é controlada para
evitar transformar um incidente isolado ou ambíguo em regra permanente.

## Avaliação

pass@k mede se o sistema consegue; pass^k mede se repete. O loop só trata release-critical como
estável quando o gate de regressão passa no universo e no `k` declarados.
