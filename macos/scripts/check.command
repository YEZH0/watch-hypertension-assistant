#!/bin/zsh
set -eu
cd "$(dirname "$0")/.."
if command -v uv >/dev/null; then
  uv run --no-sync pytest -q
else
  python3 -m uv run --no-sync pytest -q
fi
cd ..
macos/.venv/bin/python -m pytest tests -q -o addopts=''
