# Matriz de prova

Uma claim pública só entra aqui com reprodução.

| Claim | Comando | Critério |
|---|---|---|
| manifesto consistente | `python -m hpp doctor` | exit 0, dez módulos, zero erro |
| política bloqueia | `python -m hpp policy check --mode enforce --command "rm -rf src"` | exit 2 e `BLOCK` |
| grafos determinísticos | `python -m hpp graph --view operational --format json` duas vezes | hashes idênticos |
| eval standalone | `python -m hpp eval run examples/reliable-coding/benchmark-suite.json -k 3 --gate both` | nove controles executáveis, sem replay pré-aprovado |
| benchmark estável | `python -m hpp benchmark -k 3 --json` | pass^k 1.00 nos críticos |
| artefatos íntegros | `python instaladores/kit-forge-1.4.0/kit_doctor.py marketplace .` | status ok |

Resultados datados pertencem ao log da release, não a este documento vivo.
