#!/usr/bin/env bash
# Start the local API and frontend with the same backend address.
set -Eeuo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
python="$root/.venv/bin/python"
backend_port="${SCHOLARGRAPH_BACKEND_PORT:-8000}"
web_port="${SCHOLARGRAPH_WEB_PORT:-3000}"
if [[ "$backend_port" == "$web_port" ]]; then printf '%s\n' 'The frontend and backend need different ports.' >&2; exit 1; fi

if [[ ! -x "$python" ]]; then
  printf '%s\n' 'Python environment missing. Create .venv and install config/requirements.lock; see README.md.' >&2
  exit 1
fi
if ! "$python" -c 'import fastapi, uvicorn, numpy, onnxruntime, tokenizers' >/dev/null 2>&1; then
  printf '%s\n' 'Backend dependencies are missing. Install config/requirements.lock into .venv; see README.md.' >&2
  exit 1
fi
if ! command -v npm >/dev/null 2>&1 || [[ ! -x "$root/web/node_modules/.bin/next" ]]; then
  printf '%s\n' 'Frontend dependencies are missing. Run: cd web && npm ci' >&2
  exit 1
fi

if [[ -n "${HIRESENSE_CONFIG:-}" ]]; then
  config="$HIRESENSE_CONFIG"
elif [[ -f data/processed/recent-history/graph.sqlite3 && -f data/indexes/recent-history/manifest.json ]]; then
  config="$root/resources/experiments/backend.json"
else
  demo="$root/data/processed/local-demo"
  if [[ ! -f "$demo/backend.json" ]]; then
    if [[ -e "$demo" ]]; then
      printf 'Incomplete demo directory: %s. Choose a new output directory or remove it after inspection.\n' "$demo" >&2
      exit 1
    fi
    printf '%s\n' 'Preparing the bundled DBLP sample for a small functional demo...'
    PYTHONPATH="$root/src" "$python" -m hiresense.cli prepare-backend --data "$root/resources/examples/sample.xml" --out "$demo"
  fi
  config="$demo/backend.json"
fi
if [[ ! -f "$config" ]]; then printf 'Backend configuration not found: %s\n' "$config" >&2; exit 1; fi

"$python" - "$backend_port" "$web_port" <<'PY'
import socket, sys
for port in sys.argv[1:]:
    try:
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('127.0.0.1', int(port)))
    except (ValueError, OSError) as exc:
        raise SystemExit(f'Cannot use local port {port}: {exc}. Set SCHOLARGRAPH_BACKEND_PORT or SCHOLARGRAPH_WEB_PORT.')
PY

backend_pid=''
web_pid=''
cleanup(){
  [[ -z "$web_pid" ]] || kill "$web_pid" 2>/dev/null || true
  [[ -z "$backend_pid" ]] || kill "$backend_pid" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM
printf 'Starting research backend using %s\n' "$config"
PYTHONPATH="$root/src" "$python" "$root/scripts/run_local_backend.py" --config "$config" --host 127.0.0.1 --port "$backend_port" &
backend_pid=$!
for ((attempt=0; attempt<180; attempt++)); do
  if "$python" - "$backend_port" <<'PY' >/dev/null 2>&1
import sys, urllib.request
with urllib.request.urlopen(f'http://127.0.0.1:{sys.argv[1]}/health', timeout=1) as response:
    assert response.status == 200
PY
  then break; fi
  if ! kill -0 "$backend_pid" 2>/dev/null; then printf '%s\n' 'Backend failed to start; see the error above.' >&2; exit 1; fi
  if (( attempt == 179 )); then printf '%s\n' 'Backend did not become ready within three minutes.' >&2; exit 1; fi
  sleep 1
done
printf '\nScholarGraph: http://127.0.0.1:%s\nPress Ctrl+C to stop both services.\n\n' "$web_port"
cd "$root/web"
HIRESENSE_API_URL="http://127.0.0.1:$backend_port" SCHOLARGRAPH_NEXT_DIST_DIR=".next-local" "$root/web/node_modules/.bin/next" dev --hostname 127.0.0.1 --port "$web_port" &
web_pid=$!
wait "$web_pid"
