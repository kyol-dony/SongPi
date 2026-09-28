#!/usr/bin/env bash
set -euo pipefail

# Bootstrap a virtual environment and install dependencies on macOS.
# This script mirrors the Windows setup flow but uses python3 + venv.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FILES_DIR="$SCRIPT_DIR/Files"
VENV_DIR="$FILES_DIR/venv"
PYTHON_BIN="${PYTHON_BIN:-}"

resolve_python_bin() {
  local candidate
  for candidate in "$@"; do
    if [[ -z "$candidate" ]]; then
      continue
    fi
    if [[ "$candidate" == */* ]]; then
      if [[ -x "$candidate" ]]; then
        printf '%s\n' "$candidate"
        return 0
      fi
      continue
    fi
    if command -v "$candidate" >/dev/null 2>&1; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

if [[ -n "$PYTHON_BIN" ]]; then
  RESOLVED_PYTHON_BIN="$(resolve_python_bin "$PYTHON_BIN")" || {
    echo "Requested PYTHON_BIN '$PYTHON_BIN' was not found."
    exit 1
  }
else
  RESOLVED_PYTHON_BIN="$(resolve_python_bin python3.12 python3)" || {
    echo "Python 3.12 is required but was not found. Install Python 3.12 (https://www.python.org/downloads/ or Homebrew) and try again."
    exit 1
  }
fi

PYTHON_VERSION="$("$RESOLVED_PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "$PYTHON_VERSION" != "3.12" ]]; then
  echo "SongPi macOS setup currently requires Python 3.12."
  echo "Resolved interpreter: $RESOLVED_PYTHON_BIN ($PYTHON_VERSION)"
  echo "Install Python 3.12 or rerun with PYTHON_BIN pointing to it."
  exit 1
fi

if [[ -x "$VENV_DIR/bin/python" ]]; then
  EXISTING_VENV_VERSION="$("$VENV_DIR/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" || EXISTING_VENV_VERSION="unknown"
  if [[ "$EXISTING_VENV_VERSION" != "3.12" ]]; then
    echo "Existing virtual environment uses Python $EXISTING_VENV_VERSION."
    echo "Remove $VENV_DIR and rerun setup so it can be recreated with Python 3.12."
    exit 1
  fi
fi

echo "Using Python: $RESOLVED_PYTHON_BIN ($PYTHON_VERSION)"

echo "Creating virtual environment at: $VENV_DIR"
"$RESOLVED_PYTHON_BIN" -m venv "$VENV_DIR"

echo "Activating virtual environment and installing requirements..."
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_PYTHON -m pip"

$VENV_PIP install --upgrade pip setuptools wheel

echo "Installing numpy wheel explicitly to avoid accidental source builds..."
$VENV_PIP install --only-binary=:all: numpy==2.1.2

echo "Installing remaining requirements..."
$VENV_PIP install --prefer-binary -r "$FILES_DIR/requirements.txt"

echo ""
echo "Setup complete."
echo "Start SongPi with: ./run_macos.sh"
