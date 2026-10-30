#!/bin/bash
# Fallback launcher (Fase 0): the plain global-Azahar run, no sandbox.
# The per-game `.app` built by scripts/build_app_from_3ds.py is the real way:
# it isolates config, saves, shader cache and logs inside its own bundle.
set -euo pipefail
DIR="$( cd "$( dirname "$0" )" && pwd )"
ROM="$DIR/Legend of Zelda, The - A Link Between Worlds (USA) (En,Fr,Es).3ds"
[ -f "$ROM" ] || { echo "rom not found: $ROM" >&2; exit 1; }
exec /Applications/Azahar.app/Contents/MacOS/azahar -f "$ROM"
