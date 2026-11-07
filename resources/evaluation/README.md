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

Two observed proxy failures illustrate the limitations: for a tree-based reranking paper, none of its labeled future authors reached the candidate pool; for an industrial fault-diagnosis paper, labeled authors reached the pool but not the top ten. Independent relevance judgments are needed before attributing either miss to the production system or selecting a model change.

## Commands and artifact availability

The recorded final report identifies `scripts/evaluate_lean.py` as its evaluation command. The following commands reconstruct and evaluate an experimental run when the original local experiment manifests and exact DBLP archive are available:

```bash
uv pip install --python .venv/bin/python -r config/requirements-training.lock
PYTHONPATH=src .venv/bin/python scripts/rebuild_lean_data.py --archive data/raw/dblp.xml.gz --out data/processed/lean-rebuilt
PYTHONPATH=src .venv/bin/python scripts/train_lean.py --data data/processed/lean-rebuilt --work /tmp/lean-train --report /tmp/lean-validation.json --freeze /tmp/lean-freeze.json --model /tmp/lean-model.json
PYTHONPATH=src .venv/bin/python scripts/evaluate_lean.py --data data/processed/lean-rebuilt --freeze /tmp/lean-freeze.json --out /tmp/lean-final.json
```

The original experiment manifests, full reports, data and frozen-source archive are intentionally not distributed in this repository. Therefore a fresh clone cannot reproduce the historical metrics without those local artifacts, and a new run is not an untouched test. The model and the bundled sample remain available for the offline batch command. The [assistant scenarios](../examples/assistant-scenarios.json) are included to run the scripted assistant benchmark against a prepared graph.
