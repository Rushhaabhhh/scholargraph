# HireSense project journal

This journal records what we tried, what happened, what we learned, and what we should consider next. It is a working record for the user and AI assistant, not a claim that every assignment requirement is complete. The entries below reconstruct earlier work from saved reports and our discussion; where a precise date or detail is not recorded, it is not invented.

**Last updated:** 5 November 2026.  
**Current position:** A working offline data, graph, retrieval, ranking and API foundation exists. An expanded-data pilot has promising validation results. A new ranker for that pilot, a final untouched evaluation, the frontend, Compose and CI remain to be completed.

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

**Result.** Recorded checks passed for idempotency, foreign keys, temporal isolation, repeatable dataset creation and repeatable synthetic noise. The entire recorded data experiment took 46.4 seconds; timing depends on environment. Evidence: [50k data benchmark](../results/data-benchmark.json) and [development configuration](../experiments/development.json).

**Finding.** Fifty thousand is a minimum requirement, not a proven optimal size. The source-order slice is convenient but not a representative sample of DBLP. A future author's absence from this slice makes that person impossible to retrieve from its historical graph.

## Entry 3 — Built the context graph and first identity experiment

**Purpose.** Connect authors, papers, venues and collaborations using evidence that can be traced to DBLP.

**Work done.** Built typed author–paper, author–venue and coauthorship edge events. Each edge carries the supporting publication and year. The baseline graph contained 359,808 edge events and passed its recorded integrity check. A matcher uses name similarity plus coauthor, venue and year evidence, with candidate blocking and abstention for uncertainty. Incorrect merges can contaminate a researcher's publications and relationships, so they are treated as especially costly.

**Initial recorded result.** The synthetic known-identity linkage experiment reported 99.996% precision, 91.61% recall and one incorrect merge among 26,185 noisy observations. Evidence: [graph and ML benchmark](../results/phase23.json).

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

These results use 3,074 held-out queries in the original experiment. The learned model outperformed the tested baselines on that set, but the absolute ranking scores were low. Only 3,324 of 15,997 relevant author instances—20.78%—had historical graph records; hybrid candidates contained 4.81% of all relevant authors and 23.13% of those with history. A reranker cannot recover people who never reach its candidate set. The old test results have now been inspected and must not be presented as an untouched final test for later model decisions. Evidence: [phase 2–3 benchmark](../results/phase23.json).

**Feature finding.** In the recorded ablations, removing recency features reduced nDCG@10 from 0.02168 to 0.01837. The explicit dense-feature ablation still shares hybrid candidates and a hybrid prior, so it is not a complete removal of dense retrieval.

**Collaboration finding.** The user asked to participate directly in model decisions and training. We will use the existing model as a baseline, inspect features and labels together, and carry out the next training experiment visibly rather than treating an AI-led run as a substitute for the user's understanding.

## Entry 5 — Connected and checked the backend and assistant

**Purpose.** Make graph and ranking functionality accessible through an API and the required batch command.

**Work done.** Connected search, profiles, collaboration paths, evidence checking, query-understanding fallback, shortlist/reject memory and deletion. The default query provider can replay a limited set of recorded LLM outputs; unseen or invalid requests use deterministic fallback. The assistant uses bounded server routing and validated tools.

**Recorded checks.** Ten scripted assistant scenarios over 25 turns succeeded; 0 of 316 checked typed claims were unsupported; and eight scripted query attacks were blocked without tool calls. These are results for the scripted tests and implemented fact checks, not guarantees about arbitrary conversations or attacks. Evidence: [assistant benchmark](../results/phase4.json).

The later clean-copy run passed 65 tests and four example batch queries, with zero unsupported batch claims in that check. The browser UI, Compose startup and CI remain to be built. Evidence: [clean-copy check](../results/validation-improvements-clean.json).

## Entry 6 — Replaced synthetic examples with real DBLP records

**Purpose.** Provide a small, quick input that exercises real publication data.

**Work done.** Replaced the old four-paper synthetic example with 200 DBLP papers spanning DAC and IGARSS, together with four example queries. The sample is topic-selected for functional testing; it is not a representative evaluation dataset. Evidence and selection details: [example manifest](../examples/manifest.json), [example XML](../examples/sample.xml) and [queries](../examples/queries.txt).

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

Ingestion was idempotent, the recorded temporal checks passed, and the graph integrity audit reported zero unsupported edges. Evidence: [150k data benchmark](../results/data-benchmark-150k.json) and [150k graph/index report](../results/graph-index-150k-validation.json).

**Provenance mistake.** The assistant edited other package files while the data benchmark was running. Its package hash was calculated near the end, so that hash does not prove the package bytes loaded at process start. The data-preparation modules used by the run were unchanged, and source/config hashes were recorded; a repeat with frozen code is needed for a fully auditable result. The original temporary configuration was copied byte-for-byte to [development-150k.json](../experiments/development-150k.json).

**Fair coverage comparison.** On the same 1,631 validation queries and 7,195 relevant author instances:

| Graph | Relevant authors with historical evidence | Coverage |
|---|---:|---:|
| 50k baseline | 2,232 / 7,195 | 31.02% |
| 150k pilot | 3,112 / 7,195 | **43.25%** |

Zero queries were excluded for graph key/title overlap. This shows improved history coverage for that fixed cohort. It does not prove that the 150k slice is representative or that every ranking improves. Evidence: [history coverage comparison](../results/history-coverage-validation.json).

**Implementation improvement.** Index construction now writes vectors in bounded chunks, reducing the need to hold the full embedding output in memory. The runtime graph and exact vector search still need resource profiling at larger sizes.

## Entry 8 — Compared retrieval limits and expanded-graph ranking

**Purpose.** Separate the effects of retrieving more candidates from those of adding historical evidence.

**Candidate-budget experiment.** With the baseline graph, the same existing model and the same 200 seeded validation queries:

| Paper:author candidate limits | Recall among relevant authors with history | nDCG@10 |
|---|---:|---:|
| 256:200 | 70 / 251 = 27.89% | 0.03025 |
| 512:400 | 91 / 251 = **36.25%** | 0.03025 |

**Finding.** More candidates improved candidate recall, but did not improve top-ten ranking on this small sample. It also increased measured mean local query time from 17.8 to 24.2 ms. We did not change the default budget on this evidence. Evidence: [retrieval budget comparison](../results/retrieval-budgets-validation.json).

**Graph-size experiment.** With the same 200 validation queries, fixed retrieval limits and the existing baseline-trained model:

| Measure | Baseline graph | Expanded graph |
|---|---:|---:|
| All-author candidate recall | 70 / 858 = 8.16% | 104 / 858 = **12.12%** |
| Known-author candidate recall | 70 / 251 = 27.89% | 104 / 347 = 29.97% |
| nDCG@10 | 0.03025 | **0.04137** |
| MRR | 0.05730 | **0.07247** |

The known-author denominators differ because the expanded graph gives more authors history. The unchanged model was trained on the baseline graph; this is cross-graph inference, not a newly trained 150k model. The sample is development evidence and does not establish statistical significance or final-test generalization. Evidence: [graph retrieval comparison](../results/graph-retrieval-validation.json).

**Serving check.** An optional expanded-graph backend configuration passed local health, search, profile, path, shortlist/retry and memory/session-deletion checks. Zero of 29 checked claims were unsupported. Its graph and index are locally prepared artifacts; the configuration still uses the baseline-trained model. Evidence: [backend smoke report](../results/backend-150k-smoke.json) and [optional configuration](../experiments/backend-150k.json).

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

Known-author candidate recall was 482/495, or 97.37%, for both modes. This is a synthetic, sampled validation experiment on linkage to historical identities, not open-world clustering. The distance feature improved recall in this sample but made one additional false assignment; the default matcher was not changed. Evidence: [temporal identity validation](../results/identity-temporal-validation.json).

## Entry 10 — Traced the pipeline and fixed a model pilot

**Purpose.** Inspect a real record and query end to end, then prepare a controlled training/validation experiment before choosing or training a new model.

**Real traces.** For `graph neural networks hardware acceleration`, the existing model's top result was Chang-Jiun Chen. Its evidence included the 2018 DBLP paper `conf/vlsi-dat/ChenCM18`, *Acceleration of neural network model execution on embedded systems*, with Kai-Chun Chen and May-chen Martin-Kuo. The paper was independently found in the raw archive, and the source database and graph authorships agreed. The publication supports three author–paper, three author–venue and three coauthorship events. The title supports neural-network acceleration, but does not establish graph-neural-network expertise. Two additional illustrative queries verified authorships and graph edges for hyperspectral image classification and expert search. Evidence: [graph-neural query trace](../results/pipeline-trace-150k.json), [remote-sensing trace](../results/pipeline-trace-remote-sensing.json) and [expert-search trace](../results/pipeline-trace-expert-search.json).

**Data finding.** The 150k source-order selection contains 115,780 conference papers and 34,220 collection entries and no journal articles. Its most frequent venues include IGARSS, WCNC, DAC and SIGIR. It remains a biased slice despite the improved history coverage measured in Entry 7.

**Experiment setup.** A deterministic pilot with seed 42 now contains 1,200 training queries from 2019–2020 and 400 validation queries from 2021–2022. A later 5,588-query 2025–2026 cohort is reserved; validation and reserved test exclude the original 50k source's paper keys and normalized titles. The parent test aggregate counts were previously observed, and all records are from the same source-order 150k slice; an independently selected reviewer-style slice is still needed. The reserved labels were mechanically created and checked, but have not been scored or used for model selection in this setup. Evidence: [cohort manifest](../experiments/model-pilot-v1.manifest.json).

**Before training.** On training data, 384 of 1,200 queries had both a retrieved positive and a contrast candidate under the current 256:200 budget. On the new validation cohort, 199 of 1,711 relevant author instances were candidates: 11.63% of all relevant authors, or 29.18% of the 682 with historical graph evidence. The existing model's validation nDCG@10 was 0.03815 and MRR 0.06273; this transfers the baseline model to the expanded graph and is not a newly trained model. Evidence: [pilot inspection](../results/model-pilot-v1-inspection.json).

**Decision.** Keep the baseline; evaluate a query-grouped ranker and a bounded cross-encoder plus graph-aware reranker as next candidates, with the same validation cohort and explicit compute/label trade-offs. More complex models are hypotheses, not guaranteed improvements. Train the next model with the user's participation. Details, primary references, methods and commands: [model selection and pilot](model-selection-and-pilot.md).

## Entry 11 — Identified the most urgent ranking bottleneck

**Question.** Which issue most limits the current expert-finding pipeline, and what should we address before training a more complex model?

**Finding.** On the fixed 400-query validation pilot, 1,711 future-author relevance instances divide into three groups:

| Group | Count | Share of all relevant author instances |
|---|---:|---:|
| No history in the graph | 1,029 | 60.14% |
| Has history, but is absent from retrieved candidates | 483 | 28.23% |
| Reached the candidate list | 199 | 11.63% |

The second row is 682 historically known relevant instances minus 199 retrieved. These are author instances in automatically generated future-paper labels, not necessarily unique people or the only suitable experts. The label is an expertise proxy, and this validation sample comes from a source-order DBLP slice. Evidence: [pilot inspection](../results/model-pilot-v1-inspection.json).

**Why this is urgent.** The current reranker can only reorder retrieved candidates; it cannot recommend someone outside the graph or outside its candidate list. Only 384 of 1,200 training queries contain both a retrieved positive and a contrast under this setup, which also restricts the current trainer's useful supervision. A more advanced reranker could improve ordering among candidates but cannot, by itself, solve either coverage gap.

**Proposed fix — not yet implemented or measured.**

1. Expand and diversify **pre-cutoff** historical data, preserving author identities, source keys and graph dates. Compare history coverage on the same fixed validation queries; a larger source-order slice alone is not proof of broad coverage.
2. Improve candidate generation for authors already in the graph. Compare paper-level hybrid retrieval with author-topic profiles, candidate-budget changes and bounded graph-neighbor expansion. Measure candidate recall, latency and resource use on the same validation cohort. Do not inject future authors or target papers into retrieval.
3. Inspect missed cases and label quality, then compare a baseline ranker with a more expressive reranker on the same candidate pool. Track useful training queries, nDCG@10, MRR, scoped ablations and model cost. Non-authors are unjudged, and extra candidates may increase noise or leave top-ten ranking unchanged.
4. Keep false merges low and evaluate identity on held-out observations; additional data is harmful if it attaches another person's papers to an expert. Freeze choices before evaluating the reserved later cohort, and still test a distinct unseen slice.

**Decision.** Treat graph coverage and candidate recall as the first diagnostic priority. Keep the existing model as the baseline while we test improvements; do not claim an accuracy gain until the same-cohort measurements show one. The weak-label and identity limitations are parallel risks, not resolved by raising recall.

## Current open decisions and next steps

1. **Review the real trace and fixed pilot together.** Inspect the evidence, label limitations, candidate coverage and source-order bias documented in Entry 10.
2. **Choose the training comparison and resource budget.** The fixed pilot and reserved in-slice cohort are prepared; agree on a baseline, neural or ranking model comparison and CPU/GPU limits before training.
3. **Train a controlled model together.** Start with an appropriately sized pilot, inspect labels and feature rows, run or direct the training visibly, and record the command, seed, model hash, settings and results. The current CLI uses full partitions; a smaller reproducible pilot needs a defined way to select them.
4. **Compare methods and diagnose failures.** Use the same validation queries and candidate pool for baselines, model choices and scoped ablations. Track history coverage, candidate recall, ranking quality, incorrect merges and cost. Decide changes on validation, not on the final test.
5. **Freeze and evaluate.** Evaluate the chosen pipeline on the new untouched cohort; report the result even if it is worse. Verify the trained model works in both batch and backend paths on a new XML slice.
6. **Finish the product and submission.** Build the UI, Compose and CI; prepare the required short design PDF, results and commands, AI-tools statement, recording and clean submission package.

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
