# Local data (not part of the submission)

This directory holds local-only data. None of the raw download, generated graphs or indexes, models downloaded for optional services, session databases or user conversations should be committed or packaged.

- `raw/`: DBLP archive and checksum.
- `processed/`: prepared source data, graph snapshots and experiment caches.
- `indexes/`: generated retrieval indexes.
- `models/`: optional downloaded speech/chat models.
- `runtime/`: session and conversation state, which may contain private user data.

The bundled 200-paper sample is in `resources/examples/`; the separate, derived evaluation slice and frozen research artifacts are in `resources/evaluation/reproduction/`. The batch command builds its graph and index in a temporary directory. Compose stores its sample and sessions in a Docker volume.
