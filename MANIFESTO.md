# Manifesto House Party Protocol

## Agentes poderosos ainda precisam de uma casa operacional

House Party Protocol é um harness para operar agentes de código sob evidência. O modelo raciocina;
o harness delimita, observa, registra, verifica e decide quando o trabalho pode avançar.

Uma resposta convincente não é prova. Uma sessão ativa não é coordenação. Um processo online não
garante dado fresco. Um autor revisando o próprio trabalho não é revisão independente. HPP existe
para transformar essas diferenças em contratos executáveis.

## O protocol

O protocol é o conjunto compartilhado de invariantes:

1. estado declarado não substitui estado medido;
2. maker e checker são papéis diferentes;
3. conclusão exige critério, comando, saída e frescor;
4. trabalho concorrente declara lane, dono e território;
5. toda wave fecha sua barreira antes da próxima;
6. retomada deriva do event log, não da memória da conversa;
7. monitor separa disponibilidade, frescor e correção do dado;
8. política distingue aviso, bloqueio e gate humano;
9. capacidade e confiabilidade são medidas separadamente por pass@k e pass^k;
10. artefato distribuído é reaberto e verificado antes de ser chamado de release.

## O harness

O harness torna o protocol operável. Ele mantém um manifesto de capacidades, transforma uma spec
em WorkGraph, organiza dependências em waves, projeta Lane Map e Agent Map, compila contexto com
proveniência, registra eventos, produz retomada e conecta evidência a veredito.

Os módulos fornecem mecanismos especializados. A distribuição para Claude Code e Codex CLI leva
esses mecanismos aos hosts sem fingir que os dois oferecem os mesmos lifecycle hooks.

## Loops com freio e memória

Loop útil tem objetivo, observação, ação, budget, gate, condição de parada e escalonamento. Sem
esses elementos, repetição é apenas insistência automatizada.

Autoprompt preserva continuidade. Gotchas preservam aprendizado operacional. Monitores preservam
consciência de estado. Nenhum deles autoriza autonomia ilimitada: o próximo passo continua sujeito
à política, ao território, à evidência e ao gate humano quando necessário.

## Grafos sem teatro de infraestrutura

HPP usa grafos como modelos explicáveis, não como decoração e nem como desculpa para criar um
banco. Capability, agent, lane, work, execution, evidence e monitor maps são projeções
determinísticas de manifestos e eventos locais. Se uma aresta não muda uma decisão, ela não entra.

## Portabilidade honesta

Cross-host não significa identidade artificial. Claude Code pode executar hooks de lifecycle;
Codex CLI aplica várias capacidades por instrução ou comando explícito. O diagnóstico mostra essa
diferença. Cobertura ausente é `unsupported`, nunca “provavelmente funciona”.

## Prova antes de escala

O HPP não chama a si mesmo de confiável por possuir muitos componentes. Confiabilidade vem de
controles negativos, execução repetida, revisão independente e cadeia de publicação verificável.
Uma release crítica precisa demonstrar seu piso, não apenas o melhor resultado que conseguiu obter.

## O compromisso

Operar agentes sob evidência, preservar a separação de papéis, expor limites do host, tornar o
estado retomável e bloquear a conclusão que não atravessou o gate correspondente.

Essa é a casa. O protocol são as regras. Os módulos são as ferramentas. A prova é o que permite
abrir a próxima porta.
