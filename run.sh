#!/bin/bash
# The native way: the per-game .app built by scripts/build_app_from_3ds.py —
# the runtime is the forked zakuro (Rust, code AOT-compiled by 3dsrecomp),
# and its sandbox sits beside the app (saves, settings, logs inside it).
# Builds the app when it is missing, then opens it.
set -euo pipefail
DIR="$( cd "$( dirname "$0" )" && pwd )"
ROM="$DIR/Legend of Zelda, The - A Link Between Worlds (USA) (En,Fr,Es).3ds"
[ -f "$ROM" ] || { echo "rom not found: $ROM" >&2; exit 1; }
APP="$DIR/The Legend of Zelda - A Link Between Worlds.app"
if [ ! -x "$APP/Contents/MacOS/ctr-native" ]; then
    python3 "$DIR/scripts/build_app_from_3ds.py" "$DIR"
fi
exec /usr/bin/open "$APP"
