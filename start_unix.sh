#!/usr/bin/env bash
# One-click start for macOS / Linux.
set -e
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
    echo "Installing dependencies (this only happens once)..."
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

python run.py
