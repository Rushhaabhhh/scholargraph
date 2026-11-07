# Evaluation summary

The retained model is `models/hybrid_ranker.json` (SHA-256 `947838570ec8ba0f803f63767b618221a820b958a74118a6ad771eee765b67cb`). The reported temporal test used 500 reserved 2025 paper titles and a graph through 2024 with 142,283 papers. The model and candidate budget were selected on earlier validation data; the test has since been inspected. Future authorship supplies incomplete proxy positives, and other authors are unjudged. These figures are not human relevance or hiring accuracy.

| Method | nDCG@10 | MRR within up to 800 candidates |
|---|---:|---:|
| BM25 lexical | 0.0245 | 0.0338 |
| Pretrained dense | 0.0268 | 0.0361 |
| Untrained hybrid | 0.0313 | 0.0453 |
| Trained LambdaMART | 0.0354 | 0.0488 |
| Retrained without explicit recency | 0.0334 | 0.0479 |

The learned-minus-hybrid nDCG@10 interval was [0.0016, 0.0070] on this cohort. The ablation holds retrieval fixed and can retain other time signals. Recall@800 was 22.36% of labeled author instances and 30.83% among those with graph history. A name-swap check changed none of eight rankings; it does not establish fairness.

The model used 493 training queries, of which 270 groups had usable contrasts, and 129 validation queries. Its training graph ends in 2020 and validation history in 2023. Source IDs, years and exact normalized titles were checked for leakage; semantic near-duplicates and identity errors remain possible. A separate synthetic held-out identity experiment reported 98.25% precision and 16.76% known-author recall; it is not open-world clustering.

In a historical assistant benchmark, 10 scripted scenarios passed, 0 of 191 typed claims were unsupported, and 8 of 8 scripted query attacks were blocked. These are bounded checks rather than guarantees for general generated prose or adversarial inputs.

## Error analysis

- **Candidate retrieval:** for “You Only Evaluate Once: A Tree-based Rerank Method at Meituan,” none of the labeled future authors reached the candidate pool. Check whether their historical work is topical and evaluate bounded author-level retrieval on independent relevance judgments; more paper candidates alone did not improve retained recall in a later diagnostic.
- **Ranking:** for “Toward End-to-End Bearing Fault Diagnosis for Industrial Scenarios with Spiking Neural Networks,” labeled authors reached the pool but not the top ten. Inspect their evidence alongside the displayed results and compare rankers on independent judgments. A proxy miss does not prove the returned authors are irrelevant.

## Historical reports and replay

The original [final ranking report](lean-final-v1.json), [validation and training report](lean-validation-v1.json), [assistant report](lean-assistant-v1.json), [50,000-paper ingestion benchmark](data-benchmark.json), and [identity experiment](recovery-identity-v2.json) are included. Their recorded values are historical measurements; the test cohort is now inspected. The assistant test scenarios are in [examples](../examples/assistant-scenarios.json).

The [reproduction directory](reproduction/) contains the preserved test candidate and feature cache, the frozen source-code snapshot (`package_source_sha256` `504ec1a134328b5bf095467bdebca20dba2fec0d83dfd657249f7aa7751f5791`), original cohort and test-ID manifests, and a 165,464-record DBLP-derived XML slice. The slice contains only records selected for this experiment, not the full DBLP download. It was produced from public CC0 DBLP data; its SHA-256 is `e2334f13f74e8d62fa16ba17875072b9c206fc162642d80ea2aafcfd302f3029`. The rebuild verifies the paper-ID manifest and the original **dataset content digest**, then reconstructs temporal snapshots and checks label hashes. The retained ranker, recency ablation and MiniLM model are in `models/`.

From the repository root, with Python 3.12, `uv`, and several GB of free disk space:

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r config/requirements-training.lock
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python scripts/reproduce_historical.py --work data/processed/historical-replay
```

Use a fresh `--work` path. The command rebuilds the source database and historical graphs, extracts the original frozen code, verifies frozen package/model/label hashes, and constructs a fresh test graph and index. It writes `replayed-final.json` for fresh retrieval and `frozen-cache-rescore.json` for the preserved candidates and features, then prints each metric difference from the historical report. It uses the historical trained model and evaluation code; it does not retrain, and neither result is an independent test. It needs no network after dependencies are installed. Rebuilding indexes and graphs is compute- and disk-intensive. The original benchmark command recorded in the report is `scripts/evaluate_lean.py`; the wrapper supplies the reconstructed paths.

**Observed replay:** With the same 500 labels, 142,283 graph papers and frozen model, rebuilding the index produced learned nDCG@10 **0.03569** and MRR **0.05077**, versus the historical **0.03544** and **0.04875**. Lexical metrics matched exactly. The regenerated title-embedding file differed from the historical index file even though the paper-content and encoder signatures matched; the precise reason has not been established. Full results and file hashes are in [fresh-replay-summary.json](fresh-replay-summary.json). Rescoring the preserved, checksum-verified feature cache reproduced the historical ranking metrics exactly. That check confirms scoring on the original candidates; it does not prove a fresh retrieval run reproduces those candidates. Graph digests can differ because venue IDs were allocated differently during reconstruction, so the rescore checks source, labels, paper content, encoder and feature provenance and records both graph digests rather than treating the old cache as a fresh graph-bound cache.

The bundled slice and replay target the **ranking** experiment. The separate historical 50,000-paper ingestion and noisy-identity reports reference their original development/recovery datasets, which are not bundled; their exact historical figures have not been independently replayed from this package. The included automated assistant scenarios run on the test fixture, but their current counts are not a substitute for rerunning the original assistant report.

For a new training run on the current code, use fresh paths:

```sh
PYTHONPATH=src .venv/bin/python scripts/rebuild_lean_data.py --selected-source resources/evaluation/reproduction/lean-source.xml.gz --manifests resources/evaluation/reproduction --out data/processed/new-training-data
PYTHONPATH=src .venv/bin/python scripts/train_lean.py --data data/processed/new-training-data --manifests resources/evaluation/reproduction --work data/processed/new-training-work --report data/processed/new-validation.json --freeze data/processed/new-freeze.json --model data/processed/new-model.json
PYTHONPATH=src .venv/bin/python scripts/evaluate_lean.py --data data/processed/new-training-data --freeze data/processed/new-freeze.json --out data/processed/new-final.json
```

This retrains on already-inspected cohorts and is a new experiment, not an untouched test. Do not overwrite the included reports or describe a replay as a new held-out result.
