"""
Provider renewal calls for expiring bridge subscriptions (§10.7, Appendix H.6).
On failure callers mark the row `DEGRADED`.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
import asyncpg
import httpx

from trimcp.config import cfg

log = logging.getLogger("trimcp.bridge_renewal")

GRAPH = "https://graph.microsoft.com/v1.0"
DRIVE = "https://www.googleapis.com/drive/v3"


def parse_graph_datetime(value: str) -> datetime:
    s = str(value).replace("Z", "+00:00")
    return datetime.fromisoformat(s)


def _graph_expiration_iso(minutes: int = 4200) -> str:
    """~Graph max ~4230 minutes for drive resource subscriptions."""
    exp = datetime.now(timezone.utc) + timedelta(minutes=min(4200, minutes))
    return exp.replace(microsecond=0).isoformat().replace("+00:00", "Z")


async def renew_sharepoint(pool: asyncpg.Pool, row: asyncpg.Record) -> None:
    sub_ext = row["subscription_id"]
    if not sub_ext:
        raise RuntimeError("sharepoint renewal requires subscription_id (Graph subscription id)")
    token = (cfg.GRAPH_BRIDGE_TOKEN or "").strip()
    if not token:
        raise RuntimeError("GRAPH_BRIDGE_TOKEN not configured")

    exp_iso = _graph_expiration_iso()
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.patch(
            f"{GRAPH}/subscriptions/{sub_ext}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"expirationDateTime": exp_iso},
        )
        if r.status_code == 404:
            raise RuntimeError("Graph subscription not found (404)")
        r.raise_for_status()
        data = r.json()
        new_exp = data.get("expirationDateTime")
        if not new_exp:
            raise RuntimeError("Graph PATCH subscription: missing expirationDateTime")

    expires_at = parse_graph_datetime(str(new_exp))
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE bridge_subscriptions
            SET expires_at = $2, updated_at = NOW(), status = 'ACTIVE'
            WHERE id = $1
            """,
            row["id"],
            expires_at,
        )
    log.info("Renewed SharePoint subscription bridge_id=%s until %s", row["id"], new_exp)


async def renew_gdrive(pool: asyncpg.Pool, row: asyncpg.Record) -> None:
    """
    Drive cannot PATCH watches — stop old channel, register a new watch (Appendix H.4).
    Expects subscription_id = channel id (our UUID), resource_id = Google's resourceId.
    """
    base = (cfg.BRIDGE_WEBHOOK_BASE_URL or "").rstrip("/")
    if not base:
        raise RuntimeError("BRIDGE_WEBHOOK_BASE_URL not set — cannot renew Drive watch")

    token = (cfg.GDRIVE_BRIDGE_TOKEN or "").strip()
    if not token:
        raise RuntimeError("GDRIVE_BRIDGE_TOKEN not configured")

    old_chan = row["subscription_id"]
    old_resource = row["resource_id"]
    if not old_chan or not old_resource:
        raise RuntimeError("gdrive renewal requires subscription_id (channel id) and resource_id (Google resourceId)")

    state = row["client_state"] or ""
    new_chan = str(uuid.uuid4())
    expiration_ms = int((datetime.now(timezone.utc) + timedelta(days=6, hours=23)).timestamp() * 1000)
    watch_payload = {
        "id": new_chan,
        "type": "web_hook",
        "address": f"{base}/webhooks/drive",
        "token": state,
        "expiration": expiration_ms,
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        r_stop = await client.post(
            f"{DRIVE}/channels/stop",
            headers=headers,
            json={"id": old_chan, "resourceId": old_resource},
        )
        if r_stop.status_code not in (200, 204):
            log.warning(
                "Drive channels/stop non-success: %s %s",
                r_stop.status_code,
                r_stop.text[:200],
            )

        r = await client.post(
            f"{DRIVE}/changes/watch",
            headers=headers,
            json=watch_payload,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Drive changes/watch failed: {r.status_code} {r.text[:300]}")

        data = r.json()
        new_resource = data.get("resourceId")
        exp_ms = data.get("expiration")
        if not new_resource or not exp_ms:
            raise RuntimeError("Drive watch response missing resourceId or expiration")

    expires_at = datetime.fromtimestamp(int(exp_ms) / 1000.0, tz=timezone.utc)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE bridge_subscriptions
            SET subscription_id = $2,
                resource_id = $3,
                expires_at = $4,
                status = 'ACTIVE',
                updated_at = NOW()
            WHERE id = $1
            """,
            row["id"],
            new_chan,
            new_resource,
            expires_at,
        )
    log.info("Renewed Google Drive watch bridge_id=%s", row["id"])


async def renew_dropbox(_pool: asyncpg.Pool, row: asyncpg.Record) -> None:
    """Dropbox has no subscription expiry; optional no-op to refresh updated_at."""
    log.debug("Dropbox bridge_id=%s — no subscription renewal (cursor only)", row["id"])


async def mark_degraded(pool: asyncpg.Pool, bridge_id, reason: str) -> None:
    log.error("Marking bridge DEGRADED id=%s reason=%s", bridge_id, reason)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE bridge_subscriptions
            SET status = 'DEGRADED', updated_at = NOW()
            WHERE id = $1
            """,
            bridge_id,
        )


async def renew_expiring_subscriptions(pool: asyncpg.Pool) -> dict[str, int]:
    """
    Find ACTIVE rows whose expires_at is within BRIDGE_RENEWAL_LOOKAHEAD_HOURS,
    renew per provider, mark DEGRADED on any failure.
    """
    lookahead = timedelta(hours=max(1, cfg.BRIDGE_RENEWAL_LOOKAHEAD_HOURS))
    renewed = 0
    failed = 0
    skipped = 0

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM bridge_subscriptions
            WHERE status = 'ACTIVE'
              AND expires_at IS NOT NULL
              AND expires_at < NOW() + $1::interval
            ORDER BY expires_at ASC
            LIMIT 100
            """,
            lookahead,
        )

    for row in rows:
        prov = row["provider"]
        try:
            if prov == "sharepoint":
                await renew_sharepoint(pool, row)
                renewed += 1
            elif prov == "gdrive":
                await renew_gdrive(pool, row)
                renewed += 1
            elif prov == "dropbox":
                await renew_dropbox(pool, row)
                skipped += 1
            else:
                skipped += 1
        except Exception as e:
            log.exception("Renewal failed for bridge %s", row["id"])
            await mark_degraded(pool, row["id"], str(e))
            failed += 1

    return {"renewed": renewed, "failed": failed, "skipped": skipped, "candidates": len(rows)}
