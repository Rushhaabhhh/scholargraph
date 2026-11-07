#!/bin/sh
set -eu
if [ -n "${HIRESENSE_CONFIG:-}" ]; then
  config=$HIRESENSE_CONFIG
  if [ ! -f "$config" ]; then
    echo "Configured backend index is missing: $config" >&2
    exit 1
  fi
else
  config=/app/data/processed/app/backend.json
  if [ ! -f "$config" ]; then
    echo "Preparing the bundled 200-paper sample; set HIRESENSE_CONFIG to serve a different index." >&2
    python -m hiresense.cli prepare-backend --data /app/resources/examples/sample.xml --out /app/data/processed/app >/dev/null
  fi
fi
echo "Starting backend with configuration: $config" >&2
exec python -m hiresense.cli serve --config "$config" --host 0.0.0.0 --port "${PORT:-8000}"
