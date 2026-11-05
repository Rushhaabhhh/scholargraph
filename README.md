# HireSense.ai

Offline research-expert discovery over public DBLP data (CC0). Python owns ingestion, identity resolution, the context graph, retrieval, ranking, and evaluation. SQLite is the system of record. FastAPI exposes the backend; the React/TypeScript client will communicate only through that API. Its generated contract is in `contracts/api.openapi.json`.

## Prepare the environment

Use Python 3.12+ on Linux or macOS. With uv installed, from the repository root:

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.lock
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
./run --data examples/sample.xml --queries examples/queries.txt --out result.json
```

Dependency installation is an explicit preparation step. Runtime, model inference, batch commands, and tests require no network access or API keys. The pinned quantized MiniLM model, tokenizer, license, checksums, and trained JSON reranker are bundled under `models/`; no model download occurs at startup. `./run` selects the project virtual environment when the calling Python lacks the dependencies.

The batch command works from any directory and creates an isolated temporary database and index. It runs hybrid retrieval and the trained reranker, returning scores, explanations, and paper/year/source/collaborator evidence. Scores are ranking values, not calibrated probabilities. Unknown publication years remain null. A new input slice is indexed independently and uses the same trained model without retraining or applying the development-data cutoff.

## Run the backend

The bundled `examples/sample.xml` contains 200 real DBLP papers from DAC and IGARSS, selected across 2010–2025 for neural networks, learning and classification. Four matching queries are in `examples/queries.txt`. Source checksums, selection rules and counts are in `examples/manifest.json`; the sample is intended for quick functional testing, not representative evaluation.

Prepare a serving graph and index from this sample, then start the API:

```sh
PYTHONPATH=src .venv/bin/python -m hiresense.cli prepare-backend --data examples/sample.xml --out data/processed/backend-demo
PYTHONPATH=src .venv/bin/python -m hiresense.cli serve --config data/processed/backend-demo/backend.json
```

Use a new preparation directory when rerunning the first command. The preparation command reuses streaming ingestion, stable IDs, historical snapshots, graph audits and the trained model. It removes its all-period source intermediate and writes a portable backend configuration. `--cutoff-year` optionally restricts the serving snapshot. No model training or network request occurs.

The API binds to `127.0.0.1:8000`. `GET /health` reports readiness. `GET /openapi.json` serves the schema locally; API documentation pages that fetch CDN assets are disabled. `contracts/api.openapi.json` and `contracts/tools.schema.json` mirror the executable routes and tool validators. The optional `HIRESENSE_CONFIG` environment variable selects a configuration when `serve --config` is omitted.

To serve the larger prepared historical graph, use:

```sh
PYTHONPATH=src .venv/bin/python -m hiresense.cli serve --config experiments/backend.json
```

The research graph and lexical index open read-only. A lock serializes shared model/SQLite operations in this local worker. Sessions use a separate SQLite file, bound to the graph-content signature. Startup checks graph relationships, index/encoder checksums and model compatibility. This worker configuration is not a measured production throughput design.

## Search, conversations and memory

`POST /search` accepts `query`, optional `limit`, `recency_preference` (`any` or `recent`), and `since_year`. Its response includes parsed intent, provider/fallback information, effective date filters, ranked people, source evidence, and verified claims. Date preferences use the displayed graph cutoff; recent defaults to its last five years. Explicit past/last N years are resolved against the same cutoff.

Create a session with `POST /sessions`. It returns `session_id` and a memory snapshot with `version`. Session-backed searches also send `session_id`, `expected_version` and `request_id`; they save the result references used by subsequent assistant turns. Stateless searches keep no conversation memory.

Send turns to `POST /sessions/{session_id}/messages`, for example:

```json
{"message":"search graph neural networks","expected_version":0,"request_id":"example-search-0001"}
```

Use the returned memory version for the next request. Supported controls include `profile #1`, `shortlist #1`, `reject #1`, `show shortlist`, `search again`, `make it more recent`, `any year`, `path #1 #2`, and `clear memory`. Profiles and paths also accept explicit person IDs. A quoted string following `search` remains query data, even if it resembles a command. Other free text starts a research search. The bounded command grammar is deliberate; this is not an unrestricted autonomous planner.

The assistant calls three strictly validated graph tools: `search_experts`, `get_profile`, and `find_collaboration_path`. Tool calls, arguments, outcomes, applied decisions and memory snapshots are returned to the client. Rejected people are excluded before the result limit; shortlisted people are marked and can be inspected. Preferences and the last query support refinement.

Memory operations are also available through:

- `GET /sessions/{session_id}/memory`
- `PUT /sessions/{session_id}/decisions/{person_id}` with `decision`, `expected_version`, `request_id`
- `DELETE /sessions/{session_id}/memory` with `expected_version`, `request_id`
- `DELETE /sessions/{session_id}` to remove the whole session

Retries must reuse the same request ID and exact body. Cached responses prevent duplicate mutations after a lost response. Changed inputs with a reused ID or stale revisions return HTTP 409. A failed transaction rolls back decisions and its retry record together. Full memory deletion clears decisions, search context and prior cached turns; session deletion removes the remaining session record. Request logs exclude queries and session IDs. Session IDs are opaque capabilities for this local demo; account authentication is not implemented.

## Applied AI and grounding

Query understanding has a provider interface. The default replays exact-query outputs genuinely recorded from a local Qwen model. Unknown queries, unavailable providers, malformed JSON, invented date constraints, lost topics and instruction-like outputs use a deterministic offline fallback. Responses expose which path ran. Raw recordings and model/prompt provenance are in `recordings/`; replay coverage is finite and is measured separately from end-to-end task success.

The LLM receives only the research query. It never receives paper titles, graph-tool outputs, session decisions or tool authority. Server routing chooses operations from explicit user intent. A closed registry validates every tool argument, and source data is never parsed as a new command. Instruction-pattern checks provide another layer; the trust boundary does not depend on recognizing every attack phrase. Conservative checks can reject instruction-like research text, and fallback parsing has a bounded phrase vocabulary.

Explanations use typed authorship, coauthorship and normalized title-term facts. Each claim is checked against the authoritative paper/relationship, its year, and canonical wording. A real citation does not validate an added unsupported assertion. Unsupported claims carry `supported: false` and a reason and are excluded from explanation prose. Source text remains literal quoted data, with warnings for instruction-like titles. This verifies constrained factual claims, not arbitrary generated prose or the objective quality of an expert. The batch interface uses the same query-understanding and grounding components.

Reproduce the HTTP conversation, grounding and injection measurements on the prepared full graph:

```sh
PYTHONPATH=src .venv/bin/python -m hiresense.cli assistant-benchmark --config experiments/backend.json --out results/phase4.json
PYTHONPATH=src .venv/bin/python scripts/run_backend_tests.py --out results/backend-tests.json
PYTHONPATH=src .venv/bin/python scripts/check_backend.py --config data/processed/backend-demo/backend.json --out results/backend-smoke.json
PYTHONPATH=src .venv/bin/python scripts/check_clean_copy.py --out results/backend-clean-copy.json
```

Reports refuse to overwrite existing files. Use new report paths for repeats. The scenario file declares ten multi-turn cases and their expected tools/outcomes. Results include task success, claim support, fabricated-claim rejection, scripted injection resistance, provider fallbacks, real recording quality and HTTP turn latency. The suite also tests poisoned source titles, malicious provider outputs, persistence, isolation, concurrent updates, rollbacks and contract drift. The live-server check owns a loopback process and stops it after checking search, profile, collaboration, decisions, retries and deletion.

## Optional live local LLM

The larger query LLM is an optional preparation artifact under ignored `data/models/`, not part of the under-100-MB bundled models and not required for default serving or tests. To reproduce its genuine recordings on a supported CPU-wheel environment:

```sh
uv pip install --python .venv/bin/python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu --index-strategy unsafe-best-match --only-binary llama-cpp-python -r requirements-llm.lock
.venv/bin/python scripts/prepare_query_model.py
PYTHONPATH=src .venv/bin/python scripts/record_query_intents.py --model data/models/query-understanding.gguf
```

These explicit preparation commands may use the network; inference does not. The pinned revision, model hash and license reference are in `recordings/local-model.json`. Recordings retain unedited outputs, including model errors. The evaluator reports schema validity separately from the stronger topic/date checks. No hosted API is used and API spend is zero.

To use live local extraction, copy a backend configuration, set `query_provider` to `local_llm`, and supply `local_model` and `local_model_sha256` from that metadata. Configuration paths resolve relative to the configuration file. The provider bounds generation, uses schema-constrained decoding and clears conversational KV state between queries. It has no tools or session context. A missing optional model or failed call falls back without disabling research search.

## Reproduce the data experiment

Place the local DBLP archive and its matching checksum at `data/raw/dblp.xml.gz` and `data/raw/dblp.xml.gz.md5`:

```sh
PYTHONPATH=src .venv/bin/python -m hiresense.cli benchmark --config experiments/development.json --out data/processed/phase1 --report results/data-benchmark.json
```

The configuration fixes source selection, year boundaries, and the noise seed. The command verifies the source checksum, creates 50,000 authored, dated papers, measures ingestion, checks repeated ingestion, reproduces temporal datasets, and reproduces noisy observations. Existing data-experiment output/report paths are rejected. Use new paths for another run.

The slice selects the first matching records in source order. It is not a representative random sample. The parser supports DBLP publication types, XML/gzip, nested titles, encodings and named entities without fetching a DTD. Missing-key/title metadata records are counted and skipped. Missing years are excluded from temporal datasets. Malformed XML and invalid years roll back ingestion atomically with a failed audit record. Reingestion updates corrected relationships and invalidates derived edges and identity matches.

The prepared dataset contains a historical `graph.sqlite3`, separate `train_ground_truth.jsonl`, `validation_ground_truth.jsonl`, `test_ground_truth.jsonl`, and a hash/configuration/coverage manifest. All label periods are strictly later than the same frozen graph. Repeated normalized titles are excluded from labels across the dataset. Future-paper titles are queries and their authors are relevance labels. These labels measure future authorship as a proxy for expertise; they do not establish objective suitability. Authors without historical evidence remain in evaluation denominators.

Author IDs are deterministic and fit JavaScript's exact integer range. Identity uses a supplied DBLP PID or the complete disambiguated DBLP label, including its numeric suffix. Collisions fail rather than merging identities. PID availability must be consistent to join renamed labels. Snapshot names come from historical observations. Noise samples authorship observations with a fixed seed, removes identity suffixes, and corrupts names. Hidden identities live in the separate `.truth.jsonl` companion, read only by the evaluator.

## Reproduce graph and model evaluation

For the experimental 150,000-paper source-order pilot, fixed-cohort validation comparisons, stricter temporal identity evaluation, and a user-led training workflow, see `docs/model-training-workbook.md`. For the fixed 1,200/400-query model pilot, reserved test protocol, real evidence trace and advanced model candidates, see `docs/model-selection-and-pilot.md`. The optional `experiments/backend-150k.json` uses the existing baseline-trained model with the larger prepared historical graph; it requires locally prepared 150k artifacts and does not replace the default backend.

After preparing the data artifacts:

```sh
PYTHONPATH=src .venv/bin/python -m hiresense.cli ml-benchmark --config experiments/ranking.json
```

Use a new report path in a copied configuration for a subsequent run. This command preserves the original dataset and works on `data/processed/phase23/graph.sqlite3`. It rebuilds the graph twice, audits edge provenance, resolves noisy observations, checks or builds local retrieval indexes, trains the reranker and feature ablations, and then evaluates the held-out test period. It records commands, seeds, configuration and source hashes, package versions, model hashes, metrics, paired bootstrap intervals, cohort results, failure examples, a controlled name-swap check, and sequential warm-query timings in `results/phase23.json`.

Verified indexes and retrieval feature caches can be reused. Their manifests bind them to graph content, encoder checksums, labels, and retrieval budgets. Stale or corrupted artifacts are rejected. Training opens only train and validation labels; validation selects tree settings and blend weight. Test labels are opened for evaluation after fitting and selection finish. The benchmark writes the selected model to `models/expert_ranker.json`; it intentionally retrains derived model files. Preserve a separate model directory in the configuration when comparing experiments.

## Core methods

Identity candidate generation uses inverted indexes over unordered names, tokens/deletion signatures, and coauthor neighborhoods. Oversized blocks are skipped and candidate lists are capped. The matcher combines name compatibility with coauthor, venue, and year evidence; names alone cannot authorize a merge. A score threshold and ambiguity margin permit abstention. Incorrect merges cost more than splits because they contaminate downstream profiles and explanations. Candidate recall is evaluated from the actual emitted candidates. This evaluates linkage to known historical identities; it does not measure open-world identity discovery or unsupervised clustering.

The context graph contains typed author–paper, author–venue and undirected coauthorship events. Every event has the publication year and supporting DBLP paper key. Atomic reconstruction removes stale edges. An audit verifies dates, endpoint types and actual source relationships. Resolved observations map to these canonical profiles. Profile and bounded shortest-path queries retain supporting paper evidence.

Retrieval combines SQLite FTS5 BM25 and exact cosine search over local, unchanged MiniLM title embeddings. MiniLM uses masked mean pooling, L2 normalization and 256-token truncation. The encoder attribution, upstream model-card link, conversion revision and hashes are in `models/minilm/`. Dense and lexical paper results aggregate to authors using maximum relevance rather than raw sums; reciprocal-rank fusion supplies hybrid candidates.

The trained gradient-boosted model uses title relevance, retrieval ranks, normalized topical support, graph degree, productivity and recency relative to the graph cutoff. A validation-selected blend retains the hybrid ranking prior while learning adjustments. Display names are excluded from ranking features and tie-breaking. Training uses future-author positives and retrieved, sampled non-author contrasts with per-query/class-balanced weights; those non-authors are unjudged rather than proven irrelevant.

Recency has explicit features and a retrained ablation. Maximum paper relevance and normalized support address prolific authors with broad output. Feature ablations share hybrid candidates and the hybrid prior: removing explicit dense features does not remove dense retrieval from that prior. Standalone lexical-only and embedding-only baselines measure retrieval components. Evaluation reports nDCG@10 and MRR over each returned list, capped at 200 authors, including zero-score queries and missing-history authors. Upstream embedding pretraining overlap cannot be independently ruled out.

## Individual commands

Run these from the repository root. The graph/index paths refer to the artifacts produced by the ML benchmark:

```sh
PYTHONPATH=src .venv/bin/python -m hiresense.cli search --db data/processed/phase23/graph.sqlite3 --index data/indexes/phase23 --model models/expert_ranker.json --query 'graph neural networks for recommendation'
PYTHONPATH=src .venv/bin/python -m hiresense.cli train --db data/processed/phase23/graph.sqlite3 --index data/indexes/phase23 --dataset data/processed/phase1/dataset --cache data/processed/phase23 --model models/new-ranker.json
PYTHONPATH=src .venv/bin/python -m hiresense.cli evaluate --db data/processed/phase23/graph.sqlite3 --index data/indexes/phase23 --dataset data/processed/phase1/dataset --cache data/processed/phase23 --model models/expert_ranker.json --out results/new-evaluation.json
```

Use `python -m hiresense.cli --help` with `PYTHONPATH=src` for ingestion, slicing, preparation, noise, resolution, graph and index commands. Graph/model commands require a prepared snapshot. Source databases contain all time periods and must not supply training features or explanations. Preserve original prepared snapshots when deriving edges because adding edges changes their database-file digest.

## Layout

```text
examples/                  Small DBLP sample and example batch queries
run                        Required ./run launcher; implementation in scripts/
contracts/                 Versioned API, batch schema and acceptance criteria
experiments/               Fixed data and ML experiment inputs
models/                    Local semantic encoder and portable trained JSON trees
src/hiresense/
  contracts.py             Executable split and search-output constraints
  db.py                    SQLite schema and connection
  models.py                Shared data structures
  data/                    Parsing, ingestion, slicing, noise and data experiments
  graph/                   Blocking/matching, graph reconstruction and sourced reads
  retrieval/               Local encoder, BM25/vector indexes and author features
  ranking/                 Training, portable inference and shared search service
  assistant/               Query providers, grounding, safety, memory and orchestration
  api/                     Read-only research runtime and typed HTTP routes
  evaluation/              Temporal boundaries, metrics, ablations and experiments
  cli.py                   Offline pipeline commands
  batch.py                 Required batch interface
recordings/                Genuine LLM outputs, workload and provenance
scripts/                   Explicit preparation and verification commands
results/                   Measured JSON reports and reproduction commands
tests/                     Offline unit/integration tests and tiny fixtures
```

Raw DBLP, generated databases/indexes/features, virtual environments, caches and secrets are excluded from version control. Keep the small fixtures, contracts, experiment inputs, bundled models with licenses, and measured reports in the submission.
