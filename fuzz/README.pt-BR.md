[English](README.md) · [Português](README.pt-BR.md)

# Fuzzing do contrato de política

O job Fuzzing compila o alvo Python com ClusterFuzzLite e executa Atheris/libFuzzer por 120
segundos nos pull requests e pushes para main. As etapas de build e fuzz precisam passar. A imagem do container
está fixada por digest e as ações por SHA de commit. As dependências de fuzzing ficam nessa
imagem; o pacote HPP mantém seu runtime em biblioteca padrão.

Cada entrada exercita a classificação com regras literais geradas, os dois níveis de ação e
elevações opcionais dos gates manuais básicos. O alvo verifica que a política customizada só
pode endurecer a básica, que classificações repetidas e round-trips JSON concordam, que os
campos do veredito são válidos, que audit sai zero e que a saída de enforce corresponde à ação.
A mesma entrada também passa como JSON adversarial pela validação de políticas. Rejeições
PolicyError esperadas são verificadas quanto ao determinismo; erros inesperados chegam ao
libFuzzer. As strings de comando são classificadas em memória. O alvo não as executa nem usa
a entrada como caminho de arquivo ou endereço de rede.

Regexes customizadas arbitrárias são compiladas no caminho de validação JSON. As buscas por
regex customizada usam padrões literais gerados, mantendo a campanha focada no contrato de
política. O desempenho do motor de regex em expressões arbitrárias fica fora deste alvo.

O corpus contém políticas válidas e rejeitadas e regressões de regex já corrigidas. Rode o
replay com mutações determinísticas a partir da raiz do produto, no Windows, macOS ou Linux:

```sh
python3 -B fuzz/check_corpus.py --mutations 2000
```

Esse comando verifica as propriedades sem um motor guiado por cobertura. A campanha nativa
Atheris roda em Linux na CI. O Atheris não oferece runtime Windows. A instrumentação dos imports
inclui o código de política do HPP.

Para um build Linux local, use a integração de build do ClusterFuzzLite com este repositório
como projeto externo. Os três arquivos de configuração estão em .clusterfuzzlite. O alvo
compilado é policy_fuzzer; suas opções limitam a entrada a 4096 bytes, cada caso a 5 segundos e
o RSS a 1024 MiB. O build gera corpus e dicionário junto do executável. O wrapper Python usa o
libFuzzer do Atheris sem preload de sanitizador nativo, conforme necessário para este alvo de
Python puro. Consulte a [integração de build Python](https://google.github.io/clusterfuzzlite/build-integration/python-lang/)
e a [documentação do Atheris](https://github.com/google/atheris).

Uma campanha limitada que passou mede os casos e a cobertura que executou. Preserve o log da
CI e qualquer entrada reproduzível ao investigar um achado.

