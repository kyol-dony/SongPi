#!/usr/bin/env bash
set -euo pipefail

# Bootstrap a virtual environment and install dependencies on macOS.
# This script mirrors the Windows setup flow but uses python3 + venv.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FILES_DIR="$SCRIPT_DIR/Files"
VENV_DIR="$FILES_DIR/venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "python3 is required but was not found. Install Python 3 (https://www.python.org/downloads/ or Homebrew) and try again."
  exit 1
fi

echo "Creating virtual environment at: $VENV_DIR"
"$PYTHON_BIN" -m venv "$VENV_DIR"

echo "Activating virtual environment and installing requirements..."
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

pip install --upgrade pip
pip install -r "$FILES_DIR/requirements.txt"

echo ""
echo "Setup complete."
echo "Start SongPi with: ./run_macos.sh"
