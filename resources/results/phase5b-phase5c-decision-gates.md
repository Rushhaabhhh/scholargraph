# Phase 5C: evidence gates

Current decision: **BLOCKED_PENDING_HUMAN_REVIEW**. Choose no intervention until independent review is complete enough to distinguish topical relevance from proxy recovery. Evaluate P and Q separately and disclose incomplete evidence, sampling and disagreement.

| Possible intervention | Minimum evidence required before investment |
|---|---|
| A. Historical corpus coverage | Several independent, grade-≥2 archive-only cases across multiple queries, source/identity checked, and a reproducible historical selection rule fixed without target-author IDs. Show a plausible query-level opportunity and estimate indexing/serving costs. |
| B. Semantic paper retrieval | Grade-≥2 experts whose historical publications are already indexed but missed despite topical evidence; distinguish synonyms from adjacent/unrelated work and show a bounded retrieval route could reach them. |
| C. Candidate aggregation | Grade-≥2 experts reached by papers but outside the author cap, with compared top-800 boundary candidates judged on the same queries. A label-based oracle is not a production effect. |
| D. Person-level ranking | Multiple grade-≥2 candidates already in the pool but below less relevant top-ten people, with sufficient judged top-ten/pool coverage and agreement. |
| E. Supervision or benchmark mismatch | Repeated verified disagreements between future-authorship proxy and human grades, including strong unlabelled experts and weak future-author evidence; demonstrate impact or a planned controlled test. |

Once evidence exists, the evaluation owner should select **exactly one** supported action with the best expected relevance benefit relative to engineering, CPU, latency and risk; otherwise retain the current system or remain blocked. Before changing production, preregister a bounded comparison on a common judged pool and a genuinely untouched later cohort. The earlier proposed practical gate is +0.05 absolute human-graded nDCG@10 with a positive paired interval, no material MRR/Hit regression and acceptable end-to-end cost; its feasibility and sample size must be assessed before use. Do not treat this target as observed performance or guaranteed improvement.
