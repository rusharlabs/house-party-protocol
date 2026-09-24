[English](README.md) · [Português](README.pt-BR.md)

# Decisões tipadas — um conselheiro opcional que você declara e mede

O harness não chama modelo e não guarda chave ([MANIFESTO](../../MANIFESTO.pt-BR.md)). Isso não
muda aqui. Este diretório mostra como uma decisão tomada **fora** do harness — por um modelo de
decisão tipada hospedado, um modelo local, uma regra ou uma pessoa — entra nele como evidência
conferível:

| peça | onde | chama modelo? |
|---|---|---|
| o registro `hpp.decision/v1` | `hpp/decision.py` · `hpp decide validate` | não |
| a régua | `hpp decide eval` | não — roda o decisor que **você** nomeia, como comando |
| um baseline léxico | `baseline_decider.py` | não |
| um adaptador HTTP | `decide.py` | **sim**, só quando você o roda, com a sua chave |

`hpp init --decision-advisor typesafe|openrouter|compatible` registra qual conselheiro você
declarou e imprime estes passos. O padrão é `off`.

## Leia antes de enviar qualquer coisa

Antes de confiar em qualquer decisor hospedado, assuma isto até que as suas medições digam o contrário:

1. **Uma resposta válida pode estar errada.** O esquema só garante que a resposta é uma das suas
   opções, não que esteja certa.
2. **`confidence` é uma fórmula sobre a distribuição, não probabilidade de acerto**, e a calibração
   depende da pergunta. Calibre o limiar por pergunta, com os seus rótulos.
3. **O fornecedor não tem estado de abstenção.** A abstenção aqui é nossa: confiança baixa →
   `abstention`.
4. **O texto julgado não é tratado como hostil.** Instruções plantadas no texto julgado podem
   mudar a resposta. Passe `--declared <valor>` e o registro vira `raise-only`: o conselho pode elevar
   o valor que você declarou, nunca baixá-lo.
5. **Texto de shell pode ser recusado no caminho.** Um estado com comandos de shell como `curl` pode
   voltar como página de erro HTML em vez de JSON. Isso, timeout ou qualquer resposta não-JSON é `instrument-failure`.
6. **O idioma principal do fornecedor é o inglês.** Português e outros: meça antes.
7. **Nada é reproduzível perguntando de novo.** O registro guarda o modelo fixo que respondeu e o
   hash da resposta crua, gravada ao lado (`.hpp/decisions/raw/`).
8. **Toda chamada manda o texto para fora da sua máquina.** Nunca chame um conselheiro de um hook,
   nunca envie segredo (o adaptador recusa texto com cara de segredo) e leia os termos de dados do
   seu provedor. `hpp policy check` classifica rodar o `decide.py` como `MANUAL`, como `curl` para
   uma URL.

A versão 1 mede só perguntas de **escolha** (`choice`). Uma nota ou uma probabilidade de sim não
têm definição combinada de "certo", então o contrato recusa esses tipos em vez de reportar um 0%
vazio.

## Os três desfechos

| desfecho | significado |
|---|---|
| `recommendation` | um valor das suas opções, com a confiança que o decisor informou (ou null) |
| `abstention` | o decisor não quis escolher — não muda nada |
| `instrument-failure` | timeout, erro HTTP, HTML, resposta malformada — não muda nada, nunca é veredito |

Com `direction: raise-only` e um valor `declared`, `hpp decide validate` imprime o valor
**efetivo**: o maior dos dois nas opções ordenadas da pergunta.

## Meça antes de confiar

```bash
# the baseline every advisor has to beat
python -m hpp decide eval examples/typed-decisions/gotcha-family-suite.json \
  --decider-command '["python", "examples/typed-decisions/baseline_decider.py"]'

# your advisor, on the same cases (the key lives only in your shell)
export TYPESAFE_API_KEY=<your key>
python -m hpp decide eval examples/typed-decisions/gotcha-family-suite.json \
  --decider-command '["python", "examples/typed-decisions/decide.py", "--provider", "typesafe", "--model", "jev-1.13.0"]'
```

O relatório separa **cobertura** (quanto decidiu), **acerto seletivo** (quanto acertou quando
decidiu), **erros confiantes** (errado acima do limiar da suíte), abstenções corretas e perdidas,
falhas de instrumento, uma **curva de cobertura** nos limiares 0,5–0,9 quando há confiança, e Brier
só quando há probabilidades. Nenhuma decisão é reportada como sem amostra, nunca como 0%.

⚠️ **Sobre a suíte que vem junto.** São quinze mensagens sintéticas escritas à mão, e o baseline
léxico foi escrito junto com ela — o resultado dele ali é circular e prova só que a régua funciona.
Monte a sua suíte com casos rotulados seus antes de ler qualquer número como qualidade.

## Uma pergunta por vez

```bash
python examples/typed-decisions/decide.py --provider typesafe --model jev-1.13.0 \
  --question examples/typed-decisions/route-risk-question.json --state-file change.txt --declared low > decision.json
python -m hpp decide validate decision.json
```

Provedores: `typesafe` (`TYPESAFE_API_KEY`), `openrouter` (`OPENROUTER_API_KEY`, endpoint alpha),
`compatible` (`--endpoint`, para um servidor local ou próprio que fale o mesmo formato).
Aliases como `jev-latest` são recusados, inclusive quando o servidor responde sob um: fixe a versão
para o registro dizer quem respondeu. O adaptador faz uma tentativa e nunca repete; o timeout vale
para cada espera de socket, o corpo da resposta tem teto de 1 MiB, redirecionamentos são recusados
(a chave vai para um host só) e a chave só é enviada por https ou para um endereço de loopback.
