# Model training and experiment workbook

**Frozen-source note:** The repository was reorganized after the measured run. Its unchanged freeze requires the original package in `resources/experiments/frozen-source-504ec1.zip`; the current package has a different hash. See the README before attempting a replay.

**Current lean run:** `scripts/train_lean.py` trains on the 2020 snapshot and validates on the separate 2023 snapshot. Validation selected the 1,024-paper / 800-author budget. The model was frozen, selected for serving against the previous model on validation, and evaluated once on 500 reserved 2025 queries; the absolute final scores remain low. The [results file](../resources/results/README.md) gives commands, baselines and limitations. The README explains how to attempt reconstruction from the pinned DBLP archive; a full-archive replay has not yet been verified.

**Historical workflow:** The older `scripts/train_hybrid.py`, `scripts/freeze_hybrid.py` and `scripts/evaluate_hybrid.py` used a different single-graph protocol. The sections below preserve that record. Some old comparison scripts have been removed from the current checkout; inspect them at Git revision `87c48ac`.

This workbook is for the user and assistant to inspect, run and interpret experiments together. It records what has actually been done and provides repeatable commands; it is not evidence that a planned run has happened. The assistant should explain decisions and obtain the user's involvement in the next model-training run. The assignment permits AI coding tools but requires the submitter to explain and defend the work.

**Later update:** A new hybrid LambdaRank model has now been trained and evaluated. The sections below preserve the earlier baseline and planning context; see [hybrid experiment (archive: hybrid-experiment.md)](historical.zip) and [journal entry 13](project-journal.md#entry-13--completed-hybrid-training-and-rolling-evaluation) for current results and limitations.

**Historical pilot:** The fixed 1,200-query training / 400-query validation setup and reserved later cohort are prepared. See [model selection and pilot (archive: model-selection-and-pilot.md)](historical.zip) for the query trace, hashes, new validation baselines, caveats and candidate architectures. The full-partition command later in this workbook is an alternative, larger run; it is not required for the pilot.

## 1. What model are we training?

We train an expert reranker, not MiniLM or Qwen. Retrieval first finds possible researchers. For each query–researcher pair the project computes 12 numerical features: lexical and dense similarity/ranks, title coverage, topical support, recency, publication and collaboration counts, and a hybrid retrieval prior. A scikit-learn gradient-boosted classifier learns from those feature vectors; its score is blended with the hybrid prior and used to order candidates. The saved JSON contains the trained decision-tree thresholds/values and can be evaluated without loading scikit-learn at serving time. It is a ranking score, not a calibrated hiring probability.

Future paper titles are queries; their authors are positives. Retrieved people absent from that authorship are **unjudged contrasts**, not necessarily irrelevant. Queries with no retrieved positive or no contrast cannot be used by the current trainer. Train and validation graph features come from the same frozen historical snapshot; only later paper titles and labels come from each period. The trainer opens train and validation labels, chooses settings on validation, and does not read test labels. Repeated source paper keys or normalized titles between graph and label queries are rejected or excluded.

The existing baseline selected 80 trees of depth 2 and a 0.5 blend by validation nDCG@10 (then MRR) from the configured small candidate grid. These numbers are experiment choices, not assignment requirements. Other options worth evaluating include logistic regression, pairwise/listwise learning-to-rank, cross-encoders and fine-tuned embeddings. They add different compute, complexity and leakage risks. Compare alternatives on the same graph, queries, labels and candidate pool before deciding; keep a separate untouched final cohort. Do not claim the current model is globally optimal.

## 2. What exists versus the next experiment

| Item | Status and provenance |
|---|---|
| 50k baseline | Source-order sample; graph through 2018; labels in 2019–20 train, 2021–22 validation and 2023–26 test. Earlier test was inspected and is no longer a pristine test for our next design. |
| Existing model | `models/expert_ranker.json`, 26,523 examples from 782 usable queries. Previously trained by the assistant; it is retained as a baseline. |
| Expanded data | `data/processed/phase1_150k` is a 150k source-order pilot, not a representative random sample. It contains 106,978 historical graph papers and 151,156 historical authors. |
| Identity evaluation | A later-period, held-out-authorship validation protocol now compares exact-year and distance-based temporal evidence and counts unknown identities separately. It does not establish open-world clustering quality. |
| New trained model | **Not yet trained.** The user and assistant should review the data/graph and decide the experiment before running the next training command. |

## 3. Reproduction and decision log

All paths below are relative to the repository root. Use Python 3.12+ and the prepared `.venv` with `config/requirements.lock` installed. Runtime uses local data and model files without API keys. Paths below may already exist from the recorded runs: use fresh output/report paths to repeat. Do not overwrite the baseline model or historic results. A run with a different source snapshot or library version may have different checksums and metrics.

### 3.1 Prepare or reproduce the 150k pilot

The archive and matching MD5 checksum must already be at `data/raw/dblp.xml.gz` and `data/raw/dblp.xml.gz.md5`. The configured slice is the **first matching 150,000** papers, a known limitation. The exact config used by the recorded run was copied from `/tmp/hiresense-150k-data-config.json` to `resources/experiments/development-150k.json` with identical bytes; the report records the original temporary config path.

```bash
PYTHONPATH=src .venv/bin/python -m hiresense.cli benchmark \
  --config resources/experiments/development-150k.json \
  --out data/processed/phase1_150k_repeat \
  --report resources/results/data-benchmark-150k-repeat.json
```

Recorded result: 150,000 papers, 227,941 source authors, 106,978 graph-period papers, 151,156 graph authors and 80,462 synthetic noisy authorship observations. Ingestion was idempotent and temporal checks passed. Total experiment time was 166.9 seconds on that run; individual machines and workload differ. The resulting evaluation label periods also contain many more queries, so their aggregate scores cannot be compared directly against the old 50k cohort.

Provenance caveat: the assistant edited other package files while this data benchmark was running. The report computes `package_source_sha256` near the end of the run, so that hash is not proof of the exact package bytes loaded at process start. The data-preparation modules used for this run were not changed during the run, and source/configuration checksums are recorded, but a clean reproduction with code frozen is needed for a fully auditable benchmark.

### 3.2 Compare history on a fixed validation cohort

```bash
PYTHONPATH=src .venv/bin/python scripts/compare_history.py \
  --baseline-graph data/processed/phase1/dataset/graph.sqlite3 \
  --expanded-graph data/processed/phase1_150k/dataset/graph.sqlite3 \
  --dataset data/processed/phase1/dataset \
  --out resources/results/history-coverage-validation-repeat.json
```

The recorded `resources/results/history-coverage-validation.json` compares the same 1,631 validation queries and 7,195 relevant author instances in both graphs. History coverage rose from 2,232/7,195 (31.02%) to 3,112/7,195 (43.25%); 0 queries were excluded for key/title leakage. This is a data-coverage improvement for this fixed cohort, not a guarantee of ranking improvement or representative DBLP coverage.

### 3.3 Compare retrieval budgets

```bash
PYTHONPATH=src .venv/bin/python scripts/compare_retrieval.py \
  --db data/processed/phase23/graph.sqlite3 \
  --index data/indexes/phase23 \
  --dataset data/processed/phase1/dataset \
  --model models/expert_ranker.json \
  --queries 200 --seed 42 \
  --budgets 256:200 512:200 512:400 \
  --out resources/results/retrieval-budgets-validation-repeat.json
```

The recorded run uses the same seeded 200 validation queries, fixed model and same labels for each budget. At paper:author limits 256:200, known-author candidate recall was 70/251 (27.89%); at 512:400 it was 91/251 (36.25%). All-author candidate recall was 70/858 (8.16%) and 91/858 (10.61%), respectively. nDCG@10 was 0.03025 in both, and MRR was approximately 0.0573. The measured mean query times were 17.8 and 24.2 ms, in a local sequential run subject to workload. Increasing candidates improved recall but did not establish a top-ten ranking gain on this sample. The selected 200 queries and results are development evidence, not final-test evidence.

To compare both graph sizes with the same baseline model and the same 200 validation queries:

```bash
PYTHONPATH=src .venv/bin/python scripts/compare_graph_retrieval.py \
  --baseline-graph data/processed/phase23/graph.sqlite3 \
  --baseline-index data/indexes/phase23 \
  --expanded-graph data/processed/validation-150k/graph.sqlite3 \
  --expanded-index data/indexes/validation-150k \
  --dataset data/processed/phase1/dataset --model models/expert_ranker.json \
  --queries 200 --seed 42 --out resources/results/graph-retrieval-validation-repeat.json
```

Recorded in `resources/results/graph-retrieval-validation.json`: baseline versus expanded history coverage 251/858 (29.25%) versus 347/858 (40.44%); candidate recall over all authors 70/858 (8.16%) versus 104/858 (12.12%); candidate recall over known authors 70/251 (27.89%) versus 104/347 (29.97%); nDCG@10 0.03025 versus 0.04137; MRR 0.05730 versus 0.07247. Mean local query time was 19.35 versus 32.30 ms. The unchanged model was trained on the baseline graph, so this is a cross-graph inference comparison, not a newly trained 150k model. The 200-query sample is development evidence; it does not establish out-of-sample generalization or statistical significance.

The expanded graph build took 59.0 seconds and index build 269.7 seconds in this run; see `resources/results/graph-index-150k-validation.json`. `resources/experiments/backend-150k.json` opts into this graph with the existing model, separately from the default backend. A local API smoke test covered health, search, profile, collaboration path, shortlist/retry and memory/session deletion, with zero unsupported claims among 29 checked. Startup took 10.9 seconds in that test. Reproduce with:

```bash
PYTHONPATH=src .venv/bin/python scripts/check_backend.py \
  --config resources/experiments/backend-150k.json --out /tmp/hiresense-backend-150k-repeat.json
```

### 3.4 Evaluate temporal identity resolution

```bash
PYTHONPATH=src .venv/bin/python -m hiresense.cli identity-temporal \
  --source-db data/processed/phase1/source.sqlite3 \
  --graph-db data/processed/phase1/dataset/graph.sqlite3 \
  --start-year 2021 --end-year 2022 --rate 0.2 --seed 42 \
  --out resources/results/identity-temporal-validation-repeat.json
```

Reference profiles contain papers through 2018. Later authorship records have synthetic name corruptions and their own observed coauthors/venue/year; their source paper and its identity truth are not in those profiles. The report separates 495 previously known from 1,014 unseen author observations. Exact-year overlap: 143 correct, 5 incorrect assignments, precision 96.62%, known-author recall 28.89%, unseen false merges 4/1,014. Year-distance scoring: 177 correct, 6 incorrect assignments, precision 96.72%, known recall 35.76%, unseen false merges 5/1,014. Candidate recall among known authors was 482/495 (97.37%). This is one sampled validation run; thresholds have not been selected for deployment, and false merges carry a high cost. The default matcher remains exact-year. Synthetic noise and known-reference linkage are not an open-world clustering benchmark.

### 3.5 A user-led training run after reviewing the design

The expanded graph and matching index must be prepared first. The current `data/processed/validation-150k/graph.sqlite3` is a separate derived graph; `data/indexes/validation-150k` is its index once index preparation completes. The 150k train/validation partitions contain 13,049 and 10,948 queries respectively. Materializing all their candidates can take substantial CPU, time, RAM and disk; a smaller well-defined training pilot may be preferable. The current CLI trains the complete partitions; it does not currently expose a sample-size flag. Do not assume it is a quick operation.

To recreate the graph and index under new paths without modifying the frozen snapshot:

```bash
mkdir -p data/processed/my-150k-graph
.venv/bin/python - <<'PY'
import sqlite3
from pathlib import Path
target = Path('data/processed/my-150k-graph/graph.sqlite3')
if target.exists():
    raise SystemExit('Choose a new graph path')
with sqlite3.connect('data/processed/phase1_150k/dataset/graph.sqlite3') as source:
    with sqlite3.connect(target) as destination:
        source.backup(destination)
PY
PYTHONPATH=src .venv/bin/python -m hiresense.cli graph \
  --db data/processed/my-150k-graph/graph.sqlite3
PYTHONPATH=src .venv/bin/python -m hiresense.cli index \
  --db data/processed/my-150k-graph/graph.sqlite3 --out data/indexes/my-150k-index
```

Use `data/processed/my-150k-graph/graph.sqlite3` and `data/indexes/my-150k-index` in the training command below if you create these paths. Building the index runs local MiniLM inference and can take minutes. The index builder now writes vectors in bounded batches, although the full runtime graph and exact vector search still require memory and should be profiled.

After we agree to use the full partitions and verify the graph and index exist, the following writes a **new experimental model** and cache. Check the model path does not already exist; the trainer can overwrite it.

```bash
if test -e models/experimental-150k-ranker.json; then
  echo 'Choose a new model path; the existing file was not changed.'
else
  PYTHONPATH=src .venv/bin/python -m hiresense.cli train \
    --db data/processed/validation-150k/graph.sqlite3 \
    --index data/indexes/validation-150k \
    --dataset data/processed/phase1_150k/dataset \
    --cache data/processed/training-150k \
    --model models/experimental-150k-ranker.json
fi
```

The trainer prints examples used, selected trees, blend and validation metrics. Inspect the output model's `training` and `validation_candidates` fields, its SHA-256, and the cache manifests. It does not automatically promote the experimental model to the application. Do not run `evaluate` against the previously inspected test and present it as a new untouched final evaluation. First reserve a new final cohort and freeze all choices. Compare competing methods on identical evaluation queries and candidate pools.

### 3.6 Record every training decision

For every new run record: operator and AI assistance, UTC/local date, hypothesis, code version/hash, raw source checksum, sampling and selection criteria, graph cutoff and label periods, train/validation/test cohort IDs or hashes, seed, model/feature configuration, candidate budgets, full command, environment/dependency versions, hardware, timings and peak memory, model checksum, baselines, validation selection rationale, held-out metrics, false merges, failures, and known limitations. Never invent values or edit an older report to describe a later run. Store large raw/derived artifacts outside submission; include the small trained model and reproducible commands.

## 4. What to review before deciding

1. Does a broader **representative or field-coherent** dataset improve historical coverage on a fixed cohort? The 150k pilot is still source-order biased.
2. Does retrieval candidate recall improve on the same inputs, and at what latency/memory cost? Top-ten ranking may remain unchanged.
3. Do alternate model families improve validation nDCG@10 and MRR under the same retrieval setup? A prior selected tree count is not proof that it remains optimal for a changed graph.
4. Can identity resolution maintain low false-merge risk on held-out observations and unseen identities?
5. Are any results supported only by a small sample, an already inspected test, or a different query cohort? Label them accordingly.
6. Freeze the final design before a new held-out generalization test; then make the exact trained model available to both backend and batch flows.
