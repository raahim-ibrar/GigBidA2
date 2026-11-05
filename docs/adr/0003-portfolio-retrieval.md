# ADR 0003: Portfolio ingestion and retrieval

Use Postgres for authoritative source revisions/chunks and Qdrant for vectors. Qdrant payloads contain account/document IDs, not source text. Every vector search includes tenant and authoritative current-chunk filters, followed by a fresh source check. Replacing a source invalidates prior IDs immediately. Deleting it removes source text in the database transaction and writes a durable vector-cleanup outbox.

Uploads persist before queuing. Arq indexes in a separate process; a periodic reconciliation task recovers queued uploads if the API dies before enqueueing. Job IDs identify a source revision, while the indexer checks the current revision before committing results. Windows development uses the Linux Docker worker because Arq 0.28 shutdown references a Unix-only signal.

Use FastEmbed's CPU BGE-small English embeddings and Apache-licensed MiniLM cross-encoder as starting candidates. V0 uses fixed word windows; V1 decomposes newline/semicolon requirements; V2 fuses BM25L and dense ranks; V3 reranks hybrid candidates; V8 is a bounded LangGraph retrieval/grade/correction loop. BM25L avoids zero/negative rare-term IDF in very small portfolios. Corrective relevance thresholds remain provisional and need calibration on the supplied dev set.

These choices make the algorithms executable, not experimentally proven. Control-flow tests inject clearly labelled deterministic doubles. Opt-in runtime tests exercise actual open models/Qdrant/Redis. Neither replaces gold-data retrieval metrics or GigSim outcomes.

References: [FastEmbed](https://qdrant.tech/documentation/fastembed/), [cross-encoders](https://qdrant.tech/documentation/fastembed/fastembed-rerankers/), [tenant filtering](https://qdrant.tech/documentation/examples/multitenancy/).
