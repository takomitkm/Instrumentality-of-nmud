#!/bin/sh
# One click: the clipboard in, the nmud style out, back into the clipboard.
# Needs the environment that setup.sh creates.
HERE=$(cd "$(dirname "$0")" && pwd)
PY="$HERE/.venv/bin/python"

if [ ! -x "$PY" ]; then
    if command -v python3 >/dev/null 2>&1; then
        PY=python3
    elif command -v python >/dev/null 2>&1; then
        PY=python
    else
        echo "[nmud-style] no python here yet."
        echo "[nmud-style] run ./setup.sh once, it installs what is missing."
        exit 1
    fi
fi

cd "$HERE"
exec "$PY" -m nmud_style --clip "$@"
