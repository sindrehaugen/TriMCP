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


# Module-level singleton — import `cfg` everywhere inside the package.
cfg = _Config()

# Keep OrchestratorConfig as an alias so server.py and external code that
# already imports it by name doesn't break.
OrchestratorConfig = _Config
