# TriMCP — Enterprise-Grade AI Memory Layer

TriMCP is an **MCP-native memory engine** for autonomous agents: a **quad-database** stack (PostgreSQL + pgvector, MongoDB, Redis, MinIO) with a **Saga**-style write path, **temporal** recall (`as_of` time-travel on semantic and graph search), **A2A** scoped sharing between agents, and **background workers** for re-embedding, bridge renewal, and GC. This repository documents **TriMCP v1.0** — the shipped integration surface in `server.py`, `admin_server.py`, `trimcp/a2a_server.py`, and `trimcp/cron.py`.

Longer-horizon roadmap items (universal installers, 300+ language packs, broad format extraction) live in the innovation roadmap; deploy today **from source** with Docker Compose per [deploy/README.md](deploy/README.md).

## v1.0 capabilities

- **Semantic search & GraphRAG**: pgvector nearest-neighbor search, MongoDB hydration, BFS over `kg_edges` with structured subgraphs.
- **Temporal queries**: Optional **`as_of`** (ISO 8601) on `semantic_search` and `graph_search` via `trimcp/temporal.py` and orchestrator filters.
- **A2A protocol**: Grant/verify token flow and JSON-RPC skills on **`trimcp/a2a_server.py`** (`trimcp/a2a.py`, `a2a_grants` table).
- **Quotas & auth**: Namespace-scoped consumption and HMAC-aware admin API patterns (see tests and config).
- **Cognitive workers**: **`python -m trimcp.cron`** — APScheduler jobs for **document-bridge renewal** and **`ReembeddingWorker`** sweeps; **`ConsolidationWorker`** (`trimcp/consolidation.py`) for sleep-style abstraction (integrate with your scheduler); MCP startup runs **orphan GC** (`run_gc_loop`).
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

**Full diagrams** (sequence charts for temporal + A2A, worker data flow): **[docs/architecture-v1.md](docs/architecture-v1.md)**.

## 🛠️ Tech Stack

- **Language**: Python 3.9+ (3.10+ recommended for upstream MCP SDK compatibility)
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
- **Python 3.9+** — **3.10+** recommended for the MCP SDK and async patterns.
- **pip** - For managing Python dependencies.

## 🚀 Quick Start

For **v1.0**, run from this repository: start the **Compose** stack (see [deploy/README.md](deploy/README.md)), configure `.env`, then launch `server.py` and workers as needed. Optional packaged installers remain on the **product roadmap**; multi-mode install flows below describe the target operator experience once shipping.

### 1. Environment & deployment mode (reference)

- **Local**: Quad-DB via Docker on one machine (default dev path).
- **Multi-user**: Shared Postgres/Mongo/Redis/MinIO; enforce namespace isolation and auth in production.
- **Cloud**: Managed databases and object storage; same codebase, different connection strings.

### 2. Environment Configuration

If running from source or configuring the server manually, copy the environment template:

```bash
cp .env.example .env
```

Core variables required in `.env`:

| Variable                | Description                                       | Example                                                |
| ----------------------- | ------------------------------------------------- | ------------------------------------------------------ |
| `MONGO_URI`             | MongoDB connection string                         | `mongodb://localhost:27017`                            |
| `PG_DSN`                | PostgreSQL connection string                      | `postgresql://mcp_user:mcp_password@localhost:5432/memory_meta` |
| `REDIS_URL`             | Redis connection string                           | `redis://localhost:6379/0`                             |
| `MINIO_ENDPOINT`        | MinIO connection endpoint                         | `localhost:9000`                                       |
| `DROPBOX_APP_SECRET`    | Secret for Dropbox webhook HMAC validation        | `your_dropbox_secret`                                  |
| `GRAPH_CLIENT_STATE`    | Client state token for MS Graph webhooks          | `your_graph_state`                                     |
| `DRIVE_CHANNEL_TOKEN`   | Channel token for Google Drive webhooks           | `your_drive_token`                                     |

*Note: Never commit `.env` to version control.*

### 3. Start the Server

In development, start the **RQ worker** (`start_worker.py`) and **MCP server** separately (or use your process supervisor). MCP listens on stdio:

```bash
python server.py
```

## 🧠 Architecture Deep-Dive

For **temporal**, **A2A**, and **background worker** sequence diagrams, use **[docs/architecture-v1.md](docs/architecture-v1.md)**. The following sections summarise the quad-DB and saga contracts.

TriMCP is built to treat memory as distinct layers with strict boundaries and absolute rollback guarantees. 

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

TriMCP can autonomously ingest its own codebase. When an LLM agent calls the `index_code_file` tool, the request is instantly enqueued to an asynchronous Redis Queue (RQ) worker (`start_worker.py`). The worker handles the heavy AST parsing (via Tree-sitter) to split the source into chunks, stores the raw payload in Mongo, embeds vectors/KG triplets in Postgres, and updates the working context in Redis. The MCP tool immediately returns a `job_id` to the LLM to track progress via `check_indexing_status`.

See the [Recursive Indexing Flow Diagram](docs/recursive_indexing_flow.md) and [v1.0 architecture](docs/architecture-v1.md) (temporal, A2A, cognitive workers).

### Advanced GraphRAG Layer

TriMCP implements a state-of-the-art GraphRAG pipeline:
1. The query undergoes a pgvector cosine search to find the nearest **anchor knowledge graph node**.
2. A **BFS traversal** executes over `kg_edges` (up to 3 hops, max 50 nodes).
3. The engine **hydrates source documents** from MongoDB (e.g., 600-character excerpts) mapped to the nodes.
4. Returns a highly structured subgraph context: `{ nodes, edges, sources }`.

## 📂 Directory Structure

```text
TriMCP/
├── docker-compose.yml       # Redis, PostgreSQL/pgvector, MongoDB, MinIO
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variable template
├── start_worker.py          # Background worker (RQ) for async indexing
├── index_all.py             # Bulk recursive code ingestion
├── server.py                # MCP stdio server
├── admin_server.py          # Admin UI & Observability
├── admin/
│   └── index.html           # Admin dashboard UI
├── trimcp/
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

TriMCP exposes the following tools directly to LLM clients via JSON-RPC 2.0, utilizing a highly efficient API cache layer with generation-counter invalidation:

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

*Full list and schemas: `TOOLS` in `server.py`.*

## 🔗 Connecting to an LLM Client

The MCP server block is identical across all clients. Here are common configurations:

### Cursor

Add to your `~/.cursor/mcp.json` or configure via **Cursor Settings → MCP → Add Server**:

```json
{
  "mcpServers": {
    "tri-stack-memory": {
      "command": "python",
      "args": ["/absolute/path/to/TriMCP/server.py"],
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
*Note for Windows: Use double backslashes `C:\\path\\to\\TriMCP\\server.py` or forward slashes `C:/path/to/TriMCP/server.py`.*

### Claude Desktop

Edit your `claude_desktop_config.json` (Windows: `%APPDATA%\Claude\`, macOS: `~/Library/Application Support/Claude/`):

```json
{
  "mcpServers": {
    "tri-stack-memory": {
      "command": "python",
      "args": ["/absolute/path/to/TriMCP/server.py"],
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