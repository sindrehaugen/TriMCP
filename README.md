# TriMCP — Enterprise-Grade AI Memory Layer

TriMCP is the ultimate **Enterprise-Grade AI Memory Layer**, designed to serve as the cognitive core for autonomous agents. Operating as an MCP Protocol Native engine, it empowers LLMs to persist, structure, and recall knowledge across a highly optimized, multi-database architecture. TriMCP v2.2 brings unprecedented scale, enabling true self-awareness of codebases, enterprise document indexing, and seamless cloud or on-premise deployments.

## 🌟 v2.2 Capabilities & Core Features

- **Semantic Search & GraphRAG**: Combines pgvector cosine similarity search with BFS Knowledge Graph traversal (up to 3 hops). Dynamically hydrates source excerpts from MongoDB for rich, structured subgraphs and codebase entity mapping.
- **3 Deployment Modes**: Flexible deployment via a single native installer (`trimcp-launch`) for **Local** (Docker Desktop), **Multi-User** (On-Premise), and **Cloud** (Azure/AWS/GCP via Terraform/Bicep).
- **Hardware Acceleration**: Auto-detects and utilizes the best available compute backend, supporting CPU, NVIDIA CUDA, AMD ROCm, Intel NPU/XPU (OpenVINO), and Apple Silicon.
- **305+ Programming Languages**: Comprehensive AST parsing powered by `tree-sitter-language-pack`, replacing hardcoded grammars for universal codebase understanding.
- **Universal File Format Extraction**: Extracts, chunks, and indexes Office (Word, Excel, PowerPoint), PDF (with OCR fallback), CAD (DXF/DWG/Revit), Adobe CS, Diagrams (Visio/Mermaid), and MS Project files.
- **Push-Architecture Document Bridges**: Real-time webhook receivers and integrations for SharePoint, Google Workspace/Drive, Dropbox, and Miro. Documents are indexed automatically upon creation or modification.
- **Quad-DB Architecture**: Data segregation across MongoDB (Episodic Archive), PostgreSQL/pgvector (Semantic Index), Redis (Working Memory & Queues), and MinIO (Media Store).
- **Saga Pattern Guarantee**: Atomic distributed writes ensure absolute data purity. Any failure in Postgres automatically triggers a rollback in MongoDB.

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

## 🚀 Quick Start

TriMCP v2.2 introduces a unified native installer (`trimcp-launch`) that handles environment setup, hardware acceleration detection, and service orchestration across three deployment modes.

### 1. Installation & Deployment Mode

Download and run the installer for your platform (Windows EXE/MSI, macOS DMG, or Linux). During installation, select your deployment mode:

- **Local Mode**: Installs Docker Desktop automatically and runs the Quad-DB stack locally. Best for solo developers.
- **Multi-User Mode**: Connects to an on-premise server. Requires Azure AD UPN resolution.
- **Cloud Mode**: Connects to managed cloud services (AWS/Azure/GCP) provisioned via our Terraform/Bicep modules.

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

The `trimcp-launch` shim automatically manages the background worker (`start_worker.py`) and the FastAPI webhook receiver. To start the MCP server manually for development (listens on stdio):

```bash
python server.py
```

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