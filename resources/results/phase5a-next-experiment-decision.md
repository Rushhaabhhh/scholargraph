# Phase 5A: next-experiment decision

**Decision: stop algorithm tuning and do a blinded relevance assessment first.** Do not promote larger retrieval depths, change the graph, train a model, or treat any previously inspected 2024/2025 cohort as a fresh final test. The 1,024 → 4,096 depth increase raised source-reached future-author instances from 330 to 408, while candidates at the 800-person cap fell from 222 to 221 and proxy oracle nDCG@10 fell slightly. This is insufficient evidence of better expert recommendations.

The most valuable immediate intervention is better evaluation: use the existing 40-query blinded pool in `resources/experiments/phase3-review-template.csv`, plus a small prespecified sample of 2024 source and aggregation misses and matched current candidates. Show reviewers query and pre-cutoff evidence, without future labels, names of methods, ranks or scores. Have at least two independent reviewers assess a subset, report agreement, track unjudged cases, and do not call incomplete judgments ground truth. The existing 2024 cohort is for diagnosis only. This is an assessment, not an algorithmic improvement claim.

Only consider a focused retrieval or aggregation experiment if those judgments establish a substantial pool of missed experts with genuinely strong historical evidence. Before implementing or selecting anything, reserve new independent queries and freeze the protocol, labels, data cutoff, candidate budget, baseline and resource limits. Construct any broader history using an independent declared venue/year rule, never identities from evaluation labels. The pool must include baseline candidates and potential new candidates to limit judgment-pool bias.

A provisional **go/no-go gate**, to freeze before running a later experiment:

- At least **+0.05 absolute** human-graded nDCG@10 versus the fixed baseline on an independent development set, with a paired bootstrap 95% interval above zero; confirm direction on a separate untouched temporal test. This is a proposed practical threshold, not an assignment requirement or a guaranteed achievable result.
- Human-graded MRR@10 and Hit@10 must not regress by more than 0.02 absolute; report uncertainty and the grading scale. Report known-author proxy Recall@800 as a secondary diagnostic, with a target of at least +5 percentage points if retrieval is the intervention.
- No temporal leakage, unsupported publication evidence, identity/source inconsistency, or regression in filters or API/batch parity. Keep the 800-author limit unless a separate budget study is declared.
- Measure warmed end-to-end p95 latency and peak memory on the same hardware; investigate increases above 25% before promotion. Do not use the isolated retrieval timings as end-to-end costs.
- Inspect per-topic groups and paired query changes so that a few repeated topics cannot determine the conclusion. If sample size cannot support the interval or the effect is smaller, retain the current pipeline and stop.

No honest numeric estimate of the expected human-relevance gain is available before judgments. Proxy gains or an oracle ceiling alone are not a sufficient trigger for a graph rebuild, deeper retrieval, new infrastructure, or model training.
