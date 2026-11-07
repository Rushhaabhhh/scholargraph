# Architecture and data flow

The diagram describes the current research-search path. It is not a capacity claim or live telemetry.

```mermaid
flowchart LR
  XML["DBLP XML / sample"] --> P["Parse + idempotent ingest"]
  P --> G["SQLite: dated, sourced graph"]
  G --> I["Offline BM25 + MiniLM indexes"]
  Q["Research query"] --> U["Validated intent / offline fallback"]
  U --> I
  I --> A["Paper-to-author aggregation"]
  A --> R["Trained LambdaMART inference"]
  R --> V["Evidence and typed-claim verification"]
  G --> V
  V --> API["FastAPI"]
  API --> WEB["Next.js search + profiles"]
  API --> BATCH["Offline batch JSON"]
  API <--> S["Separate SQLite session state"]
```

Training is separate from query-time inference:

```mermaid
flowchart LR
  D["Frozen 165,464 paper IDs"] --> H["History through 2020"]
  D --> F["2021–2023 paper titles + authors"]
  H --> C["Retrieve and build author features"]
  F --> C
  C --> T["CPU LambdaMART training"]
  T --> V["Validation: history through 2023"]
  V --> M["Frozen 800-candidate model"]
  M --> E["Inspected 2025 proxy evaluation"]
```

The 2025 test is no longer untouched. Future-paper authors are incomplete proxy labels, and non-authors are unjudged. The API's command-based graph assistant exposes three validated tools and session memory; the shared conversation UI can attach a researcher profile but does not expose those graph tools or memory. The 50-million-paper scale-out proposal is in the [design document](design.md); it has not been load-tested.
