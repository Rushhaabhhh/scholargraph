# Phase 5B: review-pool coverage

The review package is ready for independent grading. **No human judgments exist yet**, so no relevance metrics or intervention effects have been calculated. Share only `phase5b-blinded-review.csv` with reviewers; the sample mapping, production-order mapping, source cohort IDs, and Phase 5A report must remain private until grades are submitted. Publication titles or names may themselves be recognizable, so blinding cannot guarantee that reviewers have no prior knowledge.

## Existing production review pool

The original 40 queries were a predetermined convenience set, spanning NLP, graphs, retrieval, databases, systems, vision, privacy, security and ML. The Phase 3 script pooled authors from the lexical, dense, untrained hybrid and trained top-ten lists, deduplicated each query–author pair, and shuffled within each query with seed 314159 plus query number. This is not a representative random sample of real user queries. The pool was generated using the production graph through **2024 inclusive** and does not represent the 2023 graph used in Phase 5A.

A fresh read-only production search on all 40 queries returned ten results per query. All **400/400 production query–author positions** are represented in the original 752 unique query–author pairs. All recorded trained top-ten entries are also represented. There were **zero duplicate query–author pairs**, zero empty evidence packets, and **zero mismatches** among 1,971 evidence entries when checking paper title, year, venue and authorship against the configured graph; none was undated or later than 2024. This checks source consistency, not topical relevance or person identity. Original review CSV has 752 blank grades; it was not modified. The original rows and any grades in it are copied into the new blinded package unchanged, with cutoff and review-slot columns added.

Evidence packets contain at most three selected titles; they are not a complete publication history, and absent abstracts, affiliations and disambiguating evidence may prevent a confident grade. Where evidence is insufficient, reviewers should leave the grade blank and explain why, rather than infer grade 0. The graph primarily uses DBLP name-derived keys, so namesakes and alias changes remain possible. Source-consistent authorship does not prove real-world identity. The cutoff is inclusive of the calendar year shown in each row, and records after that year must not be consulted when grading.

## Ten-query diagnostic pilot

The supplementary pilot is separate from the 40-query production pool. It uses the **2023 inclusive historical graph**, the frozen production ranker and its 1,024-paper/800-author retrieval configuration, applied offline to previously inspected 2024 title queries. Its top ten is the frozen model's historical-snapshot output, not a fresh run of the current 2024 serving graph, and may differ from the API's filtered results. It is not an independent final test.

Five queries were selected by SHA-256 ordering (salt `phase5b-v1:`) from queries where Phase 5A recorded both deeper-retrieval and exact-key archive opportunities; five more were selected by the same deterministic order from the remaining queries. Candidate sampling uses seed 314159 plus the pilot query number, and samples without replacement within each query. At most two per additional stratum were sampled after the ten baseline candidates. The apparent-evidence stratum requires rank below 100 and at least 30% exact query-token overlap with one indexed title; this is a selection heuristic, not a relevance judgment. The archive packet is the first exact-key pre-cutoff record captured in the full scan, not necessarily that person's best or most topical work. Different eligible strata can have few or no cases; the actual unique sample contains:

| Private stratum | Query–author pairs |
|---|---:|
| A: historical frozen-model top ten | 100 |
| B: historical frozen-model ranks 11–800 | 20 |
| C: reached at greater paper depth, outside both 800-author pools | 8 |
| D: exact-key pre-cutoff record in archive, absent selected source | 11 |
| E: below rank 100, apparent title evidence | 17 |

The 156 pilot pairs have two blank independent reviewer slots each, giving **312 pilot review rows**. The complete blinded CSV contains 752 original rows and 312 pilot slots, **1,064 rows** in total. Reviewers should start with `P01`–`P10`; different reviewers must fill slots 1 and 2 independently. Leave existing blank or completed grades as they are and add a reviewer identifier to each completed row.

For C and D, the candidate list was derived from known Phase 5A future-authorship losses; this is an intentionally enriched, proxy-conditioned diagnostic sample, not a population prevalence estimate. Its source labels and future-author status must not be shown to reviewers. A paper's existence or title-token overlap does not establish that its author is a relevant expert. Review only the research evidence supplied through the row's cutoff:

- **0:** evidence is clearly irrelevant.
- **1:** weak or adjacent evidence.
- **2:** direct topical expertise.
- **3:** strong, well-supported expertise.
- **Blank:** evidence is insufficient or identity cannot be resolved; explain in notes.

The private `phase5b-excluded-author-sample.csv` maps the pilot to strata, historical rank and proxy status. `phase5b-production-results-private.json` records the actual 40-query production order for later evaluation. Neither is a blinded reviewer artifact.

## Evaluation after review

Merge independent reviewer grades into a copy of the blinded CSV without disclosing the private maps while grading. Then run:

```sh
PYTHONPATH=src .venv/bin/python scripts/phase5b_evaluate.py --reviews <graded.csv> --out resources/results/phase5b-human-evaluation.json
```

The script refuses empty grades, requires reviewer identifiers, keeps unjudged candidates unjudged, reports query-level coverage and metrics only for fully judged top tens, computes paired bootstrap comparisons on common fully judged queries, and reports reviewer agreement, stratum summaries and proxy disagreement. Pooled ideal DCG is limited to judged candidates; fully judged query selection can bias results. The pilot is not a controlled alternative-system comparison. This evaluator has only been checked to reject an empty review file; it must be validated with independently reviewed data before results are relied on.

## Reproduce preparation and coverage audit

With the prepared production and 2023 historical graph/index artifacts available, run `PYTHONPATH=src .venv/bin/python scripts/phase5b_audit_coverage.py` for the production coverage audit and `PYTHONPATH=src .venv/bin/python scripts/phase5b_prepare_review.py` to regenerate the review package. The preparation command overwrites the two Phase 5B CSVs; back up any human-graded copy first. The scripts write private intermediate audit data under `/tmp`.
