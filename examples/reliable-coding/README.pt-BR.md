[English](README.md) · [Português](README.pt-BR.md)

# Exemplo de codificação confiável

Esta fixture é um benchmark determinístico e offline para o harness. Os nove
controles dela executam mecanismos reais do HPP com casos positivos e negativos;
eles não reproduzem resultados pré-aprovados. Um resultado que passa prova apenas
esses controles declarados, não a qualidade de um modelo nem a saúde de um serviço
remoto.

```text
python -m hpp benchmark -k 3 --json
python -m hpp event append --type work_started
python -m hpp resume
```

A sequência de eventos é estrita de propósito: trabalho, evidência, checagem
read-only, gate humano e então verificação. Um evento registrado é a fronteira de
recuperação; nenhum processo em segundo plano é necessário.
