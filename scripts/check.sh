#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv run python scripts/check_sensitive.py
uv run python scripts/check_sensitive.py --staged
uv run ruff check .
uv run python -m unittest discover -s tests -v
uv run aether --demo
uv run aether --demo --debug
