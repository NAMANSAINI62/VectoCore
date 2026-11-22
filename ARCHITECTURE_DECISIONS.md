# Architecture Decisions

## ADR-001: Embedding Model Upgrade to `nvidia/nemotron-3.5-embed-1b` (2048-D)
- **Decision:** Use `langchain_nvidia_ai_endpoints.NVIDIAEmbeddings` with `nvidia/nemotron-3.5-embed-1b` (`2048` dimensions) and `pgvector` 0.8.7 `halfvec(2048)` HNSW cosine index (`((query_embedding::halfvec(2048)) halfvec_cosine_ops)`).
- **Reason:** `pgvector` standard `vector` HNSW indexes cap at 2000 dimensions, whereas `halfvec(2048)` supports up to 4000 dimensions while keeping full `vector(2048)` column storage and `<=>` cosine distance accuracy.

## ADR-002: Live Operational Monitoring
- **Decision:** Use request logs, cache hit/miss status, model usage, input/output token counts, and measured latency as the operational monitoring surface.
- **Reason:** These metrics describe actual production requests directly.

## ADR-003: Redis Scope
- **Decision:** Redis remains the exact-cache implementation and PostgreSQL remains the semantic-cache source of truth.
- **Reason:** The two cache layers provide deterministic exact reuse and language-aware semantic reuse.
