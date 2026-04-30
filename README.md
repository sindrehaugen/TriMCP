# TriMCP — The Semantic Memory Engine

TriMCP is not just another standard Model Context Protocol (MCP) server. It is a cutting-edge **Semantic Memory Engine** designed to be the cognitive core for AI agents. By operating as an MCP Protocol Native engine, it empowers LLMs to persist, structure, and recall knowledge autonomously across an advanced multi-database architecture.

Most remarkably, TriMCP possesses **Recursive Capability**—it uses its own MCP tools to ingest, parse, and index its own AST, achieving true self-awareness of its codebase.

## 🌟 Key Features

- **Quad-DB Architecture**: Highly optimized data segregation across four distinct layers:
  - **MongoDB** (Episodic Archive) for raw, heavy payloads and transcripts.
  - **PostgreSQL/pgvector** (Semantic Index) for ACID-compliant vector embeddings and Knowledge Graph triplets.
  - **Redis** (Working Memory) for sub-millisecond summary caching and RQ background job queues.
  - **MinIO** (Media Store) for large audio, video, and image files.
- **Advanced GraphRAG Capabilities**: Combines pgvector cosine similarity search to find anchor nodes with BFS graph traversal over Knowledge Graph edges (up to 3 hops). It dynamically hydrates source excerpts from MongoDB to return a rich, structured subgraph.
- **Token-Saving Caching System**: A robust API call caching layer built on Redis that drastically reduces LLM token usage on repeated semantic and graph searches. It features **O(1) read-after-write invalidation via generation counters**, guaranteeing that agents never receive stale context after a mutation.
- **Saga Pattern Guarantee**: Powered by the core `TriStackEngine`, memory ingestion employs atomic distributed writes. Any failure in Postgres automatically triggers a rollback in MongoDB, maintaining absolute data purity.
- **Background Garbage Collection (GC)**: An independent hourly safety net that purges orphaned MongoDB documents, protecting the engine against hard-kills mid-transaction.

## 🛠️ Tech Stack

- **Language**: Python 3.10+
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
- **Python 3.10+** - Required by the MCP SDK.
- **pip** - For managing Python dependencies.

## 🚀 Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/sindrehaugen/TriMCP.git
cd TriMCP
```

### 2. Environment Setup

Copy the example environment file:

```bash
cp .env.example .env
```

Configure the following variables in `.env` if needed (the defaults usually work for local Docker setup):

| Variable                | Description                                       | Example                                                |
| ----------------------- | ------------------------------------------------- | ------------------------------------------------------ |
| `MONGO_URI`             | MongoDB connection string                         | `mongodb://localhost:27017`                            |
| `PG_DSN`                | PostgreSQL connection string                      | `postgresql://mcp_user:mcp_password@localhost:5432/memory_meta` |
| `REDIS_URL`             | Redis connection string                           | `redis://localhost:6379/0`                             |
| `MINIO_ENDPOINT`        | MinIO connection endpoint                         | `localhost:9000`                                       |
| `MINIO_ACCESS_KEY`      | MinIO access key                                  | `minioadmin`                                           |
| `MINIO_SECRET_KEY`      | MinIO secret key                                  | `minioadmin`                                           |
| `PG_MIN_POOL`           | Minimum PG connection pool size                   | `1`                                                    |
| `PG_MAX_POOL`           | Maximum PG connection pool size                   | `10`                                                   |
| `REDIS_TTL`             | Redis cache TTL in seconds                        | `3600`                                                 |
| `GC_INTERVAL_SECONDS`   | How often the GC runs                             | `3600`                                                 |
| `GC_ORPHAN_AGE_SECONDS` | Minimum age before a document is considered an orphan | `300`                                                  |

*Note: Never commit `.env` to version control.*

### 3. Database Setup

Start the quad-database stack using Docker Compose:

```bash
docker compose up -d
```

Verify all containers are healthy:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

### 4. Install Dependencies

Create and activate a virtual environment:

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

Install core dependencies:

```bash
pip install -r requirements.txt
```

**Optional Dependencies (Recommended for full capability):**

AST parsing (falls back to line splitter without this):
```bash
pip install tree-sitter==0.20.4 tree-sitter-python==0.20.4 tree-sitter-javascript==0.20.1
```

Semantic embeddings (falls back to hash stub without this):
```bash
pip install sentence-transformers>=2.3.1 transformers>=4.36.2 torch>=2.1.2
```

GraphRAG entity extraction (falls back to regex without this):
```bash
pip install spacy>=3.7.0
python -m spacy download en_core_web_sm
```

### 5. Start the Server

Start the standard MCP server (listens on stdio):

```bash
python server.py
```

Alternatively, to start the async background worker for async indexing:

```bash
.venv\Scripts\python.exe start_worker.py
```

To start the SSE (HTTP) server:

```bash
.venv\Scripts\python.exe sse_server.py
```
*(Listens on `http://localhost:8000/sse`)*

## 🧠 Architecture Deep-Dive

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

See the [Recursive Indexing Flow Diagram](docs/recursive_indexing_flow.md).

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
├── sse_server.py            # MCP SSE (HTTP) server
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
│   ├── garbage_collector.py # Hourly orphan GC (paginated, retry-enabled)
│   ├── notifications.py     # SSE notification dispatcher
│   └── tasks.py             # RQ async tasks and indexing logic
├── tests/
│   ├── __init__.py
│   ├── test_integration_engine.py  # End-to-end integration tests
│   ├── test_mcp_cache.py           # API Caching logic testing
│   ├── test_notifications.py       # SSE events testing
│   ├── test_smoke_sse.py           # Smoke testing for SSE
│   └── test_smoke_stdio.py         # Smoke testing for Stdio MCP
└── docs/                    # Architectural diagrams and documentation
```

## 🔌 MCP Tool Reference

TriMCP exposes the following tools directly to LLM clients via JSON-RPC 2.0, utilizing a highly efficient API cache layer with generation-counter invalidation:

| Tool | Description |
|---|---|
| `store_memory` | Persist a memory to the DB stack. Triggers entity extraction and KG upsert. |
| `store_media` | Save a media payload (MinIO) and index its metadata into the memory stack. |
| `semantic_search` | Cosine-similarity search over stored memories, hydrated from MongoDB. *(Cached)* |
| `index_code_file` | AST-parse a source file into chunks, embed each chunk, archive the full file. Returns `job_id` asynchronously. |
| `check_indexing_status` | Check the progress of an async indexing job using its `job_id`. |
| `search_codebase` | Semantic search over indexed code chunks, returning file path and exact line numbers. *(Cached)* |
| `graph_search` | GraphRAG traversal: vector anchor → BFS subgraph → hydrated source excerpts. *(Cached)* |
| `get_recent_context`| Redis-only instant recall for the most recent session summary. |

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

The test suite validates:
1. Full saga writes and Redis API caching invalidation rules.
2. pgvector cosine search and MongoDB document hydration.
3. AST parser chunks resolving to exact function definitions via `search_codebase`.
4. MD5 hash-skip optimizations for unchanged file re-submissions.
5. KG entity extraction + GraphRAG graph-traversal returning non-empty subgraphs.
6. Triggered PostgreSQL failures successfully initiating MongoDB rollbacks.

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