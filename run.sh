#!/bin/bash

# LaTeXGen Local Development Server
# Requires: Python 3.11+, LuaLaTeX (via MacTeX or TeX Live)

set -euo pipefail

# Change to script directory
cd "$(dirname "$0")"

VENV_DIR="${VENV_DIR:-.venv}"
FALLBACK_VENV_DIR="${FALLBACK_VENV_DIR:-data/.venv}"
PYTHON_BIN="${PYTHON:-python3}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
RELOAD_DIR="${RELOAD_DIR:-app}"

create_venv() {
    echo "Creating virtual environment with $PYTHON_BIN..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
}

venv_works() {
    [ -x "$VENV_DIR/bin/python" ] && "$VENV_DIR/bin/python" -c 'import pip' >/dev/null 2>&1
}

prepare_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        create_venv
        return
    fi

    if venv_works; then
        return
    fi

    if [ "$VENV_DIR" != "$FALLBACK_VENV_DIR" ] && [ -d "$FALLBACK_VENV_DIR" ]; then
        primary_venv="$VENV_DIR"
        VENV_DIR="$FALLBACK_VENV_DIR"
        if venv_works; then
            echo "Existing virtual environment at $primary_venv is broken; using fallback at $VENV_DIR"
            return
        fi
        VENV_DIR="$primary_venv"
    fi

    backup="${VENV_DIR}.broken.$(date +%Y%m%d%H%M%S)"
    echo "Existing virtual environment is broken; moving it to $backup"
    if mv "$VENV_DIR" "$backup"; then
        create_venv
        return
    fi

    echo "WARNING: Could not move broken virtual environment at $VENV_DIR."
    return 1
}

# Create data directories if they don't exist
mkdir -p data/styles data/fonts data/outputs

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "ERROR: $PYTHON_BIN not found. Install Python 3.11+ or set PYTHON=/path/to/python3."
    exit 1
fi

# Check if virtual environment exists and can run pip.
if ! prepare_venv; then
    if [ "$VENV_DIR" = "$FALLBACK_VENV_DIR" ]; then
        echo "ERROR: Could not prepare virtual environment at $VENV_DIR."
        exit 1
    fi

    echo "Using fallback virtual environment at $FALLBACK_VENV_DIR"
    VENV_DIR="$FALLBACK_VENV_DIR"
    prepare_venv
fi

# Install/update dependencies
"$VENV_DIR/bin/python" -m pip install -q -r requirements.txt

# Check for LuaLaTeX
if ! command -v lualatex &> /dev/null; then
    echo "WARNING: lualatex not found. Please install MacTeX or TeX Live."
    echo "  macOS: brew install --cask mactex"
    echo "  Or download from: https://www.tug.org/mactex/"
fi

# Run the server
echo "Starting LaTeXGen server at http://localhost:$PORT"
echo "Press Ctrl+C to stop"
echo ""
"$VENV_DIR/bin/python" -m uvicorn app.main:app --reload --reload-dir "$RELOAD_DIR" --host "$HOST" --port "$PORT"
