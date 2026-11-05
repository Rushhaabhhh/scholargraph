#!/bin/sh
set -eu
config=/app/data/processed/app/backend.json
if [ ! -f "$config" ]; then
  python -m hiresense.cli prepare-backend --data /app/resources/examples/sample.xml --out /app/data/processed/app >/dev/null
fi
exec python -m hiresense.cli serve --config "$config" --host 0.0.0.0 --port 8000
