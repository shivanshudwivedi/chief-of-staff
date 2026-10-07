#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -f frontend/dist/index.html ]; then
  printf '%s\n' 'Building the dashboard…'
  npm --prefix frontend ci
  npm run build
fi
exec uv run uvicorn backend.app:app --host 127.0.0.1 --port 8000
