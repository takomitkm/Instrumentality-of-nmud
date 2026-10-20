#!/bin/sh
# Find a python, then let setup_env.py check this device and install
# whatever the generator is missing.
HERE=$(cd "$(dirname "$0")" && pwd)
SCRIPT="$HERE/setup_env.py"

for PY in python3 python; do
    if command -v "$PY" >/dev/null 2>&1; then
        exec "$PY" "$SCRIPT" "$@"
    fi
done

echo "[setup] no python found. Install Python 3.9 or newer, then run this again."
exit 1
