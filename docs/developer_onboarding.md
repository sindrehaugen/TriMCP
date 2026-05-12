# TriMCP Developer Onboarding

Quick start for local development, test execution, and contribution standards.

---

## 1. Prerequisites

| Tool | Minimum version | Notes |
|---|---|---|
| Python | 3.10 | 3.12 recommended; tested against both |
| Docker + Compose | Docker 24+ | Runs the four backing services |
| Git | Any recent | Repo uses standard branching |

Python dependencies are pinned in `requirements.txt`. Optional cognitive backends (spaCy, OpenVINO) are gated behind env flags and not required for most unit tests.

---

## 2. Local Quad-DB Environment Setup

### 2a. Start backing services

The root `docker-compose.yml` starts PostgreSQL (pgvector), MongoDB, Redis, and MinIO with developer defaults:

```bash
docker compose up -d postgres mongodb redis minio
```

This is enough for the full MCP and admin server surface. The `cognitive`, `worker`, `cron`, `admin`, `a2a`, and `webhook-receiver` containers are optional for local development.

Wait ~5 seconds for PostgreSQL to finish initialising, then verify:

```bash
docker compose ps       # all four should be "running"
docker compose logs postgres --tail 20   # look for "database system is ready to accept connections"
```

### 2b. Apply the schema

PostgreSQL schema initialisation runs automatically when using the full `docker compose up -d --build` path. For a manual setup (or after resetting the `postgres` container):

```bash
docker exec -i trimcp-postgres-1 psql -U mcp_user memory_meta < trimcp/schema.sql
```

Verify extensions:

```bash
docker exec trimcp-postgres-1 psql -U mcp_user memory_meta -c "\dx" | grep -E "pgvector|uuid"
```

### 2c. Environment variables

Copy and edit the example file:

```bash
cp .env.example .env
```

Minimum overrides for local development (the rest of the defaults in `.env.example` work as-is with Docker Compose):

```bash
# .env (local only — never commit)
TRIMCP_MASTER_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx   # any 32+ chars for local dev
MINIO_ACCESS_KEY=mcp_admin
MINIO_SECRET_KEY=super_secure_minio_password
```

`tests/conftest.py` sets `TRIMCP_MASTER_KEY` automatically for the test runner — you only need it in `.env` when running `server.py` or `admin_server.py` directly.

For a full variable reference, see [configuration_reference.md](configuration_reference.md).

### 2d. Install Python dependencies

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

Optional cognitive backend (only needed for `index_code_file` with NLP extraction):

```bash
pip install spacy
python -m spacy download en_core_web_sm
```

### 2e. Run the MCP server

```bash
python server.py
```

The process starts and waits on stdin for JSON-RPC 2.0 messages. Press `Ctrl+C` to stop. To connect Claude Desktop, see the MCP stdio section in [usage_modes.md](usage_modes.md) §1.

### 2f. Run the Admin REST server

```bash
python admin_server.py
# Listens on http://localhost:8003
```

Health check:

```bash
curl http://localhost:8003/api/health
```

Expected response when all four backing services are up:

```json
{
  "status": "healthy",
  "databases": { "postgres": "up", "mongodb": "up", "redis": "up", "minio": "up" }
}
```

---

## 3. Running Tests

### 3a. Full suite

```bash
pytest
```

Most tests are unit/integration tests that run without the Docker services (they mock or stub the database layer). Tests that require live services are marked `@pytest.mark.integration` and skip automatically when services are unavailable.

### 3b. Useful flags

```bash
# Run a specific file
pytest tests/test_signing_cache.py -v

# Run tests matching a keyword
pytest -k "merkle" -v

# Stop on first failure
pytest -x

# Show local variables on failure
pytest -l

# Run integration tests (requires Docker services)
pytest -m integration
```

### 3c. Test layout

| File | What it covers |
|---|---|
| `tests/conftest.py` | `TRIMCP_MASTER_KEY` bootstrap; signing key cache reset between tests |
| `tests/fixtures/fake_asyncpg.py` | In-process fake asyncpg pool used by unit tests |
| `tests/fixtures/http_hmac_helpers.py` | HMAC request signing helpers for admin API tests |
| `tests/test_signing_cache.py` | Key cache isolation and TTL |
| `tests/test_merkle_chain.py` | WORM event log Merkle chain integrity |
| `tests/test_event_log_append.py` | Append-only event log invariants |
| `tests/test_hmac_edge_cases.py` | HMAC auth edge cases (replay, clock skew) |
| `tests/test_integration_engine.py` | Full engine bring-up against live services |
| `tests/test_graph_query.py` | GraphRAG BFS traversal and cycle guard |
| `tests/test_memory_time_travel.py` | Temporal `as_of` query correctness |
| `tests/test_pii_repr.py` | PII redaction and repr safety |
| `tests/test_dsn_redaction.py` | DSN credential scrubbing in logs |

### 3d. Why tests use real databases for integration paths

Unit tests mock the asyncpg pool via `FakeAsyncpgPool` (in `tests/fixtures/`). Integration tests hit real Postgres — this is intentional. TriMCP's correctness depends on RLS `SET LOCAL` semantics, transaction isolation, and trigger behaviour that cannot be reproduced in a pure in-process mock. Running `pytest -m integration` with live services is the definitive correctness check for the storage layer.

---

## 4. Codebase Map

| Module | Responsibility |
|---|---|
| `server.py` | MCP stdio entry point; tool definitions and dispatch |
| `admin_server.py` | Admin REST API; Starlette routes; HMAC + mTLS middleware |
| `trimcp/orchestrator.py` | `TriStackEngine` — connection lifecycle, health checks |
| `trimcp/config.py` | `_Config` — all env vars; `validate()` runs at import |
| `trimcp/db_utils.py` | `scoped_pg_session`, `unmanaged_pg_connection`, `POOL_ACQUIRE_TIMEOUT` |
| `trimcp/orchestrators/memory.py` | `store_memory`, `semantic_search`, Saga pattern |
| `trimcp/orchestrators/graph.py` | KG write path |
| `trimcp/orchestrators/temporal.py` | `as_of` time-travel query filters |
| `trimcp/graph_query.py` | `GraphRAGTraverser` — BFS recursive CTE |
| `trimcp/event_log.py` | `append_event()`, Merkle chain, `verify_merkle_chain()` |
| `trimcp/signing.py` | HMAC-SHA256 signing, key rotation, master key |
| `trimcp/pii.py` | Presidio NER + regex redaction pipeline |
| `trimcp/auth.py` | `HMACAuthMiddleware`, `BasicAuthMiddleware`, `RateLimitError` |
| `trimcp/mtls.py` | `MTLSAuthMiddleware` for client certificate enforcement |
| `trimcp/garbage_collector.py` | Keyset-paginated orphan sweep |
| `trimcp/ast_parser.py` | Tree-sitter AST → code chunks |
| `trimcp/graph_extractor.py` | spaCy NLP → KG triplets; `@lru_cache` model loader |
| `trimcp/schema.sql` | Full PostgreSQL schema, RLS policies, indexes, triggers |

For deep-dives on specific subsystems:

| Topic | Document |
|---|---|
| Connection pools, Saga, GraphRAG pipeline | [database_architecture.md](database_architecture.md) |
| All environment variables | [configuration_reference.md](configuration_reference.md) |
| mTLS, JWT/SSO, HMAC, RLS | [enterprise_security.md](enterprise_security.md) |
| MCP vs. REST API payloads | [usage_modes.md](usage_modes.md) |
| SharePoint / Google Drive / Dropbox bridges | [service_integrations.md](service_integrations.md) |
| Runtime topology, time-travel, A2A, partitioning | [architecture-v1.md](architecture-v1.md) |

---

## 5. Key Invariants for Contributors

These invariants are enforced in code and tests. Violating them will break integration tests or cause silent data corruption in production.

### 5a. All user-facing SQL must use `scoped_pg_session`

```python
# Correct — RLS is active, namespace is isolated
from trimcp.db_utils import scoped_pg_session

async with scoped_pg_session(pool, namespace_id=ns_id) as conn:
    rows = await conn.fetch("SELECT id, content FROM memories")

# Wrong — bypasses RLS, leaks cross-tenant data
async with pool.acquire() as conn:
    rows = await conn.fetch("SELECT id, content FROM memories")
```

Admin and background paths use `unmanaged_pg_connection` — this is intentional and documented. See [database_architecture.md](database_architecture.md) §3.

### 5b. `append_event()` must be called inside the same transaction as the data write

```python
# Correct — event log and memory INSERT are atomic
async with scoped_pg_session(pool, namespace_id=ns_id) as conn:
    memory_id = await conn.fetchval("INSERT INTO memories ... RETURNING id")
    await append_event(conn, event_type="store", memory_id=memory_id, ...)

# Wrong — fire-and-forget breaks WORM atomicity (FIX-012)
await store_memory(...)
await append_event(...)  # separate connection — can succeed while memory write failed
```

### 5c. Never set credentials as defaults in `config.py`

`MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY` default to `""`. `validate_minio_credentials()` raises `ValueError` at startup if they are empty. Do not add non-empty defaults — this is a P0 security control (FIX-013).

### 5d. The ON CONFLICT clause on `kg_edges` requires all four columns

```sql
-- Correct (matches the UNIQUE constraint)
ON CONFLICT (subject_label, predicate, object_label, namespace_id) DO NOTHING

-- Wrong (constraint mismatch → runtime error; FIX-038)
ON CONFLICT (subject_label, predicate, object_label) DO NOTHING
```

### 5e. `SET LOCAL` requires an explicit transaction

`scoped_pg_session` wraps every connection in `conn.transaction()` because `SET LOCAL trimcp.namespace_id` only survives the transaction boundary. Without the explicit `BEGIN`, the variable reverts at the next statement and RLS is silently unenforced (FIX-011).

---

## 6. Contribution Standards

- Follow PEP 8. `ruff` is the linter (`ruff check .`).
- Type-annotate all public functions. `mypy --strict` passes on the `trimcp/` package.
- No magic numbers — use module-level named constants (see `_MAX_AST_DEPTH` in `trimcp/ast_parser.py` as an example).
- Comments explain *why*, not *what*. One short line max; no multi-line docstring blocks.
- New storage paths must use `scoped_pg_session` (§5a) and call `append_event()` inside the same transaction (§5b).
- Tests for new write paths must cover the compensating-delete (Saga) failure branch.
- PRs that touch `trimcp/schema.sql` must include a migration file under `migrations/`.
