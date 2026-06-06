"""
NCE — centralised environment configuration.

All env-var reads for the entire package live here. No other module should
call os.getenv() directly. This makes the full configuration surface visible
in one place, easy to validate, and easy to override in tests.

Import pattern inside the package:
    from nce.config import cfg
"""

import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from dotenv import load_dotenv

# Conditionally load .env — disabled in production by setting NCE_LOAD_DOTENV=false.
if os.environ.get("NCE_LOAD_DOTENV", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}:
    load_dotenv()

# Hard cutover guard: raise early if any legacy TRIMCP_ keys are present so
# operators get an explicit, actionable error rather than silent misconfiguration.
_LEGACY_PREFIX = "TRIMCP_"
_NCE_PREFIX = "NCE_"
_legacy_keys = [k for k in os.environ if k.startswith(_LEGACY_PREFIX)]
if _legacy_keys:
    _mapping = "\n".join(
        f"  {k}  →  {_NCE_PREFIX}{k[len(_LEGACY_PREFIX):]}" for k in sorted(_legacy_keys)
    )
    raise EnvironmentError(
        "Legacy TRIMCP_* environment variables detected. "
        "Rename them to NCE_* before starting the server:\n" + _mapping
    )

log = logging.getLogger("nce-config")

_MASTER_KEY_MIN_UTF8_BYTES: int = 32

# Match ``scheme://user:password@`` for common datastore / cache URI schemes (exception text scrubbing).
_RE_URI_CREDS = re.compile(
    r"(?P<prefix>(?:mongodb\+srv|mongodb|postgresql|postgres|redis|rediss)://)"
    r"(?P<user>[^:/?#\s]+):(?P<password>[^@/?#\s]+)@",
    re.IGNORECASE,
)
# Redis/Mongo ``scheme://:password@host`` (no username).
_RE_URI_PASS_ONLY = re.compile(
    r"(?P<prefix>(?:mongodb\+srv|mongodb|postgresql|postgres|redis|rediss)://)"
    r":(?P<password>[^@/?#\s]+)@",
    re.IGNORECASE,
)


def redact_dsn(dsn: str) -> str:
    """Mask the password component of a database/service URI.

    Handles the standard ``scheme://user:password@host/path`` format
    (including ``mongodb+srv``, ``redis://:password@host``).
    Returns the URI with the password replaced by ``***``.
    If parsing fails, returns ``<redacted>`` so the raw DSN is never
    accidentally surfaced in log or exception messages.
    """
    try:
        parsed = urlparse(dsn)
        if parsed.password:
            # Rebuild with masked password
            netloc = parsed.hostname or ""
            if parsed.port:
                netloc = f"{netloc}:{parsed.port}"
            if parsed.username:
                netloc = f"{parsed.username}:***@{netloc}"
            else:
                # Password-only auth (Redis format: redis://:pass@host)
                netloc = f":***@{netloc}"
            return urlunparse(parsed._replace(netloc=netloc))
        return dsn
    except Exception:
        return "<redacted>"


def redact_secrets_in_text(text: str) -> str:
    """Scrub ``user:password@`` fragments from arbitrary log/exception strings.

    Database clients sometimes echo the full DSN in connection errors. This
    regex pass catches embedded URIs that :func:`redact_dsn` would parse in
    isolation but appear inside longer messages.
    """
    if not text:
        return text
    scrubbed = _RE_URI_CREDS.sub(r"\g<prefix>\g<user>:***@", text)
    return _RE_URI_PASS_ONLY.sub(r"\g<prefix>:***@", scrubbed)


def _fail_unless_nce_master_key_ok(raw: str) -> None:
    """Raise RuntimeError if the master key is missing or shorter than 32 UTF-8 bytes."""
    v = (raw or "").strip()
    if not v or len(v.encode("utf-8")) < _MASTER_KEY_MIN_UTF8_BYTES:
        raise RuntimeError(
            "CRITICAL SECURITY FAILURE: NCE_MASTER_KEY is missing or too short. "
            f"A minimum of {_MASTER_KEY_MIN_UTF8_BYTES} UTF-8 bytes of random key material "
            "is required to import or start the server."
        )


# ---------------------------------------------------------------------------
# Env-var parsing helpers — used only by _Config below.
# ---------------------------------------------------------------------------


def _bool_env(name: str, default: bool = False) -> bool:
    """Parse a boolean environment variable.

    Accepts ``1``, ``true``, ``yes``, ``on`` (case-insensitive) as truthy.
    Returns *default* when the variable is unset.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int, *, minimum: int | None = None) -> int:
    """Parse an integer environment variable, optionally enforcing a minimum."""
    raw = os.getenv(name)
    value = default if raw is None or raw.strip() == "" else int(raw)
    if minimum is not None and value < minimum:
        raise RuntimeError(f"{name} must be >= {minimum}, got {value}")
    return value


def live_env_str(name: str, *, default: str = "") -> str:
    """Read a string from the live process environment (honours runtime / pytest changes).

    Unlike ``cfg`` fields captured at import, this always reflects the current env.
    Auth scope checks use these helpers so ``monkeypatch.setenv`` / ``delenv`` behave correctly.
    """
    return (os.getenv(name, default) or "").strip()


def live_admin_override_enabled() -> bool:
    return live_env_str("NCE_ADMIN_OVERRIDE").lower() in {"1", "true", "yes", "on"}


def live_admin_api_key() -> str:
    return live_env_str("NCE_ADMIN_API_KEY")


def live_mcp_api_key() -> str:
    return live_env_str("NCE_MCP_API_KEY")


def live_mcp_namespace_id() -> str:
    return live_env_str("NCE_MCP_NAMESPACE_ID")


def _float_env(name: str, default: float, *, minimum: float | None = None) -> float:
    """Parse a float environment variable, optionally enforcing a minimum."""
    raw = os.getenv(name)
    value = default if raw is None or raw.strip() == "" else float(raw)
    if minimum is not None and value < minimum:
        raise RuntimeError(f"{name} must be >= {minimum}, got {value}")
    return value


class _EmbeddingConfig:
    """
    Embedding / pgvector dimension. Must stay aligned with ``memories.embedding`` and
    ``kg_nodes.embedding`` in ``schema.sql`` — changing this requires a DB migration.
    """

    VECTOR_DIM: int = int(os.getenv("EMBEDDING_VECTOR_DIM", "768"))


class _Config:
    EMBEDDING = _EmbeddingConfig

    # --- Environment mode ---
    # Set NCE_ENV=prod in production. Controls fail-fast validation and
    # whether dev-convenience defaults are accepted at startup.
    ENVIRONMENT: str = os.getenv("NCE_ENV", "dev").strip().lower()
    IS_PROD: bool = ENVIRONMENT in {"prod", "production"}
    IS_TEST: bool = ENVIRONMENT in {"test", "testing", "ci"}
    IS_DEV: bool = not IS_PROD and not IS_TEST

    # --- Database connections ---
    # ``DATABASE_URL`` is accepted as a 12-factor alias for ``PG_DSN`` (same precedence: explicit PG_DSN wins).
    NCE_APP_PASSWORD: str = os.getenv("NCE_APP_PASSWORD", "nce_app_secret").strip()
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    PG_DSN: str = (
        os.getenv("PG_DSN")
        or os.getenv("DATABASE_URL")
        or "postgresql://mcp_user:mcp_password@localhost:5432/memory_meta"
    )
    # Read/write split — fall back to PG_DSN when not explicitly configured
    DB_READ_URL: str = (
        os.getenv("DB_READ_URL")
        or os.getenv("PG_DSN")
        or os.getenv("DATABASE_URL")
        or "postgresql://mcp_user:mcp_password@localhost:5432/memory_meta"
    )
    DB_WRITE_URL: str = (
        os.getenv("DB_WRITE_URL")
        or os.getenv("PG_DSN")
        or os.getenv("DATABASE_URL")
        or "postgresql://mcp_user:mcp_password@localhost:5432/memory_meta"
    )
    PG_BOUNCER_URL: str = os.getenv("PG_BOUNCER_URL", "")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # --- Redis ---
    REDIS_TTL: int = int(os.getenv("REDIS_TTL", "3600"))
    REDIS_MAX_CONNECTIONS: int = int(os.getenv("REDIS_MAX_CONNECTIONS", "20"))

    # --- PostgreSQL connection pool ---
    PG_MIN_POOL: int = int(os.getenv("PG_MIN_POOL", "1"))
    PG_MAX_POOL: int = int(os.getenv("PG_MAX_POOL", "10"))
    NCE_PARTITION_LOOKAHEAD_MONTHS: int = _int_env("NCE_PARTITION_LOOKAHEAD_MONTHS", 3, minimum=1)

    # --- Garbage collector ---
    GC_INTERVAL_SECONDS: int = int(os.getenv("GC_INTERVAL_SECONDS", "3600"))
    GC_ORPHAN_AGE_SECONDS: int = int(os.getenv("GC_ORPHAN_AGE_SECONDS", "86400"))
    GC_PAGE_SIZE: int = int(os.getenv("GC_PAGE_SIZE", "500"))
    GC_MAX_CONNECT_ATTEMPTS: int = int(os.getenv("GC_MAX_CONNECT_ATTEMPTS", "5"))
    GC_CONNECT_BASE_DELAY: float = float(os.getenv("GC_CONNECT_BASE_DELAY", "2.0"))
    GC_ALERT_THRESHOLD: int = int(os.getenv("GC_ALERT_THRESHOLD", "100"))

    # --- Attachment / extraction size limits ---
    # Maximum blob size accepted by extract_bytes and store_media.
    # Oversized payloads are rejected before any I/O to prevent RQ worker OOM.
    NCE_MAX_ATTACHMENT_BYTES: int = int(
        os.getenv("NCE_MAX_ATTACHMENT_BYTES", str(50 * 1024 * 1024))
    )  # 50 MB default

    # --- MCP Sizing Limits ---
    NCE_MAX_ARGUMENTS_JSON_SIZE: int = _int_env(
        "NCE_MAX_ARGUMENTS_JSON_SIZE", 1_000_000, minimum=1024
    )
    NCE_MAX_METADATA_KEYS: int = _int_env(
        "NCE_MAX_METADATA_KEYS", 512, minimum=1
    )
    NCE_MAX_METADATA_KEY_LEN: int = _int_env(
        "NCE_MAX_METADATA_KEY_LEN", 256, minimum=1
    )
    NCE_MAX_METADATA_STRING_VALUE_LEN: int = _int_env(
        "NCE_MAX_METADATA_STRING_VALUE_LEN", 4096, minimum=1
    )
    NCE_MAX_METADATA_LIST_ITEMS: int = _int_env(
        "NCE_MAX_METADATA_LIST_ITEMS", 256, minimum=1
    )

    # --- Temporal queries ---
    # Maximum lookback window for ``as_of`` temporal queries.  Prevents
    # unbounded historical searches that trigger full-table scans on
    # ``event_log``.  Set to 0 to disable the boundary (not recommended).
    NCE_MAX_TEMPORAL_LOOKBACK_DAYS: int = int(
        os.getenv("NCE_MAX_TEMPORAL_LOOKBACK_DAYS", "90")
    )

    # --- Code indexing limits ---
    # Max raw bytes allowed through index_code_file() before the file is skipped.
    NCE_MAX_CODE_INDEX_BYTES: int = _int_env(
        "NCE_MAX_CODE_INDEX_BYTES", 2 * 1024 * 1024, minimum=1024
    )
    # Max AST/line chunks extracted per file — prevents embedding queue flood.
    NCE_MAX_CODE_CHUNKS_PER_FILE: int = _int_env(
        "NCE_MAX_CODE_CHUNKS_PER_FILE", 500, minimum=1
    )

    # --- Embeddings ---
    EMBEDDING_MAX_WORKERS: int = _int_env("EMBEDDING_MAX_WORKERS", 1, minimum=1)
    EMBED_BATCH_CHUNK: int = int(os.getenv("EMBED_BATCH_CHUNK", "64"))
    # Model identity — configurable so operators can swap the embedding model without a code change.
    NCE_EMBEDDING_MODEL_ID: str = os.getenv(
        "NCE_EMBEDDING_MODEL_ID", "jinaai/jina-embeddings-v2-base-code"
    )
    # Pin model revision for supply-chain safety; empty string means "latest" (not recommended in prod).
    NCE_EMBEDDING_MODEL_REVISION: str = os.getenv("NCE_EMBEDDING_MODEL_REVISION", "")
    # trust_remote_code=True is required for some Jina models; must be explicit in production.
    NCE_EMBEDDING_TRUST_REMOTE_CODE: bool = os.getenv(
        "NCE_EMBEDDING_TRUST_REMOTE_CODE", "false"
    ).strip().lower() in {"1", "true", "yes", "on"}
    # Input guard — reject batches that exceed these limits rather than silently truncating.
    NCE_EMBED_MAX_BATCH_TEXTS: int = int(os.getenv("NCE_EMBED_MAX_BATCH_TEXTS", "512"))
    NCE_EMBED_MAX_TEXT_CHARS: int = int(os.getenv("NCE_EMBED_MAX_TEXT_CHARS", "32000"))
    # Enterprise §8 — hardware backend / OpenVINO NPU (see nce.embeddings, openvino_npu_export).
    NCE_BACKEND: str = (os.getenv("NCE_BACKEND") or "").strip().lower()
    NCE_OPENVINO_MODEL_DIR: str = (os.getenv("NCE_OPENVINO_MODEL_DIR") or "").strip()
    NCE_OPENVINO_SEQ_LEN: int = int(os.getenv("NCE_OPENVINO_SEQ_LEN", "512"))

    # --- Contradictions / NLI ---
    NLI_MODEL_ID: str = os.getenv("NLI_MODEL_ID", "cross-encoder/nli-deberta-v3-small")
    NCE_CONTRADICTION_SIMILARITY_THRESHOLD: float = _float_env("NCE_CONTRADICTION_SIMILARITY_THRESHOLD", 0.85, minimum=0.0)
    NCE_CONTRADICTION_MAX_CANDIDATES: int = _int_env("NCE_CONTRADICTION_MAX_CANDIDATES", 3, minimum=1)
    NCE_CONTRADICTION_NLI_THRESHOLD: float = _float_env("NCE_CONTRADICTION_NLI_THRESHOLD", 0.8, minimum=0.0)
    NCE_CONTRADICTION_LLM_MIN_CONFIDENCE: float = _float_env("NCE_CONTRADICTION_LLM_MIN_CONFIDENCE", 0.6, minimum=0.0)

    # --- D2 / D7 — Local cognitive bundle (OpenAI-compatible HTTP on port 11435) ---
    # When NCE_COGNITIVE_BASE_URL is set (e.g. http://cognitive:11435), embeddings
    # route to POST {base}/v1/embeddings unless NCE_BACKEND selects an in-process backend.
    NCE_COGNITIVE_BASE_URL: str = (
        (os.getenv("NCE_COGNITIVE_BASE_URL") or "").strip().rstrip("/")
    )
    NCE_COGNITIVE_EMBEDDING_MODEL: str = (
        os.getenv("NCE_COGNITIVE_EMBEDDING_MODEL") or ""
    ).strip()
    # Fallback model used when the primary cognitive backend returns 429 or times out.
    NCE_COGNITIVE_FALLBACK_MODEL: str = os.getenv(
        "NCE_COGNITIVE_FALLBACK_MODEL", "text-embedding-3-small"
    ).strip()
    NCE_COGNITIVE_API_KEY: str = (os.getenv("NCE_COGNITIVE_API_KEY") or "").strip()
    # Declarative default LLM provider label for operators / future LLMProvider wiring [D2].
    NCE_LLM_PROVIDER: str = (os.getenv("NCE_LLM_PROVIDER") or "local-cognitive-model").strip()

    # --- A2A server ---
    # Base URL at which the A2A server is reachable (used in agent card discovery).
    NCE_A2A_URL: str = os.getenv("NCE_A2A_URL", "http://localhost:8004").rstrip("/")

    # --- Document bridges (Phase 2 / §10.3) — OAuth tokens from env or future bridge_tokens PG ---
    GRAPH_BRIDGE_TOKEN: str = os.getenv("GRAPH_BRIDGE_TOKEN", "")
    GDRIVE_BRIDGE_TOKEN: str = os.getenv("GDRIVE_BRIDGE_TOKEN", "")
    DROPBOX_BRIDGE_TOKEN: str = os.getenv("DROPBOX_BRIDGE_TOKEN", "")
    # Bridge worker token-resolution timeout (seconds). Prevents RQ workers
    # from hanging on slow DB/OAuth exchanges.
    BRIDGE_RESOLVE_TIMEOUT_S: float = _float_env("BRIDGE_RESOLVE_TIMEOUT_S", 10.0, minimum=0.1)

    # --- Bridge OAuth / webhooks (§10.6–10.7) ---
    BRIDGE_WEBHOOK_BASE_URL: str = os.getenv("BRIDGE_WEBHOOK_BASE_URL", "").rstrip("/")
    # When true, webhook rate limits use the first X-Forwarded-For hop (trusted proxy only).
    NCE_WEBHOOK_TRUST_PROXY: bool = _bool_env("NCE_WEBHOOK_TRUST_PROXY", False)
    WEBHOOK_MAX_BODY_BYTES: int = max(1, int(os.getenv("WEBHOOK_MAX_BODY_BYTES", "1048576")))
    WEBHOOK_RATE_LIMIT: int = max(1, int(os.getenv("WEBHOOK_RATE_LIMIT", "120")))
    WEBHOOK_RATE_PERIOD_SECONDS: int = max(1, int(os.getenv("WEBHOOK_RATE_PERIOD_SECONDS", "60")))
    WEBHOOK_DEDUP_TTL_SECONDS: int = max(60, int(os.getenv("WEBHOOK_DEDUP_TTL_SECONDS", "86400")))
    WEBHOOK_DEDUP_FAIL_OPEN: bool = _bool_env("WEBHOOK_DEDUP_FAIL_OPEN", False)
    DROPBOX_APP_SECRET: str = os.getenv("DROPBOX_APP_SECRET", "")
    GRAPH_CLIENT_STATE: str = os.getenv("GRAPH_CLIENT_STATE", "")
    DRIVE_CHANNEL_TOKEN: str = os.getenv("DRIVE_CHANNEL_TOKEN", "")
    AZURE_CLIENT_ID: str = os.getenv("AZURE_CLIENT_ID", "")
    AZURE_CLIENT_SECRET: str = os.getenv("AZURE_CLIENT_SECRET", "")
    AZURE_TENANT_ID: str = os.getenv("AZURE_TENANT_ID", "common")
    BRIDGE_OAUTH_REDIRECT_URI: str = os.getenv(
        "BRIDGE_OAUTH_REDIRECT_URI", "http://127.0.0.1:8765/bridge/oauth/callback"
    )
    GDRIVE_OAUTH_CLIENT_ID: str = os.getenv("GDRIVE_OAUTH_CLIENT_ID", "")
    GDRIVE_OAUTH_CLIENT_SECRET: str = os.getenv("GDRIVE_OAUTH_CLIENT_SECRET", "")
    DROPBOX_OAUTH_CLIENT_ID: str = os.getenv("DROPBOX_OAUTH_CLIENT_ID", "")
    BRIDGE_RENEWAL_LOOKAHEAD_HOURS: int = int(os.getenv("BRIDGE_RENEWAL_LOOKAHEAD_HOURS", "12"))
    BRIDGE_CRON_INTERVAL_MINUTES: int = int(os.getenv("BRIDGE_CRON_INTERVAL_MINUTES", "45"))

    # --- MinIO Object Storage ---
    MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY", "")
    MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "")
    MINIO_SECURE: bool = _bool_env("MINIO_SECURE", False)
    # Set to false to skip MinIO credential validation in validate().
    # Useful for test environments or deployments that do not use MinIO.
    NCE_MINIO_REQUIRED: bool = _bool_env("NCE_MINIO_REQUIRED", True)

    # --- Phase 0.1 / 0.2: Auth + Signing ---
    # NCE_API_KEY        — HMAC-SHA256 key for HTTP admin API authentication.
    #                         Required in production.  Server logs a warning if absent.
    # NCE_ADMIN_API_KEY  — Bearer token checked by require_scope("admin") in A2A/MCP.
    #                         Required in production.
    # NCE_ADMIN_USERNAME / NCE_ADMIN_PASSWORD — HTTP Basic credentials
    #                         required for non-API admin UI routes.
    # NCE_MASTER_KEY     — AES-256 master key for encrypting signing keys at rest.
    #                         Importing this module or calling validate() raises RuntimeError
    #                         if missing or under 32 UTF-8 bytes [D 0.2].
    # NCE_ADMIN_OVERRIDE — Dev-only bypass of admin scope checks. Must never be
    #                         true in production.
    NCE_API_KEY: str = os.getenv("NCE_API_KEY", "")
    # Shared secret for MCP stdio tenant tools (namespace-scoped). Required in production.
    NCE_MCP_API_KEY: str = os.getenv("NCE_MCP_API_KEY", "")
    # When set, tenant MCP tools are bound to this namespace UUID (required in prod with MCP key).
    NCE_MCP_NAMESPACE_ID: str = os.getenv("NCE_MCP_NAMESPACE_ID", "")
    NCE_ADMIN_API_KEY: str = os.getenv("NCE_ADMIN_API_KEY", "")
    NCE_ADMIN_OVERRIDE: bool = _bool_env("NCE_ADMIN_OVERRIDE", False)
    # Startup WORM / RLS probe bypass (dev/support only — rejected when IS_PROD).
    NCE_BYPASS_WORM: bool = _bool_env("NCE_BYPASS_WORM", False)
    NCE_BYPASS_RLS: bool = _bool_env("NCE_BYPASS_RLS", False)
    # Admin UI may persist connector/datastore edits to a local .env file (dev only).
    NCE_ALLOW_ADMIN_DOTENV_PERSIST: bool = _bool_env(
        "NCE_ALLOW_ADMIN_DOTENV_PERSIST",
        ENVIRONMENT not in {"prod", "production"},
    )
    NCE_ADMIN_USERNAME: str = os.getenv("NCE_ADMIN_USERNAME", "")
    NCE_ADMIN_PASSWORD: str = os.getenv("NCE_ADMIN_PASSWORD", "")
    NCE_MASTER_KEY: str = os.getenv("NCE_MASTER_KEY", "")
    # When true, HTTP admin ``HMACAuthMiddleware`` uses ``NonceStore(cfg.REDIS_URL)``
    # for replay protection across multiple admin replicas (see nce.auth).
    NCE_DISTRIBUTED_REPLAY: bool = _bool_env("NCE_DISTRIBUTED_REPLAY", False)

    # --- PBKDF2 iteration counts (signing + admin password hashing) ---
    # NCE_PBKDF2_ITERATIONS    — v2 blob compat path (minimum 100K, NIST minimum).
    #                               Used by signing.py to decrypt legacy v2 blobs.
    # NCE_PBKDF2_ITERATIONS_V4 — v4 new-write path (minimum 600K, OWASP 2026).
    #                               auth.py clamps admin password hashing to max(600K, this).
    NCE_PBKDF2_ITERATIONS: int = _int_env("NCE_PBKDF2_ITERATIONS", 100_000, minimum=100_000)
    NCE_PBKDF2_ITERATIONS_V4: int = _int_env(
        "NCE_PBKDF2_ITERATIONS_V4", 600_000, minimum=600_000
    )

    # --- Phase 0.2: JWT Bridge ---
    # NCE_JWT_SECRET     — HS256 shared secret for JWT validation (dev / testing).
    #                         Either this or NCE_JWT_PUBLIC_KEY must be set when
    #                         JWTAuthMiddleware is active.
    # NCE_JWT_PUBLIC_KEY — RS256/ES256 PEM-encoded public key for production JWT
    #                         validation.  May be a raw PEM string or a file URI
    #                         (file:///path/to/pub.pem). Takes precedence over the
    #                         secret when both are set.
    # NCE_JWT_ALGORITHM  — One of HS256 | RS256 | ES256 (default: HS256).
    # NCE_JWT_ISSUER     — Expected ``iss`` claim.  Omit to skip issuer check.
    # NCE_JWT_AUDIENCE   — Expected ``aud`` claim.  Omit to skip audience check.
    # NCE_JWT_PREFIX     — Route prefix protected by JWTAuthMiddleware.
    #                         Default: "/api/v1/" (agent-facing endpoints).
    NCE_JWT_SECRET: str = os.getenv("NCE_JWT_SECRET", "")
    NCE_JWT_PUBLIC_KEY: str = os.getenv("NCE_JWT_PUBLIC_KEY", "")
    NCE_JWT_ALGORITHM: str = (os.getenv("NCE_JWT_ALGORITHM") or "HS256").upper().strip()
    NCE_JWT_ISSUER: str = os.getenv("NCE_JWT_ISSUER", "")
    NCE_JWT_AUDIENCE: str = os.getenv("NCE_JWT_AUDIENCE", "")
    NCE_JWT_PREFIX: str = os.getenv("NCE_JWT_PREFIX", "/api/v1/")
    NCE_JWT_KEY_DIR: str = os.getenv("NCE_JWT_KEY_DIR", str(Path.cwd()))
    NCE_JWT_LEEWAY_SECONDS: int = int(os.getenv("NCE_JWT_LEEWAY_SECONDS", "30"))

    # --- Phase 3.1: Per-service JWT audience overrides ---
    # Each service (A2A, admin, etc.) can require its own ``aud`` claim value
    # to prevent token replay across system boundaries.  When set, tokens
    # intended for one service are rejected by another.
    #
    # If unset, the default is ``f"nce_{service}"`` per server.
    NCE_A2A_JWT_AUDIENCE: str = os.getenv(
        "NCE_A2A_JWT_AUDIENCE",
        "nce_a2a",
    )

    # --- Phase 3.1: A2A mTLS — client certificate enforcement ---
    # When enabled, the A2A server requires a valid client TLS certificate
    # from connecting agents.  Certificates are validated by SAN or SHA-256
    # fingerprint against an explicit allowlist.
    #
    # NCE_A2A_MTLS_ENABLED           — Master switch (default: false)
    # NCE_A2A_MTLS_ALLOWED_SANS      — Comma-separated list of allowed
    #                                     Subject Alternative Name values
    #                                     (case-insensitive DNS / URI match).
    # NCE_A2A_MTLS_ALLOWED_FINGERPRINTS — Comma-separated list of allowed
    #                                     SHA-256 certificate fingerprints
    #                                     (colon-separated hex, case-insensitive).
    # NCE_A2A_MTLS_STRICT            — When true, reject any connection that
    #                                     does not present a valid client cert
    #                                     (default: true).
    # NCE_A2A_MTLS_TRUSTED_PROXY_HOP — Number of reverse-proxy hops to trust
    #                                     for X-Forwarded-Client-Cert header.
    #                                     0 = only direct TLS (uvicorn SSL).
    #                                     1 = one reverse proxy (Caddy / nginx).
    NCE_A2A_MTLS_ENABLED: bool = _bool_env("NCE_A2A_MTLS_ENABLED", False)
    NCE_A2A_MTLS_ALLOWED_SANS: list[str] = [
        s.strip().lower()
        for s in os.getenv("NCE_A2A_MTLS_ALLOWED_SANS", "").split(",")
        if s.strip()
    ]
    NCE_A2A_MTLS_ALLOWED_FINGERPRINTS: list[str] = [
        s.strip().lower()
        for s in os.getenv("NCE_A2A_MTLS_ALLOWED_FINGERPRINTS", "").split(",")
        if s.strip()
    ]
    NCE_A2A_MTLS_STRICT: bool = _bool_env("NCE_A2A_MTLS_STRICT", True)
    NCE_A2A_MTLS_TRUSTED_PROXY_HOP: int = int(
        os.getenv("NCE_A2A_MTLS_TRUSTED_PROXY_HOP", "1")
    )

    # --- Admin server mTLS (B6) ---
    # Mirror of the A2A mTLS block but scoped to the admin surface.
    # All vars default to disabled/empty so existing deployments are unaffected.
    NCE_ADMIN_MTLS_ENABLED: bool = _bool_env("NCE_ADMIN_MTLS_ENABLED", False)
    NCE_ADMIN_MTLS_STRICT: bool = _bool_env("NCE_ADMIN_MTLS_STRICT", True)
    NCE_ADMIN_MTLS_TRUSTED_PROXY_HOP: int = int(
        os.getenv("NCE_ADMIN_MTLS_TRUSTED_PROXY_HOP", "1")
    )
    NCE_ADMIN_MTLS_ALLOWED_SANS: list[str] = [
        s.strip().lower()
        for s in os.getenv("NCE_ADMIN_MTLS_ALLOWED_SANS", "").split(",")
        if s.strip()
    ]
    NCE_ADMIN_MTLS_ALLOWED_FINGERPRINTS: list[str] = [
        s.strip().lower()
        for s in os.getenv("NCE_ADMIN_MTLS_ALLOWED_FINGERPRINTS", "").split(",")
        if s.strip()
    ]

    # --- General mTLS (CC) ---
    NCE_MTLS_STRICT: bool = _bool_env("NCE_MTLS_STRICT", True)
    NCE_MTLS_CERT_PATH: str = os.getenv("NCE_MTLS_CERT_PATH", "").strip()
    NCE_MTLS_KEY_PATH: str = os.getenv("NCE_MTLS_KEY_PATH", "").strip()
    NCE_MTLS_CA_PATH: str = os.getenv("NCE_MTLS_CA_PATH", "").strip()

    # Per-IP HTTP rate limits on admin_server (/api/* and sensitive POST paths).
    NCE_ADMIN_HTTP_RATE_LIMIT: int = _int_env("NCE_ADMIN_HTTP_RATE_LIMIT", 120, minimum=1)
    NCE_ADMIN_HTTP_RATE_PERIOD: int = _int_env("NCE_ADMIN_HTTP_RATE_PERIOD", 60, minimum=1)
    NCE_ADMIN_HTTP_SENSITIVE_RATE_LIMIT: int = _int_env(
        "NCE_ADMIN_HTTP_SENSITIVE_RATE_LIMIT", 30, minimum=1
    )
    NCE_ADMIN_HTTP_SENSITIVE_RATE_PERIOD: int = _int_env(
        "NCE_ADMIN_HTTP_SENSITIVE_RATE_PERIOD", 60, minimum=1
    )

    # --- Phase 0.1: HMAC replay-protection clock skew ---
    # Maximum allowed drift between client timestamp and server time (seconds).
    # Requests with timestamps outside this window are rejected as replays.
    NCE_CLOCK_SKEW_TOLERANCE_S: int = int(os.getenv("NCE_CLOCK_SKEW_TOLERANCE_S", "300"))

    # --- Phase 3.2: Per-namespace / per-agent quotas ---
    # When false, no quota queries run on the tool hot path.
    NCE_QUOTAS_ENABLED: bool = _bool_env("NCE_QUOTAS_ENABLED", True)
    # Rough chars-per-token for pre-flight estimates (embedding / LLM analog).
    NCE_QUOTA_TOKEN_ESTIMATE_DIVISOR: int = int(
        os.getenv("NCE_QUOTA_TOKEN_ESTIMATE_DIVISOR", "4")
    )
    # Hot-path quota increments via Redis (avoids row-level UPDATE serialization).
    NCE_QUOTA_REDIS_COUNTERS: bool = _bool_env("NCE_QUOTA_REDIS_COUNTERS", True)
    NCE_QUOTA_REDIS_FLUSH_INTERVAL_S: float = float(
        os.getenv("NCE_QUOTA_REDIS_FLUSH_INTERVAL_S", "60")
    )

    # --- Consolidation ---
    CONSOLIDATION_DECAY_SOURCES: bool = _bool_env("CONSOLIDATION_DECAY_SOURCES", False)
    CONSOLIDATION_CRON_INTERVAL_MINUTES: int = int(
        os.getenv("CONSOLIDATION_CRON_INTERVAL_MINUTES", "360")
    )
    CONSOLIDATION_HALF_LIFE_DAYS: float = float(os.getenv("CONSOLIDATION_HALF_LIFE_DAYS", "30.0"))

    # --- Cron startup jitter ---
    # Maximum random startup delay (seconds) applied before the first cron
    # execution cycle.  Prevents thundering-herd database CPU spikes when
    # multiple NCE instances boot simultaneously (e.g. rolling deployment,
    # docker-compose scale).  The jitter is a one-time shift — subsequent
    # interval fires inherit the offset evenly.
    # Set to 0 to disable.
    CRON_STARTUP_JITTER_MAX_SECONDS: float = float(
        os.getenv("CRON_STARTUP_JITTER_MAX_SECONDS", "60.0")
    )
    OUTBOX_RELAY_INTERVAL_SECONDS: int = max(
        1, int(os.getenv("OUTBOX_RELAY_INTERVAL_SECONDS", "5"))
    )

    # --- Re-embedding worker (Phase 2.1) ---
    REEMBED_BATCH_SIZE: int = max(1, int(os.getenv("REEMBED_BATCH_SIZE", "32")))
    REEMBED_BATCHES_PER_MINUTE: int = max(1, int(os.getenv("REEMBED_BATCHES_PER_MINUTE", "20")))
    REEMBED_MAX_ROWS_PER_RUN: int = max(0, int(os.getenv("REEMBED_MAX_ROWS_PER_RUN", "0")))
    REEMBED_INCLUDE_KG_NODES: bool = _bool_env("REEMBED_INCLUDE_KG_NODES", False)
    REEMBED_MAX_TEXT_CHARS: int = max(256, int(os.getenv("REEMBED_MAX_TEXT_CHARS", "4096")))
    REEMBED_CRON_INTERVAL_MINUTES: int = max(
        1, int(os.getenv("REEMBED_CRON_INTERVAL_MINUTES", "60"))
    )

    # --- Orchestrator artifact staging ---
    NCE_ARTIFACT_STAGING_DIR: str = os.getenv("NCE_ARTIFACT_STAGING_DIR", "")

    # --- Phase 1.2: LLM Provider API keys (BYO — no shared platform key [D3]) ---
    # All keys default to empty string; factory logs a warning if the needed
    # key is absent.  Use ref:env/<VAR> in namespace metadata to override
    # per-namespace without touching global config.
    #
    # NCE_ANTHROPIC_API_KEY     — Anthropic Claude (claude-opus-4-6, etc.)
    # NCE_OPENAI_API_KEY        — OpenAI (gpt-5, gpt-4.5-turbo)
    # NCE_AZURE_OPENAI_API_KEY  — Azure OpenAI api-key header
    # NCE_AZURE_OPENAI_ENDPOINT — Azure resource endpoint (required for azure_openai provider)
    # NCE_AZURE_OPENAI_DEPLOYMENT — Default deployment name
    # NCE_GEMINI_API_KEY        — Google AI Studio / Gemini API key
    # NCE_DEEPSEEK_API_KEY      — DeepSeek (cost-sensitive deployments)
    # NCE_MOONSHOT_API_KEY      — Moonshot / Kimi (large-context clusters)
    # NCE_OPENAI_COMPAT_BASE_URL — Base URL for openai_compatible provider
    # NCE_OPENAI_COMPAT_API_KEY  — API key for openai_compatible provider
    # NCE_OPENAI_COMPAT_MODEL    — Default model for openai_compatible provider
    NCE_ANTHROPIC_API_KEY: str = os.getenv("NCE_ANTHROPIC_API_KEY", "")
    NCE_OPENAI_API_KEY: str = os.getenv("NCE_OPENAI_API_KEY", "")
    NCE_AZURE_OPENAI_API_KEY: str = os.getenv("NCE_AZURE_OPENAI_API_KEY", "")
    NCE_AZURE_OPENAI_ENDPOINT: str = os.getenv("NCE_AZURE_OPENAI_ENDPOINT", "")
    NCE_AZURE_OPENAI_DEPLOYMENT: str = os.getenv("NCE_AZURE_OPENAI_DEPLOYMENT", "")
    NCE_GEMINI_API_KEY: str = os.getenv("NCE_GEMINI_API_KEY", "")
    NCE_DEEPSEEK_API_KEY: str = os.getenv("NCE_DEEPSEEK_API_KEY", "")
    NCE_MOONSHOT_API_KEY: str = os.getenv("NCE_MOONSHOT_API_KEY", "")
    NCE_OPENAI_COMPAT_BASE_URL: str = os.getenv("NCE_OPENAI_COMPAT_BASE_URL", "")
    NCE_OPENAI_COMPAT_API_KEY: str = os.getenv("NCE_OPENAI_COMPAT_API_KEY", "")
    NCE_OPENAI_COMPAT_MODEL: str = os.getenv("NCE_OPENAI_COMPAT_MODEL", "")

    # --- Phase 2: Observability (Prometheus + OTel) ---
    NCE_PROMETHEUS_PORT: int = int(os.getenv("NCE_PROMETHEUS_PORT", "8000"))
    NCE_OTEL_EXPORTER_OTLP_ENDPOINT: str = os.getenv(
        "NCE_OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"
    )
    NCE_OTEL_SERVICE_NAME: str = os.getenv("NCE_OTEL_SERVICE_NAME", "nce-python")
    NCE_OBSERVABILITY_ENABLED: bool = _bool_env("NCE_OBSERVABILITY_ENABLED", True)

    # --- Phase 3: Background Task Poison Pill / Dead Letter Queue ---
    # Maximum times a background task (RQ worker) is retried before the payload
    # is routed to the dead_letter_queue table and removed from the active
    # processing loop.  Set to 0 to disable DLQ routing (all failures retry
    # indefinitely — not recommended for production).
    TASK_MAX_RETRIES: int = int(os.getenv("TASK_MAX_RETRIES", "5"))

    # --- Migration MCP tools disable switch ---
    # When true, start_migration / commit_migration / abort_migration are excluded
    # from the MCP tool list and dispatch table.  Defaults to true in production;
    # set NCE_DISABLE_MIGRATION_MCP=false explicitly to enable migration tools.
    NCE_DISABLE_MIGRATION_MCP: bool = _bool_env(
        "NCE_DISABLE_MIGRATION_MCP",
        IS_PROD,
    )
    # Redis TTL (seconds) for attempt-count keys.  After this window, a task
    # that has been failing for longer than TTL will restart its attempt
    # counter from 1.  Default 86 400 s = 24 h.
    TASK_DLQ_REDIS_TTL: int = int(os.getenv("TASK_DLQ_REDIS_TTL", "86400"))

    # --- Spreading Activation Telemetry Defaults (BATCH-P3-003) ---
    NCE_TELEMETRY_SPIKE_THRESHOLD: float = _float_env("NCE_TELEMETRY_SPIKE_THRESHOLD", 8.0, minimum=0.0)
    NCE_TELEMETRY_SPIKE_THETA: float = _float_env("NCE_TELEMETRY_SPIKE_THETA", 0.25, minimum=0.0)
    NCE_TELEMETRY_SPIKE_CHARGE: float = _float_env("NCE_TELEMETRY_SPIKE_CHARGE", 2.0, minimum=0.0)

    # --- Active Learning Gamification (BATCH-P3-005) ---
    NCE_ACTIVE_LEARNING_CONFIRM_XP: int = _int_env("NCE_ACTIVE_LEARNING_CONFIRM_XP", 10, minimum=0)
    NCE_ACTIVE_LEARNING_REJECT_XP: int = _int_env("NCE_ACTIVE_LEARNING_REJECT_XP", 5, minimum=0)

    # --- NetBox Discovery Defaults (BATCH-P3-NB-005) ---
    NCE_NETBOX_DEFAULT_INTERFACE_TYPE: str = os.getenv("NCE_NETBOX_DEFAULT_INTERFACE_TYPE", "1000base-t").strip()

    @classmethod
    def validate_minio_credentials(cls) -> None:
        """Validate that MinIO credentials are set via environment.

        No hardcoded defaults are permitted — FIX-013 requires explicit env vars.
        """
        if not cls.MINIO_ACCESS_KEY:
            raise ValueError(
                "MINIO_ACCESS_KEY must be set via the MINIO_ACCESS_KEY environment variable. "
                "No default is permitted in production."
            )
        if not cls.MINIO_SECRET_KEY:
            raise ValueError(
                "MINIO_SECRET_KEY must be set via the MINIO_SECRET_KEY environment variable. "
                "No default is permitted in production."
            )

    @classmethod
    def validate_datastore_config(cls) -> None:
        """In production, reject missing or default-value datastore connection strings."""
        if not cls.IS_PROD:
            return

        missing = [k for k in ("MONGO_URI", "PG_DSN", "REDIS_URL") if not getattr(cls, k)]
        if missing:
            raise RuntimeError(
                "CRITICAL CONFIGURATION FAILURE: Missing required production datastore config: "
                + ", ".join(missing)
            )

        _insecure_defaults = {
            "PG_DSN": "postgresql://mcp_user:mcp_password@localhost:5432/memory_meta",
            "MONGO_URI": "mongodb://localhost:27017",
            "REDIS_URL": "redis://localhost:6379/0",
        }
        for key, default in _insecure_defaults.items():
            if getattr(cls, key) == default:
                raise RuntimeError(
                    f"CRITICAL CONFIGURATION FAILURE: {key} uses development default in production."
                )

    @classmethod
    def validate_jwt_config(cls) -> None:
        """Validate JWT configuration. Fail in production if no key is set."""
        if not cls.NCE_JWT_SECRET and not cls.NCE_JWT_PUBLIC_KEY:
            if cls.IS_PROD:
                raise RuntimeError(
                    "CRITICAL CONFIGURATION FAILURE: JWT validation requires "
                    "NCE_JWT_PUBLIC_KEY or NCE_JWT_SECRET in production."
                )
            log.warning(
                "SECURITY WARNING: Neither NCE_JWT_SECRET nor NCE_JWT_PUBLIC_KEY is set. "
                "A2A sharing will be disabled."
            )

        if cls.IS_PROD and cls.NCE_JWT_ALGORITHM == "HS256":
            log.warning(
                "SECURITY WARNING: HS256 JWT is configured in production. "
                "Prefer RS256/ES256 with NCE_JWT_PUBLIC_KEY."
            )

    @classmethod
    def validate(cls) -> None:
        """
        Validates environment configuration.
        Strictly halts (raises RuntimeError) if P0 security requirements are missing.
        """
        # P0: Master Key (Required for signing/encryption)
        _fail_unless_nce_master_key_ok(cls.NCE_MASTER_KEY)

        # P0: Datastore connections — reject dev defaults in production
        cls.validate_datastore_config()

        # P0: MinIO Credentials (FIX-013) — skipped when NCE_MINIO_REQUIRED=false
        if cls.NCE_MINIO_REQUIRED:
            cls.validate_minio_credentials()

        # P0: Database connections present in all environments
        missing_conns = [k for k in ("MONGO_URI", "PG_DSN", "REDIS_URL") if not getattr(cls, k)]
        if missing_conns:
            raise RuntimeError(
                f"CRITICAL CONFIGURATION FAILURE: Missing required connection strings: {', '.join(missing_conns)}"
            )

        # P1: HMAC API key
        if not cls.NCE_API_KEY:
            if cls.IS_PROD:
                raise RuntimeError(
                    "CRITICAL CONFIGURATION FAILURE: NCE_API_KEY is required in production."
                )
            log.warning(
                "SECURITY WARNING: NCE_API_KEY is not set. "
                "Admin API routes will be inaccessible."
            )

        # P1: JWT
        cls.validate_jwt_config()

        # P1: MCP stdio tenant plane
        cls.validate_mcp_api_key()
        cls.validate_mcp_namespace_binding()

        # P1: Admin plane (HTTP Basic UI + MCP admin scope)
        cls.validate_admin_credentials()

        # P1: Live migration MCP tools are high-risk in production
        cls.validate_migration_mcp_surface()

        # P1: Webhook dedup must fail closed when Redis is unavailable
        cls.validate_webhook_dedup_policy()

    @classmethod
    def validate_webhook_dedup_policy(cls) -> None:
        """Reject fail-open webhook dedup in production (duplicate bridge deliveries)."""
        if not cls.IS_PROD or not cls.WEBHOOK_DEDUP_FAIL_OPEN:
            return
        raise RuntimeError(
            "CRITICAL CONFIGURATION FAILURE: WEBHOOK_DEDUP_FAIL_OPEN must be false in "
            "production so webhook deduplication fails closed when Redis is unavailable."
        )

    @classmethod
    def validate_migration_mcp_surface(cls) -> None:
        """Disable migration MCP tools in production unless explicitly opted in."""
        if not cls.IS_PROD or cls.NCE_DISABLE_MIGRATION_MCP:
            return
        if _bool_env("NCE_ALLOW_MIGRATION_MCP_IN_PROD", False):
            log.warning(
                "Migration MCP tools are enabled in production "
                "(NCE_ALLOW_MIGRATION_MCP_IN_PROD=true). "
                "Disable after the migration window."
            )
            return
        raise RuntimeError(
            "CRITICAL CONFIGURATION FAILURE: Migration MCP tools must not run in "
            "production unless NCE_ALLOW_MIGRATION_MCP_IN_PROD=true is set for a "
            "controlled window. Otherwise set NCE_DISABLE_MIGRATION_MCP=true."
        )

    @classmethod
    def validate_mcp_api_key(cls) -> None:
        """Require MCP tenant API key in production (stdio tool authentication)."""
        if (cls.NCE_MCP_API_KEY or "").strip():
            return
        if cls.IS_PROD:
            raise RuntimeError(
                "CRITICAL CONFIGURATION FAILURE: NCE_MCP_API_KEY is required "
                "in production for MCP stdio tenant tools."
            )
        log.warning(
            "SECURITY WARNING: NCE_MCP_API_KEY is not set. "
            "MCP tenant tools are unauthenticated in this environment."
        )

    @classmethod
    def validate_mcp_namespace_binding(cls) -> None:
        """Require a bound tenant namespace when MCP auth is enabled in production."""
        from uuid import UUID

        bound = (cls.NCE_MCP_NAMESPACE_ID or "").strip()
        if bound:
            try:
                UUID(bound)
            except ValueError as exc:
                raise RuntimeError(
                    "CRITICAL CONFIGURATION FAILURE: NCE_MCP_NAMESPACE_ID must be "
                    f"a valid UUID, got {bound!r}."
                ) from exc
            return

        if cls.IS_PROD and (cls.NCE_MCP_API_KEY or "").strip():
            raise RuntimeError(
                "CRITICAL CONFIGURATION FAILURE: NCE_MCP_NAMESPACE_ID is required "
                "in production when NCE_MCP_API_KEY is set so MCP stdio tools "
                "cannot target arbitrary tenant UUIDs."
            )
        if (cls.NCE_MCP_API_KEY or "").strip():
            log.warning(
                "SECURITY WARNING: NCE_MCP_NAMESPACE_ID is not set. "
                "MCP tenant tools accept caller-supplied namespace_id."
            )

    @classmethod
    def validate_admin_credentials(cls) -> None:
        """Require admin API key and HTTP Basic credentials in production."""
        missing: list[str] = []
        if not (cls.NCE_ADMIN_API_KEY or "").strip():
            missing.append("NCE_ADMIN_API_KEY")
        if not (cls.NCE_ADMIN_USERNAME or "").strip():
            missing.append("NCE_ADMIN_USERNAME")
        if not (cls.NCE_ADMIN_PASSWORD or "").strip():
            missing.append("NCE_ADMIN_PASSWORD")

        if cls.IS_PROD:
            if missing:
                raise RuntimeError(
                    "CRITICAL CONFIGURATION FAILURE: Missing required admin credentials: "
                    + ", ".join(missing)
                )
            stored = cls.NCE_ADMIN_PASSWORD
            if not stored.startswith("$pbkdf2$"):
                raise RuntimeError(
                    "CRITICAL CONFIGURATION FAILURE: NCE_ADMIN_PASSWORD must be a "
                    "$pbkdf2$ hash in production (plaintext passwords are forbidden)."
                )
            return

        if missing:
            log.warning(
                "SECURITY WARNING: Incomplete admin credentials (%s). "
                "Admin UI and MCP admin tools may be inaccessible.",
                ", ".join(missing),
            )


# Module-level singleton — import `cfg` everywhere inside the package.
cfg = _Config()

if cfg.IS_PROD and cfg.NCE_BYPASS_WORM:
    raise RuntimeError("NCE_BYPASS_WORM is forbidden in production")
if cfg.IS_PROD and cfg.NCE_BYPASS_RLS:
    raise RuntimeError("NCE_BYPASS_RLS is forbidden in production")
if cfg.IS_PROD and cfg.NCE_ALLOW_ADMIN_DOTENV_PERSIST:
    raise RuntimeError("NCE_ALLOW_ADMIN_DOTENV_PERSIST is forbidden in production")
if cfg.IS_PROD and cfg.NCE_ADMIN_OVERRIDE:
    raise RuntimeError(
        "NCE_ADMIN_OVERRIDE is forbidden in production. "
        "Remove this environment variable from the production configuration."
    )
if cfg.IS_PROD and os.environ.get("NCE_LOAD_DOTENV", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}:
    raise RuntimeError(
        "NCE_LOAD_DOTENV must be false in production. "
        "Inject secrets via the orchestrator; do not load a .env file at runtime."
    )

_fail_unless_nce_master_key_ok(cfg.NCE_MASTER_KEY)


def assert_admin_override_not_in_production() -> None:
    """Raise if the dev-only admin override bypass is enabled in production."""
    if cfg.NCE_ADMIN_OVERRIDE and cfg.IS_PROD:
        raise RuntimeError(
            "NCE_ADMIN_OVERRIDE must not be set when NCE_ENV is production. "
            "Remove this environment variable from the production configuration."
        )


def __getattr__(name: str) -> Any:
    if name == "OrchestratorConfig":
        import warnings
        warnings.warn(
            "OrchestratorConfig is deprecated; use cfg (the Config instance) instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return _Config
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
