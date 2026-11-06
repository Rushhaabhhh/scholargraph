# Phase 5B evaluator validation

The evaluator was revised without modifying the actual review grades. Blank, `U` and numeric `0` are distinct. Every required slot must have a numeric grade for a pair to count as fully graded; unresolved identities and evidence are listed separately with reviewer notes. A reviewer cannot fill both independent slots for the same pair. IDs, slot, query, year, name and evidence are checked against the trusted master file. Duplicate rows, unknown IDs, changed evidence, invalid years, mixed cohort mappings and an entirely blank submission are rejected.

Per-query metrics are withheld unless the entire judged pool for that query and its top ten are complete. Cohort aggregate metrics and query-bootstrap intervals are withheld unless **every query in that cohort** meets that criterion. Therefore U, blank, and insufficient coverage do not become negative judgments. Q (2024) and P (2023) remain separate. Confidence intervals resample queries, not individual papers or per-query assessor uncertainty. The nDCG ideal uses the fully reviewed **pooled** candidates only; it is not an exhaustive ideal over all researchers. Two numeric grades use their median provisionally, including half grades on disagreements; exact agreement and individual disagreements are reported. The coordinator must inspect and adjudicate disputes where appropriate.

Deterministic query-paired comparisons report within-query grade-≥2 proportions for each pilot stratum against its sampled A candidates only when every required pair for that comparison is graded. These are exploratory, enriched diagnostic comparisons, not a measured alternative system's nDCG or population effects. Proxy disagreement is similarly withheld as an aggregate until the complete pilot is graded; individual completed comparisons remain visible privately. No alternative retrieval ranking was supplied, so the evaluator does not invent paired system nDCG comparisons.

## Focused regression checks

Executed from the repository root:

```sh
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_phase5b_evaluator.py' -v
```

Result: **16 tests passed**. Tests use isolated synthetic cases only, including temporary CSV and JSON fixture files. They cover hand-computed nDCG, Precision@10 and MRR@10, ID joins, duplicate slots, empty submissions, insufficient coverage, U versus 0, disagreement, independent reviewers, cutoff isolation, evidence tampering, the requirement that the complete pool be judged for pooled nDCG, deterministic bootstrap, and incomplete double review.

The following deliberately blank real-template invocation exited nonzero with `No completed human judgments supplied` and created no human-results file:

```sh
PYTHONPATH=src .venv/bin/python scripts/phase5b_evaluate.py --reviews resources/results/phase5b-blinded-review.csv --out /tmp/phase5b-blank-check.json
```

## Review-packet audit

Checked all **1,064** review slots and **908** unique query–author pairs. The 2,709 graph-backed evidence appearances match the appropriate historical graph's title, year, venue and author link. The 22 archive-only evidence appearances match the exact-identity, pre-cutoff records recorded by the completed Phase 5A archive scan. Counts include the repeated pilot reviewer slots. No ID, slot, date, source, evidence-link or private-column failures were found. This validates traceability to the stored archive scan, not an independent human identity determination. It does not guarantee topical relevance or complete career evidence.
