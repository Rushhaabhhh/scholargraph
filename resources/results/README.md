# Results and reproduction

These measurements were recorded before the repository reorganization. Original machine-readable reports and the frozen package hash are unchanged; the corresponding source snapshot is in `../experiments/frozen-source-504ec1.zip`. The retired frontend and its 80-test clean-copy result are historical. Current verification covers the Python backend and batch interface; the new frontend is not yet implemented.

These are measured local results, not user-facing hiring accuracy. Future-paper authors are incomplete relevance judgments: non-authors may also be valid experts. The 500-query final sample was selected from nine venue families in 2025 and is not representative of DBLP or a human relevance assessment. The test has now been inspected and must not be reused for new model selection.

## Ranking on the frozen 2025 test

The model and its 800-author retrieval budget were chosen using 129 earlier validation queries before the test authors were read. Inference used a graph of 142,283 papers through 2024; 500 later paper titles supplied queries.

| Method | nDCG@10 | MRR |
|---|---:|---:|
| Lexical | 0.0245 | 0.0338 |
| Pretrained dense | 0.0268 | 0.0361 |
| Untrained lexical+dense hybrid | 0.0313 | 0.0453 |
| CPU-trained LambdaRank | **0.0354** | **0.0488** |
| Ranker without explicit recency features | 0.0334 | 0.0479 |

MRR is calculated within the method's returned candidate list, up to 800 authors. The recency ablation shares candidate generation and other features; it does not remove every possible source of temporal information. The ranker beat the tested baselines in this evaluation, but **absolute performance is weak**. Paired bootstrap 95% interval for learned minus hybrid nDCG@10 was [0.0016, 0.0070]; this conditional interval does not correct incomplete labels or domain selection. [Full final report](lean-final-v1.json).

Of 2,683 labelled author instances, 1,946 (72.53%) had graph history. The candidate set retrieved 22.36% of all labelled authors and 30.83% of those with history. A display-name swap changed zero of eight tested rankings/scores; this narrow check does not establish demographic fairness. Warm sequential search including encoding and ranker, but excluding HTTP, measured p50 94.5 ms and p95 108.0 ms over 20 queries on this machine; no throughput or production-scale claim follows.

Two documented failure modes: a CIKM reranking query had seven authors with historical records, but no relevant author reached its candidate list; a KDD bearing-fault query had relevant candidates but none ranked in the top ten. A third ICML example had no authors in the selected history. The report contains their paper titles, identities and proposed next steps. The 129-query validation set was balanced by family; the 500-query test was sampled by hash and included 229 ICML papers. These different query mixes and years limit a direct comparison of their aggregate scores.

## Training and validation

The locally trained LightGBM LambdaRank model uses 80 trees and 12 author/paper relevance features. MiniLM is pretrained and was not fine-tuned. Training used 493 temporally held-out queries; 270 had at least one retrieved positive and contrast candidate at the selected budget, producing 17,978 training examples, of which 698 were positive. Sampled non-authors are unjudged. Validation chose the 800-candidate budget and a 0.25 learned-score blend. It achieved nDCG@10 0.1181 versus 0.1145 for the untrained hybrid; the paired 95% interval for the difference was [-0.0020, 0.0103]. The previous served model scored 0.1090 on the same validation cohort, versus 0.1181 for the new model. The observed validation gain is small and uncertain. [Training report](lean-validation-v1.json), [serving comparison](lean-serving-comparison-v1.json), [freeze](../experiments/lean-freeze-v1.json).

## Assistant and graph

On the 200-paper sample with the selected model, all 10 scripted multi-turn scenarios passed. There were 0 unsupported claims among 191 generated typed claims; all 120 fabricated-claim checks were rejected; and 8/8 scripted query injections were blocked without tool calls. These are bounded test cases, not proof of general correctness or security. [Assistant report](lean-assistant-v1.json).

Historical noisy-identity evaluation on a broader graph found conservative matching precision 98.25% (450 correct of 458 assignments) and known-author recall 16.76%; candidate blocking recall was 93.18%. This is a different cohort from the ranking test, not the accuracy of every author identity. The learned identity experiment was not promoted. [Identity report](recovery-identity-v2.json).

## Commands

Run the app and included-data batch check from the repository root:

```sh
docker compose up --build
./run --data resources/examples/sample.xml --queries resources/examples/queries.txt --out /tmp/hiresense-results.json
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

The actual training/final run used `PYTHONPATH=src .venv/bin/python scripts/train_lean.py` followed by `PYTHONPATH=src .venv/bin/python scripts/evaluate_lean.py` after validation selection and a frozen serving decision. Reproduction needs the exact historical DBLP archive and fresh output paths. The [README](../../README.md#results-and-reproducibility) gives reconstruction and repeat commands. Full reconstruction from raw data has only been checked with synthetic fixtures and a 100-record source sample; a full archive replay has not been run.

For the current assistant measurement, prepare a fresh sample backend and evaluate it:

```sh
PYTHONPATH=src .venv/bin/python -m hiresense.cli prepare-backend --data resources/examples/sample.xml --out /tmp/hiresense-assistant-repeat
PYTHONPATH=src .venv/bin/python -m hiresense.cli assistant-benchmark --config /tmp/hiresense-assistant-repeat/backend.json --out /tmp/hiresense-assistant-repeat.json
```
