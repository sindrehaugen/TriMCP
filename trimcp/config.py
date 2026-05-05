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

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("tri-stack-config")


class _Config:
    # --- Database connections ---
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    PG_DSN:    str = os.getenv("PG_DSN",    "postgresql://mcp_user:mcp_password@localhost:5432/memory_meta")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # --- Redis ---
    REDIS_TTL:             int = int(os.getenv("REDIS_TTL",             "3600"))
    REDIS_MAX_CONNECTIONS: int = int(os.getenv("REDIS_MAX_CONNECTIONS", "20"))

    # --- PostgreSQL connection pool ---
    PG_MIN_POOL: int = int(os.getenv("PG_MIN_POOL", "1"))
    PG_MAX_POOL: int = int(os.getenv("PG_MAX_POOL", "10"))

    # --- Garbage collector ---
    GC_INTERVAL_SECONDS: int = int(os.getenv("GC_INTERVAL_SECONDS",  "3600"))
    GC_ORPHAN_AGE_SECONDS: int = int(os.getenv("GC_ORPHAN_AGE_SECONDS", "300"))

    # --- Embeddings ---
    EMBED_BATCH_CHUNK: int = int(os.getenv("EMBED_BATCH_CHUNK", "64"))
    # Enterprise §8 — hardware backend / OpenVINO NPU (see trimcp.embeddings, openvino_npu_export).
    TRIMCP_BACKEND: str = (os.getenv("TRIMCP_BACKEND") or "").strip().lower()
    TRIMCP_OPENVINO_MODEL_DIR: str = (os.getenv("TRIMCP_OPENVINO_MODEL_DIR") or "").strip()
    TRIMCP_OPENVINO_SEQ_LEN: int = int(os.getenv("TRIMCP_OPENVINO_SEQ_LEN", "512"))

    # --- D2 / D7 — Local cognitive bundle (OpenAI-compatible HTTP on port 11435) ---
    # When TRIMCP_COGNITIVE_BASE_URL is set (e.g. http://cognitive:11435), embeddings
    # route to POST {base}/v1/embeddings unless TRIMCP_BACKEND selects an in-process backend.
    TRIMCP_COGNITIVE_BASE_URL: str = (os.getenv("TRIMCP_COGNITIVE_BASE_URL") or "").strip().rstrip("/")
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
    BRIDGE_WEBHOOK_BASE_URL: str = (os.getenv("BRIDGE_WEBHOOK_BASE_URL", "").rstrip("/"))
    AZURE_CLIENT_ID: str = os.getenv("AZURE_CLIENT_ID", "")
    AZURE_CLIENT_SECRET: str = os.getenv("AZURE_CLIENT_SECRET", "")
    AZURE_TENANT_ID: str = os.getenv("AZURE_TENANT_ID", "common")
    BRIDGE_OAUTH_REDIRECT_URI: str = os.getenv("BRIDGE_OAUTH_REDIRECT_URI", "http://127.0.0.1:8765/bridge/oauth/callback")
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
    #                     Server must refuse to start if this is missing/empty [D 0.2].
    TRIMCP_API_KEY: str = os.getenv("TRIMCP_API_KEY", "")
    TRIMCP_ADMIN_USERNAME: str = os.getenv("TRIMCP_ADMIN_USERNAME", "")
    TRIMCP_ADMIN_PASSWORD: str = os.getenv("TRIMCP_ADMIN_PASSWORD", "")
    TRIMCP_MASTER_KEY: str = os.getenv("TRIMCP_MASTER_KEY", "")

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

    # --- Phase 3.2: Per-namespace / per-agent quotas ---
    # When false, no quota queries run on the tool hot path.
    TRIMCP_QUOTAS_ENABLED: bool = os.getenv("TRIMCP_QUOTAS_ENABLED", "true").lower() == "true"
    # Rough chars-per-token for pre-flight estimates (embedding / LLM analog).
    TRIMCP_QUOTA_TOKEN_ESTIMATE_DIVISOR: int = int(
        os.getenv("TRIMCP_QUOTA_TOKEN_ESTIMATE_DIVISOR", "4")
    )

    # --- Consolidation ---
    CONSOLIDATION_DECAY_SOURCES: bool = os.getenv("CONSOLIDATION_DECAY_SOURCES", "false").lower() == "true"

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
    TRIMCP_ANTHROPIC_API_KEY:          str = os.getenv("TRIMCP_ANTHROPIC_API_KEY",          "")
    TRIMCP_OPENAI_API_KEY:             str = os.getenv("TRIMCP_OPENAI_API_KEY",             "")
    TRIMCP_AZURE_OPENAI_API_KEY:       str = os.getenv("TRIMCP_AZURE_OPENAI_API_KEY",       "")
    TRIMCP_AZURE_OPENAI_ENDPOINT:      str = os.getenv("TRIMCP_AZURE_OPENAI_ENDPOINT",      "")
    TRIMCP_AZURE_OPENAI_DEPLOYMENT:    str = os.getenv("TRIMCP_AZURE_OPENAI_DEPLOYMENT",    "")
    TRIMCP_GEMINI_API_KEY:             str = os.getenv("TRIMCP_GEMINI_API_KEY",             "")
    TRIMCP_DEEPSEEK_API_KEY:           str = os.getenv("TRIMCP_DEEPSEEK_API_KEY",           "")
    TRIMCP_MOONSHOT_API_KEY:           str = os.getenv("TRIMCP_MOONSHOT_API_KEY",           "")
    TRIMCP_OPENAI_COMPAT_BASE_URL:     str = os.getenv("TRIMCP_OPENAI_COMPAT_BASE_URL",     "")
    TRIMCP_OPENAI_COMPAT_API_KEY:      str = os.getenv("TRIMCP_OPENAI_COMPAT_API_KEY",      "")
    TRIMCP_OPENAI_COMPAT_MODEL:        str = os.getenv("TRIMCP_OPENAI_COMPAT_MODEL",        "")

    @classmethod
    def validate(cls) -> None:
        """Warn on startup if required env vars are not set (uses insecure defaults)."""
        missing = [k for k in ("MONGO_URI", "PG_DSN", "REDIS_URL") if not os.getenv(k)]
        if missing:
            log.warning(
                "Using default connection strings for: %s. "
                "Set these env vars for production.",
                ", ".join(missing),
            )
        if not os.getenv("TRIMCP_API_KEY"):
            log.warning(
                "TRIMCP_API_KEY is not set. "
                "All /api/* routes will reject every request until it is configured."
            )
        if not os.getenv("TRIMCP_JWT_SECRET") and not os.getenv("TRIMCP_JWT_PUBLIC_KEY"):
            log.warning(
                "Neither TRIMCP_JWT_SECRET nor TRIMCP_JWT_PUBLIC_KEY is set. "
                "JWTAuthMiddleware will reject all requests until one is configured."
            )


# Module-level singleton — import `cfg` everywhere inside the package.
cfg = _Config()

# Keep OrchestratorConfig as an alias so server.py and external code that
# already imports it by name doesn't break.
OrchestratorConfig = _Config
