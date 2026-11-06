# Phase 3 and Phase 4: measured results

## Summary

The application was verified against its configured DBLP graph and the existing production paper LambdaMART model. The production model and candidate generator were not changed. A 40-query blinded human-review pool was prepared, but **human relevance assessment remains pending**. Two bounded Phase 4 pilots failed to establish a defensible ranking improvement; neither was promoted. The known zero-token-overlap false-abstention problem remains unresolved.

## Production and integrity

The configured graph has 265,885 papers and 332,611 author records through 2024. The model is `paper-lambdamart-v1`, SHA-256 `947838570ec8ba0f803f63767b618221a820b958a74118a6ad771eee765b67cb`; retrieval uses BM25 and local dense embeddings, 1,024 papers per channel and 800 candidate authors. The 40-query audit repeated every API-core query, finding no differing responses and no date violations. See `phase3-production-audit.json`.

All 1,971 blinded-pool paper evidence entries matched their graph title, year, venue, source and author links. This establishes database consistency, not topical suitability or person identity. The graph has 332,611 name-derived author keys and no PID-based keys; numeric suffixes help disambiguate names but do not independently verify aliases. Earlier synthetic identity evaluation found 450 correct matches, eight incorrect merges and 98.25% precision; that experiment is not a production merge-rate estimate. A prior eight-query display-name counterfactual changed no rankings; this does not establish demographic fairness. See `phase3-evidence-identity-audit.json`, `recovery-identity-v2.json` and `lean-final-v1.json`.

## Human relevance

`../experiments/phase3-human-queries.jsonl` contains 40 predeclared diverse queries, and `../experiments/phase3-judgment-pool.jsonl` contains 752 ungraded records pooled across lexical, dense, hybrid and trained top tens. `../experiments/phase3-review-template.csv` is blinded to algorithm and score. The method mapping is in `phase3-pool-methods-private.json` and should be concealed from reviewers until after annotation.

Reviewers should enter grades 0 (no convincing evidence), 1 (related but weak), 2 (clearly relevant), or 3 (strong direct sustained or recent expertise), plus a reviewer ID and optional notes. Duplicate rows with different reviewer IDs enable agreement measurement. Blank grades remain unjudged. `scripts/evaluate_human_review.py` refuses to report human results without actual judgments and excludes each query/method with unjudged top-ten results; it reports pool coverage and exact reviewer agreement. Pooled ideal DCG and fully judged-query metrics do not represent exhaustive relevance. No human-results file has been generated.

## Search correctness and remaining risk

Explicit query dates and explicit overrides were checked against the live graph; evidence matched the effective cutoff. Gibberish returned no results. However, the deployed hard lexical-overlap condition rejects legitimate zero-overlap paraphrases, and a shared title term does not prove relevance. An exploratory cosine alternative accepted 4/4 tiny held-back synthetic paraphrase pairs and 0/4 synthetic nonsense strings, but its training and test examples were too few, manually authored, and used different comparison settings. Its numeric cutoff is **not calibrated or deployed**. See `phase3-search-correctness.json`.

## Reliability and performance

A clean source/model copy with prepared dependencies passed 89 offline backend tests and four batch queries. A different-field, disjoint XML slice ran three batch queries with zero unsupported claims. The API and batch match on IDs and scores for an equivalent sample query; the production HTTP smoke exercised search, profile, path, shortlist, idempotent retry and memory deletion with zero unsupported claims among 49 checked. Frontend component tests passed 7/7, the Next.js build passed, and browser tests passed 12/12 against isolated local services.

A 200-paper sample took 0.082 s to ingest, 0.041 s for repeat ingestion, and 0.584 s to build an index; component timings and small-sample limitations are in `phase3-component-benchmark.json`. On a warm local full-graph service, 20 sequential API requests measured p50 134 ms/p95 247 ms; 12 requests at four concurrent workers measured p50 528 ms/p95 572 ms. These are small local samples, not 200-QPS load tests. Browser-overlap measurements are retained separately. Docker Compose was **not verified** because the local Docker Desktop daemon failed to start; remote CI execution was not verified. See `phase3-release-verification.json`.

## Phase 4

The Phase 1 proxy funnel's largest loss was 204 known-author instances whose historical papers did not enter the retrieval pool. Bounded acronym expansion was therefore tested as a second paper-retrieval route with the same 800-author cap. Only five of 129 inspected development queries changed; known-author Recall@800 stayed 41.57%, nDCG@10 0.11811, MRR@10 0.14493 and Hit@10 21.71%. This is too small a changed-query subset to generalize; the branch stopped without promotion. See `phase4-failure-prioritization.json` and `phase4-query-expansion-pilot.json`.

A separate 30-author cross-encoder pilot scored one paper per author. Its best tested development fusion changed nDCG@10 from 0.11811 to 0.12011, an uncertain +0.00200 (paired 95% interval −0.00430 to +0.00916), with 113.5 ms median extra cross-encoder scoring. Stronger fusion reduced ranking quality. The method was not promoted, and no fresh final test was consumed. See `phase4-crossencoder-pilot.json`.

The existing Phase 2 300-query temporal proxy evaluation reported production nDCG@10 0.04953, MRR@10 0.07197 and Hit@10 14%; it is now inspected and not a fresh test. No new validated nDCG or MRR improvement has been established.

## Remaining work

Independent human review and meaningful graded metrics; a safe validated replacement for lexical-only abstention; topical evidence and author identity assessment beyond database consistency; Compose verification on a working daemon; and the intentionally excluded section 3.5 documentation and submission tasks remain. Submission readiness is therefore **not established**. No claim of real-world expert recommendation accuracy is supported.

## Reproduction

With prepared local data/models and dependencies:

```sh
PYTHONPATH=src .venv/bin/python scripts/phase3_audit.py
PYTHONPATH=src .venv/bin/python scripts/phase3_integrity.py
PYTHONPATH=src .venv/bin/python scripts/phase3_search_correctness.py
PYTHONPATH=src .venv/bin/python scripts/phase4_query_expansion.py
PYTHONPATH=src .venv/bin/python scripts/phase4_crossencoder_pilot.py
PYTHONPATH=src .venv/bin/python scripts/check_clean_copy.py --out /tmp/phase3-clean-copy.json
```

The first five commands require their named output paths not to exist; reproduce in a separate copy or archive outputs first. Prepared graph, raw data and indexes are local artifacts and are not included in a clean checkout. After independent review: `PYTHONPATH=src .venv/bin/python scripts/evaluate_human_review.py --reviews <reviewed.csv> --out <new-report.json>`.
