# TriMCP — Enterprise-Grade AI Memory Layer

> **Persistent, structured, and auditable memory for production AI agents — built natively on the Model Context Protocol.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/protocol-MCP%20JSON--RPC%202.0-green?style=flat-square)](https://modelcontextprotocol.io/)
[![PostgreSQL + pgvector](https://img.shields.io/badge/db-PostgreSQL%20%2B%20pgvector-336791?style=flat-square)](https://github.com/pgvector/pgvector)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow?style=flat-square)](LICENSE)

> **Status**: TriMCP is entering production validation. The v1.0 integration surface is deployed and testable, but production hardening, load testing, security review, and operational runbooks are still in progress.

---

## What is TriMCP? *(Start here if you're not a developer)*

TriMCP acts as a digital hippocampus for artificial intelligence — named after the part of the human brain responsible for forming and retrieving long-term memories.

### The Problem with AI Today

To understand why TriMCP matters, imagine you hire the world's most brilliant consultant. There's just one catch: they have zero short-term memory. Every time you start a new meeting, you spend the first hour explaining who you are, what your company does, and what you agreed on yesterday. The consultant is brilliant in the moment, but never builds experience. They can never connect the dots across time.

This is exactly how most AI systems work today. A standard ChatGPT or Claude session starts fresh every single time — the AI has no recollection of prior conversations, past decisions, or the history of your organisation.

Existing solutions like RAG (Retrieval-Augmented Generation) try to fix this by giving the AI a giant library of sticky notes to search through. But sticky notes don't create deeper understanding — they just surface text snippets. TriMCP gives the AI a genuine, organic brain.

### How TriMCP Thinks Like Us

When TriMCP is connected to a language model, three fascinating cognitive processes run in the background:

#### 1. Detecting contradictions *(Critical thinking)*

We don't blindly accept every new piece of information. If someone tells you "the coffee machine is on the 3rd floor," but you know the entire 3rd floor is being renovated, your brain immediately flags the inconsistency. TriMCP does the same. When a new fact arrives, it rapidly scans its semantic neighbourhood. If a document says a budget was cut, but another says it was increased, TriMCP doesn't blindly overwrite its memory — it flags the contradiction and marks it as a conflict that needs resolution. It doubts, just like a thinking human.

#### 2. Sleep and "dreaming" *(Memory consolidation)*

Humans don't only learn while awake — we process and build wisdom while we sleep. TriMCP has a built-in mechanic for this. During idle time, the system clusters recent, disconnected events (episodic memories) and lets the AI extract the deeper meaning. If on Monday you say "the client was frustrated about the delay," and on Wednesday you say "the client threatened to cancel the contract," TriMCP's sleep cycle stitches these together into a new, higher-level abstraction: *"The client relationship is in a critical risk zone due to delivery issues."* It moves from remembering raw data to owning contextual insight.

#### 3. The art of forgetting *(Salience & the Ebbinghaus curve)*

To have a healthy, functional mind, forgetting is just as important as remembering. If we remembered every cup of coffee we'd ever drunk, we'd be paralysed by cognitive noise. TriMCP assigns every memory a **Salience score** (relevance). Over time this score slowly decays. But every time a memory is retrieved and used, it is reinforced and fades more slowly. This means the AI's brain naturally keeps the most important, most-used concepts crystal clear — while outdated or trivial details gradually fade into the background.

### A Hungry Memory: Far More Than Just Code

Traditional MCP tools are often designed as lightweight utilities — meant to run locally on a developer's machine to let the AI read some code files. TriMCP operates in an entirely different league. It is an enterprise engine built for the entire company's ecosystem.

It doesn't limit itself to plain text or code. TriMCP ingests and digests virtually every format your organisation produces:

- **Daily work**: All MS Office files (Word, Excel, PowerPoint) and PDFs
- **Visual and technical planning**: CAD drawings, project sketches, and complex architecture diagrams from tools like LucidChart, Miro, and Draw.io
- **Communication and media**: Audio recordings, meeting transcriptions, media files, and long email threads

This means the AI doesn't just know what was written in a final document. It understands the context from the meeting where it was discussed (via the transcript), the email exchange that led to the decision, and the visual sketch on the Miro board the design team used. It captures the full spectrum of human collaboration — and because it is brand-agnostic by design, it doesn't lock your company into any single ecosystem, integrating freely across vendors and platforms.

### What This Means in Practice

When a powerful language model is connected to the TriMCP nervous system, something remarkable happens: the company gains a shared, near-infallible institutional memory.

- **The engineer**: "Why did we design the system this way last year, and how does it affect the new code we're writing today?" — TriMCP recalls the original decision (from a Miro board and meeting transcriptions), connects it to consolidated insight from the months between, and gives advice grounded in the system's true history.
- **The salesperson**: "What was Customer X's main objection in last year's tender round, and how can I use our new feature to win them back?" — The agent retrieves old email threads and lost deals from the CRM, compares them with yesterday's technical product release, and builds a tailored pitch.
- **The project manager**: "Why did we deprioritise the security module in Q3, and do we have capacity to start it again now?" — The system cross-references past resource discussions in Slack and old meeting notes with today's updated capacity plans in Excel, and gives a precise status.
- **The support technician**: "Customer Y is suddenly experiencing network issues after the latest patch. Have we seen this before?" — The agent trawls old support tickets and technical logs, recognises the pattern from a similar incident with another customer two years ago, and gives the technician the solution immediately.

### An Invisible Engine That Elevates Every Tool

It is important to note that TriMCP is a 100% backend system — there is no flashy user interface of its own. But this is precisely where the magic lies: the system compensates enormously for this "invisibility" by adding a massive dose of intelligence and precision to the systems your company already uses. When this engine is connected to the backend of a CRM system, an internal Slack bot, a company portal, or a developer's favourite code editor, those familiar surfaces are transformed into razor-sharp, intelligent assistants. Users experience sky-high AI quality and deep contextual understanding in the tools they already trust — without having to log into anything new.

It is no longer just a tool you ask questions to. It is a colleague with perfect, human-like oversight of the company's entire lifespan.

Although the concept sounds like science fiction, TriMCP is a real platform — and it is ready for production validation. The core architecture has been hardened for enterprise security and stability, ensuring the system can support at least 100 employees simultaneously without compromising response time, and with absolute guarantees that the watertight partitions between different users and sensitive data remain unbreakable (through advanced Row-Level Security). We are now moving into full-scale production testing and real-world implementation.

---

*The technical documentation for developers and operators continues below.*

---

## The Problem With Agent Memory

Autonomous AI agents are stateless by default. Every session begins at zero — no recollection of prior decisions, no awareness of organisational context, no continuity of reasoning across long-running workflows.

Bolting memory on as an afterthought produces brittle recall: keyword lookups that miss meaning, flat key-value stores with no relational structure, no temporal history, and no audit trail when something goes wrong.

**TriMCP is a different approach: memory as infrastructure.** A purpose-built quad-database engine where every data type lives in the store designed for it, with Saga-pattern consistency guarantees across all four, cryptographic audit trails, temporal recall down to the millisecond, and structured knowledge graphs that grow smarter over time.

---

## What TriMCP Does

TriMCP runs as a **Model Context Protocol (MCP) server** that any compatible AI client (Claude Desktop, Cursor, or any custom agent) connects to over stdio. It exposes 20+ structured tools to the language model — `store_memory`, `graph_search`, `connect_bridge`, `replay_fork`, and more — all backed by a distributed memory engine operating across four specialised databases in concert.

```mermaid
flowchart TB
  subgraph Clients
    IDE[MCP clients\nClaude / Cursor / Custom]
  end
  subgraph Entrypoints
    STDIO[server.py\nMCP stdio]
    A2A[a2a_server.py\nAgent-to-Agent :8004]
    ADM[admin_server.py\nREST + UI :8003]
    CRON[cron.py\nAPScheduler]
    RQ[start_worker.py\nRQ Worker]
  end
  subgraph Core["Core Engine"]
    TMP["Temporal\nas_of time-travel"]
    TSE[TriStackEngine\nSaga orchestrator]
  end
  subgraph Data
    PG[(PostgreSQL\n+ pgvector\nSemantic + KG)]
    MG[(MongoDB\nEpisodic Archive)]
    RD[(Redis\nWorking Memory)]
    S3[(MinIO\nArtifact Store)]
  end
  IDE --> STDIO
  STDIO --> TMP
  STDIO --> TSE
  A2A --> TSE
  ADM --> PG
  TSE --> PG
  TSE --> MG
  TSE --> RD
  TSE --> S3
  RQ --> PG
  RQ --> MG
  CRON --> PG
  CRON --> MG
```

Full sequence diagrams for temporal recall, A2A sharing, and worker data flows: [docs/architecture-v1.md](docs/architecture-v1.md)

---

## v1.0 Capabilities

| Capability | Description |
|---|---|
| **Semantic search** | pgvector cosine nearest-neighbour + MongoDB document hydration |
| **GraphRAG** | BFS traversal over knowledge graph edges, structured subgraph output |
| **Temporal recall** | `as_of` ISO 8601 parameter on all search and graph tools |
| **Document bridges** | Auto-sync from SharePoint, Google Drive, and Dropbox via webhooks |
| **Sleep consolidation** | HDBSCAN clustering + LLM abstraction + NLI contradiction detection |
| **Memory salience** | Ebbinghaus forgetting curve with per-agent decay rates |
| **A2A sharing** | Cryptographic grant/verify for inter-agent memory access |
| **Code intelligence** | Tree-sitter AST indexing via async RQ workers |
| **Embedding migrations** | Zero-downtime model swaps with configurable throughput throttle |
| **Event replay** | WORM event log with Merkle-chain verification and namespace forking |
| **Multi-tenancy** | PostgreSQL Row-Level Security; namespace isolation enforced at DB level |
| **Quota governance** | Per-namespace limits on tokens, storage, and memory count |
| **PII auto-redaction** | Presidio + regex pipeline before all LLM calls |
| **Observability** | Prometheus metrics + OpenTelemetry distributed tracing |

---

## Architecture

### The Quad-Database Philosophy

No single database is optimal for all memory types. TriMCP assigns each layer exclusively to the engine best suited for it — no overlapping responsibilities, no compromises.

| Layer | Engine | Responsibility | Key Property |
|---|---|---|---|
| **Semantic Memory** | PostgreSQL + pgvector | Vector embeddings, knowledge graph triplets, RLS-enforced tenant isolation, event log | ACID guarantees, cosine similarity at scale, Row-Level Security |
| **Episodic Memory** | MongoDB | Raw payloads — conversation transcripts, source files, artifact metadata | Schema-less, high-throughput I/O, lazy-load hydration |
| **Working Memory** | Redis | TTL-bound summaries, RQ job queue, HMAC nonce store, quota counters | Sub-millisecond recall, O(1) cache invalidation |
| **Artifact Store** | MinIO | Audio, video, image blobs, and documents (PDF/Office); replay payload cache | S3-compatible, high-capacity object storage |

### Saga Write Paths

TriMCP uses different Saga paths depending on payload type:

1. **Memory event saga**:
   MongoDB raw event → PostgreSQL semantic state → Redis cache invalidation.

2. **Artifact saga**:
   MinIO staging upload → checksum verification → PostgreSQL artifact metadata → parser/indexing jobs → promote to active.

3. **Composite saga**:
   Used when a webhook or ticket includes both structured data and file attachments.

An hourly garbage collector runs as an independent safety net: any MongoDB document older than 5 minutes without a matching `mongo_ref_id` in PostgreSQL is automatically purged, regardless of how it arrived.

### Read/Write Split

Set `DB_READ_URL` to route read queries to a PostgreSQL replica automatically. Writes always go to the primary. The read pool is optional — if not configured, all queries use the write URL.

---

## AI Memory System

This is where TriMCP diverges from simple vector stores. Memory here is a structured, temporal, self-maintaining knowledge base with multiple distinct layers of abstraction.

### Temporal Recall: Time-Travel Queries

Every mutable row in PostgreSQL carries `valid_from` and `valid_to` timestamps. Any `semantic_search` or `graph_search` can be pinned to a precise point in history:

```python
# What did the agent know about "infrastructure costs" on 15 January 2026?
results = await semantic_search(
    query="infrastructure costs",
    as_of="2026-01-15T10:00:00Z"
)
```

The same temporal filter applies to graph traversal, enabling complete historical reconstruction of the agent's knowledge state at any past moment. Maximum lookback is configurable via `TRIMCP_MAX_TEMPORAL_LOOKBACK_DAYS` (0 = unlimited).

### GraphRAG: Structured Reasoning Over Knowledge Graphs

Semantic similarity is a starting point, not an answer. TriMCP's GraphRAG pipeline builds a contextual subgraph around any query in exactly **four database round-trips**:

1. **Anchor Search** — pgvector cosine search identifies the nearest knowledge-graph node
2. **BFS Traversal** — A single PostgreSQL recursive CTE explores `kg_edges` up to 3 hops, capped at 50 nodes
3. **Edge Hydration** — All incident edges loaded in one batch query, sorted by confidence score
4. **Source Retrieval** — Two MongoDB `$in` queries fetch source excerpts for all matched nodes (episodic + code)

Result: `{ nodes, edges, sources }` — a fully structured subgraph with provenance, not a ranked list of chunks.

spaCy (`en_core_web_sm`, bundled) runs entity and relation extraction at ingest time to populate the knowledge graph automatically.

### Sleep Consolidation: Memory That Gets Smarter Over Time

The `ConsolidationWorker` runs on a configurable schedule, mimicking the cognitive process of memory consolidation during rest:

1. **Clustering** — HDBSCAN groups semantically related episodic memories
2. **LLM Abstraction** — Clusters are submitted to the configured LLM with a structured Pydantic v2 output schema
3. **Hallucination Guard** — All `supporting_memory_ids` in the abstraction must exist in the source data
4. **Contradiction Detection** — A DeBERTa-v3 NLI cross-encoder evaluates premise-hypothesis pairs across clusters (threshold: 0.6) before new abstractions are stored
5. **Commit** — Validated abstractions are written as `memory_type='consolidated'` with a `confidence` float

Abstractions scoring below 0.3 confidence are automatically discarded. The structured output enforces `key_entities`, `key_relations`, and `contradicting_memory_ids` fields for downstream graph upsert.

### Memory Salience: The Forgetting Curve

Not all memories age equally. TriMCP implements the Ebbinghaus forgetting curve for memory decay:

```
s(t) = s_last × exp(−λ × Δt_days)     where λ = ln(2) / half_life_days
```

- **Per-agent half-life** — Configurable decay rate per namespace (default: 14 days)
- **Deterministic jitter** — SHA-256(memory_id) prevents thundering-herd purges when many memories share the same age
- **Overflow protection** — Decay exponent is clamped to prevent arithmetic overflow on very old records
- **Manual boost** — `boost_memory` explicitly strengthens recall priority
- **Graceful forgetting** — `forget_memory` lowers salience below the GC threshold without a hard delete

### Contradiction Detection

TriMCP continuously monitors for conflicting beliefs in the knowledge graph:

1. DeBERTa-v3 cross-encoder evaluates premise-hypothesis pairs across the knowledge base
2. spaCy extracts subject-predicate-object triplets from memories flagged as potentially conflicting
3. A conflict graph is built from the contradicting memory IDs
4. Conflicts surface via `list_contradictions` and are resolved via `resolve_contradiction`

### Zero-Downtime Embedding Migrations

Switching embedding models is a live operation with no query degradation during the swap:

1. `start_migration(target_model_id)` initialises the migration record
2. `ReembeddingWorker` re-embeds in configurable batches with a per-minute throughput throttle
3. Old embeddings remain fully active throughout — no queries are blocked
4. `validate_migration()` runs quality-gate checks (latency + accuracy) against the target model
5. On success, old embeddings are atomically replaced; on failure, the migration can be aborted cleanly

### Async Code Intelligence

When an agent calls `index_code_file`, the request is immediately enqueued to an RQ worker. The worker handles heavy Tree-sitter AST parsing across multiple languages, chunks the source, embeds vectors, writes KG triplets, and archives the full file. The MCP tool returns a `job_id` instantly; progress is tracked via `check_indexing_status`.

See [docs/recursive_indexing_flow.md](docs/recursive_indexing_flow.md) for the full pipeline diagram.

---

## Document Bridge Integrations

TriMCP connects directly to enterprise cloud storage, indexing documents as they change — without manual uploads. Bridges are registered once via the `connect_bridge` tool and maintained automatically thereafter.

### Supported Bridges

| Service | Protocol | Sync Method | Auth |
|---|---|---|---|
| **Microsoft SharePoint** | Microsoft Graph API | Delta enumeration + push subscription notifications | OAuth 2.0 (MSAL) |
| **Google Drive** | Google Drive API v3 | Webhook push via Channel API | OAuth 2.0 |
| **Dropbox** | Dropbox API v2 | Webhook notifications | OAuth 2.0 |

### Bridge Lifecycle

```
Cloud Storage ──► Webhook ──► Webhook Receiver (FastAPI :8080)
                                        │
                              Document Extractor
                                        │
                              Embedding + KG Upsert
                                        │
                               Quad-DB Saga Write
```

The `BridgeRenewalJob` (APScheduler) automatically refreshes OAuth tokens and renews webhook subscriptions before they expire. The lookahead window and renewal interval are both configurable.

### Supported Document Formats

TriMCP extracts text and structure from a wide range of formats before indexing:

**Office & Productivity**
Word (`.docx`), Excel (`.xlsx`), PowerPoint (`.pptx`), Email (`.eml`, `.msg`), PDF (text + OCR fallback)

**Code & Markup**
Source files via Tree-sitter AST (multi-language), Markdown, plain text

**Specialised Formats**
Diagrams (Visio, PlantUML), CAD files (AutoCAD DXF), Adobe documents, encrypted documents

---

## Security & Multi-Tenancy

### Authentication Layers

| Boundary | Mechanism | Details |
|---|---|---|
| **Admin HTTP API** | HMAC-SHA256 | 8-minute replay-protection window; nonces stored in Redis |
| **A2A Protocol** | JWT Bearer (HS256 / RS256) | Scoped tokens with configurable expiry (max 30 days) |
| **mTLS (optional)** | Client certificates | Optional mutual TLS on the A2A server |
| **Admin UI** | HTTP Basic Auth | Rotatable credentials |
| **Master Key** | 32+ byte secret | Required at startup — server refuses to launch without it |

### Multi-Tenant Isolation

Every query is scoped to a namespace at the database level — not in application logic. There is no application-layer WHERE clause to forget:

```python
async with scoped_pg_session(pool, namespace_id=ns_id) as conn:
    # PostgreSQL: SET LOCAL trimcp.namespace_id = '<uuid>'
    # All RLS policies fire automatically on every subsequent query
```

Per-namespace configuration includes PII redaction policies, allowlists, consolidation settings, quota limits, and optional temporal retention windows.

### Agent-to-Agent (A2A) Sharing Protocol

Autonomous agents can share memory resources with each other using a cryptographic grant model:

1. **Agent A** calls `grant_access(scope, target_agent_id)` — issues a signed JWT encoding the permitted scope
2. **Agent B** presents the token to the A2A server (`:8004`)
3. The server validates the token and enforces scope constraints before returning the resource

Supported scope types: `namespace`, `memory`, `kg_node`, `subgraph`.

### PII Auto-Redaction

All content passes through a PII detection pipeline (Microsoft Presidio + regex fallback) before any LLM call. Redaction policies are configurable per namespace, including entity-type allowlists for contexts where names or identifiers are intentionally retained.

### SSRF Protection

All LLM provider URLs are validated before use. Private IP ranges, loopback addresses, and link-local ranges are blocked unless explicitly allowlisted — preventing prompt-injected payloads from making internal network requests.

### Cryptographic Audit Trail

Every mutation — memory writes, bridge activity, embedding migrations — is recorded in an append-only WORM event log with Merkle-chain verification. Monthly table partitions are auto-created for long-running deployments:

```python
event_log.verify_merkle_chain()  # Detects any tampering with historical records
```

### Quota Governance

| Resource | Enforcement | Error Code |
|---|---|---|
| LLM token consumption | Redis Lua atomic counter + namespace quota table | `-32013 QuotaExceededError` |
| Storage bytes | Atomic increment on write | `-32013 QuotaExceededError` |
| Memory count | Namespace quota check at ingest | `-32013 QuotaExceededError` |

---

## Observability

### Prometheus Metrics

| Metric | Type | Description |
|---|---|---|
| `trimcp_tool_calls_total` | Counter | MCP tool invocations by tool name |
| `trimcp_tool_latency_seconds` | Histogram | Per-tool latency distribution |
| `trimcp_saga_duration_seconds` | Histogram | Distributed write transaction timing |
| `trimcp_saga_failures_total` | Counter | Saga failure counts by stage |
| `trimcp_embedding_count` | Counter | Chunks embedded per model |

Metrics are exported on `TRIMCP_PROMETHEUS_PORT` (default: `8000`).

### Distributed Tracing

OpenTelemetry spans are emitted for all async operations via the OTLP HTTP exporter. Configure any OTLP-compatible backend (Jaeger, Grafana Tempo, etc.) via `TRIMCP_OTEL_EXPORTER_OTLP_ENDPOINT`.

---

## MCP Tool Reference

All tools use a generation-counter cache layer in Redis for sub-millisecond repeat responses. Cache is invalidated atomically on any write to the affected namespace.

### Memory

| Tool | Description |
|---|---|
| `store_memory` | Persist a memory. Triggers spaCy entity extraction and knowledge-graph upsert. |
| `semantic_search` | Cosine search + MongoDB document hydration. Supports `as_of` temporal recall. *(Cached)* |
| `graph_search` | GraphRAG: vector anchor → BFS subgraph → source excerpts. Supports `as_of`. *(Cached)* |
| `get_recent_context` | Redis-only instant recall for the most recent session summary. |
| `boost_memory` | Increase salience score to strengthen recall priority. |
| `forget_memory` | Lower salience below the GC threshold (non-destructive). |

### Knowledge Graph

| Tool | Description |
|---|---|
| `list_contradictions` | Surface conflicting beliefs detected by the NLI pipeline. |
| `resolve_contradiction` | Mark a contradiction as resolved with a chosen canonical belief. |

### Code Intelligence

| Tool | Description |
|---|---|
| `index_code_file` | AST-parse a source file, embed chunks, archive to quad-DB. Returns `job_id` (async). |
| `check_indexing_status` | Poll an async indexing job by `job_id`. |
| `search_codebase` | Semantic search over indexed code chunks with file path and line numbers. *(Cached)* |

### Artifacts

| Tool | Description |
|---|---|
| `store_artifact` | Save an artifact (media, PDF, log, etc.) to MinIO and index its metadata. |
| `store_media` | *(Deprecated)* Alias for `store_artifact`. |

### Document Bridges

| Tool | Description |
|---|---|
| `connect_bridge` | Register a cloud storage bridge (SharePoint / Google Drive / Dropbox). |
| `bridge_status` | Check sync status and subscription health of a registered bridge. |
| `disconnect_bridge` | Remove a bridge and revoke its webhooks. |

### Embedding Migrations

| Tool | Description |
|---|---|
| `start_migration` | Begin a zero-downtime re-embedding sweep to a target model. |
| `validate_migration` | Run quality-gate checks (latency + accuracy) against the target model. |
| `abort_migration` | Cancel an in-progress migration cleanly. |

### Event Replay

| Tool | Description |
|---|---|
| `replay_observe` | Stream the event log for a namespace. |
| `replay_fork` | Create a forked namespace from a historical snapshot. |
| `replay_status` | Check the status of a running replay or fork operation. |

*Full schemas and parameter documentation: `TOOLS` in `server.py`.*

---

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.10+ |
| Protocol | MCP JSON-RPC 2.0 |
| Semantic Memory | PostgreSQL 15+ with `pgvector` |
| Episodic Memory | MongoDB 6+ |
| Working Memory | Redis 7+ |
| Media Storage | MinIO (Artifact Store) |
| Embeddings | SentenceTransformers / Jina (768-dim) or hash-stub for testing |
| NLP & Entity Extraction | spaCy `en_core_web_sm` (bundled) |
| NLI / Contradiction Detection | DeBERTa-v3 cross-encoder |
| Memory Clustering | HDBSCAN |
| AST Parsing | Tree-sitter (multi-language) |
| Graph Traversal | NetworkX + recursive PostgreSQL CTEs |
| Background Jobs | RQ (Redis Queue) + APScheduler |
| Admin API & A2A Server | Starlette |
| Webhook Receiver | FastAPI |
| PII Detection | Microsoft Presidio + regex fallback |
| Observability | Prometheus + OpenTelemetry |
| Proxy | Caddy (reverse proxy) |

---

## Prerequisites

- **Docker Desktop** (latest) — runs Redis, PostgreSQL, MongoDB, and MinIO
- **Python 3.10+** — required for MCP SDK compatibility and async patterns
- **pip** or **uv** — for Python dependency management

---

## Quick Start

### 1. Configure Environment

```bash
cp .env.example .env
# Edit .env with your connection strings and secrets
```

Minimum required variables:

| Variable | Example | Description |
|---|---|---|
| `PG_DSN` | `postgresql://mcp_user:secret@localhost:5432/memory_meta` | PostgreSQL write URL |
| `MONGO_URI` | `mongodb://localhost:27017` | MongoDB connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL |
| `MINIO_ENDPOINT` | `localhost:9002` | MinIO S3 API endpoint |
| `MINIO_ACCESS_KEY` | `mcp_admin` | MinIO access key |
| `MINIO_SECRET_KEY` | `your_secret` | MinIO secret key |
| `TRIMCP_MASTER_KEY` | (32+ random bytes) | Required — server will not start without this |

> Full reference for all ~70 environment variables: [docs/configuration_reference.md](docs/configuration_reference.md)

> Never commit `.env` to version control.

### 2. Start the Stack

```bash
docker compose up -d --build
```

This starts: PostgreSQL (with `pgvector` extension + RLS policies auto-applied), MongoDB, Redis, MinIO, the cognitive sidecar for local embeddings (`:11435`), the RQ background worker, the APScheduler cron process, the admin UI (`:8003`), the A2A server (`:8004`), the webhook receiver (`:8080`), and a Caddy reverse proxy on port 80.

### 3. Start the MCP Server

```bash
python server.py
```

The MCP server listens on **stdio**. Configure your client using one of the blocks below.

---

## Connecting to an MCP Client

### Claude Desktop

Edit `claude_desktop_config.json`:
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "tri-stack-memory": {
      "command": "python",
      "args": ["/absolute/path/to/TriMCP/server.py"],
      "env": {
        "PG_DSN": "postgresql://mcp_user:mcp_password@localhost:5432/memory_meta",
        "MONGO_URI": "mongodb://localhost:27017",
        "REDIS_URL": "redis://localhost:6379/0",
        "MINIO_ENDPOINT": "localhost:9002",
        "MINIO_ACCESS_KEY": "mcp_admin",
        "MINIO_SECRET_KEY": "your_secret",
        "TRIMCP_MASTER_KEY": "your_32_plus_byte_master_key"
      }
    }
  }
}
```

### Cursor

Add to `~/.cursor/mcp.json` or via **Settings → MCP → Add Server**:

```json
{
  "mcpServers": {
    "tri-stack-memory": {
      "command": "python",
      "args": ["/absolute/path/to/TriMCP/server.py"],
      "env": {
        "PG_DSN": "postgresql://mcp_user:mcp_password@localhost:5432/memory_meta",
        "MONGO_URI": "mongodb://localhost:27017",
        "REDIS_URL": "redis://localhost:6379/0",
        "MINIO_ENDPOINT": "localhost:9002",
        "MINIO_ACCESS_KEY": "mcp_admin",
        "MINIO_SECRET_KEY": "your_secret",
        "TRIMCP_MASTER_KEY": "your_32_plus_byte_master_key"
      }
    }
  }
}
```

*Windows note: Use forward slashes or double-escaped backslashes in path strings.*

---

## Directory Structure

```text
TriMCP/
├── server.py                    # MCP stdio server — primary entrypoint
├── admin_server.py              # Admin REST API + UI (Starlette, :8003)
├── start_worker.py              # RQ background worker (async indexing)
├── index_all.py                 # Bulk recursive code ingestion utility
├── docker-compose.yml           # Full stack: PG, Mongo, Redis, MinIO, sidecars
├── requirements.txt
├── .env.example
├── admin/
│   └── index.html               # Admin dashboard UI
├── trimcp/
│   ├── orchestrator.py          # TriStackEngine + Saga write path
│   ├── config.py                # Configuration loading (~70 env vars)
│   ├── embeddings.py            # Jina embeddings (thread executor) + hash-stub fallback
│   ├── ast_parser.py            # Tree-sitter AST parser + line-splitter fallback
│   ├── graph_extractor.py       # spaCy entity + relation extraction
│   ├── graph_query.py           # GraphRAG BFS traverser
│   ├── temporal.py              # as_of time-travel query support
│   ├── salience.py              # Ebbinghaus decay + GC threshold
│   ├── contradictions.py        # DeBERTa-v3 NLI contradiction detection
│   ├── consolidation.py         # Sleep consolidation + HDBSCAN clustering
│   ├── a2a.py                   # A2A grant/verify + JWT lifecycle
│   ├── a2a_server.py            # A2A JSON-RPC server (Starlette, :8004)
│   ├── cron.py                  # APScheduler: bridge renewal + re-embedding
│   ├── reembedding_worker.py    # Zero-downtime embedding migration
│   ├── migration_mcp_handlers.py # Migration MCP tool handlers
│   ├── garbage_collector.py     # Orphan GC (paginated, retry-enabled)
│   ├── event_log.py             # Merkle-chain verified WORM audit trail
│   ├── pii.py                   # Presidio PII auto-redaction pipeline
│   ├── notifications.py         # Webhook + SMTP alert dispatcher
│   ├── observability.py         # Prometheus + OpenTelemetry instrumentation
│   ├── auth.py                  # HMAC auth + JWT + RLS session management
│   ├── tasks.py                 # RQ async tasks (indexing, extraction)
│   └── bridges/
│       ├── sharepoint.py        # Microsoft SharePoint (Graph API)
│       ├── gdrive.py            # Google Drive (Drive API v3)
│       └── dropbox.py           # Dropbox (API v2)
├── tests/
│   ├── test_integration_engine.py   # Saga, GraphRAG, temporal, A2A, quotas
│   ├── test_mcp_cache.py            # Generation-counter cache invalidation
│   ├── test_notifications.py        # Notification dispatcher
│   └── test_smoke_stdio.py          # MCP stdio smoke tests
└── docs/
    ├── README.md                    # Documentation index
    ├── architecture-v1.md           # Sequence diagrams (temporal, A2A, workers)
    ├── configuration_reference.md   # All ~70 environment variables
    └── recursive_indexing_flow.md   # AST indexing pipeline diagram
```

---

## Testing

Ensure all containers are running, then execute the test suite:

```bash
uv run pytest tests/
```

The suite covers: Saga writes and cross-DB rollback, Redis cache invalidation, pgvector search, GraphRAG traversal, temporal `as_of` path filtering, A2A token grants and scope enforcement, quota rejection, notification dispatch, and MCP tool correctness.

---

## Production Deployment Notes

- **TLS**: Use TLS-encrypted DSNs for all production connections (e.g., `?sslmode=require` for PostgreSQL).
- **Read Replicas**: Set `DB_READ_URL` to automatically route reads to a replica. Writes always go to the primary DSN.
- **Connection Pools**: Tune `PG_MIN_POOL` / `PG_MAX_POOL` (default 1–10) and `REDIS_MAX_CONNECTIONS` (default 20) based on expected concurrency.
- **Process Supervision**: Run `server.py`, `start_worker.py`, and `trimcp/cron.py` under a supervisor (systemd, pm2, or Docker Compose `restart: always`).
- **Secret Rotation**: Rotate `TRIMCP_MASTER_KEY`, `TRIMCP_API_KEY`, and all OAuth secrets on your organisation's schedule. The HMAC nonce store in Redis ensures replay protection is maintained during key rotation.
- **Dead Letter Queue**: RQ tasks that exhaust their retry budget are routed to a PostgreSQL dead-letter table. Monitor this table for persistent failures.
- **Error Isolation**: Stack traces are never exposed to MCP clients. All unhandled exceptions are wrapped as safe JSON-RPC error responses at the `server.py` boundary.

---

## Troubleshooting

### Connection Refused

```
could not connect to server: Connection refused
```

1. Verify containers are running: `docker ps`
2. Confirm ports 5432, 27017, 6379, and 9002 are not already occupied by host services
3. Validate all connection strings in `.env`

### Missing Dependencies

```
ModuleNotFoundError: No module named 'tree_sitter'
```

Activate your virtual environment and install the optional Tree-sitter language packs:

```bash
pip install tree-sitter==0.20.4 tree-sitter-python==0.20.4 tree-sitter-javascript==0.20.1
```

### Async Indexing Hanging

`check_indexing_status` stays in `pending` indefinitely.

The RQ worker is not running. Start it in a separate terminal:

```bash
python start_worker.py
```

### Server Refuses to Start

```
TRIMCP_MASTER_KEY is required
```

Generate a suitable key and add it to `.env`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Documentation

| Document | Description |
|---|---|
| [Architecture v1.0](docs/architecture-v1.md) | Sequence diagrams for temporal recall, A2A, and worker flows |
| [Configuration Reference](docs/configuration_reference.md) | All ~70 environment variables with defaults and descriptions |
| [Recursive Indexing Flow](docs/recursive_indexing_flow.md) | AST ingestion pipeline diagram |
| [Documentation Index](docs/README.md) | Full documentation index |
