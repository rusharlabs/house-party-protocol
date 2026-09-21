[English](BENCHMARK.md) · [Português](BENCHMARK.pt-BR.md)

# Benchmark reproduzível

O benchmark público mede o harness local sem chamar APIs de modelo.

## Executar

```bash
python -m hpp doctor
python -m hpp benchmark -k 3
python -m hpp benchmark -k 3 --json
```

## Cenários

| Cenário | Controle positivo | Controle negativo | Gate |
|---|---|---|---|
| manifesto | dez módulos resolvidos | integração aponta módulo ausente | validação bloqueia |
| política | comando seguro | operação destrutiva | enforce retorna 2 |
| event log | sequência válida chega a verified | verified sem evidência | append é recusado sem criar log |
| WorkGraph | DAG com duas waves | ciclo A→B→A | compilação falha |
| Lane Map | lane morta não bloqueia | sobreposição viva | colisão aparece |
| Monitor Map | sinal fresco | serviço online/dado stale | dimensões separadas |
| contexto | fonte com hash e orçamento | material semelhante a segredo | compilação recusa |
| roteamento | trabalho seguro usa economy | alto risco sem frontier | não rebaixa o piso |
| grafos | mesma entrada duas vezes | projeção vazia | JSON idêntico e não vazio |

## Critério

O benchmark executa cada controle local `k=3`; não usa outcomes replayados como verdade pronta.
Casos release-critical exigem `pass^k=1.00`. A saída JSON inclui versão, plataforma, hash da
suite, tentativas e resultado individual. Integridade dos ZIPs é um gate separado da release.

O benchmark prova somente o checkout, a plataforma e os cenários executados. Não mede qualidade
geral de um modelo e não transforma um host sem lifecycle hook em enforcement automático.
