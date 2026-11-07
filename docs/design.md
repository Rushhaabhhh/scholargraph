# ScholarGraph design

ScholarGraph finds researchers from public DBLP records and presents the publications and graph relationships behind each result. The deployed frontend and backend serve a prepared DBLP snapshot; the offline batch command accepts another DBLP-format XML file and query list.

## Data and context graph

DBLP XML is streamed into SQLite. Ingestion uses DBLP author PIDs when present and names otherwise, preserves source keys, and is idempotent. The research graph contains people, papers and venues, with dated, sourced author–paper, author–venue and coauthorship edges. Search indexes and mutable session data are separate from the read-only serving graph. A historical benchmark ingested 50,000 papers; the selected ML source slice contains 165,464 papers from specified venue families and years.

A separate experimental resolver matches synthetically corrupted author observations to historical profiles. It uses bounded candidate generation based on name variants and coauthors, then scores names, coauthors, venues and years. In its conservative held-out experiment, precision was 98.25% and known-author recall was 16.76%. This is synthetic known-reference linkage, not an open-world clustering or production merge-rate measurement. Incorrect merges are costlier than splits because they attach another person's evidence to a profile; the resolver abstains when evidence is insufficient. Normal DBLP ingestion does not apply this experimental matcher.

## Retrieval, training and evaluation

BM25 and pretrained local MiniLM embeddings each retrieve up to 1,024 papers. Paper evidence is aggregated into up to 800 author candidates. An 80-tree LambdaMART model trained for this project ranks candidates using relevance, publication history, recency and graph features. Scores order candidates; they are not probabilities. A lexical-overlap guard may also abstain on valid synonym-only searches.

Training uses later paper titles as queries and their authors as proxy positives against a historical graph. The training graph ends in 2020; validation uses history through 2023, and the reported test uses history through 2024 and 500 reserved 2025 titles. Source IDs, dates and exact normalized titles are checked for leakage. The test has since been inspected; non-authors are unjudged and semantic near-duplicates or identity errors remain possible.

| Method | nDCG@10 | MRR within up to 800 candidates |
|---|---:|---:|
| BM25 lexical | 0.0245 | 0.0338 |
| Pretrained dense | 0.0268 | 0.0361 |
| Untrained hybrid | 0.0313 | 0.0453 |
| Trained LambdaMART | 0.0354 | 0.0488 |
| Retrained without explicit recency | 0.0334 | 0.0479 |

The trained model improves on these baselines, but absolute scores are low and future authorship is incomplete proxy supervision, not human relevance or hiring accuracy. The recency ablation holds retrieval fixed and can retain other time signals. Independent relevance review remains incomplete. A small name-swap check changed none of eight rankings; it does not establish fairness. Detailed evaluation artifacts are kept locally and are not included in the repository.

## Assistant and reliability

The search page's graph assistant uses explicit commands and three schema-validated tools: search experts, retrieve a profile, and find a collaboration path. Session state keeps shortlist and reject decisions; the interface shows applied memory and tool activity and can delete the memory. Typed claims are checked against source records and graph edges. In a historical benchmark, 10 scripted scenarios passed, 0 of 191 typed claims were unsupported, and 8 of 8 scripted query attacks were blocked. These bounded checks do not verify unrestricted generated prose or guarantee resistance to all attacks.

Prepared backends can use a schema-validated local LLM to interpret search topics and recency. Recorded outputs or deterministic parsing provide offline fallback. If Gemini is configured, unsupported graph-assistant questions can use general chat without graph data or tool access; those answers are marked unverified. The separate conversation interface supports local or configured remote models. Source text and provider output do not select graph tools.

## Operations, scale and trade-offs

SQLite and in-process indexes keep a small, offline-capable setup simple; partitioned relational storage, separate search services and caching would add operational complexity but support greater concurrency. The API provides health and request logs, and CI runs backend, frontend, browser and Compose checks. Image building downloads dependencies and models; runtime works without API keys once provisioned. The clean Compose CI job passed for commit `05d834c`; first-time offline installation was not verified.

The deployed backend runs on a Google Cloud Compute Engine VM with 2 vCPUs and 8 GB RAM, using a prepared index on its persistent disk. On 7 November 2026, the backend and Vercel proxy health endpoints reported 265,885 papers and 332,611 authors, and a search through the proxy returned results. The backend uses `SCHOLARGRAPH_QUERY_PROVIDER=recorded`; unseen queries use deterministic parsing. This smoke check is not a concurrency or capacity test, and chat and voice can require additional resources.

To target **50 million papers, 200 queries/s and p95 500 ms**, use partitioned ingestion with versioned graph snapshots, precomputed embeddings and author features, sharded and replicated lexical and approximate-vector indexes, bounded candidate reranking, batched evidence retrieval, caching and backpressure. An illustrative latency budget is 30 ms for network/auth, 150 ms retrieval, 100 ms reranking, 100 ms evidence and 120 ms remaining overhead. These are design allocations, not measured performance. Load testing must assess ANN recall, update lag, hot authors, cost, resilience and consistency.

DBLP is public, but profiles and session decisions still require care. The reference application has no account authentication or tenant isolation. A production system needs access control, tenant isolation and retention policies; outreach should require human approval and an audit trail; user feedback should be consented and evaluated for bias before training. Deeper graph relationships can be added as versioned, dated, sourced edges.
