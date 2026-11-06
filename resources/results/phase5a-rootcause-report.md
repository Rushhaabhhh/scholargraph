# Phase 5A: root-cause diagnostic

## Scope and interpretation

This is a diagnostic of the already-inspected 129-query 2024 cohort, not a test set for choosing or promoting a model. A query is the title of a 2024 publication; its 686 author instances are positive **future-authorship proxies**. They are not graded judgments of whether a researcher was a suitable expert for the query before 2024. Non-authors are unjudged. The 2023 graph, its index, query encoder and candidate cap were held fixed. No production artifact was modified and no model was trained.

The frozen funnel has 152 author instances without graph history, 204 with history but no paper in either 1,024-paper source pool, 108 reached by a source paper but absent from the 800 candidates, 132 in the candidates below the model top ten, and 90 in the top ten. Counts are query-author instances, not necessarily distinct people.

## Missing history: is the slice a material cause?

The full `data/raw/dblp.xml.gz` archive was scanned through all 13,070,766 parseable publications using the same exact DBLP PID/name-derived identity keys, a 2023 cutoff and a required usable title. The archive SHA-256 matches the recorded cohort source. Of 152 missing-history instances:

- **117** have an exact-key pre-cutoff publication in the raw archive but none in the selected source/graph: history was excluded upstream of the frozen graph. The first recorded raw example for 23 of these is present in the broader preselected recovery source, showing that the final slice excluded it; the remaining cases may have been excluded earlier. This does not independently prove whether a qualifying record was lost during ingestion, so do not attribute all 117 to a single selection rule.
- **35** had no exact-key usable pre-cutoff publication in the scanned DBLP archive. This is exact-key non-observation, not proof of true absence from DBLP under another name, publication type, source, or external databases. No same-observed-name/different-key match was found by this limited check; aliases and mergers remain unresolved.
- **0 confirmed** selected-source-to-graph ingestion/snapshot losses: the selected source contained no pre-cutoff record with the missing exact IDs. This does not audit every upstream ingestion step. **0 confirmed** identity mismatches; the 35 remain unresolved for identity and true historical absence.

The slice is therefore a material cause of the proxy coverage ceiling: 117/686 (17.06 percentage points) of all labeled instances have historical records outside the selected source, before asking whether those publications are topically useful.

For comparison, the previously documented independent historical extension added 130,861 papers and covered only 11 of these 152 instances. This is not inconsistent with a wider full-archive finding: the extension is itself a restricted venue-family slice. The full-archive audit diagnoses lost availability only; it does not establish how many missed publications are topical or that an expanded corpus would improve top-ten results. An earlier separate 4,061-instance audit found exact-key history for 624/895 absent instances, but it must not be substituted for this cohort's counts.

## The 204 source misses

All 204 have at least one historical paper in the graph, and the checked index has 123,672 graph papers, 123,672 lexical records and 123,672 vectors; the index also passed its content and file signature checks on opening. Thus no missing indexed paper was detected for these instances. At 2,048, the best paper in either channel enters for 38; at 4,096 another 40 enter; 126 still have no paper within either channel's first 4,096. Median best dense paper rank is 10,016. Ninety-nine have no BM25 title match at all, and 116 have no exact query-token overlap across their indexed titles. These are different tokenizers and measures. A lack of literal overlap may indicate synonyms or weak historical evidence; it proves neither irrelevance nor a semantic-retrieval failure.

Examples illustrating uncertainty, not human grades:

- For the future paper “Bots Shield Fake News,” one missed author's closest historical title concerned 2D/3D object retrieval (dense rank 114,792), which does not obviously establish fake-news expertise from the title alone. Another author's best title concerned sparse robust generalization (dense rank 4,279); this could be related to robustness but the record does not establish the needed expertise.
- For “Adversarial Graph Neural Network for Multivariate Time Series Anomaly Detection,” a historical title about time-aware dynamic graph embeddings appeared at dense rank 2,532. It is plausibly graph-related but not necessarily evidence of anomaly-detection expertise. A reviewer needs to inspect the work.

The available evidence therefore does **not** support a defensible percentage split between poor semantics and genuinely off-topic history. The answer is mixed: some misses are recoverable by depth, most exceed 4,096, and many have weak literal evidence. Manual independent relevance judgments are necessary to distinguish topical misses from a misleading future-author proxy.

## The 108 aggregation losses

The existing channel ranks authors by their best paper score, fuses the two author rank lists using reciprocal rank fusion, then truncates at 800. On these instances the median author position was 2,684.5; only 10 were ranked 801–1,000 and 35 within 801–1,600. Of the 108, 54 appeared only in the dense source channel, 18 only in lexical, and 36 in both. A paper merely entering the top 1,024 does not put its authors near the top of an author list: many other authors have stronger channel ranks, and single-channel authors lack the second RRF contribution.

For 23 of 108 lost instances, the maximum exact title-token overlap exceeded that of the author at the 800th boundary. This is only a screening indicator: title overlap is neither a relevance judgment nor a comparison with the actual candidate displaced by a new method. It cannot establish that a lost author is better. For example, “Position: Tensor Networks are a Valuable Asset for Green AI” reached an author via “Large-Scale Learning with Fourier Features and Tensor Decompositions” but ranked that author at 1,297, while the boundary author had a graph-defense title. Both require substantive review.

## Depth experiment and candidate alternative

| Papers per channel | Source-reached instances | Authors in top 800 | Known-author Recall@800 | Query hit@800 | Oracle nDCG@10 | Retrieval p50/p95 |
|---:|---:|---:|---:|---:|---:|---:|
| 1,024 | 330 | 222 | 41.57% | 59.69% | 0.3852 | 38.8/58.0 ms |
| 2,048 | 368 | 221 | 41.39% | 59.69% | 0.3842 | 52.4/68.2 ms |
| 4,096 | 408 | 221 | 41.39% | 59.69% | 0.3842 | 80.7/101.3 ms |

Timings are sequential CPU candidate-context and author-order operations on pre-encoded queries, excluding query encoding, feature assembly, model scoring, grounding, HTTP, and cold start. These measurements are not end-to-end production latency; process peak RSS was 596.3 MiB and is shared across variants. No 8,192 run was justified: 4,096 increased source reach but did not improve candidate retention or query hit.

A prior controlled, same-source comparison of one simple alternative, weighted top-three paper aggregation at depth 1,024, retained 223 rather than 222 proxy instances; nDCG@10 and MRR@10 remained 0.11811 and 0.14493, respectively. Candidate oracle nDCG@10 fell from 0.38524 to 0.38199. That is not evidence of a meaningful improvement in real relevance. This previous alternative was reused; no new production code or second alternative was introduced.

## Labels, temporal isolation and risk

`src/hiresense/evaluation/split.py` exports only pre-cutoff graph papers and authors, and `assert_no_leakage` checks graph papers and dated edges, future query years, unique IDs, and exact normalized-title or source-ID overlap. The diagnostic ran these checks, and the index verifies content/hash alignment. Features are derived from that graph. These checks do not rule out semantic near-duplicates, mistaken author identities, title-only query mismatch, previously inspected cohorts, or all possible training-pipeline contamination.

In `src/hiresense/ranking/lambdamart.py`, future-paper authors among retrieved candidates receive binary label 1, while sampled non-authors receive 0 as contrast examples. The comments correctly describe them as unjudged, but the optimization algorithm still treats those zeros as negatives. A potentially excellent expert absent from the future paper can therefore be pushed down, and an author whose only relevant work appears later can be treated as positive despite weak historical evidence. These metrics measure recovery of incomplete future-authorship labels, not recommendation accuracy or graded expertise.

## Prioritized causes and decision

1. **Unmeasured topical relevance and incomplete proxy supervision** — affects interpretation of all 686 labels and unjudged candidates. Highest potential value for avoiding wrong optimizations; incremental code and runtime low because a 40-query, 752-item blinded review pool already exists. Human review is the main cost and has not been completed.
2. **Missing historical coverage** — 117 of 152 missing exact identities have pre-cutoff raw evidence outside the selected source; exact evidence is recoverable from the archive, but topical benefit and a label-independent ingestion policy remain unmeasured. Full graph/index rebuild has high CPU, memory and storage cost.
3. **Source retrieval and title-only signals** — 204 known instances unreached, 78 enter at deeper depth, but weaker or unjudged topical support and no retained-candidate gain make the real benefit uncertain. Query and embedding investigation is moderate engineering cost.
4. **Author aggregation and cap** — 108 source-reached instances lost, 10 near the first 1,000; most far below the boundary. One simple top-three alternative yielded only +1 instance and no top-ten gain. Moderate engineering cost; deeper pools raise runtime.
5. **Ranking of retained candidates** — 132 labeled instances outside top ten and an oracle gap, but earlier alternatives and graph ablations did not establish a robust improvement. Changes cannot be justified from the oracle alone.

**Strongest-supported next action:** obtain blinded human judgments on the existing pool and add a small blinded sample of the diagnosed source-missed and aggregation-missed authors alongside existing candidates, with pre-cutoff evidence only. This fixes the measurement problem first; no algorithmic fix is proven to improve real expert relevance. See `phase5a-next-experiment-decision.md` for the preregistered decision gate.

## Reproduce

Run from the repository root with prepared local artifacts. The full scan is CPU/IO intensive and takes several minutes; it writes a temporary file and does not ingest data. The second command runs offline retrieval only. The third assembles the machine-readable reports. Scripts currently write temporary working files under `/tmp`; back up any same-named files first.

```sh
PYTHONPATH=src .venv/bin/python scripts/phase5a_archive_diagnostic.py
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 PYTHONPATH=src .venv/bin/python scripts/phase5a_retrieval_diagnostic.py
PYTHONPATH=src .venv/bin/python scripts/phase5a_make_reports.py
```

Per-query positions, source titles, boundary candidates, hashes and machine-readable metrics are in `phase5a-loss-attribution.json` and `phase5a-retrieval-depth.json`. No training or final-test evaluation was run.
