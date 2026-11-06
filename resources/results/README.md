# Authoritative ML results and reproduction

The retained production model is `models/hybrid_ranker.json`, SHA-256 `947838570ec8ba0f803f63767b618221a820b958a74118a6ad771eee765b67cb`. The authoritative ranking report is [lean-final-v1.json](lean-final-v1.json). It used 500 previously reserved 2025 future-paper titles and a 2024 historical graph of 142,283 papers; this cohort is now inspected. The model and its candidate budget were frozen using earlier validation data. This is a research benchmark, not a measure of human recommendation or hiring accuracy.

| Method | nDCG@10 | MRR within up to 800 candidates |
|---|---:|---:|
| BM25 lexical | 0.0245 | 0.0338 |
| Pretrained dense | 0.0268 | 0.0361 |
| Untrained hybrid | 0.0313 | 0.0453 |
| Trained LambdaMART | **0.0354** | **0.0488** |
| Retrained without explicit recency | 0.0334 | 0.0479 |

The measured learned-minus-hybrid nDCG@10 interval was [0.0016, 0.0070]; the interval is conditional on incomplete labels and the selected query set. The ablation keeps retrieval fixed and may retain other temporal signals. The trained model improves on the baselines in this experiment, but absolute scores are low. Future-paper authors are proxy positives; other authors are unjudged, not confirmed irrelevant. Recall@800 was 22.36% of all labeled author instances and 30.83% among those with historical graph evidence. A name-swap check changed 0 of 8 rankings; it is not proof of fairness.

[lean-validation-v1.json](lean-validation-v1.json) records training and validation: 493 training queries, 270 usable groups, 17,978 sampled examples, 698 positives, an 80-tree model and seed 42. The training history graph ends in 2020; validation uses history through 2023 with 129 future queries. The independently selected source slice has 165,464 papers across the declared 18 venue families and 1995–2025; the cohort, label hashes, venue rules and reserved test IDs are in `resources/experiments/lean-cohorts.json`, `lean-data.json`, `lean-paper-ids.txt.gz` and `lean-test-ids.json`. The frozen paper-ID manifest is necessary because the original upstream source selection narrowed the venue/year filter; its SHA-256 is `f07b607cfb5e2af3616c4cdd95315b044592efb10032e44d5081bcdd89266a56`.

Other essential evidence: [50,000-paper benchmark](data-benchmark.json), [synthetic noisy-identity precision/recall](recovery-identity-v2.json), and [scripted assistant/grounding benchmark](lean-assistant-v1.json). Historical evaluations and alternative approaches are retained in `historical-ml.zip`; extract from the repository root to restore their original relative paths. The older `historical.zip` and frozen source snapshot remain unchanged. The Phase 5 human-review materials remain active and ungraded.

See the root [README](../../README.md#final-backend-and-ml-pipeline) for exact raw-data rebuild, fresh CPU training and evaluation commands. Dependencies are pinned in `config/requirements.lock` and `config/requirements-training.lock`. The original recorded experiment used an older frozen package hash; a current-code replay is a new reproducibility check, not the exact frozen experiment. Full raw replay and new training should be reported separately and must never be called a new untouched test.

## Two recorded failures

- **Candidate retrieval:** for “You Only Evaluate Once: A Tree-based Rerank Method at Meituan,” historical authors existed but none of the proxy-labeled authors reached the candidate pool. Inspect whether their pre-cutoff work is genuinely topical and then test a bounded author-level retrieval alternative on independent judgments. Larger paper depth alone did not improve retained Recall@800 in the later diagnostic.
- **Ranking:** for “Toward End-to-End Bearing Fault Diagnosis for Industrial Scenarios with Spiking Neural Networks,” proxy-labeled authors reached the candidate pool but none appeared in the top ten. Inspect their actual evidence alongside the top results; future non-authors are unjudged, so the proxy miss does not prove the displayed experts were irrelevant. A ranker change needs a controlled human-judged comparison.

These cases and their source IDs appear in `lean-final-v1.json`; neither is a human-validated failure rate.

## Rebuild verification (6 November 2026)

The full raw archive was rescanned (13,070,766 parsed records) and rebuilt the 165,464-paper source with its original dataset hash. Both historical snapshots matched their original label hashes and retrieval content signatures; all sourced graph edges matched after normalizing venue IDs to venue names. Raw graph digests differ because venue IDs were allocated differently, so old graph-bound caches must not be reused for the rebuild. The rebuild took 635 seconds locally; the 500-query saved feature cache was separately rescored with the unchanged production model and reproduced the reported nDCG/MRR exactly. This verification did not retrain or create a new independent test.
