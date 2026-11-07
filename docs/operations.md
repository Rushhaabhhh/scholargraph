# Operations and development

## Local development

Requires Python 3.12, `uv`, Node.js and npm. From the repository root:

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r config/requirements.lock -r config/requirements-llm.lock
(cd web && npm ci)
.venv/bin/python scripts/prepare_query_model.py
SCHOLARGRAPH_QUERY_PROVIDER=local_llm ./scripts/start-local.sh
```

Open http://127.0.0.1:3000. The launcher prepares the bundled sample if no prepared index is configured. Set `HIRESENSE_CONFIG` to a prepared backend configuration; `SCHOLARGRAPH_BACKEND_PORT` and `SCHOLARGRAPH_WEB_PORT` override the ports. Press Ctrl+C to stop both processes. The optional local model runtime needs CMake and a C++ compiler; model preparation downloads weights.

## Configuration and voice

Copy `.env.example` to `.env` only if optional settings are needed. `GEMINI_API_KEY` enables Gemini with the configured `SCHOLARGRAPH_CHAT_PROVIDER`; never commit it. A configured remote provider receives the messages and any retrieved excerpts supplied to it. `SCHOLARGRAPH_STT_PROVIDER=gemini` and `SCHOLARGRAPH_TTS_PROVIDER=gemini` also send audio and response text to that provider. The default offline options use the provisioned local model, Vosk and Piper/eSpeak. Browser microphone access requires localhost or HTTPS.

For local voice outside Docker:

```sh
uv pip install --python .venv/bin/python -r config/voice-requirements.lock
.venv/bin/python scripts/prepare_voice.py
.venv/bin/python -m piper.download_voices --data-dir data/models/piper en_US-ljspeech-medium
```

Compose settings are documented in `compose.yaml`. Image builds download models and packages; runtime works without API keys after provisioning. The reference application has no user authentication or tenant isolation.

## Deploying a prepared backend index

The graph and indexes under `data/` are not part of the image. Package an existing configuration with `python scripts/package_deployment_index.py --config /path/to/backend.json --out /tmp/scholargraph-index.tar`. Transfer it to the VM and extract it in a new empty, versioned directory on persistent storage. Mount that directory at `/var/data`, set `HIRESENSE_CONFIG=/var/data/backend.json` and `SCHOLARGRAPH_QUERY_PROVIDER=recorded`, then recreate the backend container. Keep the separate session database if it must survive a migration. Startup fails if an explicitly configured index is missing.

Set Vercel's server-side `HIRESENSE_API_URL` to the backend HTTPS origin, without `/api`, and redeploy the frontend. Verify both `/health` endpoints and an actual search. The deployment is a snapshot; refreshing DBLP requires rebuilding, packaging and switching the mounted index. Do not infer throughput or capacity from a smoke check.

## Design PDF

With Chromium installed, run `python3 scripts/render_design.py` from the repository root to render `docs/design.md` as `docs/design.pdf`. The page-break markers in the Markdown keep the submission at three pages.
