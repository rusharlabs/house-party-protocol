[English](LOOPS.md) · [Português](LOOPS.pt-BR.md)

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

Para um critério end-to-end ou visual, a trava é o `hpp evidence run` (novo na
2.6.0): ele reexecuta o comando declarado, mede
o código de saída fora do modelo e faz hash dos artefatos que ficaram. O `hpp evidence verify` é
reconciliação posterior — re-deriva um registro a partir dos arquivos em disco — e nunca a trava: o
hash próprio do registro torna uma edição visível, não é uma assinatura, então quem não pode
confiar no maker roda o comando de novo. O hpp não dirige navegador; o navegador roda dentro do
comando que você declara.

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

Uma falha que não casa com nenhuma família fica `unknown` e nunca é reclassificada
automaticamente. Uma reclassificação consultiva via `hpp decide` (novo na 2.6.0) é offline:
uma pessoa a roda, nunca um hook, depois de medir o decisor com `hpp decide eval`; o registro
continua consultivo, e uma família nova só entra no classificador como mudança revisada.

## Avaliação

pass@k mede se o sistema consegue; pass^k mede se repete. O loop só trata release-critical como
estável quando o gate de regressão passa no universo e no `k` declarados.

A mesma regra vale para os instrumentos em que um loop se apoia. `hpp retrieval eval` mede um
retriever e `hpp decide eval` um decisor (ambos novos na 2.6.0), cada um em casos rotulados,
com falhas de instrumento — timeout, crash, resposta malformada — contadas à parte e nunca
pontuadas. Best-of-N, em que N lanes constroem alternativas e um revisor de outra lane e de outra
família de modelo escolhe uma (`lane_board.py compete` e `select`, novos na 2.6.0), é pass@N:
escolher 1 de N mede se o sistema consegue, não se repete, então o vencedor ainda precisa da
própria verificação e de pass^k.
