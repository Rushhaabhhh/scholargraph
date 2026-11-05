# Recovery run v2

This is the implementation/reproduction record for the user-authorized data, retrieval, training and identity recovery run. The full baseline review is in [system-review-and-recovery-plan.md](system-review-and-recovery-plan.md); progression and failures are appended to [the journal](project-journal.md). Results remain pending until their reports exist. Stronger score goals are hypotheses, never a promise of 0.8 metrics.

The run uses local CPU. MiniLM and the evidence cross-encoder remain pretrained. New supervised query-side residual Ridge adapters are compared with unchanged embeddings; LambdaRank author models are trained on rolling historical windows. A notebook is optional. Large transformer fine-tuning would be a distinct GPU experiment if subsequent validation justifies it.

The source portfolio spans AI, language, vision, databases, systems, security, software, networking, hardware, theory and robotics. It preserves the previous source and adds complete selected venue-family history from 1995 onward. Future publications supply labels only. This is a declared portfolio and is not a random sample of all DBLP. The source selection is fixed in `experiments/recovery-data-v2.json`.

Before fitting, the primary cohort is restricted to the venue portfolio declared before the scan; legacy source retention is for historical evidence and the separate unchanged broad regression cohort. Initial unscored cohorts are archived with their original manifests.

Training graph cutoffs are 2020 and 2022, with labels in 2021–2022 and 2023. Validation uses history through 2023 and labels in 2024. The new final test uses history through 2024 and labels in 2025–2026. The measured CPU/memory budget uses 1,500 queries per training window, 800 validation and 1,000 final queries. Initial 2,000-per-window allocations remain archived; the reduction follows measured cost, not outcomes. Query sampling is deterministic round-robin by venue-key family, with hash order within families. Query keys/titles from prior evaluation datasets and repeated normalized titles are excluded. No filtering uses retrieval success, author history or model scores. The old 1,000-query test is explicitly an inspected regression cohort. See `experiments/recovery-protocol-v2.json` for exact exclusions, seeds and sizes.

Retrieval adds author-title lexical search, several bounded topic profiles, larger measured candidate budgets and topic-conditioned collaborator candidates. The evidence cross-encoder receives a defined author shortlist and allocates first papers before second papers. Date-filtered searches select and score eligible evidence. Feature ablations retain the same candidates and therefore do not disable all graph/profile effects; candidate-channel ablations are measured separately. The compact adapter is fit only from historical evidence of labeled training authors, and can be rejected on validation. Runtime adapters use exported numeric matrices and trees without importing training libraries.

From the repository root with the prepared `.venv` and checksummed DBLP archive, run these sequentially. Existing output/report paths must be preserved; copy configs and change paths for another experiment.

```sh
PYTHONPATH=src .venv/bin/python scripts/prepare_recovery_source.py --config experiments/recovery-data-v2.json --out data/processed/recovery-v2/source.xml
PYTHONPATH=src .venv/bin/python scripts/prepare_recovery.py --config experiments/recovery-protocol-v2.json
PYTHONPATH=src .venv/bin/python scripts/prepare_recovery_cohort.py --config experiments/recovery-cohort-v2.json
PYTHONPATH=src .venv/bin/python scripts/train_recovery.py --config experiments/recovery-training-v2.json
PYTHONPATH=src .venv/bin/python scripts/freeze_recovery.py --training-report results/recovery-validation-v2.json --out experiments/recovery-freeze-v2.json
PYTHONPATH=src .venv/bin/python scripts/evaluate_recovery.py --freeze experiments/recovery-freeze-v2.json --out results/recovery-final-v2.json
```

Source preparation is checksummed and manifest-bound. Rolling preparation reuses verified unchanged title vectors; it does not reuse author profiles from another cutoff. Feature caches bind graph, encoder, query adapter, source code and budgets. Training reads only declared training/validation windows. Freeze binds code, runner files, model hashes and final-cohort provenance. No code/model changes are permitted during frozen training/evaluation. Old cache versions are intentionally rejected; use the v2 work directory.

The first goals are known-author candidate recall >=50%, query candidate success >=50%, nDCG@10 >=.10 and MRR >=.15, with all failures retained in denominators. Final reports also include top-one/top-ten query success, candidate/graph oracle bounds, author-history cohorts, common-cutoff MRR against the old fixed cohort, grounding samples and warm search latency. If a gate is missed, record it and diagnose on validation; do not tune against the final score.

Human relevance has not been established by automatic authorship labels. After training, export a blinded review pool:

```sh
PYTHONPATH=src .venv/bin/python scripts/export_judgment_pool.py --training-report results/recovery-validation-v2.json --out results/recovery-human-review-v2.json
```

Grades remain null until a human reviews the evidence. This pool complements the required automatic benchmark. It does not establish complete relevance judgments, and judged coverage must be reported. Frontend, Compose, CI and final submission materials remain separate product deliverables; this run does not claim to finish them.
