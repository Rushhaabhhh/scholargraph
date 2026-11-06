# Phase 5B: error attribution pending human review

No independent relevance grades have been supplied. Consequently there are **zero human-supported relevance failures in every category**, and their severity and recoverable query-level improvement are **unknown**, not zero. The following are diagnostic proxy opportunities, not verified errors or effect estimates.

| Category | Available evidence | Possible intervention and approximate cost | Key uncertainty |
|---|---|---|---|
| Source corpus exclusion | 117/152 missing-history proxy instances had exact-key earlier archive records; 11 sampled packets | Independently specified historical slice and index rebuild; high storage/compute | Whether earlier work is topical or identity is correct; sample enriched by future authorship |
| Paper retrieval | 204 known proxy instances were not reached at 1,024; eight sampled deeper-only cases | Improve semantic matching or bounded retrieval; moderate engineering/runtime | 78 reached by deeper paper retrieval did not yield an 800-author gain; topic relevance unjudged |
| Author candidate selection | 108 source-reached proxy instances excluded by the author cap | Revisit aggregation; moderate engineering | Most are far below rank 800; prior simple alternative yielded one extra proxy instance, no top-ten metric gain |
| Person-level ranking | 132 proxy instances in candidates but below top ten; 17 pilot lower-rank apparent-evidence cases | Person-level ranker or evidence features; moderate training/evaluation cost | Title overlap is not expertise; no judged ranking gain |
| Incomplete supervision | Future coauthors are binary positives; unjudged non-authors are used as 0-valued contrasts | Human-graded relevance or better supervision; human annotation cost, low infrastructure cost | Disagreement rate and effect on trained ordering are unknown |
| Weak/ambiguous evidence | Existing review packets contain up to three titles; source-consistency checks pass | Better evidence collection or identity review; moderate cost | Title-only evidence and name-derived identity may be insufficient to grade |

For each category, a defensible supported-example count, severity and query-level gain require independent judgments over a comparable pool. None is inferred from an oracle or a future-author label here. The 40-query production pool and the enriched historical pilot have different cutoffs and must be reported separately.
