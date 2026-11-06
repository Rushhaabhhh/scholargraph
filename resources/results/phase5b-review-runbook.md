# Phase 5B human-review runbook

1. Keep `phase5b-excluded-author-sample.csv`, `phase5b-production-results-private.json`, the Phase 5A loss report, and model/source mappings away from reviewers. Provide only a copy of `phase5b-blinded-review.csv` and `phase5b-reviewer-instructions.md`.
2. Assign two independent reviewers to `P01`–`P10`: reviewer 1 fills only rows with `reviewer_slot` 1 and reviewer 2 only rows with slot 2. Each reviewer returns a CSV containing only their assigned rows. Do not rewrite IDs, cutoff, query, name, evidence, or slot. For the separate 40-query Q benchmark, one slot is currently provided for each pair; arrange extra review only using a new, explicitly versioned master if needed.
3. Enter 0–3, or `U` with a reason, plus a reviewer ID. Leave not-yet-reviewed rows blank. Keep originals and record any adjudication separately. A returned CSV must not repeat a query/person/slot already present in another submitted file, including blank rows. A single merged CSV containing each slot once is also accepted.
4. Check reviewer agreement and unresolved entries; independently resolve ambiguities or request an adjudicated replacement copy as appropriate. For an adjudication, preserve the original review files and replace the affected slot values in the merged evaluation copy with a documented reason and reviewer ID. The evaluator uses the median of the two current numeric slot grades; it does not implement a third adjudicator slot.
5. After grades are returned, from the repository root run:

```sh
PYTHONPATH=src .venv/bin/python scripts/phase5b_evaluate.py --reviews /path/to/reviewer-1.csv /path/to/reviewer-2.csv --out resources/results/phase5b-human-evaluation.json
```

Use as many review-file paths as necessary, or one deduplicated merged file. The evaluator refuses to overwrite an existing output. To rerun after corrections, choose a fresh output path. The Q rows can be absent in a pilot-only submission; Q results then remain unavailable. Any incomplete or U slot prevents the corresponding pair from being graded and may prevent query/cohort metrics. Inspect `review_slots`, `unresolved`, `reviewer_agreement`, per-query coverage, separate `cohorts`, `strata`, and `proxy_summary`. A report containing only coverage and unresolved issues is not a human relevance result.

The P sample deliberately overrepresents diagnostic opportunities and uses future-authorship proxy information for candidate sampling; reviewers are not shown that information. Its estimates are not population-level quality or an untouched final test. The reviewer package is prepared, but the final decision stays **BLOCKED_PENDING_HUMAN_REVIEW** until meaningful independent judgments have been assessed.
