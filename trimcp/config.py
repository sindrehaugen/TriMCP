"""
TriMCP — centralised environment configuration.

All env-var reads for the entire package live here. No other module should
call os.getenv() directly. This makes the full configuration surface visible
in one place, easy to validate, and easy to override in tests.

Import pattern inside the package:
    from trimcp.config import cfg
"""

import logging
import os
import re
from urllib.parse import urlparse, urlunparse

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("tri-stack-config")

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


def _fail_unless_trimcp_master_key_ok(raw: str) -> None:
    """Raise RuntimeError if the master key is missing or shorter than 32 UTF-8 bytes."""
    v = (raw or "").strip()
    if not v or len(v.encode("utf-8")) < _MASTER_KEY_MIN_UTF8_BYTES:
        raise RuntimeError(
            "CRITICAL SECURITY FAILURE: TRIMCP_MASTER_KEY is missing or too short. "
            f"A minimum of {_MASTER_KEY_MIN_UTF8_BYTES} UTF-8 bytes of random key material "
            "is required to import or start the server."
        )


class _EmbeddingConfig:
    """
    Embedding / pgvector dimension. Must stay aligned with ``memories.embedding`` and
    ``kg_nodes.embedding`` in ``schema.sql`` — changing this requires a DB migration.
    """

    VECTOR_DIM: int = int(os.getenv("EMBEDDING_VECTOR_DIM", "768"))


class _Config:
    EMBEDDING = _EmbeddingConfig

    # --- Database connections ---
    # ``DATABASE_URL`` is accepted as a 12-factor alias for ``PG_DSN`` (same precedence: explicit PG_DSN wins).
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    PG_DSN: str = (
        os.getenv("PG_DSN")
        or os.getenv("DATABASE_URL")
        or "postgresql://mcp_user:mcp_password@localhost:5432/memory_meta"
    )
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # --- Redis ---
    REDIS_TTL: int = int(os.getenv("REDIS_TTL", "3600"))
    REDIS_MAX_CONNECTIONS: int = int(os.getenv("REDIS_MAX_CONNECTIONS", "20"))

    # --- PostgreSQL connection pool ---
    PG_MIN_POOL: int = int(os.getenv("PG_MIN_POOL", "1"))
    PG_MAX_POOL: int = int(os.getenv("PG_MAX_POOL", "10"))

    # --- Garbage collector ---
    GC_INTERVAL_SECONDS: int = int(os.getenv("GC_INTERVAL_SECONDS", "3600"))
    GC_ORPHAN_AGE_SECONDS: int = int(os.getenv("GC_ORPHAN_AGE_SECONDS", "300"))

    # --- Temporal queries ---
    # Maximum lookback window for ``as_of`` temporal queries.  Prevents
    # unbounded historical searches that trigger full-table scans on
    # ``event_log``.  Set to 0 to disable the boundary (not recommended).
    TRIMCP_MAX_TEMPORAL_LOOKBACK_DAYS: int = int(
        os.getenv("TRIMCP_MAX_TEMPORAL_LOOKBACK_DAYS", "90")
    )

    # --- Embeddings ---
    EMBED_BATCH_CHUNK: int = int(os.getenv("EMBED_BATCH_CHUNK", "64"))
    # Enterprise §8 — hardware backend / OpenVINO NPU (see trimcp.embeddings, openvino_npu_export).
    TRIMCP_BACKEND: str = (os.getenv("TRIMCP_BACKEND") or "").strip().lower()
    TRIMCP_OPENVINO_MODEL_DIR: str = (os.getenv("TRIMCP_OPENVINO_MODEL_DIR") or "").strip()
    TRIMCP_OPENVINO_SEQ_LEN: int = int(os.getenv("TRIMCP_OPENVINO_SEQ_LEN", "512"))

    # --- Contradictions / NLI ---
    NLI_MODEL_ID: str = os.getenv("NLI_MODEL_ID", "cross-encoder/nli-deberta-v3-small")

    # --- D2 / D7 — Local cognitive bundle (OpenAI-compatible HTTP on port 11435) ---
    # When TRIMCP_COGNITIVE_BASE_URL is set (e.g. http://cognitive:11435), embeddings
    # route to POST {base}/v1/embeddings unless TRIMCP_BACKEND selects an in-process backend.
    TRIMCP_COGNITIVE_BASE_URL: str = (
        (os.getenv("TRIMCP_COGNITIVE_BASE_URL") or "").strip().rstrip("/")
    )
    TRIMCP_COGNITIVE_EMBEDDING_MODEL: str = (
        os.getenv("TRIMCP_COGNITIVE_EMBEDDING_MODEL") or ""
    ).strip()
    TRIMCP_COGNITIVE_API_KEY: str = (os.getenv("TRIMCP_COGNITIVE_API_KEY") or "").strip()
    # Declarative default LLM provider label for operators / future LLMProvider wiring [D2].
    TRIMCP_LLM_PROVIDER: str = (os.getenv("TRIMCP_LLM_PROVIDER") or "local-cognitive-model").strip()

    # --- Document bridges (Phase 2 / §10.3) — OAuth tokens from env or future bridge_tokens PG ---
    GRAPH_BRIDGE_TOKEN: str = os.getenv("GRAPH_BRIDGE_TOKEN", "")
    GDRIVE_BRIDGE_TOKEN: str = os.getenv("GDRIVE_BRIDGE_TOKEN", "")
    DROPBOX_BRIDGE_TOKEN: str = os.getenv("DROPBOX_BRIDGE_TOKEN", "")

    # --- Bridge OAuth / webhooks (§10.6–10.7) ---
    BRIDGE_WEBHOOK_BASE_URL: str = os.getenv("BRIDGE_WEBHOOK_BASE_URL", "").rstrip("/")
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
    MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY", "mcp_admin")
    MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "super_secure_minio_password")
    MINIO_SECURE: bool = os.getenv("MINIO_SECURE", "false").lower() == "true"

    # --- Phase 0.1 / 0.2: Auth + Signing ---
    # TRIMCP_API_KEY    — HMAC-SHA256 key for HTTP admin API authentication.
    #                     Required in production.  Server logs a warning if absent.
    # TRIMCP_ADMIN_USERNAME / TRIMCP_ADMIN_PASSWORD — HTTP Basic credentials
    #                     required for non-API admin UI routes.
    # TRIMCP_MASTER_KEY — AES-256 master key for encrypting signing keys at rest.
    #                     Importing this module or calling validate() raises RuntimeError
    #                     if missing or under 32 UTF-8 bytes [D 0.2].
    TRIMCP_API_KEY: str = os.getenv("TRIMCP_API_KEY", "")
    TRIMCP_ADMIN_USERNAME: str = os.getenv("TRIMCP_ADMIN_USERNAME", "")
    TRIMCP_ADMIN_PASSWORD: str = os.getenv("TRIMCP_ADMIN_PASSWORD", "")
    TRIMCP_MASTER_KEY: str = os.getenv("TRIMCP_MASTER_KEY", "")
    # When true, HTTP admin ``HMACAuthMiddleware`` uses ``NonceStore(cfg.REDIS_URL)``
    # for replay protection across multiple admin replicas (see trimcp.auth).
    TRIMCP_DISTRIBUTED_REPLAY: bool = os.getenv(
        "TRIMCP_DISTRIBUTED_REPLAY", ""
    ).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

    # --- Phase 0.2: JWT Bridge ---
    # TRIMCP_JWT_SECRET     — HS256 shared secret for JWT validation (dev / testing).
    #                         Either this or TRIMCP_JWT_PUBLIC_KEY must be set when
    #                         JWTAuthMiddleware is active.
    # TRIMCP_JWT_PUBLIC_KEY — RS256/ES256 PEM-encoded public key for production JWT
    #                         validation.  May be a raw PEM string or a file URI
    #                         (file:///path/to/pub.pem). Takes precedence over the
    #                         secret when both are set.
    # TRIMCP_JWT_ALGORITHM  — One of HS256 | RS256 | ES256 (default: HS256).
    # TRIMCP_JWT_ISSUER     — Expected ``iss`` claim.  Omit to skip issuer check.
    # TRIMCP_JWT_AUDIENCE   — Expected ``aud`` claim.  Omit to skip audience check.
    # TRIMCP_JWT_PREFIX     — Route prefix protected by JWTAuthMiddleware.
    #                         Default: "/api/v1/" (agent-facing endpoints).
    TRIMCP_JWT_SECRET: str = os.getenv("TRIMCP_JWT_SECRET", "")
    TRIMCP_JWT_PUBLIC_KEY: str = os.getenv("TRIMCP_JWT_PUBLIC_KEY", "")
    TRIMCP_JWT_ALGORITHM: str = (os.getenv("TRIMCP_JWT_ALGORITHM") or "HS256").upper().strip()
    TRIMCP_JWT_ISSUER: str = os.getenv("TRIMCP_JWT_ISSUER", "")
    TRIMCP_JWT_AUDIENCE: str = os.getenv("TRIMCP_JWT_AUDIENCE", "")
    TRIMCP_JWT_PREFIX: str = os.getenv("TRIMCP_JWT_PREFIX", "/api/v1/")

    # --- Phase 3.1: Per-service JWT audience overrides ---
    # Each service (A2A, admin, etc.) can require its own ``aud`` claim value
    # to prevent token replay across system boundaries.  When set, tokens
    # intended for one service are rejected by another.
    #
    # If unset, the default is ``f"trimcp_{service}"`` per server.
    TRIMCP_A2A_JWT_AUDIENCE: str = os.getenv(
        "TRIMCP_A2A_JWT_AUDIENCE",
        "trimcp_a2a",
    )

    # --- Phase 3.1: A2A mTLS — client certificate enforcement ---
    # When enabled, the A2A server requires a valid client TLS certificate
    # from connecting agents.  Certificates are validated by SAN or SHA-256
    # fingerprint against an explicit allowlist.
    #
    # TRIMCP_A2A_MTLS_ENABLED           — Master switch (default: false)
    # TRIMCP_A2A_MTLS_ALLOWED_SANS      — Comma-separated list of allowed
    #                                     Subject Alternative Name values
    #                                     (case-insensitive DNS / URI match).
    # TRIMCP_A2A_MTLS_ALLOWED_FINGERPRINTS — Comma-separated list of allowed
    #                                     SHA-256 certificate fingerprints
    #                                     (colon-separated hex, case-insensitive).
    # TRIMCP_A2A_MTLS_STRICT            — When true, reject any connection that
    #                                     does not present a valid client cert
    #                                     (default: true).
    # TRIMCP_A2A_MTLS_TRUSTED_PROXY_HOP — Number of reverse-proxy hops to trust
    #                                     for X-Forwarded-Client-Cert header.
    #                                     0 = only direct TLS (uvicorn SSL).
    #                                     1 = one reverse proxy (Caddy / nginx).
    TRIMCP_A2A_MTLS_ENABLED: bool = os.getenv("TRIMCP_A2A_MTLS_ENABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    TRIMCP_A2A_MTLS_ALLOWED_SANS: list[str] = [
        s.strip().lower()
        for s in os.getenv("TRIMCP_A2A_MTLS_ALLOWED_SANS", "").split(",")
        if s.strip()
    ]
    TRIMCP_A2A_MTLS_ALLOWED_FINGERPRINTS: list[str] = [
        s.strip().lower()
        for s in os.getenv("TRIMCP_A2A_MTLS_ALLOWED_FINGERPRINTS", "").split(",")
        if s.strip()
    ]
    TRIMCP_A2A_MTLS_STRICT: bool = os.getenv("TRIMCP_A2A_MTLS_STRICT", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    TRIMCP_A2A_MTLS_TRUSTED_PROXY_HOP: int = int(
        os.getenv("TRIMCP_A2A_MTLS_TRUSTED_PROXY_HOP", "1")
    )

    # --- Phase 3.2: Per-namespace / per-agent quotas ---
    # When false, no quota queries run on the tool hot path.
    TRIMCP_QUOTAS_ENABLED: bool = os.getenv("TRIMCP_QUOTAS_ENABLED", "true").lower() == "true"
    # Rough chars-per-token for pre-flight estimates (embedding / LLM analog).
    TRIMCP_QUOTA_TOKEN_ESTIMATE_DIVISOR: int = int(
        os.getenv("TRIMCP_QUOTA_TOKEN_ESTIMATE_DIVISOR", "4")
    )

    # --- Consolidation ---
    CONSOLIDATION_DECAY_SOURCES: bool = (
        os.getenv("CONSOLIDATION_DECAY_SOURCES", "false").lower() == "true"
    )
    CONSOLIDATION_CRON_INTERVAL_MINUTES: int = int(
        os.getenv("CONSOLIDATION_CRON_INTERVAL_MINUTES", "360")
    )

    # --- Cron startup jitter ---
    # Maximum random startup delay (seconds) applied before the first cron
    # execution cycle.  Prevents thundering-herd database CPU spikes when
    # multiple TriMCP instances boot simultaneously (e.g. rolling deployment,
    # docker-compose scale).  The jitter is a one-time shift — subsequent
    # interval fires inherit the offset evenly.
    # Set to 0 to disable.
    CRON_STARTUP_JITTER_MAX_SECONDS: float = float(
        os.getenv("CRON_STARTUP_JITTER_MAX_SECONDS", "60.0")
    )

    # --- Phase 1.2: LLM Provider API keys (BYO — no shared platform key [D3]) ---
    # All keys default to empty string; factory logs a warning if the needed
    # key is absent.  Use ref:env/<VAR> in namespace metadata to override
    # per-namespace without touching global config.
    #
    # TRIMCP_ANTHROPIC_API_KEY     — Anthropic Claude (claude-opus-4-6, etc.)
    # TRIMCP_OPENAI_API_KEY        — OpenAI (gpt-5, gpt-4.5-turbo)
    # TRIMCP_AZURE_OPENAI_API_KEY  — Azure OpenAI api-key header
    # TRIMCP_AZURE_OPENAI_ENDPOINT — Azure resource endpoint (required for azure_openai provider)
    # TRIMCP_AZURE_OPENAI_DEPLOYMENT — Default deployment name
    # TRIMCP_GEMINI_API_KEY        — Google AI Studio / Gemini API key
    # TRIMCP_DEEPSEEK_API_KEY      — DeepSeek (cost-sensitive deployments)
    # TRIMCP_MOONSHOT_API_KEY      — Moonshot / Kimi (large-context clusters)
    # TRIMCP_OPENAI_COMPAT_BASE_URL — Base URL for openai_compatible provider
    # TRIMCP_OPENAI_COMPAT_API_KEY  — API key for openai_compatible provider
    # TRIMCP_OPENAI_COMPAT_MODEL    — Default model for openai_compatible provider
    TRIMCP_ANTHROPIC_API_KEY: str = os.getenv("TRIMCP_ANTHROPIC_API_KEY", "")
    TRIMCP_OPENAI_API_KEY: str = os.getenv("TRIMCP_OPENAI_API_KEY", "")
    TRIMCP_AZURE_OPENAI_API_KEY: str = os.getenv("TRIMCP_AZURE_OPENAI_API_KEY", "")
    TRIMCP_AZURE_OPENAI_ENDPOINT: str = os.getenv("TRIMCP_AZURE_OPENAI_ENDPOINT", "")
    TRIMCP_AZURE_OPENAI_DEPLOYMENT: str = os.getenv("TRIMCP_AZURE_OPENAI_DEPLOYMENT", "")
    TRIMCP_GEMINI_API_KEY: str = os.getenv("TRIMCP_GEMINI_API_KEY", "")
    TRIMCP_DEEPSEEK_API_KEY: str = os.getenv("TRIMCP_DEEPSEEK_API_KEY", "")
    TRIMCP_MOONSHOT_API_KEY: str = os.getenv("TRIMCP_MOONSHOT_API_KEY", "")
    TRIMCP_OPENAI_COMPAT_BASE_URL: str = os.getenv("TRIMCP_OPENAI_COMPAT_BASE_URL", "")
    TRIMCP_OPENAI_COMPAT_API_KEY: str = os.getenv("TRIMCP_OPENAI_COMPAT_API_KEY", "")
    TRIMCP_OPENAI_COMPAT_MODEL: str = os.getenv("TRIMCP_OPENAI_COMPAT_MODEL", "")

    # --- Phase 2: Observability (Prometheus + OTel) ---
    TRIMCP_PROMETHEUS_PORT: int = int(os.getenv("TRIMCP_PROMETHEUS_PORT", "8000"))
    TRIMCP_OTEL_EXPORTER_OTLP_ENDPOINT: str = os.getenv(
        "TRIMCP_OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"
    )
    TRIMCP_OTEL_SERVICE_NAME: str = os.getenv("TRIMCP_OTEL_SERVICE_NAME", "trimcp-python")
    TRIMCP_OBSERVABILITY_ENABLED: bool = (
        os.getenv("TRIMCP_OBSERVABILITY_ENABLED", "true").lower() == "true"
    )

    # --- Phase 3: Background Task Poison Pill / Dead Letter Queue ---
    # Maximum times a background task (RQ worker) is retried before the payload
    # is routed to the dead_letter_queue table and removed from the active
    # processing loop.  Set to 0 to disable DLQ routing (all failures retry
    # indefinitely — not recommended for production).
    TASK_MAX_RETRIES: int = int(os.getenv("TASK_MAX_RETRIES", "5"))
    # Redis TTL (seconds) for attempt-count keys.  After this window, a task
    # that has been failing for longer than TTL will restart its attempt
    # counter from 1.  Default 86 400 s = 24 h.
    TASK_DLQ_REDIS_TTL: int = int(os.getenv("TASK_DLQ_REDIS_TTL", "86400"))

    @classmethod
    def validate(cls) -> None:
        """
        Validates environment configuration.
        Strictly halts (raises RuntimeError) if P0 security requirements are missing.
        """
        # P0: Master Key (Required for signing/encryption)
        _fail_unless_trimcp_master_key_ok(cls.TRIMCP_MASTER_KEY)

        # P0: Database connections
        missing_conns = [k for k in ("MONGO_URI", "PG_DSN", "REDIS_URL") if not getattr(cls, k)]
        if missing_conns:
            raise RuntimeError(
                f"CRITICAL CONFIGURATION FAILURE: Missing required connection strings: {', '.join(missing_conns)}"
            )

        # P1: Auth Warnings (Non-halting but noisy)
        if not cls.TRIMCP_API_KEY:
            log.warning(
                "SECURITY WARNING: TRIMCP_API_KEY is not set. "
                "Admin API routes will be inaccessible."
            )

        if not cls.TRIMCP_JWT_SECRET and not cls.TRIMCP_JWT_PUBLIC_KEY:
            log.warning(
                "SECURITY WARNING: Neither TRIMCP_JWT_SECRET nor TRIMCP_JWT_PUBLIC_KEY is set. "
                "A2A sharing will be disabled."
            )


# Module-level singleton — import `cfg` everywhere inside the package.
cfg = _Config()
_fail_unless_trimcp_master_key_ok(cfg.TRIMCP_MASTER_KEY)

# Keep OrchestratorConfig as an alias so server.py and external code that
# already imports it by name doesn't break.
OrchestratorConfig = _Config
