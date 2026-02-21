#!/bin/bash

# LaTeXGen Local Development Server
# Requires: Python 3.11+, LuaLaTeX (via MacTeX or TeX Live)

set -e

# Change to script directory
cd "$(dirname "$0")"

# Create data directories if they don't exist
mkdir -p data/styles data/fonts data/outputs

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

# Install/update dependencies
pip install -q -r requirements.txt

# Check for LuaLaTeX
if ! command -v lualatex &> /dev/null; then
    echo "WARNING: lualatex not found. Please install MacTeX or TeX Live."
    echo "  macOS: brew install --cask mactex"
    echo "  Or download from: https://www.tug.org/mactex/"
fi

# Run the server
echo "Starting LaTeXGen server at http://localhost:8000"
echo "Press Ctrl+C to stop"
echo ""
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
