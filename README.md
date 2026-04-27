# TriMCP — Tri-Stack Memory Server

> A production-grade, local-first **Model Context Protocol (MCP)** memory server backed by a Redis + PostgreSQL/pgvector + MongoDB tri-database stack. Implements the **Saga Pattern** for atomic distributed writes, AST-aware code indexing, and a **GraphRAG** knowledge-graph layer — all accessible to any MCP-compatible LLM client via JSON-RPC over stdio.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Security Model](#security-model)
3. [Prerequisites](#prerequisites)
4. [Quick Start](#quick-start)
5. [Configuration Reference](#configuration-reference)
6. [MCP Tool Reference](#mcp-tool-reference)
7. [SSE Mode (HTTP)](#sse-mode-http)
8. [Connecting to an LLM Client](#connecting-to-an-llm-client) — Claude Desktop, Cursor, Windsurf, Gemini CLI, Gemini Antigravity, VS Code, Continue.dev, Zed
9. [Windows Auto-start](#windows-auto-start)
10. [Running the Test Suite](#running-the-test-suite)
11. [Production Deployment Notes](#production-deployment-notes)
12. [Project Structure](#project-structure)

---

## Architecture

### The Tri-Stack Philosophy

Each database is assigned exclusively to the data structure it is optimal for — no overlapping responsibilities:

| Layer | Database | Role | Key Property |
|---|---|---|---|
| **Working Memory** | Redis | TTL-bound summary cache | Sub-millisecond recall, no disk I/O |
| **Semantic Index** | PostgreSQL + pgvector | Vector embeddings + KG triplets | ACID guarantees, cosine similarity search |
| **Episodic Archive** | MongoDB | Raw heavy payloads (transcripts, source files) | Schema-less, high-throughput I/O |

### Data Flow

```
LLM Client (Claude Desktop / Cursor / API)
        │
        │  JSON-RPC over stdio
        ▼
┌─────────────────────────────────────┐
│           server.py (MCP)           │
│  Input validation · Error wrapping  │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│        orchestrator.py (Saga)       │
│                                     │
│  Step 0 ── graph_extractor.py       │  Entity + triplet extraction
│             (spaCy / regex)         │
│                                     │
│  Step 1 ──► MongoDB                 │  Heavy payload → inserted_id
│                                     │
│  Step 2 ──► PostgreSQL/pgvector     │  Vector index + KG nodes/edges
│               │                     │
│            FAIL? ──► Mongo ROLLBACK │  Orphan prevention
│                                     │
│  Step 3 ──► Redis (TTL cache)       │  Immediate availability
└─────────────────────────────────────┘
               │
               ├── ast_parser.py       (Tree-sitter / line-splitter)
               ├── embeddings.py       (Jina 768-dim / hash stub)
               ├── graph_query.py      (BFS GraphRAG traverser)
               └── garbage_collector.py (Hourly orphan GC, background)
```

### Saga Rollback Guarantee

```
Mongo ──► PG ──► Redis
            │
         FAILURE
            │
            └──► DELETE Mongo doc  ← automatic, synchronous
                 RAISE exception   ← propagates to caller
```

The `garbage_collector.py` runs hourly as an independent safety net: any MongoDB document older than 5 minutes with no matching `mongo_ref_id` in PostgreSQL is automatically purged — protecting against hard-kills mid-transaction.

### GraphRAG Layer

```
query
  │
  ▼
pgvector cosine search → anchor kg_node
  │
  ▼
BFS traversal over kg_edges (max 3 hops, max 50 nodes)
  │
  ▼
Hydrate source documents from MongoDB (600-char excerpts)
  │
  ▼
Structured subgraph: { nodes, edges, sources }
```

---

## Security Model

### Input Validation

All tool inputs are validated at two layers:

1. **MCP boundary** (`server.py`): integer clamping (`top_k` → 1–100, `max_depth` → 1–3), all exceptions caught and returned as safe MCP error responses — no stack traces leak to the client.
2. **Engine boundary** (`orchestrator.py`): Pydantic validators enforce:
   - `user_id` / `session_id`: `^[\w\-]{1,128}$` — alphanumeric, hyphens, underscores only. Prevents Redis key injection.
   - `content_type`: `Literal["chat", "code"]` — strict enum, no arbitrary strings.
   - `summary`: max 8,192 characters.
   - `heavy_payload`: max 10 MB.
   - `filepath`: path traversal check rejects `..`, `/etc`, `/proc`.
   - `language`: allowlist `{"python", "javascript"}`.

### Secrets Management

- All credentials are loaded exclusively from environment variables via `python-dotenv`.
- **`.env` is listed in `.gitignore`** — never committed.
- `.env.example` documents every variable with production URI templates (TLS, auth).
- `OrchestratorConfig.validate()` logs a warning at startup if default (insecure) connection strings are in use.

### Connection Hardening

| Component | Hardening Applied |
|---|---|
| MongoDB | `serverSelectionTimeoutMS=5000` |
| PostgreSQL | Pool min/max bounded (default 1–10), `command_timeout=30s` |
| Redis | `socket_connect_timeout=5s`, `socket_timeout=5s` |
| GC pool | Separate bounded pool (max 3), exponential backoff on startup |

### Logging

- All internal logging uses Python `logging` module at `DEBUG`/`INFO`/`WARNING`/`ERROR` — never `print()`.
- Error messages never expose raw exception stack traces to the MCP client.
- Sensitive values (passwords, tokens) are never interpolated into log messages.

---

## Prerequisites

| Requirement | Version | Purpose |
|---|---|---|
| Docker Desktop | Latest | Run Redis, PostgreSQL, MongoDB |
| Python | 3.10+ | MCP SDK requires ≥ 3.10 |
| pip | Latest | Dependency management |

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/sindrehaugen/TriMCP.git
cd TriMCP
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env if you need non-default ports or credentials
```

### 3. Start the databases

```bash
docker compose up -d
```

Verify all three containers are healthy:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

Expected output:
```
tri-stack-redis     Up
tri-stack-postgres  Up
tri-stack-mongo     Up
```

### 4. Create a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 5. Install dependencies

**Core (required):**
```bash
pip install -r requirements.txt
```

**AST parsing (optional — falls back to line splitter):**
```bash
pip install tree-sitter==0.20.4 tree-sitter-python==0.20.4 tree-sitter-javascript==0.20.1
```

**Semantic embeddings (optional — falls back to hash stub):**
```bash
pip install sentence-transformers>=2.3.1 transformers>=4.36.2 torch>=2.1.2
```

**GraphRAG entity extraction (optional — falls back to regex):**
```bash
pip install spacy>=3.7.0
python -m spacy download en_core_web_sm
```

### 6. Run the test suite

```bash
python test_stack.py
```

All 6 tests must pass before connecting a client.

### 7. Start the MCP server

```bash
python server.py
```

The server listens on **stdio** (JSON-RPC). The garbage collector starts automatically as a background task.

---

## Configuration Reference

Copy `.env.example` to `.env` and set the following variables:

| Variable | Default | Description |
|---|---|---|
| `MONGO_URI` | `mongodb://localhost:27017` | MongoDB connection string |
| `PG_DSN` | `postgresql://mcp_user:mcp_password@localhost:5432/memory_meta` | PostgreSQL DSN |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `PG_MIN_POOL` | `1` | Minimum PG connection pool size |
| `PG_MAX_POOL` | `10` | Maximum PG connection pool size |
| `REDIS_TTL` | `3600` | Redis cache TTL in seconds |
| `GC_INTERVAL_SECONDS` | `3600` | How often the GC runs |
| `GC_ORPHAN_AGE_SECONDS` | `300` | Minimum age before a document is considered an orphan |

---

## MCP Tool Reference

### `store_memory`

Persist a memory to the full Tri-Stack. Triggers entity extraction and KG upsert.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `user_id` | string | ✅ | User identifier (`^[\w\-]{1,128}$`) |
| `session_id` | string | ✅ | Session or conversation ID |
| `content_type` | `"chat"` \| `"code"` | ✅ | Content classification |
| `summary` | string | ✅ | Short summary — used for vector embedding (max 8,192 chars) |
| `heavy_payload` | string | ✅ | Full raw content to archive in MongoDB (max 10 MB) |

**Returns:** `{ "status": "ok", "mongo_ref_id": "<id>" }`

---

### `semantic_search`

Cosine-similarity search over stored memories, hydrated from MongoDB.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `user_id` | string | ✅ | Scope search to this user |
| `query` | string | ✅ | Natural language search query |
| `top_k` | integer | — | Max results (default 5, max 100) |

**Returns:** Array of `{ mongo_ref_id, distance, raw_data }`

---

### `index_code_file`

AST-parse a source file into function/class chunks, embed each chunk, archive the full file.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `filepath` | string | ✅ | File path (path traversal is rejected) |
| `raw_code` | string | ✅ | Full source code (max 10 MB) |
| `language` | `"python"` \| `"javascript"` | ✅ | Source language |

**Returns:** `{ "status": "indexed"|"skipped", "filepath", "chunks", "mongo_ref_id" }`  
Re-indexing an unchanged file returns `"status": "skipped"` (MD5 hash-check).

---

### `search_codebase`

Semantic search over indexed code chunks, returns file path and exact line numbers.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `query` | string | ✅ | Natural language description of the code |
| `language_filter` | string | — | Filter by `"python"` or `"javascript"` |
| `top_k` | integer | — | Max results (default 5, max 100) |

**Returns:** Array of `{ filepath, language, node_type, name, start_line, end_line, distance, raw_code_preview }`

---

### `graph_search`

GraphRAG traversal: vector anchor → BFS subgraph → hydrated source excerpts.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `query` | string | ✅ | Natural language anchor query |
| `max_depth` | integer | — | BFS hop depth (default 2, max 3) |

**Returns:** `{ anchor, nodes: [{label, type, distance}], edges: [{subject, predicate, object, confidence}], sources: [{mongo_ref_id, type, excerpt}] }`

---

### `get_recent_context`

Redis-only instant recall for the most recent session summary.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `user_id` | string | ✅ | User identifier |
| `session_id` | string | ✅ | Session identifier |

**Returns:** `{ "context": "<summary string or null>" }`

---

## Connecting to an LLM Client

The MCP server block is identical across all clients — only the config file location differs.

**Reusable server block:**
```jsonc
"tri-stack-memory": {
  "command": "python",
  "args": ["/absolute/path/to/TriMCP/server.py"],
  "env": {
    "MONGO_URI": "mongodb://localhost:27017",
    "PG_DSN": "postgresql://mcp_user:mcp_password@localhost:5432/memory_meta",
    "REDIS_URL": "redis://localhost:6379/0"
  }
}
```

> **Windows paths:** use double backslashes `C:\\Users\\...\\TriMCP\\server.py` or forward slashes `C:/Users/.../TriMCP/server.py`.

---

### Claude Desktop

Config file location:
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

```jsonc
{
  "mcpServers": {
    "tri-stack-memory": {
      "command": "python",
      "args": ["C:\\path\\to\\TriMCP\\server.py"],
      "env": {
        "MONGO_URI": "mongodb://localhost:27017",
        "PG_DSN": "postgresql://mcp_user:mcp_password@localhost:5432/memory_meta",
        "REDIS_URL": "redis://localhost:6379/0"
      }
    }
  }
}
```

Restart Claude Desktop. The server appears under **Settings → Developer → MCP Servers**.

---

### Cursor

Config file location:
- **Windows / macOS / Linux:** `~/.cursor/mcp.json`  
  *(or via GUI: **Cursor Settings → MCP → Add Server**)*

```jsonc
{
  "mcpServers": {
    "tri-stack-memory": {
      "command": "python",
      "args": ["/path/to/TriMCP/server.py"],
      "env": {
        "MONGO_URI": "mongodb://localhost:27017",
        "PG_DSN": "postgresql://mcp_user:mcp_password@localhost:5432/memory_meta",
        "REDIS_URL": "redis://localhost:6379/0"
      }
    }
  }
}
```

Reload the window (`Ctrl+Shift+P` → **Reload Window**). The tools appear in the Agent panel.

---

### Windsurf (Codeium)

Config file location:
- **Windows:** `%APPDATA%\Windsurf\mcp_config.json`
- **macOS:** `~/.windsurf/mcp_config.json`  
  *(or via GUI: **Windsurf Settings → Cascade → MCP Servers → Add**)*

```jsonc
{
  "mcpServers": {
    "tri-stack-memory": {
      "command": "python",
      "args": ["/path/to/TriMCP/server.py"],
      "env": {
        "MONGO_URI": "mongodb://localhost:27017",
        "PG_DSN": "postgresql://mcp_user:mcp_password@localhost:5432/memory_meta",
        "REDIS_URL": "redis://localhost:6379/0"
      }
    }
  }
}
```

Restart Cascade. The `tri-stack-memory` tools become available to the Cascade AI agent automatically.

---

### Gemini CLI

Google's `gemini` CLI supports MCP servers via its `settings.json`.

Config file location:
- **All platforms:** `~/.gemini/settings.json`

```jsonc
{
  "mcpServers": {
    "tri-stack-memory": {
      "command": "python",
      "args": ["/path/to/TriMCP/server.py"],
      "env": {
        "MONGO_URI": "mongodb://localhost:27017",
        "PG_DSN": "postgresql://mcp_user:mcp_password@localhost:5432/memory_meta",
        "REDIS_URL": "redis://localhost:6379/0"
      }
    }
  }
}
```

Verify the server is discovered:
```bash
gemini mcp list
```

The tools are then callable within any `gemini` session automatically.

---

### Gemini Antigravity

Antigravity agent sessions load MCP servers from a `mcp_servers` key in the project's `.antigravity/config.json`.

```jsonc
{
  "mcp_servers": {
    "tri-stack-memory": {
      "transport": "stdio",
      "command": "python",
      "args": ["/path/to/TriMCP/server.py"],
      "env": {
        "MONGO_URI": "mongodb://localhost:27017",
        "PG_DSN": "postgresql://mcp_user:mcp_password@localhost:5432/memory_meta",
        "REDIS_URL": "redis://localhost:6379/0"
      }
    }
  }
}
```

Alternatively, export the path for inline session use:
```bash
export MCP_SERVER_CMD="python /path/to/TriMCP/server.py"
antigravity run --mcp "$MCP_SERVER_CMD"
```

---

### VS Code (GitHub Copilot Agent Mode)

Requires VS Code ≥ 1.99 with the GitHub Copilot extension.

Config file location (workspace-scoped, recommended):
- `.vscode/mcp.json` in your project root

```jsonc
{
  "servers": {
    "tri-stack-memory": {
      "type": "stdio",
      "command": "python",
      "args": ["/path/to/TriMCP/server.py"],
      "env": {
        "MONGO_URI": "mongodb://localhost:27017",
        "PG_DSN": "postgresql://mcp_user:mcp_password@localhost:5432/memory_meta",
        "REDIS_URL": "redis://localhost:6379/0"
      }
    }
  }
}
```

Open the Copilot Chat panel in **Agent mode** (`@workspace`). The `tri-stack-memory` tools appear in the tool picker.

---

### Continue.dev

Config file location:
- **All platforms:** `~/.continue/config.json`

Add to the `"mcpServers"` array:

```jsonc
{
  "mcpServers": [
    {
      "name": "tri-stack-memory",
      "command": "python",
      "args": ["/path/to/TriMCP/server.py"],
      "env": {
        "MONGO_URI": "mongodb://localhost:27017",
        "PG_DSN": "postgresql://mcp_user:mcp_password@localhost:5432/memory_meta",
        "REDIS_URL": "redis://localhost:6379/0"
      }
    }
  ]
}
```

Reload Continue (`Ctrl+Shift+P` → **Continue: Reload Config**). Tools appear under the **@** context menu in chat.

---

### Zed

Config file location:
- **macOS / Linux:** `~/.config/zed/settings.json`
- **Windows:** `%APPDATA%\Zed\settings.json`

Add to the `"context_servers"` object:

```jsonc
{
  "context_servers": {
    "tri-stack-memory": {
      "command": {
        "path": "python",
        "args": ["/path/to/TriMCP/server.py"],
        "env": {
          "MONGO_URI": "mongodb://localhost:27017",
          "PG_DSN": "postgresql://mcp_user:mcp_password@localhost:5432/memory_meta",
          "REDIS_URL": "redis://localhost:6379/0"
        }
      }
    }
  }
}
```

Restart Zed. The tools are available in the Assistant panel via the **Insert** context menu.

---

### Client Compatibility Summary

| Client | Config format | Config location | Reload method |
|---|---|---|---|
| Claude Desktop | `mcpServers` object | `%APPDATA%\Claude\` / `~/Library/...` | Restart app |
| Cursor | `mcpServers` object | `~/.cursor/mcp.json` | Reload window |
| Windsurf | `mcpServers` object | `~/.windsurf/mcp_config.json` | Restart Cascade |
| Gemini CLI | `mcpServers` object | `~/.gemini/settings.json` | Automatic |
| Gemini Antigravity | `mcp_servers` object | `.antigravity/config.json` | Session restart |
| VS Code Copilot | `servers` array | `.vscode/mcp.json` | Automatic |
| Continue.dev | `mcpServers` array | `~/.continue/config.json` | Reload config |
| Zed | `context_servers` object | `~/.config/zed/settings.json` | Restart app |

---

## Running the Test Suite

Requires all three Docker containers to be running.

```bash
python test_stack.py
```

| Test | What it validates |
|---|---|
| T1 | Full saga write; Redis cache hit on recall |
| T2 | pgvector cosine search returns the correct document |
| T3 | AST parser splits ≥2 chunks; `search_codebase` resolves to exact function name |
| T4 | MD5 hash-skip fires on unchanged re-submit |
| T5 | KG entity extraction + GraphRAG returns non-empty subgraph |
| T6 | PG failure triggers Mongo rollback; document count unchanged |

---

## Production Deployment Notes

### TLS / Authentication

Use authenticated, TLS-encrypted URIs in `.env`:

```bash
MONGO_URI=mongodb://user:password@host:27017/memory_archive?authSource=admin
PG_DSN=postgresql://user:password@host:5432/memory_meta?sslmode=require
REDIS_URL=rediss://:password@host:6380/0
```

### Connection Pool Sizing

Tune to your workload:

```bash
PG_MIN_POOL=2
PG_MAX_POOL=20
```

### Embedding Model (Production)

Install the full model stack and the Jina model will be loaded automatically:

```bash
pip install sentence-transformers transformers torch
```

The `embeddings.py` module hot-swaps from the hash stub to `jinaai/jina-embeddings-v2-base-code` (768-dim, code-optimised) with no code changes required.

### Process Management

Run the MCP server under a supervisor for automatic restart:

```bash
# systemd example
[Service]
ExecStart=/path/to/.venv/bin/python /path/to/TriMCP/server.py
Restart=on-failure
RestartSec=5
```

### `.gitignore` Essentials

Ensure these are excluded from version control:

```
.env
.venv/
__pycache__/
*.pyc
```

---

## Project Structure

```
TriMCP/
├── docker-compose.yml       # Redis, PostgreSQL/pgvector, MongoDB
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variable template
├── .env                     # Local secrets (never commit)
├── .gitignore
│
├── orchestrator.py          # Core Saga engine + Pydantic models
├── embeddings.py            # Jina embeddings (thread executor + stub fallback)
├── ast_parser.py            # Tree-sitter AST parser + line-splitter fallback
├── graph_extractor.py       # Entity + relation extraction (spaCy / regex)
├── graph_query.py           # GraphRAG BFS traverser
├── garbage_collector.py     # Hourly orphan GC (paginated, retry-enabled)
├── server.py                # MCP stdio server — 6 tools
├── sse_server.py            # MCP SSE (HTTP) server — 6 tools
├── run_sse.bat              # Batch runner for SSE + Docker
├── start_trimcp.vbs         # Background runner for Windows
│
├── mcp_config.json          # Client configuration for Claude Desktop / Cursor
├── test_stack.py            # End-to-end integration tests (6 live tests)
└── README.md
```

---

## SSE Mode (HTTP)

By default, the server runs over **stdio**, which is ideal for LLM clients that spawn the server themselves (Claude Desktop, Gemini CLI). 

To run TriMCP as a persistent background service that multiple clients can connect to simultaneously via HTTP/SSE:

1.  **Start the SSE server:**
    `ash
    .venv\Scripts\python.exe sse_server.py
    `
2.  **Access the endpoint:**
    The server listens on http://localhost:8000/sse.

---

## Windows Auto-start

To ensure TriMCP and its databases start automatically when your PC boots:

1.  **Configure Docker Desktop:** Ensure "Start Docker Desktop when you log in" is enabled in settings.
2.  **Use the Startup script:**
    - The repository includes start_trimcp.vbs and un_sse.bat.
    - Copy start_trimcp.vbs to your Windows Startup folder:
      %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
3.  **Silent Operation:** The .vbs script launches the server completely hidden in the background. No terminal window will remain open.


---

## Scalability & Advanced Search

### Hybrid Search (RRF)
TriMCP now uses **Reciprocal Rank Fusion (RRF)** to combine vector similarity (pgvector) with Full-Text Search (FTS). This significantly improves retrieval quality by catching exact keyword matches that vector embeddings might miss.

### Graph Decay
Knowledge Graph edges now feature **temporal decay**. The confidence score of a relationship decreases over time if not refreshed, ensuring that stale architectural patterns naturally depreciate in relevance compared to recent ones.

### Async Indexing
Code indexing is now **asynchronous**. 
- index_code_file returns a job_id immediately.
- Use check_indexing_status(job_id) to track progress.
- Requires the background worker to be running.

#### Starting the Background Worker:
`ash
.venv\Scripts\python.exe start_worker.py
`

