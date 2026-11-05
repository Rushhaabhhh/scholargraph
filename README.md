# ScholarGraph

Offline research-expert discovery using public DBLP bibliographic data. The Python backend owns ingestion, identity resolution, the dated context graph, retrieval, ranking, grounded explanations and session memory. SQLite stores research data and sessions separately.

The Next.js/TypeScript application in `web/` connects to the Python API. It includes search and supported recency/year filters, sourced evidence, author profiles, an assistant, a shortlist/rejected list, and session-memory controls. It uses a local browser session because the API has no account system. The earlier static prototype is preserved in `resources/experiments/frozen-source-504ec1.zip`.

## Setup

Use Python 3.12 or newer. Keep `pyproject.toml` at the root: it is the standard package/build configuration. Pinned runtime, training and optional local-LLM dependencies are in `config/`.

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r config/requirements.lock
(cd web && npm ci)
```

Install `config/requirements-training.lock` when training or reproducing model experiments.

Dependency installation and the initial Docker image build may require network access. Inference, prepared tests, the batch command and the running API require no API key or network access.

## Run the required batch interface

```sh
./run --data resources/examples/sample.xml --queries resources/examples/queries.txt --out /tmp/hiresense-results.json
```

The command accepts another valid DBLP-style XML slice and a text file with one query per line. It creates an isolated temporary graph/index and writes ranked people, scores, explanations and sourced paper evidence as JSON. Scores are ranking values, not probabilities. The included 200-paper sample is a functional demonstration, not an accuracy benchmark.

## Run the application

For local development, start the API and frontend together:

```sh
./scripts/start-local.sh
```

Open `http://127.0.0.1:3017`. The command uses the existing prepared research graph and trained model when available; otherwise it prepares the bundled sample as a small functional demo. It waits for the API to become ready and stops both services with Ctrl+C. Set `SCHOLARGRAPH_BACKEND_PORT` or `SCHOLARGRAPH_WEB_PORT` if the defaults are occupied, or set `HIRESENSE_CONFIG` to use a different prepared backend. Install the Python and frontend dependencies from the setup instructions first.

Alternatively, with Docker:

```sh
docker compose up --build
```

The first start prepares the bundled sample graph. Open `http://localhost:3000` for the application. The API is available at `http://localhost:8000`; `GET /health` reports readiness and `GET /openapi.json` exposes its contract. Building images requires dependencies and base images; once prepared, the application runs offline without API keys. The small included sample is for functional testing, not a measure of ranking quality.

For frontend development, prepare the API as below, then run `cd web && npm ci && npm run dev`. Run `cd web && npm test` for component tests. With the API and frontend running, use `cd web && npm run test:e2e` for browser tests (install Playwright Chromium first with `npx playwright install chromium`, or set `CHROMIUM_PATH` to a compatible local executable).

For local Python development without Docker, use a new output directory:

```sh
PYTHONPATH=src .venv/bin/python -m hiresense.cli prepare-backend --data resources/examples/sample.xml --out data/processed/backend-demo-new
PYTHONPATH=src .venv/bin/python -m hiresense.cli serve --config data/processed/backend-demo-new/backend.json
```

## Results and reproducibility

See [results and measured limitations](resources/results/README.md), the [project journal](docs/project-journal.md), and the [training workbook](docs/model-training-workbook.md). The trained ranker's final held-out nDCG@10 and MRR were 0.0354 and 0.0488; these are weak future-authorship-proxy scores, not hiring accuracy. The recorded test has been inspected and must not be reused for model selection.

Current experiment inputs and results are in `resources/experiments/` and `resources/results/`. Earlier configurations and reports are in the respective `historical.zip` archives. Their contents are preserved as historical records, including their original paths and hashes.

Moving runtime assets required changes to Python source paths. **The previously frozen experiment binds the old exact package hash.** Its original source, scripts, configuration, recordings, sample, model JSON and prototype were captured before the move in `resources/experiments/frozen-source-504ec1.zip`. Reproduce that frozen run from the restored snapshot, with the matching raw DBLP and generated data artifacts; do not alter its freeze or claim the reorganized package has the old hash. Full raw-archive replay was not completed; a synthetic rebuild and 100 sampled source records were checked.

For an engineering replay of the same data and inspected test, use the original DBLP archive whose SHA-256 is recorded in `resources/experiments/lean-cohorts.json`, and fresh output paths:

```sh
PYTHONPATH=src .venv/bin/python scripts/rebuild_lean_data.py --archive data/raw/dblp.xml.gz --out data/processed/lean-rebuilt
PYTHONPATH=src .venv/bin/python scripts/train_lean.py --data data/processed/lean-rebuilt --work /tmp/lean-train --report /tmp/lean-validation.json --freeze /tmp/lean-freeze.json --model /tmp/lean-model.json
PYTHONPATH=src .venv/bin/python scripts/evaluate_lean.py --data data/processed/lean-rebuilt --freeze /tmp/lean-freeze.json --out /tmp/lean-final.json
```

These commands have not been replayed end to end on the full archive. Their fixed test is already inspected and is suitable only for reproduction or regression; use a new untouched test when making further model decisions.

## Layout

```text
config/          Pinned dependency files
contracts/       API, batch and tool schemas
resources/
  examples/      Small public DBLP sample and queries
  experiments/   Active configurations, frozen source snapshot and historical archive
  recordings/    Local query-understanding outputs and provenance
  results/       Current reports and historical archive
src/hiresense/   Python data, graph, retrieval, ranking, assistant and API code
scripts/         Preparation, training and verification entry points
tests/           Python tests and fixtures
models/          Local encoders and trained numeric models
web/             Next.js application, frontend tests and container configuration
docs/            Journal, design and assignment materials
data/            Ignored local raw and generated artifacts
run              Required offline batch command
```

The existing [design PDF](docs/design.pdf), [demo recording](docs/demo.mp4) and [AI-use statement](docs/ai-use-statement.md) describe the earlier prototype and need review/update for the new frontend. The demo uses synthetic narration. The repository contains no account authentication and is a local assignment demo.
