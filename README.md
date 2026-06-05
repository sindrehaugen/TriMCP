# NCE — Enterprise-Grade AI Memory Layer

NCE is an **MCP-native memory engine** for autonomous agents: a **quad-database** stack (PostgreSQL + pgvector, MongoDB, Redis, MinIO) with a **Saga**-style write path, **temporal** recall (`as_of` time-travel on semantic and graph search), **A2A** scoped sharing between agents, and **background workers** for re-embedding, bridge renewal, and GC. This repository ships **release 2.0.0** (`pyproject.toml`) with a **v1.0 integration surface** in `server.py`, `admin_server.py`, `nce/a2a_server.py`, and `nce/cron.py`.

Longer-horizon roadmap items (universal installers, 300+ language packs, broad format extraction) live in the innovation roadmap; deploy today **from source** with Docker Compose per [deploy/README.md](deploy/README.md).

## v1.0 capabilities

- **Semantic search & GraphRAG**: pgvector nearest-neighbor search, MongoDB hydration, BFS over `kg_edges` with structured subgraphs. Includes automated spaCy entity extraction (bundled).
- **Zero-Config Deployment**: Automated PostgreSQL schema initialization with extensions (vector, pgcrypto) and mandatory Row Level Security (RLS) policies.
- **Temporal queries**: Optional **`as_of`** (ISO 8601) on `semantic_search` and `graph_search` via `nce/temporal.py` and orchestrator filters.
- **A2A protocol**: Grant/verify token flow and JSON-RPC skills on **`nce/a2a_server.py`** (`nce/a2a.py`, `a2a_grants` table).
- **Quotas & auth**: Namespace-scoped consumption and HMAC-aware admin API patterns with deep v1.0 health monitoring.
- **Cognitive workers**: **`python -m nce.cron`** — APScheduler jobs for **document-bridge renewal** and **`ReembeddingWorker`** sweeps; **`ConsolidationWorker`** (`nce/consolidation.py`) for sleep-style abstraction (integrate with your scheduler); MCP startup runs **orphan GC** (`run_gc_loop`).
- **MCP tools**: Memory, media, code indexing (RQ async), bridges, salience, contradictions, embedding migration, **replay** (`replay_observe` / `replay_fork` / `replay_status`), and more — see `TOOLS` in `server.py`.
- **Quad-DB + Saga**: Mongo payload → Postgres vectors/KG, with rollback on failure; see diagram below.

## v1.0 architecture (MCP, temporal, A2A, workers)

```mermaid
flowchart TB
  subgraph Clients
    IDE[MCP clients]
  end
  subgraph Entrypoints
    STDIO[server.py MCP stdio]
    A2A[a2a_server.py skills]
    ADM[admin_server.py REST]
    CRON[cron.py scheduler]
    RQ[start_worker.py RQ]
  end
  subgraph Data
    PG[(Postgres pgvector)]
    MG[(MongoDB)]
    RD[(Redis)]
    S3[(MinIO)]
  end
  subgraph Cross_cutting["Cross-cutting"]
    TMP["temporal.parse_as_of"]
    TSE[TriStackEngine]
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

Full diagrams (sequence charts for temporal + A2A, worker data flow): [docs/architecture-v1.md](docs/architecture-v1.md).

**Documentation index**: [docs/README.md](docs/README.md) — architecture, database internals, security, service integrations, configuration reference, and developer onboarding.

## 🛠️ Tech Stack

- **Language**: Python 3.10+ (required by `pyproject.toml` and the MCP SDK stack)
- **Protocol**: MCP (Model Context Protocol) JSON-RPC 2.0
- **Working Memory & Queues**: Redis
- **Semantic Memory**: PostgreSQL with `pgvector`
- **Episodic Memory**: MongoDB
- **Media Storage**: MinIO
- **Embeddings**: SentenceTransformers (Jina 768-dim) or Hash Stub
- **AST Parsing**: Tree-sitter
- **GraphRAG**: spaCy (Entity Extraction) / NetworkX (or custom BFS)

## 📋 Prerequisites

- **Docker Desktop** (Latest) - To run the Redis, PostgreSQL, MongoDB, and MinIO containers.
- **Python 3.10+** — matches `requires-python` in `pyproject.toml`.
- **pip** - For managing Python dependencies.

Pinned transitive versions for reproducible installs live in **`requirements.lock`** (regenerate with `make lockfile` or `python scripts/compile_requirements.py` after editing `requirements.txt`).

## 🚀 Quick Start

For **v1.0**, run from this repository: start the **Compose** stack (see [deploy/README.md](deploy/README.md)), configure `.env`, then launch `server.py` and workers as needed. Optional packaged installers remain on the **product roadmap**; multi-mode install flows below describe the target operator experience once shipping.

### 1. Environment & deployment mode (reference)

- **Local**: Quad-DB via Docker on one machine (default dev path).
- **Multi-user**: Shared Postgres/Mongo/Redis/MinIO; enforce namespace isolation and auth in production.
- **Cloud**: Managed databases and object storage; same codebase, different connection strings.

### 2. Environment Configuration

Copy the environment template and fill in your values:

```bash
cp .env.example .env
```

Minimum variables for local development:

| Variable | Example | Notes |
|---|---|---|
| `PG_DSN` | `postgresql://mcp_user:mcp_password@localhost:5432/memory_meta` | Required |
| `MONGO_URI` | `mongodb://localhost:27017` | Required |
| `REDIS_URL` | `redis://localhost:6379/0` | Required |
| `MINIO_ENDPOINT` | `localhost:9000` | Required |
| `MINIO_ACCESS_KEY` | `mcp_admin` | Required — no default in production |
| `MINIO_SECRET_KEY` | `your_secret` | Required — no default in production |
| `NCE_MASTER_KEY` | 32+ random bytes | Required — server refuses to start without it |
| `NCE_MCP_API_KEY` | long random secret | Required in production for MCP stdio tenant tools (`mcp_api_key` argument) |
| `NCE_MCP_NAMESPACE_ID` | UUID | Required in production when `NCE_MCP_API_KEY` is set — binds stdio tenant tools to one namespace |
| `NCE_ADMIN_API_KEY` | long random secret | Required in production for MCP admin tools (`admin_api_key` argument) |

For Cursor/Claude, copy [mcp_config.json.example](mcp_config.json.example) to `mcp_config.json` (gitignored) and set both keys in the `env` block.

For the complete reference of all ~70 environment variables, see [docs/configuration_reference.md](docs/configuration_reference.md).

*Never commit `.env` or `mcp_config.json` to version control.*

### 3. Start the Server

In development, start the **RQ worker** (`start_worker.py`) and **MCP server** separately (or use your process supervisor). MCP listens on stdio:

```bash
python server.py
```

## 🧠 Architecture Deep-Dive

For **temporal**, **A2A**, and **background worker** sequence diagrams, use **[docs/architecture-v1.md](docs/architecture-v1.md)**. The following sections summarise the quad-DB and saga contracts.

NCE is built to treat memory as distinct layers with strict boundaries and absolute rollback guarantees. 

### The Quad-DB Philosophy

Each database is assigned exclusively to the data structure it is optimal for — no overlapping responsibilities:

| Layer | Database | Role | Key Property |
|---|---|---|---|
| **Working Memory & Cache** | Redis | TTL-bound summary cache, RQ, and API cache | Sub-millisecond recall, O(1) cache invalidation |
| **Semantic Index** | PostgreSQL + pgvector | Vector embeddings + KG triplets | ACID guarantees, cosine similarity search |
| **Episodic Archive** | MongoDB | Raw heavy payloads (transcripts, source files) | Schema-less, high-throughput I/O |
| **Media Store** | MinIO | Audio, Video, Image blob storage | High capacity object storage |

### Saga Pattern Guarantee

When a memory or file is ingested, the `TriStackEngine` employs the Saga pattern to guarantee data purity across the stack. If an error occurs in Postgres, MongoDB is automatically rolled back.

```text
Mongo ──► PG ──► Redis
            │
         FAILURE
            │
            └──► DELETE Mongo doc  ← automatic, synchronous
                 RAISE exception   ← propagates to caller
```

The `garbage_collector.py` runs hourly as an independent safety net: any MongoDB document older than 5 minutes with no matching `mongo_ref_id` in PostgreSQL is automatically purged.

### Recursive AST Indexing & Background Processing

NCE can autonomously ingest its own codebase. When an LLM agent calls the `index_code_file` tool, the request is instantly enqueued to an asynchronous Redis Queue (RQ) worker (`start_worker.py`). The worker handles the heavy AST parsing (via Tree-sitter) to split the source into chunks, stores the raw payload in Mongo, embeds vectors/KG triplets in Postgres, and updates the working context in Redis. The MCP tool immediately returns a `job_id` to the LLM to track progress via `check_indexing_status`.

See the [Recursive Indexing Flow Diagram](docs/recursive_indexing_flow.md) and [v1.0 architecture](docs/architecture-v1.md) (temporal, A2A, cognitive workers).

### Advanced GraphRAG Layer

NCE implements a state-of-the-art GraphRAG pipeline:
1. The query undergoes a pgvector cosine search to find the nearest **anchor knowledge graph node**.
2. A **BFS traversal** executes over `kg_edges` (up to 3 hops, max 50 nodes).
3. The engine **hydrates source documents** from MongoDB (e.g., 600-character excerpts) mapped to the nodes.
4. Returns a highly structured subgraph context: `{ nodes, edges, sources }`.

## 📂 Directory Structure

```text
NCE/
├── docker-compose.yml       # Redis, PostgreSQL/pgvector, MongoDB, MinIO
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variable template
├── start_worker.py          # Background worker (RQ) for async indexing
├── index_all.py             # Bulk recursive code ingestion
├── server.py                # MCP stdio server
├── admin_server.py          # Admin UI & Observability
├── admin/
│   └── index.html           # Admin dashboard UI
├── nce/
│   ├── __init__.py
│   ├── orchestrator.py      # Core Saga engine + Quad-Stack connections
│   ├── config.py            # Configuration loading
│   ├── embeddings.py        # Jina embeddings (thread executor + stub fallback)
│   ├── ast_parser.py        # Tree-sitter AST parser + line-splitter fallback
│   ├── graph_extractor.py   # Entity + relation extraction (spaCy / regex)
│   ├── graph_query.py       # GraphRAG BFS traverser
│   ├── temporal.py          # as_of parsing (time-travel queries)
│   ├── a2a.py               # Agent-to-agent grants + token verify
│   ├── a2a_server.py        # A2A JSON-RPC / Starlette app
│   ├── cron.py              # Bridge renewal + re-embedding scheduler
│   ├── reembedding_worker.py # Batch re-embed sweep
│   ├── consolidation.py    # Sleep / cluster consolidation (LLM)
│   ├── garbage_collector.py # Orphan GC (paginated, retry-enabled)
│   ├── notifications.py     # Webhook / alert notification dispatcher
│   └── tasks.py             # RQ async tasks and indexing logic
├── tests/
│   ├── __init__.py
│   ├── test_integration_engine.py  # End-to-end integration tests
│   ├── test_mcp_cache.py           # API Caching logic testing
│   ├── test_notifications.py       # Notification dispatcher tests
│   └── test_smoke_stdio.py         # Smoke testing for Stdio MCP
└── docs/                    # Architectural diagrams and documentation
```

## 🔌 MCP Tool Reference

NCE exposes the following tools directly to LLM clients via JSON-RPC 2.0, utilizing a highly efficient API cache layer with generation-counter invalidation:

| Tool | Description |
|---|---|
| `store_memory` | Persist a memory to the DB stack. Triggers entity extraction and KG upsert. |
| `store_media` | Save a media payload (MinIO) and index its metadata into the memory stack. |
| `semantic_search` | Cosine search + Mongo hydration; optional **`as_of`** for temporal recall. *(Cached)* |
| `index_code_file` | AST-parse a source file into chunks, embed each chunk, archive the full file. Returns `job_id` asynchronously. |
| `check_indexing_status` | Check the progress of an async indexing job using its `job_id`. |
| `search_codebase` | Semantic search over indexed code chunks, returning file path and exact line numbers. *(Cached)* |
| `graph_search` | GraphRAG: vector anchor → BFS subgraph → excerpts; optional **`as_of`**. *(Cached)* |
| `get_recent_context`| Redis-only instant recall for the most recent session summary. |
| `connect_bridge` … `bridge_status` | Document bridge OAuth and lifecycle (SharePoint / Google Drive / Dropbox). |
| `boost_memory` / `forget_memory` | Salience tuning (per agent). |
| `list_contradictions` / `resolve_contradiction` | Contradiction workflow. |
| `start_migration` … `abort_migration` | Embedding model migration controls. |
| `replay_observe` / `replay_fork` / `replay_status` | Event-log replay and forked namespaces. |
| `a2a_create_grant` / `a2a_revoke_grant` / `a2a_list_grants` | Basic agent sharing grant administration. |
| `a2a_verify_grant_status` | Verify the validity, scopes, status, and expiration of a grant by token/ID. |
| `a2a_update_grant_scopes` | Dynamically mutate scopes on an active grant (replace or append strategy). |
| `a2a_inspect_grant` | Retrieve metadata for a single grant safely for audit compliance (cryptographically secure). |

*Full list and schemas: `TOOLS` in `nce/mcp_stdio_tools.py`.*

## 🎛️ Dynamic Tools Control Console & Interceptor Routing

NCE features an **Enterprise-Grade Admin Tools Console** integrated directly into the Starlette Admin panel. This console allows IT administrators to dynamically enable and disable specific local stdio MCP tools and public A2A server skills at runtime with zero system downtime.

### Architecture & Propagation
1. **Dynamic State Persistence**: Toggling a tool's state dynamically publishes and persists the value within a Redis hash named `nce:tools:disabled`.
2. **Real-time Routing Interceptors**:
   - **Stdio MCP Transport**: Custom middleware intercepts invocations in `mcp_stdio_dispatch.py`. If a tool is flagged as disabled, the server rejects it instantly, returning JSON-RPC error code `-32005` (Scope forbidden).
   - **Agent-to-Agent (A2A) Skill Server**: Inbound network skills are intercepted inside `a2a_server.py`. If a skill is disabled, the request is rejected with RPC code `-32011` / HTTP 403 (Scope violation).
3. **High-Availability Resiliency**: In the event of a Redis outage or fallback, the interceptor defaults to "enabled" (no-op pass-through) to guarantee high availability and prevent downstream microservice cascading failures.

### Admin API Endpoints
- `GET /api/admin/tools`: Retrieve a list of all MCP tools and A2A network skills, including localized operational impact descriptions, descriptions, and toggle states.
- `POST /api/admin/tools/toggle`: Persist the state mutation (`tool_name`, `tool_type`, `enabled`) to the Redis registry.

## 🔗 Connecting to an LLM Client

The MCP server block is identical across all clients. Here are common configurations:

### Cursor

Add to your `~/.cursor/mcp.json` or configure via **Cursor Settings → MCP → Add Server**:

```json
{
  "mcpServers": {
    "nce-memory": {
      "command": "python",
      "args": ["/absolute/path/to/NCE/server.py"],
      "env": {
        "MONGO_URI": "mongodb://localhost:27017",
        "PG_DSN": "postgresql://mcp_user:mcp_password@localhost:5432/memory_meta",
        "REDIS_URL": "redis://localhost:6379/0",
        "MINIO_ENDPOINT": "localhost:9000",
        "MINIO_ACCESS_KEY": "minioadmin",
        "MINIO_SECRET_KEY": "minioadmin"
      }
    }
  }
}
```
*Note for Windows: Use double backslashes `C:\\path\\to\\NCE\\server.py` or forward slashes `C:/path/to/NCE/server.py`.*

### Claude Desktop

Edit your `claude_desktop_config.json` (Windows: `%APPDATA%\Claude\`, macOS: `~/Library/Application Support/Claude/`):

```json
{
  "mcpServers": {
    "nce-memory": {
      "command": "python",
      "args": ["/absolute/path/to/NCE/server.py"],
      "env": {
        "MONGO_URI": "mongodb://localhost:27017",
        "PG_DSN": "postgresql://mcp_user:mcp_password@localhost:5432/memory_meta",
        "REDIS_URL": "redis://localhost:6379/0",
        "MINIO_ENDPOINT": "localhost:9000",
        "MINIO_ACCESS_KEY": "minioadmin",
        "MINIO_SECRET_KEY": "minioadmin"
      }
    }
  }
}
```

## 🧪 Testing

Ensure all containers are running, then execute the test suite:

```bash
uv run pytest tests/
```

The test suite validates saga writes, Redis cache invalidation, pgvector search, code search, GraphRAG, temporal `as_of` paths, A2A grants, quotas, notifications, and related MCP tools. Run `pytest tests/` from the repo root (see `pytest.ini`).

## 🛡️ Production Deployment Notes

- **TLS / Authentication**: Always use authenticated, TLS-encrypted URIs in `.env` for production (e.g., `?sslmode=require`).
- **Connection Pools**: Tune `PG_MIN_POOL` and `PG_MAX_POOL` based on your expected traffic.
- **Process Management**: Run `server.py` and `start_worker.py` under a supervisor (e.g., systemd or pm2) for automatic restarts.
- **Security**: The server boundary (`server.py`) wraps all exceptions as safe MCP error responses. Stack traces are never leaked to the client. Input validation strictly bounds parameter limits and sanitizes file paths.

## ⚠️ Troubleshooting

### Connection Refused
**Error**: `could not connect to server: Connection refused`
**Solution**:
1. Verify Docker containers are running: `docker ps`.
2. Check that ports (27017, 5432, 6379, 9000) are not occupied by local host services.
3. Validate connection strings in your `.env` or MCP config block.

### Missing Dependencies
**Error**: `ModuleNotFoundError: No module named 'tree_sitter'`
**Solution**: Ensure you have activated your virtual environment and installed the optional dependencies:
```bash
pip install tree-sitter==0.20.4 tree-sitter-python==0.20.4 tree-sitter-javascript==0.20.1
```

### Async Indexing Hanging
**Error**: `check_indexing_status` stays pending indefinitely.
**Solution**: The background worker process may not be running. Start it in a separate terminal:
```bash
.venv\Scripts\python.exe start_worker.py
```
