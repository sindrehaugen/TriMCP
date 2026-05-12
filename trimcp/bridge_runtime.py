"""
Sync entrypoints for bridge workers (RQ) — fetch OAuth tokens encrypted at rest.
"""

from __future__ import annotations

import asyncio
import logging
import os

from trimcp import bridge_repo
from trimcp.bridge_renewal import ensure_fresh_oauth_token
from trimcp.orchestrator import TriStackEngine

log = logging.getLogger("trimcp.bridge_runtime")

# Hard deadline for the entire token-resolution path (DB fetch + decrypt).
# External bridges (SharePoint, GDrive, Dropbox) are called from bridge workers;
# if the upstream OAuth exchange or DB query hangs, we must not tie up asyncio
# workers indefinitely.  Default: 10 s.  Override via BRIDGE_RESOLVE_TIMEOUT_S.
_RESOLVE_TIMEOUT_S: float = float(os.environ.get("BRIDGE_RESOLVE_TIMEOUT_S", "10"))


def resolve_stored_oauth_access_token(
    provider: str,
    *,
    client_state: str | None = None,
    subscription_id: str | None = None,
    resource_id: str | None = None,
) -> str | None:
    """Load and decrypt OAuth access token from ``bridge_subscriptions`` (if present).

    Raises ``asyncio.TimeoutError`` (surfaced as a logged warning) if the
    operation exceeds ``BRIDGE_RESOLVE_TIMEOUT_S`` (default 10 s).  Returns
    ``None`` on timeout or any other failure so the caller can degrade
    gracefully rather than blocking the worker indefinitely.
    """
    if not any((client_state, subscription_id, resource_id)):
        return None

    async def _run() -> str | None:
        engine = TriStackEngine()
        await engine.connect()
        try:
            async with engine.pg_pool.acquire(timeout=10.0) as conn:
                row = await bridge_repo.fetch_active_subscription(
                    conn,
                    provider,
                    client_state=client_state,
                    subscription_id=subscription_id,
                    resource_id=resource_id,
                )
            if not row:
                return None
            try:
                return await ensure_fresh_oauth_token(engine.pg_pool, row, "")
            except Exception as e:
                log.warning("Stored bridge OAuth token fetch/refresh failed: %s", e)
                return None
        finally:
            await engine.disconnect()

    async def _run_with_timeout() -> str | None:
        try:
            return await asyncio.wait_for(_run(), timeout=_RESOLVE_TIMEOUT_S)
        except TimeoutError:
            log.warning(
                "resolve_stored_oauth_access_token timed out after %.1fs for "
                "provider=%r — upstream vendor did not respond. "
                "Returning None so worker can degrade gracefully.",
                _RESOLVE_TIMEOUT_S,
                provider,
            )
            return None
        except Exception as exc:
            log.warning(
                "resolve_stored_oauth_access_token failed for provider=%r: %s",
                provider,
                exc,
            )
            return None

    return asyncio.run(_run_with_timeout())
