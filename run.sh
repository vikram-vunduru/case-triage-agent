#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Creating virtual env at .venv …"
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ""
  echo "Created .env from .env.example. Edit it to set ANTHROPIC_API_KEY before continuing."
  echo ""
  exit 1
fi

echo "Building Confluence KB index …"
python seed/build_index.py

echo ""
echo "Starting server at http://127.0.0.1:8000"
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
