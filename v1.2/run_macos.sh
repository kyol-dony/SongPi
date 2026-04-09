#!/usr/bin/env bash
set -euo pipefail

# Launch SongPi on macOS using the virtual environment created by setup_macos.sh.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FILES_DIR="$SCRIPT_DIR/Files"
VENV_DIR="$FILES_DIR/venv"

if [ ! -d "$VENV_DIR" ]; then
  echo "Virtual environment not found at $VENV_DIR"
  echo "Run ./setup_macos.sh first."
  exit 1
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

cd "$FILES_DIR"
python3 shazam.py
