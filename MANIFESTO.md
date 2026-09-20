# Manifesto

> *Nada sai sem uma segunda medição.*

House Party Protocol é um conjunto de kits para quem parou de conversar com um agente e passou
a **operar** vários. Ele não existe para fazer o agente ir mais rápido. Existe para que, quando
o agente disser "pronto", a palavra valha alguma coisa.

Oito princípios atravessam os dez kits. Cada um nasceu de uma falha real, e cada um tem pelo
menos um gate que o impõe — porque princípio sem gate é intenção, e intenção não sobrevive à
terceira sessão em paralelo.

---

## 1 · O revisor não tem caneta

Quem constrói não aprova. Quem aprova roda em **outro modelo** e recebe um conjunto de
ferramentas **sem `Write` nem `Edit`**. Isto não é uma instrução no prompt — é a ausência
física da ferramenta. Um revisor que pode editar "conserta e segue", e o defeito de processo
que produziu o erro nunca aparece.

## 2 · A régua vai ao lado do número

Nenhum número é publicado sem o comando que o produziu. "18 testes passando" sem o comando é
uma afirmação sobre a memória de alguém. Com o comando, é uma afirmação sobre o repositório —
e qualquer pessoa pode refazê-la amanhã.

## 3 · O controle vem antes do veredito

Antes de declarar algo morto, zero ou ausente, aponte o mesmo instrumento para um caso que
você **sabe** estar vivo. Se ele também disser "morto", o instrumento não discrimina, e o
veredito não vale. Um `grep` que aborta devolve zero com a mesma cara de um `grep` que não
achou nada.

## 4 · O gate prova que sabe reprovar

Todo gate nasce com um teste que o força a falhar sobre o caso que ele existe para barrar.
Um teste que só exercita o caminho feliz não distingue "gate funcionando" de "gate ausente":
os dois passam igual.

## 5 · Parcial se declara, nunca se disfarça

Existem três estados, não dois: **feito**, **parcial declarado** e **não feito**. O parcial
declarado é a saída honesta — "não terminei, e este é o buraco". O único estado proibido é o
parcial silencioso, aquele em que o verde esconde o que faltou.

## 6 · A falha vira lição, ou vira rotina

Um comando que falha uma vez é um acidente. O mesmo comando falhando três vezes é um padrão —
e um padrão que ninguém registrou vai se repetir na próxima sessão, com a mesma surpresa. A
lição se grava, se classifica e se injeta **antes** da próxima tentativa.

## 7 · O que viaja é o que foi provado

O diretório é o que foi montado; o zip é o que viaja. São dois artefatos, e os dois precisam
de régua. Um kit só sai da forja depois que o artefato distribuído — não a cópia local — foi
reaberto, conferido byte a byte e lintado contra o que nunca pode sair de casa.

## 8 · O humano decide o que só o humano decide

Há uma classe de ação que nenhum nível de autonomia destrava: apagar dado, tocar credencial,
mover dinheiro, falar com cliente, agir em conta de terceiro. Um agente pode preparar,
recomendar e executar o reversível. O irreversível para e pergunta — e o `--human-approved`
é literal.

---

## Sobre quem faz

House Party Protocol é um projeto da **Rushar Labs**, o braço de engenharia de agentes da
[Rushar](https://rushar.com.br).

A Rushar Labs se organiza em quatro dimensões conectadas:

**Ideias** — a investigação, o território das possibilidades: o que ainda não existe e o que
pode existir. É onde este projeto começou, como uma lista de falhas que ninguém tinha
nomeado.

**Sistemas** — a transformação do conhecimento em algo que funciona. Regra vira gate, gate
vira kit, kit vira produto. Se não roda, não é sistema.

**Pessoas** — quem constrói, colabora e usa. Um kit é escrito para o operador que vai
instalá-lo às 2h da manhã com um deploy na fila; a documentação existe para essa pessoa.

**Impacto** — a mudança que acontece. Não o que foi entregue, mas o que ficou diferente depois
da entrega. Um agente que passa a dizer "não terminei" é impacto; um relatório dizendo que
ele terminou não é.

*Construindo o que vem depois.*
