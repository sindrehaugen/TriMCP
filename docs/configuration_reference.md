# TriMCP Configuration Reference

Authoritative reference for every environment variable, server entry-point, and runtime flag.
All reads happen in `trimcp/config.py` (the `_Config` class).
No other module calls `os.getenv()` directly.

---

## 1. Database & Storage Connections

| Variable | Default | Required | Description |
|---|---|---|---|
| `MONGO_URI` | `mongodb://localhost:27017` | Yes (prod) | MongoDB connection string. Used by Motor for episodic payload storage. |
| `PG_DSN` | `postgresql://mcp_user:mcp_password@localhost:5432/memory_meta` | Yes | Primary PostgreSQL DSN. Also read as `DATABASE_URL` (12-factor alias; `PG_DSN` wins when both set). |
| `DATABASE_URL` | — | No | 12-factor alias for `PG_DSN`. Ignored when `PG_DSN` is set. |
| `DB_READ_URL` | falls back to `PG_DSN` | No | Optional read-replica DSN. When set and different from `PG_DSN`, a second asyncpg pool is created for read-only queries. |
| `DB_WRITE_URL` | falls back to `PG_DSN` | No | Reserved write-DSN override (future use; engine currently uses `PG_DSN` for writes). |
| `PG_BOUNCER_URL` | `""` | No | PgBouncer connection URL when running behind a connection pooler. |
| `REDIS_URL` | `redis://localhost:6379/0` | Yes (prod) | Redis connection string. Used by both async (`redis.asyncio`) and sync clients (RQ). |
| `MINIO_ENDPOINT` | `localhost:9000` | Yes (media) | MinIO host:port. Used by the `minio` client. |
| `MINIO_ACCESS_KEY` | `""` | **P0 Required** | MinIO access key. Must be set via env — no default permitted (FIX-013). |
| `MINIO_SECRET_KEY` | `""` | **P0 Required** | MinIO secret key. Must be set via env — startup raises `ValueError` if empty. |
| `MINIO_SECURE` | `false` | No | Set `true` to use TLS for MinIO connections. |

---

## 2. PostgreSQL Pool Tuning

| Variable | Default | Description |
|---|---|---|
| `PG_MIN_POOL` | `1` | Minimum asyncpg connection pool size (`min_size`). |
| `PG_MAX_POOL` | `10` | Maximum asyncpg connection pool size (`max_size`). |

`command_timeout` is hardcoded to `30 s` in `TriStackEngine.connect()`.
Pool acquire timeout is `10.0 s` (constant `POOL_ACQUIRE_TIMEOUT` in `trimcp/db_utils.py`).

---

## 3. Redis Tuning

| Variable | Default | Description |
|---|---|---|
| `REDIS_TTL` | `3600` | Default cache TTL in seconds for Redis entries. |
| `REDIS_MAX_CONNECTIONS` | `20` | Maximum connections in the async and sync Redis pools. |

---

## 4. Authentication & Security

| Variable | Default | P-level | Description |
|---|---|---|---|
| `TRIMCP_MASTER_KEY` | `""` | **P0** | AES-256 master key for signing-key encryption at rest. **Server refuses to start** if absent or < 32 UTF-8 bytes. Minimum 32 random bytes, base64 or hex. |
| `TRIMCP_API_KEY` | `""` | P1 | HMAC-SHA256 key for HTTP admin API auth (`HMACAuthMiddleware`). Warning logged if absent. |
| `TRIMCP_ADMIN_USERNAME` | `""` | P1 | HTTP Basic Auth username for admin UI routes (`BasicAuthMiddleware`). |
| `TRIMCP_ADMIN_PASSWORD` | `""` | P1 | HTTP Basic Auth password for admin UI routes. |
| `TRIMCP_ADMIN_OVERRIDE` | `""` | **Dev only** | Set to `true` to bypass admin auth in development. **Raises `RuntimeError` at startup when `ENVIRONMENT=prod`.** |
| `ENVIRONMENT` | `dev` | P0 | Runtime environment label. Set to `prod` in production. Used by the admin-override guard (FIX-039). |
| `TRIMCP_CLOCK_SKEW_TOLERANCE_S` | `300` | No | Maximum allowed timestamp drift (seconds) for HMAC replay protection. |
| `TRIMCP_DISTRIBUTED_REPLAY` | `false` | No | Enable Redis-backed nonce store for HMAC replay protection across multiple admin replicas. |

---

## 5. JWT / Bearer Authentication

| Variable | Default | Description |
|---|---|---|
| `TRIMCP_JWT_SECRET` | `""` | HS256 shared secret for JWT validation (dev / testing). |
| `TRIMCP_JWT_PUBLIC_KEY` | `""` | RS256/ES256 PEM-encoded public key. May be a raw PEM string or `file:///path/to/pub.pem`. Takes precedence over `TRIMCP_JWT_SECRET` when both are set. |
| `TRIMCP_JWT_ALGORITHM` | `HS256` | One of `HS256`, `RS256`, `ES256`. |
| `TRIMCP_JWT_ISSUER` | `""` | Expected `iss` claim. Empty = skip issuer check. |
| `TRIMCP_JWT_AUDIENCE` | `""` | Expected `aud` claim. Empty = skip audience check. |
| `TRIMCP_JWT_PREFIX` | `/api/v1/` | Route prefix protected by `JWTAuthMiddleware`. |
| `TRIMCP_A2A_JWT_AUDIENCE` | `trimcp_a2a` | Per-service `aud` override for the A2A server, preventing token replay across system boundaries. |

---

## 6. mTLS — A2A Server

| Variable | Default | Description |
|---|---|---|
| `TRIMCP_A2A_MTLS_ENABLED` | `false` | Master switch — enable mTLS client certificate enforcement on A2A routes. |
| `TRIMCP_A2A_MTLS_STRICT` | `true` | Reject connections that present no client certificate. Set `false` for rolling deployments. |
| `TRIMCP_A2A_MTLS_TRUSTED_PROXY_HOP` | `1` | Number of trusted reverse-proxy hops. `0` = direct TLS only; `1` = one proxy (Caddy / nginx). |
| `TRIMCP_A2A_MTLS_ALLOWED_SANS` | `""` | Comma-separated allowed Subject Alternative Names (case-insensitive DNS/URI match). |
| `TRIMCP_A2A_MTLS_ALLOWED_FINGERPRINTS` | `""` | Comma-separated allowed SHA-256 certificate fingerprints (colon-separated hex). |

---

## 7. mTLS — Admin Server

| Variable | Default | Description |
|---|---|---|
| `TRIMCP_ADMIN_MTLS_ENABLED` | `false` | Enable mTLS client certificate enforcement on `/api/` admin routes. |
| `TRIMCP_ADMIN_MTLS_STRICT` | `true` | Reject connections with no client certificate. |
| `TRIMCP_ADMIN_MTLS_TRUSTED_PROXY_HOP` | `1` | Trusted reverse-proxy hops for `X-Forwarded-Client-Cert`. |
| `TRIMCP_ADMIN_MTLS_ALLOWED_SANS` | `""` | Comma-separated allowed SANs for admin mTLS. |
| `TRIMCP_ADMIN_MTLS_ALLOWED_FINGERPRINTS` | `""` | Comma-separated allowed SHA-256 fingerprints for admin mTLS. |

---

## 8. LLM Provider API Keys

All keys default to `""`. The provider factory logs a warning when the needed key is absent.
Per-namespace overrides use `ref:env/<VAR>` in namespace metadata (see `llm_providers.md`).

| Variable | Provider |
|---|---|
| `TRIMCP_ANTHROPIC_API_KEY` | Anthropic Claude (`claude-opus-4-7`, etc.) |
| `TRIMCP_OPENAI_API_KEY` | OpenAI (GPT-4.5, etc.) |
| `TRIMCP_AZURE_OPENAI_API_KEY` | Azure OpenAI (`api-key` header) |
| `TRIMCP_AZURE_OPENAI_ENDPOINT` | Azure OpenAI resource endpoint (required for `azure_openai` provider) |
| `TRIMCP_AZURE_OPENAI_DEPLOYMENT` | Azure OpenAI default deployment name |
| `TRIMCP_GEMINI_API_KEY` | Google AI Studio / Gemini |
| `TRIMCP_DEEPSEEK_API_KEY` | DeepSeek (cost-sensitive deployments) |
| `TRIMCP_MOONSHOT_API_KEY` | Moonshot / Kimi (large-context) |
| `TRIMCP_OPENAI_COMPAT_BASE_URL` | Base URL for any OpenAI-compatible provider |
| `TRIMCP_OPENAI_COMPAT_API_KEY` | API key for OpenAI-compatible provider |
| `TRIMCP_OPENAI_COMPAT_MODEL` | Default model name for OpenAI-compatible provider |
| `TRIMCP_LLM_PROVIDER` | `local-cognitive-model` | Default LLM provider label (matches labels in `providers/factory.py`). |

---

## 9. Local Cognitive / Embedding Backend

| Variable | Default | Description |
|---|---|---|
| `TRIMCP_COGNITIVE_BASE_URL` | `""` | Base URL for the local cognitive container (e.g. `http://cognitive:11435`). When set, embeddings route to `POST {base}/v1/embeddings`. |
| `TRIMCP_COGNITIVE_EMBEDDING_MODEL` | `""` | Model name to request from the cognitive HTTP endpoint. |
| `TRIMCP_COGNITIVE_API_KEY` | `""` | API key for the cognitive endpoint (optional). |
| `TRIMCP_BACKEND` | `""` | Hardware backend selector: `openvino-npu` enables Intel NPU path via OpenVINO. |
| `TRIMCP_OPENVINO_MODEL_DIR` | `""` | Path to the exported OpenVINO IR directory (required when `TRIMCP_BACKEND=openvino-npu`). |
| `TRIMCP_OPENVINO_SEQ_LEN` | `512` | Fixed token sequence length for the static NPU graph. |
| `TRIMCP_OPENVINO_MODEL_REVISION` | `""` | HuggingFace commit SHA to pin when loading tokenizers with `trust_remote_code=True`. Warning logged if absent (FIX-053). |
| `EMBEDDING_VECTOR_DIM` | `768` | pgvector dimension. Must match the `memories.embedding` and `kg_nodes.embedding` column definition in `schema.sql`. Changing requires a DB migration. |
| `NLI_MODEL_ID` | `cross-encoder/nli-deberta-v3-small` | HuggingFace model ID for contradiction NLI scoring. |
| `EMBED_BATCH_CHUNK` | `64` | Maximum memories per embedding batch request. |

---

## 10. Document Bridges & OAuth

| Variable | Default | Description |
|---|---|---|
| `BRIDGE_WEBHOOK_BASE_URL` | `""` | Publicly-reachable HTTPS base URL for webhook callbacks. Required to register subscriptions. |
| `GRAPH_BRIDGE_TOKEN` | `""` | MS Graph API OAuth bearer token (or use `AZURE_CLIENT_*` app credentials below). |
| `GDRIVE_BRIDGE_TOKEN` | `""` | Google Drive OAuth token (or use `GDRIVE_OAUTH_*` credentials). |
| `DROPBOX_BRIDGE_TOKEN` | `""` | Dropbox OAuth token. |
| `AZURE_CLIENT_ID` | `""` | Azure AD app registration client ID (SharePoint / OneDrive). |
| `AZURE_CLIENT_SECRET` | `""` | Azure AD app registration client secret. |
| `AZURE_TENANT_ID` | `common` | Azure AD tenant ID (`common` for multi-tenant). |
| `BRIDGE_OAUTH_REDIRECT_URI` | `http://127.0.0.1:8765/bridge/oauth/callback` | OAuth redirect URI for bridge token acquisition. |
| `GDRIVE_OAUTH_CLIENT_ID` | `""` | Google Drive OAuth 2.0 client ID. |
| `GDRIVE_OAUTH_CLIENT_SECRET` | `""` | Google Drive OAuth 2.0 client secret. |
| `DROPBOX_OAUTH_CLIENT_ID` | `""` | Dropbox app client ID. |
| `BRIDGE_RENEWAL_LOOKAHEAD_HOURS` | `12` | Renew bridge subscriptions expiring within this many hours. |
| `BRIDGE_CRON_INTERVAL_MINUTES` | `45` | How often the bridge renewal cron job runs (minutes). |

### Webhook Receiver Secrets (trimcp/webhook_receiver)

| Variable | Description |
|---|---|
| `DROPBOX_APP_SECRET` | App Secret from Dropbox App Console. Verifies `X-Dropbox-Signature` HMAC-SHA256. |
| `GRAPH_CLIENT_STATE` | Secure random string used to validate `clientState` in MS Graph webhook payloads. |
| `DRIVE_CHANNEL_TOKEN` | Secure token provided during Google Drive channel creation. Validates `X-Goog-Channel-Token`. |

---

## 11. SMTP Notifications

| Variable | Default | Description |
|---|---|---|
| `TRIMCP_SMTP_FROM` | `""` | Sender address for alert emails. **Required** — startup raises `ValueError` if empty when SMTP host is configured (FIX-052). |
| `TRIMCP_SMTP_TO` | `""` | Recipient address for alert emails. **Required** (same condition as above). |

SMTP is sent on **port 587 with STARTTLS** (`aiosmtplib`). The SMTP host itself is set via `NotificationDispatcher.smtp_host` at runtime (not an env var — configure programmatically or extend the dispatcher).

---

## 12. Garbage Collector

| Variable | Default | Description |
|---|---|---|
| `GC_INTERVAL_SECONDS` | `3600` | How often the orphan GC loop runs (seconds). |
| `GC_ORPHAN_AGE_SECONDS` | `86400` | Minimum age before a payload-less Mongo document is considered an orphan (seconds). |
| `GC_PAGE_SIZE` | `500` | Keyset-paginated batch size for GC sweeps (FIX-027). |
| `GC_MAX_CONNECT_ATTEMPTS` | `5` | DB reconnect attempts before GC loop aborts. |
| `GC_CONNECT_BASE_DELAY` | `2.0` | Base back-off delay between GC reconnect attempts (seconds). |
| `GC_ALERT_THRESHOLD` | `100` | Number of orphans that triggers an alert dispatch. |

---

## 13. Cognitive / Consolidation Workers

| Variable | Default | Description |
|---|---|---|
| `CONSOLIDATION_DECAY_SOURCES` | `false` | When `true`, source memories are soft-decayed after consolidation. |
| `CONSOLIDATION_CRON_INTERVAL_MINUTES` | `360` | How often the consolidation cron job runs (6 h default). |
| `CONSOLIDATION_HALF_LIFE_DAYS` | `30.0` | Ebbinghaus half-life for memory salience decay (days). |
| `CRON_STARTUP_JITTER_MAX_SECONDS` | `60.0` | Maximum random startup delay before first cron execution. Prevents thundering-herd DB spikes on rolling deployments. Set `0` to disable. |

---

## 14. Quotas

| Variable | Default | Description |
|---|---|---|
| `TRIMCP_QUOTAS_ENABLED` | `true` | Master switch — when `false`, quota queries are skipped on the tool hot path. |
| `TRIMCP_QUOTA_TOKEN_ESTIMATE_DIVISOR` | `4` | Characters-per-token divisor for pre-flight quota estimates. |

---

## 15. Observability

| Variable | Default | Description |
|---|---|---|
| `TRIMCP_PROMETHEUS_PORT` | `8000` | Port for the Prometheus metrics scrape endpoint. |
| `TRIMCP_OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318` | OpenTelemetry OTLP gRPC/HTTP exporter endpoint. |
| `TRIMCP_OTEL_SERVICE_NAME` | `trimcp-python` | Service name reported to OTel backends. |
| `TRIMCP_OBSERVABILITY_ENABLED` | `true` | Master switch for OTel + Prometheus instrumentation. |

---

## 16. Task Queue & Dead-Letter Queue

| Variable | Default | Description |
|---|---|---|
| `TASK_MAX_RETRIES` | `5` | Maximum RQ worker retries before routing to `dead_letter_queue`. `0` = infinite retries. |
| `TASK_DLQ_REDIS_TTL` | `86400` | TTL for Redis attempt-count keys (seconds). After expiry, retry counter resets. |
| `TRIMCP_DISABLE_MIGRATION_MCP` | `false` | When `true`, `start_migration`, `commit_migration`, `abort_migration` are excluded from the MCP tool list. Recommended for production SaaS deployments. |

---

## 17. Temporal Queries

| Variable | Default | Description |
|---|---|---|
| `TRIMCP_MAX_TEMPORAL_LOOKBACK_DAYS` | `90` | Maximum lookback window for `as_of` temporal queries (days). Prevents unbounded scans on `event_log`. Set `0` to disable. |

---

## 18. Media Upload

| Variable | Default | Description |
|---|---|---|
| `TRIMCP_MAX_ATTACHMENT_BYTES` | `52428800` (50 MB) | Maximum accepted blob size for `extract_bytes` and `store_media`. Oversized payloads are rejected before any I/O. |

---

## 19. Server Entry-Points

### `server.py` — MCP stdio server

```bash
python server.py
```

Listens on **stdio** (MCP JSON-RPC 2.0). No CLI arguments — fully configured via environment.
Launched processes on startup:
- `run_gc_loop()` — orphan GC background task
- `start_re_embedder()` — re-embedding background task

### `admin_server.py` — HTTPS REST admin interface

```bash
python admin_server.py
# or via uvicorn directly:
uvicorn admin_server:app --host 0.0.0.0 --port 8003
```

Default port: **8003**. Middleware stack (applied in order):
1. `OpenTelemetryTraceMiddleware` — distributed trace context
2. `MTLSAuthMiddleware` — client certificate enforcement (when enabled)
3. `BasicAuthMiddleware` — UI routes (`/`)
4. `HMACAuthMiddleware` — API routes (`/api/`)

### `trimcp/a2a_server.py` — A2A JSON-RPC server

```bash
python -m trimcp.a2a_server
# or:
uvicorn trimcp.a2a_server:app --host 0.0.0.0 --port 8001
```

Serves agent card + JSON-RPC 2.0 skill endpoints. Protected by `MTLSAuthMiddleware` (A2A mTLS vars).

### `python -m trimcp.cron` — APScheduler cron daemon

```bash
python -m trimcp.cron
```

Runs two APScheduler jobs:
- `bridge_subscription_renewal` — renews expiring bridge webhooks
- `phase_2_1_reembedding` — re-embedding sweep

### `start_worker.py` — RQ async worker

```bash
python start_worker.py
# or:
rq worker trimcp-tasks --url $REDIS_URL
```

Processes `index_code_file` jobs from the `trimcp-tasks` Redis queue.

---

## 20. Validation at Startup

`_Config.validate()` is called automatically during `TriStackEngine.connect()`.
It halts with `RuntimeError` on:
- Missing or too-short `TRIMCP_MASTER_KEY`
- Empty `MINIO_ACCESS_KEY` or `MINIO_SECRET_KEY`
- Missing `MONGO_URI`, `PG_DSN`, or `REDIS_URL`

It logs `WARNING` (non-halting) when:
- `TRIMCP_API_KEY` is absent (admin API inaccessible)
- Neither `TRIMCP_JWT_SECRET` nor `TRIMCP_JWT_PUBLIC_KEY` is set (A2A disabled)
