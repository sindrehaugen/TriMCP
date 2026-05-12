# TriMCP Usage Modes

TriMCP exposes two distinct runtime surfaces. Choosing the right one depends on whether the caller is an LLM client or a programmatic service.

| | MCP / LLM stdio | Admin REST API |
|---|---|---|
| **Entry point** | `server.py` | `admin_server.py` |
| **Transport** | JSON-RPC 2.0 over stdin/stdout | HTTP/HTTPS, port 8003 (default) |
| **Auth** | Namespace token in tool args | HMAC-SHA256 header + optional mTLS |
| **Primary consumers** | Claude Desktop, Cursor, Windsurf, any MCP client | Dashboards, CI/CD pipelines, operators, service integrations |
| **Tool/endpoint set** | Memory, code, graph, media, migration, A2A, snapshot | Search, replay, snapshot export, GC, A2A grants, admin ops |
| **Response format** | `TextContent[]` (stringified JSON in `.text`) | `application/json` or `application/x-ndjson` (streaming) |
| **Quota enforcement** | Per-tool, per-namespace | Per-route (same quota table) |

---

## 1. MCP / LLM stdio Mode

### How it works

`server.py` wraps the `TriStackEngine` in the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) and communicates over stdin/stdout using JSON-RPC 2.0. An LLM client (e.g. Claude Desktop) launches the process, registers tools from `tools/list`, and calls them via `tools/call`.

The GC background loop is co-launched in the same process so the LLM surface is always running against a clean data set.

### Launch

```bash
python server.py
# or via Claude Desktop config:
{
  "mcpServers": {
    "tri-stack-memory": {
      "command": "python",
      "args": ["/path/to/TriMCP-1/server.py"],
      "env": { "TRIMCP_MASTER_KEY": "...", "PG_DSN": "..." }
    }
  }
}
```

### JSON-RPC wire format

All messages conform to JSON-RPC 2.0. The MCP SDK handles framing; the examples below show the logical payload.

#### tools/list response (excerpt)

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "store_memory",
        "description": "Persist a memory (conversation turn, document, or summary) to the Tri-Stack.",
        "inputSchema": {
          "type": "object",
          "properties": {
            "namespace_id": { "type": "string" },
            "agent_id":     { "type": "string" },
            "content":      { "type": "string" },
            "summary":      { "type": "string" },
            "heavy_payload":{ "type": "string" },
            "content_type": { "type": "string", "enum": ["chat", "code"] },
            "check_contradictions": { "type": "boolean", "default": false }
          },
          "required": ["namespace_id", "agent_id", "content"]
        }
      },
      {
        "name": "semantic_search",
        "description": "Search stored memories by semantic similarity.",
        "inputSchema": {
          "type": "object",
          "properties": {
            "namespace_id": { "type": "string" },
            "agent_id":     { "type": "string" },
            "query":        { "type": "string" },
            "limit":        { "type": "integer", "default": 5, "maximum": 100 },
            "offset":       { "type": "integer", "default": 0 },
            "as_of":        { "type": "string", "format": "date-time" }
          },
          "required": ["namespace_id", "agent_id", "query"]
        }
      }
    ]
  }
}
```

#### tools/call — store_memory

Request:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "store_memory",
    "arguments": {
      "namespace_id": "550e8400-e29b-41d4-a716-446655440000",
      "agent_id":     "claude-agent-01",
      "content":      "User asked about database connection pooling best practices.",
      "summary":      "DB pooling best practices conversation",
      "heavy_payload": "Full transcript: ...",
      "content_type": "chat"
    }
  }
}
```

Success response:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"memory_id\": \"a1b2c3d4-...\", \"mongo_ref_id\": \"64f9...\", \"status\": \"stored\"}"
      }
    ]
  }
}
```

#### tools/call — semantic_search (with time travel)

Request:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "semantic_search",
    "arguments": {
      "namespace_id": "550e8400-e29b-41d4-a716-446655440000",
      "agent_id":     "claude-agent-01",
      "query":        "connection pool exhaustion handling",
      "limit":        5,
      "as_of":        "2026-04-01T00:00:00Z"
    }
  }
}
```

Success response:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"results\": [{\"memory_id\": \"...\", \"score\": 0.91, \"summary\": \"DB pooling best practices\", \"content\": \"...\", \"created_at\": \"2026-03-15T09:12:00Z\"}]}"
      }
    ]
  }
}
```

#### tools/call — error (quota exceeded)

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Resource quota exceeded (-32013): namespace 550e8400 has reached its daily search limit"
      }
    ],
    "isError": true
  }
}
```

### Available MCP tools

| Tool | Description |
|---|---|
| `store_memory` | Persist a conversation turn, document, or summary |
| `semantic_search` | pgvector ANN search with optional time travel (`as_of`) |
| `graph_search` | Knowledge graph BFS traversal |
| `search_codebase` | Search indexed code chunks by semantic similarity |
| `index_code_file` | AST-parse and embed a source file (async, returns `job_id`) |
| `check_indexing_status` | Poll `index_code_file` job status |
| `store_media` | Ingest audio/video/image into MinIO + index summary |
| `get_recent_context` | Retrieve recent memories for a namespace/agent |
| `start_migration` | Begin an embedding model migration |
| `migration_status` | Check migration progress |
| `validate_migration` | Run quality gates on a finished migration |
| `commit_migration` | Promote a validated migration to active |
| `abort_migration` | Cancel and clean up a migration |

---

## 2. Admin REST API Mode

### How it works

`admin_server.py` is a Starlette application running on port 8003. It provides HTTP endpoints for programmatic search, event replay, snapshot export, A2A grant management, GC control, and admin observability. All `/api/` routes require HMAC-SHA256 authentication.

### Launch

```bash
python admin_server.py
# or with uvicorn directly:
uvicorn admin_server:app --host 0.0.0.0 --port 8003
```

With mTLS:

```bash
uvicorn admin_server:app \
  --ssl-certfile /etc/tls/server.crt \
  --ssl-keyfile  /etc/tls/server.key \
  --ssl-ca-certs /etc/tls/ca.crt
```

### Authentication

Every `/api/` request requires an `Authorization` header:

```
Authorization: HMAC-SHA256 <timestamp>:<nonce>:<signature>
```

Where `signature = HMAC-SHA256(TRIMCP_API_KEY, "<timestamp>\n<nonce>\n<method>\n<path>\n<body_sha256>")`.

See [enterprise_security.md](enterprise_security.md) §2 for the full signing algorithm and replay protection details.

### POST /api/search

Unified semantic search — equivalent to the `semantic_search` MCP tool.

Request:

```http
POST /api/search HTTP/1.1
Content-Type: application/json
Authorization: HMAC-SHA256 1715510400:abc123:<signature>

{
  "namespace_id": "550e8400-e29b-41d4-a716-446655440000",
  "agent_id":     "ci-pipeline",
  "query":        "connection pool exhaustion handling",
  "top_k":        10,
  "as_of":        "2026-04-01T00:00:00Z"
}
```

Response (`200 OK`):

```json
{
  "results": [
    {
      "memory_id":  "a1b2c3d4-...",
      "score":      0.91,
      "summary":    "DB pooling best practices",
      "content":    "Full content text...",
      "created_at": "2026-03-15T09:12:00Z"
    }
  ]
}
```

Error responses:

| Code | Condition |
|---|---|
| `400` | Malformed JSON body |
| `422` | Missing required field (`namespace_id`, `agent_id`, or `query`) |
| `429` | Quota exceeded |
| `503` | Engine not connected |

### POST /api/replay/observe (streaming NDJSON)

Stream historical events from a namespace. The response body is `application/x-ndjson` — one JSON object per line.

Request:

```http
POST /api/replay/observe HTTP/1.1
Content-Type: application/json
Authorization: HMAC-SHA256 1715510400:def456:<signature>

{
  "namespace_id":    "550e8400-e29b-41d4-a716-446655440000",
  "start_seq":       1,
  "end_seq":         500,
  "agent_id_filter": "claude-agent-01",
  "max_events":      200
}
```

Response stream (one JSON object per line):

```ndjson
{"type": "event", "seq": 1, "event_type": "store", "agent_id": "claude-agent-01", "occurred_at": "2026-03-01T10:00:00Z", "memory_id": "..."}
{"type": "progress", "events_streamed": 100}
{"type": "event", "seq": 2, "event_type": "search", "agent_id": "claude-agent-01", "occurred_at": "2026-03-01T10:05:00Z"}
{"type": "complete", "total_events": 187}
```

### POST /api/snapshot/export (streaming NDJSON)

Export all memories for a namespace at a point in time. GB-scale safe — uses server-side cursor.

Request:

```http
POST /api/snapshot/export HTTP/1.1
Content-Type: application/json
Authorization: HMAC-SHA256 1715510400:ghi789:<signature>

{
  "namespace_id": "550e8400-e29b-41d4-a716-446655440000",
  "as_of":        "2026-05-01T00:00:00Z"
}
```

Response stream:

```ndjson
{"type": "metadata", "format_version": "1.0", "as_of": "2026-05-01T00:00:00Z", "namespace_id": "550e8400-..."}
{"type": "memory", "memory_id": "...", "content": "...", "created_at": "2026-03-15T09:12:00Z"}
{"type": "progress", "memories_exported": 100}
{"type": "complete", "total_memories": 342}
```

### POST /api/replay/fork

Fork a namespace to a point in time (creates a new namespace with a snapshot of state at `fork_point`).

Request:

```http
POST /api/replay/fork HTTP/1.1
Content-Type: application/json
Authorization: HMAC-SHA256 ...

{
  "source_namespace_id": "550e8400-...",
  "fork_point":          "2026-04-15T12:00:00Z",
  "target_namespace_id": "new-namespace-uuid"
}
```

### GET /api/health

No auth required. Returns status for all four database connections.

```http
GET /api/health HTTP/1.1
```

```json
{
  "status": "healthy",
  "databases": {
    "postgres": "up",
    "mongodb":  "up",
    "redis":    "up",
    "minio":    "up"
  },
  "merkle_chain_valid": true
}
```

### Admin endpoint summary

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Multi-DB health check |
| `POST` | `/api/search` | Semantic search |
| `POST` | `/api/replay/observe` | Stream historical events (NDJSON) |
| `POST` | `/api/replay/fork` | Fork namespace to a point in time |
| `GET` | `/api/replay/status/{run_id}` | Replay job status |
| `GET` | `/api/replay/provenance/{memory_id}` | Provenance chain for a memory |
| `POST` | `/api/snapshot/export` | Full namespace export (NDJSON) |
| `POST` | `/api/a2a/grants/create` | Create an A2A grant token |
| `POST` | `/api/a2a/grants/{id}/revoke` | Revoke an A2A grant |
| `GET` | `/api/a2a/grants` | List A2A grants |
| `POST` | `/api/gc/trigger` | Force GC run |
| `GET` | `/api/admin/events` | Event log feed |
| `GET` | `/api/admin/quotas` | Quota usage |
| `POST` | `/api/admin/graph/explore` | Knowledge graph explorer |
| `GET` | `/api/admin/verify-chain/{namespace_id}` | Verify Merkle chain integrity |
| `GET` | `/api/admin/schema` | Postgres schema dump |
| `GET` | `/api/admin/dlq` | Dead-letter queue list |
| `POST` | `/api/admin/dlq/{id}/replay` | Replay a dead-letter job |
| `POST` | `/api/admin/dlq/{id}/purge` | Purge a dead-letter entry |
| `GET` | `/api/admin/embedding-models` | List available embedding models |
| `POST` | `/api/admin/embedding-migrations/start` | Start an embedding migration |

---

## 3. Choosing a Mode

**Use MCP stdio** when:
- An LLM will call tools autonomously (Claude Desktop, Cursor, Windsurf, agent frameworks).
- You want the quota + cache layer to work transparently without building HTTP signing logic.
- You are running a local or self-hosted MCP server and the LLM client manages the process lifecycle.

**Use Admin REST API** when:
- You are building a dashboard, data pipeline, or CI/CD integration that needs programmatic access.
- You want streaming NDJSON for large exports or replays without loading results into RAM.
- You need to manage A2A grants, trigger GC, inspect DLQ entries, or verify Merkle chain integrity.
- You are operating in a multi-replica deployment where HMAC + mTLS gives you the right security boundary.

Both modes share the same `TriStackEngine` and enforce the same RLS, quota, and audit trail guarantees — the surface layer is the only difference.
