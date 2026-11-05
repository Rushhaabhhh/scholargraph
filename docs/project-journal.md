# HireSense project journal

This journal records what we tried, what happened, what we learned, and what we should consider next. It is a working record for the user and AI assistant, not a claim that every assignment requirement is complete. The entries below reconstruct earlier work from saved reports and our discussion; where a precise date or detail is not recorded, it is not invented.

**Last updated:** 5 November 2026.  
**Current position:** The trained ranker and previously inspected final evaluation are recorded. The backend, batch interface and API-only Compose setup remain available; the earlier frontend was retired in preparation for the planned Next.js implementation.

For the system design, see [architecture and experiment plan](architecture-and-experiment-plan.md). For runnable commands and model-training details, see [model training workbook](model-training-workbook.md). Links to machine-readable reports in this journal preserve the evidence for each result.

## How to read this journal

- **Recorded result** means a measurement appears in an existing report. Its test set, denominators and limits matter.
- **Finding or mistake** explains what a result does or does not establish.
- **Decision** captures what we chose at that time; it can be revised with evidence.
- **Next idea** is untested until a new experiment is run and recorded.

There is no single project-wide accuracy number. nDCG@10 and MRR measure ranking; candidate recall measures whether relevant people reached the candidate list; identity precision and recall measure a different task. Comparing scores from different query cohorts as if they were the same experiment can be misleading.

## Entry 1 — Established the problem and initial architecture

**Purpose.** Build the assignment's offline expert-finding product from DBLP data: ingest publications, construct a context graph, retrieve and rank researchers with evidence, and support an assistant that uses graph tools and remembers user decisions.

**Work done.** Established a Python pipeline and SQLite data model for papers, authors, venues and authorships. The project later gained temporal snapshots, graph edges, lexical and vector retrieval, a learned ranker, a batch interface and a FastAPI backend. The assignment allows a smaller DBLP slice but requires the pipeline to handle at least 50,000 papers. It also requires an application started with Compose, a UI, CI and submission materials, which are not yet all present.

**Design decision.** SQLite and local models provide an offline, comparatively simple starting point. They do not demonstrate the assignment's 50-million-paper / 200-QPS scale scenario; that is a design question still to address and validate separately.

## Entry 2 — Prepared the 50,000-paper baseline

**Purpose.** Establish a reproducible data baseline and meet the assignment's minimum pipeline size.

**Method.** Select the first 50,000 matching, authored and dated records from the DBLP archive in source order. Ingest the records, repeat ingestion, freeze the historical graph at 2018 and construct later temporal labels. A future paper title is a query and its authors are relevance labels.

| Recorded baseline | Result |
|---|---:|
| Source papers | 50,000 |
| Authors in source | 80,147 |
| Authorship records in source | 140,412 |
| Historical papers, through 2018 | 41,786 |
| Historical authors | 61,185 |
| First ingestion | 17.9 seconds |
| Repeat ingestion | 0 inserts and 0 updates |

**Result.** Recorded checks passed for idempotency, foreign keys, temporal isolation, repeatable dataset creation and repeatable synthetic noise. The entire recorded data experiment took 46.4 seconds; timing depends on environment. Evidence: [50k data benchmark](../resources/results/data-benchmark.json) and [development configuration](../resources/experiments/development.json).

**Finding.** Fifty thousand is a minimum requirement, not a proven optimal size. The source-order slice is convenient but not a representative sample of DBLP. A future author's absence from this slice makes that person impossible to retrieve from its historical graph.

## Entry 3 — Built the context graph and first identity experiment

**Purpose.** Connect authors, papers, venues and collaborations using evidence that can be traced to DBLP.

**Work done.** Built typed author–paper, author–venue and coauthorship edge events. Each edge carries the supporting publication and year. The baseline graph contained 359,808 edge events and passed its recorded integrity check. A matcher uses name similarity plus coauthor, venue and year evidence, with candidate blocking and abstention for uncertainty. Incorrect merges can contaminate a researcher's publications and relationships, so they are treated as especially costly.

**Initial recorded result.** The synthetic known-identity linkage experiment reported 99.996% precision, 91.61% recall and one incorrect merge among 26,185 noisy observations. Evidence: [graph and ML benchmark (archive: phase23.json)](../resources/results/historical.zip).

**Mistake / limitation found later.** The canonical profiles in that experiment contained the same publication from which a noisy observation was generated. Its coauthors, year and venue could therefore appear on both sides of the match. The result is a measure of that easier setup, not reliable evidence of performance on genuinely unseen records. It also does not measure open-world clustering.

**Decision.** Preserve the original report for transparency and add a stricter later-period evaluation rather than replace the historical number.

## Entry 4 — Trained and evaluated the first ranker

**Purpose.** Meet the assignment's requirement to train a model and compare it with retrieval baselines.

**Method.** Combine lexical BM25 and pretrained MiniLM title vectors to retrieve candidates. Train a gradient-boosted classifier as an expert reranker using relevance, retrieval rank, topical support, recency, publication and graph-derived features. Future paper authors are positives; retrieved non-authors are unjudged contrast examples, not proven irrelevant. Select model settings on validation and evaluate on the later test period.

The saved model contains 80 shallow trees and was trained on 26,523 candidate examples from 782 usable queries. MiniLM is a separate pretrained encoder used unchanged. The trained tree model was previously produced by the AI assistant; a subsequent audit reproduced it byte-for-byte from the prepared data.

**Recorded test results:**

| Method | nDCG@10 | MRR |
|---|---:|---:|
| Lexical | 0.01055 | 0.01842 |
| Dense MiniLM | 0.01139 | 0.02096 |
| Hybrid | 0.01485 | 0.02719 |
| Learned ranker with hybrid prior | **0.02168** | **0.03938** |

These results use 3,074 held-out queries in the original experiment. The learned model outperformed the tested baselines on that set, but the absolute ranking scores were low. Only 3,324 of 15,997 relevant author instances—20.78%—had historical graph records; hybrid candidates contained 4.81% of all relevant authors and 23.13% of those with history. A reranker cannot recover people who never reach its candidate set. The old test results have now been inspected and must not be presented as an untouched final test for later model decisions. Evidence: [phase 2–3 benchmark (archive: phase23.json)](../resources/results/historical.zip).

**Feature finding.** In the recorded ablations, removing recency features reduced nDCG@10 from 0.02168 to 0.01837. The explicit dense-feature ablation still shares hybrid candidates and a hybrid prior, so it is not a complete removal of dense retrieval.

**Collaboration finding.** The user asked to participate directly in model decisions and training. We will use the existing model as a baseline, inspect features and labels together, and carry out the next training experiment visibly rather than treating an AI-led run as a substitute for the user's understanding.

## Entry 5 — Connected and checked the backend and assistant

**Purpose.** Make graph and ranking functionality accessible through an API and the required batch command.

**Work done.** Connected search, profiles, collaboration paths, evidence checking, query-understanding fallback, shortlist/reject memory and deletion. The default query provider can replay a limited set of recorded LLM outputs; unseen or invalid requests use deterministic fallback. The assistant uses bounded server routing and validated tools.

**Recorded checks.** Ten scripted assistant scenarios over 25 turns succeeded; 0 of 316 checked typed claims were unsupported; and eight scripted query attacks were blocked without tool calls. These are results for the scripted tests and implemented fact checks, not guarantees about arbitrary conversations or attacks. Evidence: [assistant benchmark (archive: phase4.json)](../resources/results/historical.zip).

The later clean-copy run passed 65 tests and four example batch queries, with zero unsupported batch claims in that check. The browser UI, Compose startup and CI remain to be built. Evidence: [clean-copy check (archive: validation-improvements-clean.json)](../resources/results/historical.zip).

## Entry 6 — Replaced synthetic examples with real DBLP records

**Purpose.** Provide a small, quick input that exercises real publication data.

**Work done.** Replaced the old four-paper synthetic example with 200 DBLP papers spanning DAC and IGARSS, together with four example queries. The sample is topic-selected for functional testing; it is not a representative evaluation dataset. Evidence and selection details: [example manifest](../resources/examples/manifest.json), [example XML](../resources/examples/sample.xml) and [queries](../resources/examples/queries.txt).

**Finding.** A fast example is useful for checking the pipeline. It cannot establish the quality of the model on a broader unseen dataset.

## Entry 7 — Expanded the data to a 150,000-paper pilot

**Purpose.** Test whether more historical data improves the graph's coverage of the same later researchers.

**Method.** Increase the first-matching source-order slice to 150,000 papers while retaining the same historical cutoff. This is a scaling pilot, not a representative sampling strategy or a new required size.

| Recorded pilot | Result |
|---|---:|
| Source papers | 150,000 |
| Source authors | 227,941 |
| Source authorships | 502,327 |
| Historical papers | 106,978 |
| Historical authors | 151,156 |
| Historical edge events | 1,162,624 |
| Data experiment elapsed time | 166.9 seconds |
| Graph build / index build | 59.0 / 269.7 seconds |

Ingestion was idempotent, the recorded temporal checks passed, and the graph integrity audit reported zero unsupported edges. Evidence: [150k data benchmark (archive: data-benchmark-150k.json)](../resources/results/historical.zip) and [150k graph/index report (archive: graph-index-150k-validation.json)](../resources/results/historical.zip).

**Provenance mistake.** The assistant edited other package files while the data benchmark was running. Its package hash was calculated near the end, so that hash does not prove the package bytes loaded at process start. The data-preparation modules used by the run were unchanged, and source/config hashes were recorded; a repeat with frozen code is needed for a fully auditable result. The original temporary configuration was copied byte-for-byte to [development-150k.json (archive: development-150k.json)](../resources/experiments/historical.zip).

**Fair coverage comparison.** On the same 1,631 validation queries and 7,195 relevant author instances:

| Graph | Relevant authors with historical evidence | Coverage |
|---|---:|---:|
| 50k baseline | 2,232 / 7,195 | 31.02% |
| 150k pilot | 3,112 / 7,195 | **43.25%** |

Zero queries were excluded for graph key/title overlap. This shows improved history coverage for that fixed cohort. It does not prove that the 150k slice is representative or that every ranking improves. Evidence: [history coverage comparison (archive: history-coverage-validation.json)](../resources/results/historical.zip).

**Implementation improvement.** Index construction now writes vectors in bounded chunks, reducing the need to hold the full embedding output in memory. The runtime graph and exact vector search still need resource profiling at larger sizes.

## Entry 8 — Compared retrieval limits and expanded-graph ranking

**Purpose.** Separate the effects of retrieving more candidates from those of adding historical evidence.

**Candidate-budget experiment.** With the baseline graph, the same existing model and the same 200 seeded validation queries:

| Paper:author candidate limits | Recall among relevant authors with history | nDCG@10 |
|---|---:|---:|
| 256:200 | 70 / 251 = 27.89% | 0.03025 |
| 512:400 | 91 / 251 = **36.25%** | 0.03025 |

**Finding.** More candidates improved candidate recall, but did not improve top-ten ranking on this small sample. It also increased measured mean local query time from 17.8 to 24.2 ms. We did not change the default budget on this evidence. Evidence: [retrieval budget comparison (archive: retrieval-budgets-validation.json)](../resources/results/historical.zip).

**Graph-size experiment.** With the same 200 validation queries, fixed retrieval limits and the existing baseline-trained model:

| Measure | Baseline graph | Expanded graph |
|---|---:|---:|
| All-author candidate recall | 70 / 858 = 8.16% | 104 / 858 = **12.12%** |
| Known-author candidate recall | 70 / 251 = 27.89% | 104 / 347 = 29.97% |
| nDCG@10 | 0.03025 | **0.04137** |
| MRR | 0.05730 | **0.07247** |

The known-author denominators differ because the expanded graph gives more authors history. The unchanged model was trained on the baseline graph; this is cross-graph inference, not a newly trained 150k model. The sample is development evidence and does not establish statistical significance or final-test generalization. Evidence: [graph retrieval comparison (archive: graph-retrieval-validation.json)](../resources/results/historical.zip).

**Serving check.** An optional expanded-graph backend configuration passed local health, search, profile, path, shortlist/retry and memory/session-deletion checks. Zero of 29 checked claims were unsupported. Its graph and index are locally prepared artifacts; the configuration still uses the baseline-trained model. Evidence: [backend smoke report (archive: backend-150k-smoke.json)](../resources/results/historical.zip) and [optional configuration (archive: backend-150k.json)](../resources/experiments/historical.zip).

## Entry 9 — Evaluated identity on later observations

**Purpose.** Address the same-paper overlap identified in Entry 3.

**Method.** Match synthetic noisy authorship observations from 2021–2022 against profiles built only from the historical graph through 2018. Include both known and unseen authors. Compare the existing exact-year feature with an experimental year-distance feature on the same seeded sample.

| Result | Exact year | Year distance |
|---|---:|---:|
| Known authors in sample | 495 | 495 |
| Correct known matches | 143 | 177 |
| All incorrect assignments | 5 | 6 |
| Precision of assignments | 96.62% | 96.72% |
| Recall among known authors | 28.89% | 35.76% |
| False merges among 1,014 unseen observations | 4 | 5 |

Known-author candidate recall was 482/495, or 97.37%, for both modes. This is a synthetic, sampled validation experiment on linkage to historical identities, not open-world clustering. The distance feature improved recall in this sample but made one additional false assignment; the default matcher was not changed. Evidence: [temporal identity validation (archive: identity-temporal-validation.json)](../resources/results/historical.zip).

## Entry 10 — Traced the pipeline and fixed a model pilot

**Purpose.** Inspect a real record and query end to end, then prepare a controlled training/validation experiment before choosing or training a new model.

**Real traces.** For `graph neural networks hardware acceleration`, the existing model's top result was Chang-Jiun Chen. Its evidence included the 2018 DBLP paper `conf/vlsi-dat/ChenCM18`, *Acceleration of neural network model execution on embedded systems*, with Kai-Chun Chen and May-chen Martin-Kuo. The paper was independently found in the raw archive, and the source database and graph authorships agreed. The publication supports three author–paper, three author–venue and three coauthorship events. The title supports neural-network acceleration, but does not establish graph-neural-network expertise. Two additional illustrative queries verified authorships and graph edges for hyperspectral image classification and expert search. Evidence: [graph-neural query trace (archive: pipeline-trace-150k.json)](../resources/results/historical.zip), [remote-sensing trace (archive: pipeline-trace-remote-sensing.json)](../resources/results/historical.zip) and [expert-search trace (archive: pipeline-trace-expert-search.json)](../resources/results/historical.zip).

**Data finding.** The 150k source-order selection contains 115,780 conference papers and 34,220 collection entries and no journal articles. Its most frequent venues include IGARSS, WCNC, DAC and SIGIR. It remains a biased slice despite the improved history coverage measured in Entry 7.

**Experiment setup.** A deterministic pilot with seed 42 now contains 1,200 training queries from 2019–2020 and 400 validation queries from 2021–2022. A later 5,588-query 2025–2026 cohort is reserved; validation and reserved test exclude the original 50k source's paper keys and normalized titles. The parent test aggregate counts were previously observed, and all records are from the same source-order 150k slice; an independently selected reviewer-style slice is still needed. The reserved labels were mechanically created and checked, but have not been scored or used for model selection in this setup. Evidence: [cohort manifest (archive: model-pilot-v1.manifest.json)](../resources/experiments/historical.zip).

**Before training.** On training data, 384 of 1,200 queries had both a retrieved positive and a contrast candidate under the current 256:200 budget. On the new validation cohort, 199 of 1,711 relevant author instances were candidates: 11.63% of all relevant authors, or 29.18% of the 682 with historical graph evidence. The existing model's validation nDCG@10 was 0.03815 and MRR 0.06273; this transfers the baseline model to the expanded graph and is not a newly trained model. Evidence: [pilot inspection (archive: model-pilot-v1-inspection.json)](../resources/results/historical.zip).

**Decision.** Keep the baseline; evaluate a query-grouped ranker and a bounded cross-encoder plus graph-aware reranker as next candidates, with the same validation cohort and explicit compute/label trade-offs. More complex models are hypotheses, not guaranteed improvements. Train the next model with the user's participation. Details, primary references, methods and commands: [model selection and pilot (archive: model-selection-and-pilot.md)](historical.zip).

## Entry 11 — Identified the most urgent ranking bottleneck

**Question.** Which issue most limits the current expert-finding pipeline, and what should we address before training a more complex model?

**Finding.** On the fixed 400-query validation pilot, 1,711 future-author relevance instances divide into three groups:

| Group | Count | Share of all relevant author instances |
|---|---:|---:|
| No history in the graph | 1,029 | 60.14% |
| Has history, but is absent from retrieved candidates | 483 | 28.23% |
| Reached the candidate list | 199 | 11.63% |

The second row is 682 historically known relevant instances minus 199 retrieved. These are author instances in automatically generated future-paper labels, not necessarily unique people or the only suitable experts. The label is an expertise proxy, and this validation sample comes from a source-order DBLP slice. Evidence: [pilot inspection (archive: model-pilot-v1-inspection.json)](../resources/results/historical.zip).

**Why this is urgent.** The current reranker can only reorder retrieved candidates; it cannot recommend someone outside the graph or outside its candidate list. Only 384 of 1,200 training queries contain both a retrieved positive and a contrast under this setup, which also restricts the current trainer's useful supervision. A more advanced reranker could improve ordering among candidates but cannot, by itself, solve either coverage gap.

**Proposed fix — not yet implemented or measured.**

1. Expand and diversify **pre-cutoff** historical data, preserving author identities, source keys and graph dates. Compare history coverage on the same fixed validation queries; a larger source-order slice alone is not proof of broad coverage.
2. Improve candidate generation for authors already in the graph. Compare paper-level hybrid retrieval with author-topic profiles, candidate-budget changes and bounded graph-neighbor expansion. Measure candidate recall, latency and resource use on the same validation cohort. Do not inject future authors or target papers into retrieval.
3. Inspect missed cases and label quality, then compare a baseline ranker with a more expressive reranker on the same candidate pool. Track useful training queries, nDCG@10, MRR, scoped ablations and model cost. Non-authors are unjudged, and extra candidates may increase noise or leave top-ten ranking unchanged.
4. Keep false merges low and evaluate identity on held-out observations; additional data is harmful if it attaches another person's papers to an expert. Freeze choices before evaluating the reserved later cohort, and still test a distinct unseen slice.

**Decision.** Treat graph coverage and candidate recall as the first diagnostic priority. Keep the existing model as the baseline while we test improvements; do not claim an accuracy gain until the same-cohort measurements show one. The weak-label and identity limitations are parallel risks, not resolved by raising recall.

## Entry 12 — Implemented deliberate history, hybrid retrieval and local training

**Authorization and operator.** The user explicitly requested implementing the coverage, retrieval, hybrid training and identity fixes, including local training if feasible. The assistant is operating the CPU experiment under that direction. The pretrained MiniLM encoder and new pretrained cross-encoder are used unchanged; the project trains the final author-ranking model. No GPU is available in this environment, so this run uses local CPU rather than a hosted notebook.

**Data decision.** Preserve the baseline and scan the entire DBLP archive for continuous 1995–2018 history from declared ML, retrieval, web and data-mining venue families, including journals. Selection uses only venue keys and historical dates, never target-author identities. The full scan added 53,842 papers, including 7,566 journal articles, for 203,842 source papers and 160,820 historical graph papers. On the same 400 validation queries, history coverage increased from 682/1,711 (39.86%) to 730/1,711 (42.67%). This is a purposeful domain history, not a representative random sample of all research. Configuration: [history-enrichment.json (archive: history-enrichment.json)](../resources/experiments/historical.zip); comparison: [history coverage (archive: history-enrichment-coverage.json)](../resources/results/historical.zip).

**Retrieval and model changes.** Implemented recent-paper author profiles, hybrid profile/paper candidate fusion, bounded sourced collaborator expansion, IDF-weighted topic and phrase features, and local ONNX cross-encoder evidence scores. Added query-grouped LambdaRank training with portable numeric-tree export and fixed-candidate cross-score/graph-feature ablations. The selected model will be chosen on validation against the reference classifier; advanced complexity is not automatically promoted. Configuration: [hybrid-training.json (archive: hybrid-training.json)](../resources/experiments/historical.zip). Training uses 3,000 deterministic training queries, keeps the same 400 validation queries, and retains the sealed later cohort with no new key/title leakage exclusions in the historical transfer.

**Identity work.** Added conservative and strict collaborator-supported decisions, rather than allowing temporal plausibility to establish identity. Preliminary 2021–2022 validation on enriched history reduced incorrect assignments from eight (legacy exact year) to three (conservative), with precision 95.77% to 98.33% and known-author recall 27.76% to 27.15%. This is a sampled synthetic linkage task with unseen-author rejection, not open-world clustering. Stronger rules and a later check are needed before claiming zero false merges or adopting a strict default. Reports: [development (archive: identity-history-development.json)](../resources/results/historical.zip) and [validation (archive: identity-history-validation.json)](../resources/results/historical.zip).

**Numerical finding.** The int8 encoder's activation quantization depends on the inference batch. Verified stored embeddings can be reused exactly for unchanged titles, but a fresh differently padded batch can produce small numerical differences. The reuse test now checks exact identity of reused vectors and recomputation of changed inputs in the same batch, plus a semantic similarity bound. It does not assert an invalid promise of bitwise equivalence across different batches.

**Evaluation decision made before test scoring.** A 2018 graph is stale for 2025–2026 queries. Prepare an additional inference-only snapshot through 2024, while training and model selection remain on the old historical graph. Freeze the model before evaluating a deterministic 1,000-query sample of eligible reserved records; other eligible records remain unscored. Mechanical key/title overlap exclusions are allowed, but no filtering on author history or model success. This measures chronological transfer to newer available evidence, not identical-snapshot generalization. The changed protocol and resource rationale are recorded before final scores in [final-evaluation-plan.json (archive: final-evaluation-plan.json)](../resources/experiments/historical.zip).

**Status at this entry.** Training feature preparation and the recent-history scan are running. No new trained-model score or final-test result is claimed here. The complete clean-copy suite passed 72 tests before model promotion; final model integration will be checked separately.

## Entry 13 — Completed hybrid training and rolling evaluation

**Run and operator.** The assistant resumed the interrupted, user-authorized CPU experiment. The previously materialized 3,000-query / 1.2-million-row feature cache passed its manifest hash; five queries were independently reconstructed with matching candidate rows and features. This is a spot check, not an independent full recomputation. The unchanged quantized encoder can produce small batch-dependent numerical variations. Training and evaluation used the same recorded package source hash, `61b53481d0bae8e43c3ddd054347df08d34c6dd7f001564cff04940714734920`.

**Data and graph.** The 2018 training graph contains 160,820 papers and 1,772,478 sourced edge events. A separate 2024 inference snapshot adds predeclared venue history and has 265,885 papers, 332,611 authors and 3,872,790 edge events; its graph integrity audit reports zero unsupported edges. Reingestion of its 272,592-record source changed no records. The old 2018 source scan overlapped edits to unrelated package files; the source and configuration hashes are retained, but a clean frozen-source scan remains useful provenance work. [Data report (archive: hybrid-data-pipeline-v1.json)](../resources/results/historical.zip).

**Training and selection.** A local CPU run trained query-grouped LightGBM LambdaRank models and exported portable numeric trees. It used 75,272 training examples with 2,440 positives from 1,138 usable queries of 3,000. The pretrained MiniLM encoder and cross-encoder were not fine-tuned. On 400 fixed validation queries the selected model had nDCG@10 .04363 and MRR .07518, versus .03080/.04376 for untrained hybrid ordering. Model selection omitted two explicit graph features; graph expansion still generates candidates. Validation candidate recall on the enriched graph increased only from 14.261% to 14.319% of all labeled authors with the new candidate generation, and from 33.425% to 33.562% among those with history. [Validation report (archive: hybrid-validation-v1.json)](../resources/results/historical.zip).

**Reserved evaluation.** The selected model and ablations were frozen before scoring 1,000 deterministically selected 2025–2026 queries, with the 2024 inference graph. On this cohort lexical nDCG@10/MRR were .03859/.04965, dense .03653/.04887, untrained hybrid .04224/.05549, and selected trained hybrid .05432/.07696. The full-feature ablation scored .05552/.08014, but selection remains based on validation; this does not establish that the difference generalizes. All-author candidate recall is 14.68% (627/4,271), and known-author candidate recall is 26.83% (627/2,337). Sequential warm p50/p95 was 486/594 ms across 20 queries. [Final report](../resources/results/hybrid-final-v1.json), [freeze (archive: hybrid-freeze-v1.json)](../resources/experiments/historical.zip).

**Earlier system comparison.** The previous model with its 2018 graph scored .00179/.00426 on the same 1,000 queries. Its data, graph cutoff, retrieval and model all differ, so this is a combined end-to-end comparison; it is not a model-only improvement. Paired nDCG difference was .05253, with a query-bootstrap 95% interval [.04253, .06407]; query dependence and weak labels limit the interval. [Comparison (archive: hybrid-final-paired-comparison.json)](../resources/results/historical.zip).

**Identity safety.** On 1,697 2023–2024 held-out observations, the conservative policy made 150 correct and one incorrect assignment, precision 99.34%, known-author recall 22.97%. Strict made 39 correct assignments, no observed errors, and known-author recall 5.97%. These samples do not prove zero future merges and do not assess open-world clustering. [Report (archive: identity-history-holdout-default.json)](../resources/results/historical.zip).

**Integration and checks.** Promoted the validation-selected tree model for batch and the 2024 backend; retained the prior configuration and model. The clean-copy run passed 74 tests and four example queries with no unsupported emitted claims. The full-graph live API check passed health, search, profile, collaboration, memory and session checks, with zero unsupported claims among 39 emitted. A disjoint systems XML check returned ten results for each of three queries, with no unsupported claims; it is a functional check, not an accuracy evaluation. CPU inference also ran with LightGBM, scikit-learn and PyTorch imports blocked. [Clean report (archive: hybrid-clean-copy.json)](../resources/results/historical.zip), [API report (archive: hybrid-backend-smoke.json)](../resources/results/historical.zip), [unseen slice (archive: unseen-systems-hybrid-check.json)](../resources/results/historical.zip).

**Limitations and next decisions.** The source is intentionally venue-biased; the reserved sample is not independent external data; future authorship is a weak relevance proxy and non-authors are unjudged; pretrained model overlap is unknown. Authors without graph history cannot be retrieved, and many known authors still miss the candidate set. The identity matcher abstains often. Future work should collect independent judgments and held-out identity evidence, test broader historical sources and retrieval changes on a new validation cohort, then reserve a fresh test. The frontend, deployment and assignment submission deliverables still need separate completion. [Reproduction and methods (archive: hybrid-experiment.md)](historical.zip).

## Entry 14 — Audited low scores and reset product priorities

**Question and operator.** Following the user's request for a full assessment/code/result review, the assistant inspected the assignment and current pipeline and analyzed saved frozen outputs. No runtime code, model or evaluation selection was changed.

**Additional findings.** On the same 1,000 already inspected queries, 115 have no relevant author in the graph, 573 have some relevant history but retrieve no relevant author, 183 retrieve one but miss the top ten, and 129 have a top-ten hit. Hit@1 is 5.3%. Perfect ordering of existing candidates would yield nDCG@10 .18860 and MRR .31200; perfect retrieval/order of relevant authors already in the graph would yield .62710/.88500. These are label-using diagnostic upper bounds, not model predictions or achievable forecasts. Thus coverage matters but does not explain most of the gap by itself. [Diagnostic artifact (archive: pipeline-review-diagnostics-v1.json)](../resources/results/historical.zip).

**Implementation weakness.** The neural pair budget is filled in initial candidate order. Only 28.48% of candidate rows receive any neural score, with coverage falling from 99.98% in initial ranks 1–50 to 3.67% in ranks 351–400. Some late candidates share scored papers, so 64 scored papers can cover more than 64 authors. This is a measured unevenness, not proof of its causal score cost. Compare an explicit evidence-per-shortlisted-author allocation on validation before retraining.

**Judgment correction.** Backend implementation/testing is substantially developed; expert-discovery quality and the full assignment are not complete. Original source-order slices, incomplete domain-matched history, a stale training graph, weak supervision, tiny incremental retrieval gain and repeated product deferral require correction. No specific database, GPU or neural architecture is required by the assignment. A trained ranker is valid training, while the encoder/cross-encoder remain unchanged pretrained models.

**Decision proposed.** Freeze the current run as a baseline, establish new validation/test rules and measured recall/oracle gates, and run one bounded retrieval improvement cycle. Build the missing frontend/Compose/CI alongside that cycle, then train only the model justified by the bottleneck. Preserve broad transfer evaluation and the inspected test as regression data; stronger targets require fresh reserved evaluation. The complete report contains per-stage changes, targets, trade-offs and submission gaps: [system review and recovery plan (archive: system-review-and-recovery-plan.md)](historical.zip).

## Entry 15 — Authorized recovery run: plan before implementation

**User request and estimate.** The user authorized correcting the reviewed data/retrieval/training problems, logging failures and pursuing stronger measured results. Estimated active run: 2–4 hours, local CPU first; GPU notebook training only if evidence justifies it. Targets are hypotheses, never a promise of .8 metrics.

**Failures to fix.** Baseline top-ten query success is 12.9%; 573/1,000 queries have known relevant authors but retrieve none; 183 retrieve positives but rank all below ten. Source-order/domain coverage, stale 2018 training features, compressed author profiles, unequal 64-paper neural scoring, weak labels, scoped-ablation ambiguity and post-scoring date filtering were identified in Entry 14 and the system review. Identity precision is strong on a small sample but recall is low; canonical DBLP graph identity must remain protected.

**Execution sequence and checks.** (1) Preserve the v1 models/results and scan a declared cross-CS venue portfolio independently of author labels. (2) Implement dedicated lexical author documents, multiple evidence profiles, separately measurable bounded graph candidates and fair neural shortlist allocation. (3) Construct rolling historical train/validation windows and exclude all previously used evaluation query keys/titles from a new reserved cohort. (4) Compare retrieval budgets/channels on validation; then train CPU LambdaRank and matched-row reference/feature ablations, tracking oracle, top-ten success and candidate recall. (5) Freeze settings before final evaluation, connect the selected model to API/batch, test date-filter/evidence consistency, identity acceptance and offline execution, and append results, failures and remaining limits. Human relevance judgments cannot be manufactured by an automated run; they remain a separate user-reviewed benchmark.

**Goals.** First gates: known-author recall >=50%, query candidate success >=50%, nDCG@10 .10–.15 and MRR .15–.25 on the named cohort. Stronger .25/.35 goals require a higher retrieval oracle. No filtering out failed/no-history queries, no test-based model selection, no injected test positives and no changes to metric definitions. Fresh-cohort scores and the old fixed regression cohort will be distinguished.

## Entry 16 — Recovery implementation, archive failure and repaired preparation

**Data result so far.** A full 13,070,766-record archive scan added 382,570 papers to the prior 272,592-record source, producing 655,162 papers across the declared cross-CS portfolio. Selection is independent of target-author identity and model success. All-period future records are reserved for labels; feature graphs are exported separately before each query window. This is broader coverage, not a representative random DBLP sample.

**Failure and correction.** The first scan wrote valid XML but failed while serializing its manifest: a missing venue produced a `None` dictionary key mixed with string keys. The history reporter now uses an explicit `(unknown)` count bucket, while the underlying paper's missing venue remains missing. A regression test covers mixed known/missing venues. A complete clean rerun succeeded; its XML SHA256 matched the failed run exactly, and the duplicate unmanifested output was removed. The actual selection dependency hashes stayed unchanged during the rerun, even while unrelated retrieval code was developed.

**Implemented changes.** Added capped lexical author documents and multiple topic profiles for authors with sufficient history; sparse authors retain direct paper retrieval. Added an explicit evidence-first neural shortlist with one-paper coverage before second-paper allocation. Date constraints now affect retrieval/features before ranking, with eligible-paper fallback representations for recent-only searches. Added bounded surname/first-initial identity candidate blocks while retaining contextual acceptance/ambiguity safeguards, and corruption-specific identity counts with uncertainty intervals. Added rolling training windows and fresh query selection excluding previously used evaluation keys/titles. Candidate budget/channel comparisons and model selection use validation only.

**Cohort correction before fitting.** The initial query selector treated retained legacy venues as eligible for the new portfolio benchmark, repeating the domain/history mismatch we intended to fix. Primary query sampling will use the venue families declared before scanning; the original unscored labels/manifests are archived, and the old broad 1,000-query cohort remains a separately reported regression/transfer test. This correction uses venue keys only, never author history or scores. Raw training-coverage inspection preceded it; no new validation or final scores had been calculated. Differences in cohort scope must be disclosed rather than comparing fresh portfolio scores directly with the old broad headline. Configuration: `resources/experiments/recovery-cohort-v2.json`.

**Additional training hypothesis.** Fit small residual query projections on CPU from training queries and known authors' allowed historical evidence, including positives missed by the existing retriever. Compare three regularizations with unchanged query embeddings on validation; the unchanged representation remains eligible. This is weakly supervised query-side adaptation, not MiniLM fine-tuning. The final author ranker and feature ablations remain query-grouped LambdaRank, with a classifier reference using matched contrast-row budgets.

**Measured resource adjustment before fitting.** Five initial training queries on the 404,301-paper graph averaged 1.02 seconds for evidence feature extraction with 1,200 candidates and the neural budget, with approximately 2.0 GiB peak RSS including index preparation. The portfolio-aligned training allocation is therefore 1,500 queries per rolling window, 3,000 total, retaining 800 validation and 1,000 final queries. This saves about a thousand expensive query preparations and reduces matrix memory; it is not a filter on author history or outcomes. The original 2,000-per-window unscored cohorts are archived. [Engineering timing (archive: recovery-throughput-v2.json)](../resources/results/historical.zip).

**Checks and limits so far.** The real training entrypoint passed a tiny synthetic integration test with rolling graphs, adapter fitting, model selection, export and name invariance; there was deliberately no test-label directory, proving the training route does not require it. These fixture scores are not production accuracy. An engineering smoke on twenty already-seen historical validation queries confirmed neural-shortlist coverage; it is not final evaluation. Full-graph indexing and later snapshots are still being prepared. No new final ranking quality is claimed in this entry. Preserve the prior v1 results as baseline and report common-cutoff MRR when comparing different retrieval budgets.

## Entry 17 — Broader identity checks exposed an acceptance failure

**Measured failure.** On 4,505 later observations against the enlarged 2020 history graph, surname/initial blocking increased candidate recall from 85.14% to 93.18%, but conservative assignments still made eight incorrect merges among 458 assignments (98.25% precision), with known-author recall 16.76%. Better blocking did not solve acceptance. The canonical research graph continues to use DBLP identities and is never relabeled from these proposals. [Report](../resources/results/recovery-identity-v2.json).

**First learned decision experiment.** Trained an exported quadratic-feature logistic model from 4,000 2021–2022 observations using name compatibility, independent coauthor context/rarity, venue/year evidence and alias ambiguity. Names alone cannot pass its hard support gate. Validation in 2023 selected thresholds with >=99.5% assignment precision. On 4,000 fresh 2024 observations, the model produced 543 correct and six incorrect assignments: precision 98.91%, known recall 23.57%. The conservative rule on the same records produced 328 correct and nine incorrect assignments, precision 97.33%, recall 14.24%. Thus recall and errors improved, but the learned model missed the predeclared >=99% deployment gate and was not promoted. [Model experiment](../resources/results/recovery-identity-model-v2.json).

**One predeclared follow-up.** Treat that first identity holdout as inspected. Recalibrate on the same 2023 validation records to >=99.9% point precision, extend the ambiguity-margin grid, and reserve a different 2024 observation sample excluding all papers inspected in prior identity tests, including the first learned test. Retain the same >=99% deployment precision gate and minimum assignment support. This is a new validation-driven experiment, not threshold tuning against the first test. If it also misses the gate, retain the failure and leave the learned model experimental. Finite sampled precision cannot establish zero future errors or open-world identity discovery.

**Follow-up outcome.** No parameter setting met the stricter >=99.9% validation precision requirement with at least fifty assignments. The run stopped before opening a new reserved test; no identity model was promoted. This is an unresolved quality limit, not a successful fix hidden behind a new denominator. Canonical graph identity remains protected because uncertain linkage proposals are never applied to it. [Failure record (archive: recovery-identity-strict-failure-v2.json)](../resources/results/historical.zip).

## Entry 18 — Progress checkpoint and return-on-effort review

**Actual completion.** The source now contains 655,162 records. Four historical graphs and indexes are complete, through 2020/2022/2023/2024; the final inference graph contains 561,610 papers, 544,563 authors and 8,692,012 sourced edge events. All four graph integrity audits passed. The latest complete offline suite passed 85 tests. Three residual query adapters were fitted from 2,763 training evidence targets. The production v2 author ranker has not been fitted: its run was deliberately interrupted during first-window feature preparation after the retrieval pilot missed the known-author recall gate. There is no `recovery-validation-v2.json` or `recovery-final-v2.json`, and the shipped ranker remains byte-identical to the preserved v1 model. Larger-budget comparisons were proposed but not executed before this checkpoint.

**Measured improvement, with scope.** On the same 200-query validation pilot and the same 1,200-author limit, paper-only retrieval had known-author candidate recall 38.43% and query candidate success 56%; the best tested adapter configuration reached 40.92% and 60%. Its untrained ordering had nDCG@10 .07622 versus .07063 for paper-only retrieval. These are small pilot gains, not new trained-model final results. The adapter's net recall advantage over the cheaper no-author-lexical variant is only one author instance out of 765 known relevant instances. Graph expansion added no candidate recall in this pilot; author lexical fusion slightly reduced recall. Complexity is not yet justified by a large quality improvement. [Pilot (archive: recovery-retrieval-v2.json)](../resources/results/historical.zip).

**Most actionable data finding.** Of 4,061 validation author instances, 3,166 have history in the slice and 895 do not. A complete raw-archive audit found pre-cutoff history for 624 of those 895 missing instances (69.72%). Under the exact DBLP identity join, raw historical availability is therefore 93.33% versus 77.96% in the slice. This diagnoses source-selection loss; those future-label authors were not used to enrich the graph. Broader history must follow an independently defined historical rule rather than adding test-author records. [Audit (archive: recovery-history-audit-v2.json)](../resources/results/historical.zip).

**What did not meet the plan.** Known-author candidate recall is still below the 50% initial gate. The learned identity model improved recall and errors but failed its 99% deployment precision requirement; the stricter follow-up failed validation before a new test was scored. No identity model was promoted. Full author-ranker fitting, final frozen evaluation, same-old-cohort comparison, trained-model deployment verification and human suitability review remain unfinished. Frontend, Compose, CI and final submission materials are also unfinished.

**Judgment.** The engineering/data foundation is reusable, but the run spent too much effort on large graph preparation and additional mechanisms before closing an improved training/evaluation cycle. Recorded graph construction took about 52 minutes across four snapshots, and indexing about 19 minutes. The next work should preserve these artifacts, stop adding speculative components, compare retrieval budgets/channels cheaply on the existing validation cohort, and proceed to one bounded author-ranker/final evaluation cycle only with an explicit quality/cost decision. Fresh-cohort scores cannot be compared directly with the old .0543/.0770 headline; the unchanged 1,000-query regression cohort is required for that comparison.

## Current open decisions and next steps

1. Review evidence and failure cases together, especially missing author history and retrieval misses.
2. Develop and validate broader coverage and better candidate retrieval without using the already inspected final test for selection; acquire independent relevance and identity judgments.
3. Complete and verify the frontend, deployment and remaining submission deliverables.

## Template for the next entry

```text
## Entry N — Short title
Date and operator / AI assistance:
Question or hypothesis:
Data, graph, time split and query cohort (include hashes):
Method / command / seed / model and candidate settings:
Result and denominators (include runtime and resource observations):
What worked:
Mistake, failure or limitation:
Decision and rationale:
Next idea (clearly mark as untested):
Evidence / report / model paths:
```

## Entry 19 — Lean reset

**Decision.** The unfinished recovery-v2 training path did not produce a new final ranker. Retired its evidence retriever, query adapter, learned identity matcher, dedicated runners and their exclusive tests; retained the earlier hybrid pipeline, conservative identity rules, temporal retrieval fixes, historical reports/configurations and locally generated data. The v1 backup was byte-identical to the served hybrid model and was removed as a duplicate. Historical source code remains in Git at `87c48ac`.

**Data check.** A proposed nine-family 1995–2025 slice contains 63,567 papers, 56,035 through 2024. With repeated normalized titles excluded and before prior-evaluation exclusions, relevant-author history coverage was 49.91% for 2019–2021 labels against a 2018 graph and 57.54% for 2022–2023 labels against a 2021 graph. Their perfect-graph nDCG@10 ceilings were 0.5932 and 0.6611 respectively. This is a feasibility check, not model performance; the slice should not be adopted without addressing historical coverage and defining the evaluation cohort.

**Next.** Select historical data with a rule independent of future target authors, measure history/candidate coverage, then train and compare one bounded model against fixed baselines. Preserve a fresh final test and assess user-facing relevance separately with human judgments.

**Second cleanup pass.** Removed superseded diagnostic/comparison scripts, a one-off unseen-data builder, and three generated baseline ablation JSON files; the recorded results and historical Git revision remain. Combined the batch launcher with its argument-handling wrapper and made the shipped hybrid ranker the explicit default. The baseline model remains for comparison. Historical documentation identifies commands that require the earlier revision; future data and retrieval comparisons must use a fresh, compatible protocol.

## Entry 20 — Lean data and retrieval comparison

**Data choice.** Kept nine IR/web/ML query venue families and added nine related ML/database families for historical evidence, selected by venue/year rather than target-author IDs. On the same 129 already-inspected 2024 validation queries, the nine-family history alone covered 464/686 labelled author instances (67.64%) using 49,776 historical papers; the 18-family history covered 534/686 (77.84%) with 123,672 historical papers. This validation-informed choice is not evidence of performance on a representative DBLP population. The selected 1995–2025 source contains 165,464 papers. [Data audit](../resources/results/lean-data-v1.json).

**Chronology and protection.** Prepared an 85,435-paper graph through 2020 for 493 2021–2023 training queries and a 123,672-paper graph through 2023 for 129 2024 validation queries. Both graph integrity audits passed. Labels were checked against source authors, exact paper years/titles, previous-evaluation exclusions and duplicate-title exclusions. Reserved 500 2025 paper IDs by seeded hash after exclusions; no separate test author-label file was created or evaluated. The all-period source database still contains those records, so only dated graphs may feed features. [Reserved IDs](../resources/experiments/lean-test-ids.json).

**Retrieval.** On the identical validation labels, the existing profile/graph hybrid at 512 papers and 400 authors recovered 189/534 known author instances (35.39%), with 48.84% of queries having at least one relevant candidate; nDCG@10/MRR were .1068/.1345. The paper-only hybrid at the same budget recovered 188/534 (35.21%), query success 48.84%, nDCG/MRR .1175/.1467. At 1,024 papers and 800 authors it recovered 223/534 (41.76%), query success 60.47%, nDCG/MRR .1175/.1469. All-author candidate recall for that wider configuration was 32.51%. This is untrained candidate ordering with cached query vectors and no cross-encoder, not a new trained-model or production-quality result. The wider paper hybrid is selected for subsequent training experiments; no deployed model has been changed. [Comparison](../resources/results/lean-retrieval-v1.json).

**Compute and limitations.** Preparing both graphs took 204.7 seconds; all 123,672 validation title vectors were reused rather than re-encoded. Validation is small, balanced across venues and previously inspected; future authorship is incomplete expertise supervision. The old final score used a different cohort and cannot be directly compared. The existing hybrid trainer assumes one graph, so adapting it to these two snapshots is required before training and evaluating a new model.

**Additional bounded budget check.** A separately timed 2,048-paper / 1,600-author run on the same validation queries retrieved 258/534 known relevant instances (48.31%), with 68.22% query success and 37.61% all-author recall. Its untrained nDCG@10 remained .1175 and MRR .1469; the candidate oracle nDCG@10 rose from .3867 at 800 authors to .4415. Cached-query retrieval/feature p50 was 123.5 ms versus 75.9 ms at 800, excluding encoding and reranking. This supplies more candidates for a future ranker but does not itself improve top-ten ordering. Use 1,600 provisionally for the training pilot and retain 800 as the cheaper comparison; choose only after measuring trained ranking and end-to-end cost.

## Entry 21 — CPU ranker, held-out evaluation and application

**Training and selection.** Added paper-feature LambdaRank training across separate dated graphs. On 493 available training queries, the selected 800-candidate model used 270 queries with retrieved positives and contrasts: 17,978 examples including 698 positives. It fit 80 trees on CPU and blended 25% learned score with the retrieval prior. The 129-query validation nDCG/MRR were .1181/.1522 versus .1145/.1414 for the untrained hybrid; the paired nDCG interval included zero. The 1,600-candidate model validated at .1179/.1528, so 800 was selected by nDCG before test. The previously served hybrid scored .1090/.1422 on the same validation queries. The model and decision were frozen before final author labels were read. [Training](../resources/results/lean-validation-v1.json), [serving comparison](../resources/results/lean-serving-comparison-v1.json), [freeze](../resources/experiments/lean-freeze-v1.json).

**Reserved test.** On 500 2025 queries with a 142,283-paper through-2024 graph, trained nDCG@10/MRR were .0354/.0488; lexical .0245/.0338, dense .0268/.0361, and untrained hybrid .0313/.0453. Removing explicit recency features produced .0334/.0479. Of 2,683 relevant author instances, 1,946 had historical records; candidate recall was 22.36% of all and 30.83% of known authors. These are low absolute scores and do not establish hiring accuracy. Validation was balanced by venue; the test was hash-sampled and included 229 ICML queries. Ranking, retrieval and missing-history failure examples are retained in the [final report](../resources/results/lean-final-v1.json).

**Application and verification.** Added an offline JavaScript client for search, sourced evidence, profiles, assistant tool calls and memory, backed by the existing FastAPI and SQLite implementation. Compose starts the API and sample graph. A local Chromium test covered search, evidence, profile, shortlist, assistant and deletion; the full suite ran 80 tests successfully. On the 200-paper sample, 10/10 scripted conversations passed, 0/191 generated typed claims were unsupported, and 8/8 scripted injection attempts were blocked without tools. These are bounded scenarios, not overall task accuracy. [Assistant report](../resources/results/lean-assistant-v1.json).

**Reproduction constraint.** Added a raw-archive rebuilding command and locked training/validation cohorts. A synthetic rebuild passed and 100 selected records sampled from the raw archive matched the preserved source; a full raw-archive replay has not been run. The test set is now inspected; future improvements require a new untouched test. The locally selected model is used for serving, but its final scores remain insufficient evidence of strong expert-search quality.


## Entry 22 — Repository reorganization before the new frontend

**Change.** Moved sample data, active experiment configurations, recorded LLM outputs and current reports under `resources/`; moved pinned dependency files under `config/`. Archived superseded experiment configurations and results in the `historical.zip` files in their respective folders. Archived four historical design documents under `docs/historical.zip`. Historical JSON files retain their original paths and checksums.

**Frozen provenance.** The dated evaluation froze package hash `504ec1a134328b5bf095467bdebca20dba2fec0d83dfd657249f7aa7751f5791`. Path changes necessarily changed the live package hash. Before making them, we preserved the exact old Python package, scripts, uncommitted frontend, tests and supporting inputs in `resources/experiments/frozen-source-504ec1.zip`. Its restored Python package was verified against that frozen hash. The frozen report and freeze were not changed; reproduction requires the restored snapshot and matching data artifacts.

**Frontend transition.** Retired the static prototype and its browser test after preserving them in the snapshot. `web/` is an empty workspace for the planned frontend. Compose now provides the API and sample graph, not a web application; the earlier demo and design describe the retired prototype and must be updated in the next phase. No new model training or evaluation was performed during cleanup.

**Cleanup verification.** The reorganized clean copy passed 79 backend/data/ML/assistant tests and four batch queries with no unsupported claims. The count excludes the retired prototype's browser test; the previous 80-test report remains historical. A fresh API-only Compose volume started successfully, and the pre-existing sample volume also returned recorded-provider search results after the path migration. Archive integrity and the restored frozen package hash were checked; no training or final-test replay was run.

### Frontend implementation: Next.js search and assistant

Built the replacement TypeScript interface around the existing FastAPI contracts: search with cancellable requests, evidence and author timelines, assistant tool/memory visibility, and server-confirmed shortlist/reject controls. Session decisions remain in the backend until explicitly cleared; the browser tab holds the session ID. Added a runtime API proxy and a Next.js container to Compose, along with component and browser tests.

Verification used a fresh Compose sample (200 papers, 762 authors): the production build and two component tests passed; five Chromium browser tests covered search → evidence → assistant → shortlist → profile, a failed decision, stale search, mobile memory deletion, and result-reference numbering after rejection. An earlier build-time proxy configuration would have pointed the Docker frontend at itself; switching to a runtime proxy fixed this. Result numbers are kept stable when a person is rejected so assistant references continue to identify the intended person.

These are functional checks on the sample, not new ranking evaluations. The existing low held-out ranking metrics still apply. The old design PDF and recording predate this frontend and must be updated before submission. Image/dependency preparation can require network access; the prepared application runs without external API keys.
