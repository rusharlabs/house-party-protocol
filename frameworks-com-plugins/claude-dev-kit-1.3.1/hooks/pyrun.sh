#!/usr/bin/env bash
# pyrun.sh — resolve o interprete Python do PROJETO e roda o hook com ele.
#
# Why: hooks.json chamava `python` a seco. macOS e a maioria dos Linux so tem `python3`;
# Windows so tem `python` (e um `python3` que pode ser o stub da Microsoft Store, que abre a
# loja e sai com erro). Um hook que nao acha o interprete falha em TODA ferramenta, em
# silencio — o kit inteiro vira decoracao.
#
# Ordem: .venv do projeto (CLAUDE_PROJECT_DIR, senao o cwd — o Claude Code roda hooks na
# raiz do projeto) -> o binario certo para o SO -> o outro. Nunca `py`.
#
# Duas ressalvas:
#   · o .venv do projeto e executado com a confianca que voce da ao projeto aberto — o
#     mesmo que qualquer ferramenta que respeita venv faz. Para desligar: HPP_PYRUN_NO_VENV=1.
#   · no Windows sem Python, `command -v python` ACHA o alias de WindowsApps (o stub da
#     Store, que aponta para Microsoft.DesktopAppInstaller); ele e pulado pelo ALVO do
#     symlink — Python instalado pela Store/PythonManager tambem mora em WindowsApps e fica.
root="${CLAUDE_PROJECT_DIR:-$PWD}"
if [ -z "${HPP_PYRUN_NO_VENV:-}" ]; then
  for c in "$root/.venv/bin/python" "$root/.venv/Scripts/python.exe"; do
    [ -x "$c" ] && exec "$c" "$@"
  done
fi
case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*) ordem="python python3" ;;
  *)                    ordem="python3 python" ;;
esac
for c in $ordem; do
  bin="$(command -v "$c" 2>/dev/null || true)"
  [ -n "$bin" ] || continue
  # o alias de WindowsApps e' um symlink: Python de verdade aponta para PythonSoftwareFoundation.*;
  # o stub da Store aponta para Microsoft.DesktopAppInstaller_* (medido 2026-09-20). E' o alvo que decide.
  case "$(readlink -f "$bin" 2>/dev/null || echo "$bin")" in *DesktopAppInstaller*) continue ;; esac
  exec "$bin" "$@"
done
echo "pyrun.sh: nenhum interprete Python encontrado (python3/python) — hook nao rodou" >&2
exit 0   # WARN-only: um hook sem Python nao pode derrubar a ferramenta (REGRA #29)
