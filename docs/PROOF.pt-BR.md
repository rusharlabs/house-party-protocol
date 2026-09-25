[English](PROOF.md) · [Português](PROOF.pt-BR.md)

# Matriz de prova

Uma claim pública só entra aqui com reprodução.

| Claim | Comando | Critério |
|---|---|---|
| manifesto consistente | `python -m hpp doctor` | exit 0, dez módulos, zero erro |
| política bloqueia | `python -m hpp policy check --mode enforce --command "rm -rf src"` | exit 2 e `BLOCK` |
| grafos determinísticos | `python -m hpp graph --view operational --format json` duas vezes | hashes idênticos |
| eval standalone | `python -m hpp eval run examples/reliable-coding/benchmark-suite.json -k 3 --gate both` | dez controles executáveis, sem replay pré-aprovado |
| benchmark estável | `python -m hpp benchmark -k 3 --json` | pass^k 1.00 nos críticos |
| régua de decisão | `python -m hpp decide eval examples/typed-decisions/gotcha-family-suite.json --decider-command '["python", "examples/typed-decisions/baseline_decider.py"]'` | zero falhas de instrumento; cobertura e acerto seletivo reportados à parte (a suíte que vem junto prova a régua, não um decisor) |
| pacote de evidência | `python -m hpp evidence run --id smoke-page --artifact out/report.html --artifact out/smoke.log -- python examples/evidence/smoke_page.py`, depois `python -m hpp evidence verify <record>` | exit 0 `passed`, depois exit 0 `valid` |
| pacote de evidência, controle | a mesma execução com `--break` depois do script; depois um registro que passou cujo `out/report.html` foi alterado em seguida | exit 1 `failed`, e `verify` exit 1 `not-evidence`; o artefato alterado faz o `verify` sair 2 `blocked` |
| régua de recuperação | `python -m hpp retrieval eval examples/retrieval/suite.json --retriever-command '["python", "examples/retrieval/keyword_retriever.py"]'` | sete casos medidos, zero falhas de instrumento, as mesmas métricas do replay sem `--retriever-command`; exit 1 no gate padrão (a suíte que vem junto prova a régua, não um recuperador) |
| régua de recuperação, controle | `python -m hpp retrieval eval examples/retrieval/suite.json --retriever-command '["python", "-c", "import sys; sys.exit(3)"]'` | exit 1, sete falhas de instrumento, métricas nulas, nunca 0% |
| checagem de citação | `python -m hpp cite check --text examples/citations/answer.md --context examples/citations/context.json` | exit 0, veredito `ok` |
| checagem de citação, controle | a mesma numa cópia de `answer.md` com `[ID:glossary]` trocado por `[ID:glossary-v2]` | exit 2, `UNKNOWN_ID` |
| sensibilidade do critério | `python -m hpp evidence mutate --id weak --generate examples/criterion-sensitivity/discount.py -- python examples/criterion-sensitivity/check_weak.py` | exit 1, `blind-spots`, três sobreviventes nomeados por arquivo e linha |
| sensibilidade do critério, controle | o mesmo com `check_strong.py` | exit 0, `sensitive`, score 1.0 |
| House Session | `python -m hpp decide eval examples/typed-decisions/gotcha-family-suite.json --decider-command '["python", "examples/house-session/panel_decider.py"]'` | 15 sessões gravadas, seladas e verificadas, 12 decididas, 3 abstenções, 0 falhas de instrumento, exit 0 (sessões sintéticas: provam o contrato, não que um painel é melhor) |
| House Session, controle | `python -m hpp deliberate verify` numa cópia de um registro selado com o veredito editado | exit 2, `record_sha256 does not match` |
| seleção best-of-N | `python multi-session/lane-kit-1.4.1/scripts/lane_board.py --self-test` | exit 0; o bloco de competições passa em toda checagem |
| seleção best-of-N, controle | `lane_board.py select` numa competição declarada, por um revisor da mesma família de modelo de um construtor | exit 1, `SAME model family`; nenhum vencedor registrado |
| artefatos íntegros | `python installers/kit-forge-1.4.2/kit_doctor.py marketplace .` | status ok |

Resultados datados pertencem ao log da release, não a este documento vivo.
