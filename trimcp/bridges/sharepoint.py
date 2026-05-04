"""
SharePoint / OneDrive via Microsoft Graph — delta + subscriptions (§10.3, Appendix H.3).
"""
from __future__ import annotations

import logging
from typing import Any, Iterator, Optional

import httpx

from trimcp.bridges.base import BridgeAuthError, BridgeProvider, redis_client
from trimcp.config import cfg

log = logging.getLogger("trimcp.bridges.sharepoint")

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"


def parse_sites_drives_resource(resource: str) -> Optional[tuple[str, str]]:
    """Parse `sites/{site-id}/drives/{drive-id}/root` → (site_id, drive_id)."""
    parts = resource.strip("/").split("/")
    if len(parts) >= 4 and parts[0] == "sites" and parts[2] == "drives":
        return parts[1], parts[3]
    return None


class SharePointBridge(BridgeProvider):
    """Graph delta walk for SharePoint drives."""

    @property
    def provider_key(self) -> str:
        return "sharepoint"

    def bearer_token(self) -> str:
        token = (cfg.GRAPH_BRIDGE_TOKEN or "").strip()
        if not token:
            try:
                return self.refresh_oauth_token()
            except BridgeAuthError:
                raise
        return token

    def walk_delta(self, context: dict[str, Any]) -> Iterator[dict[str, Any]]:
        notifications = context.get("notifications") or []
        seen: set[tuple[str, str]] = set()
        for n in notifications:
            resource = n.get("resource") or ""
            parsed = parse_sites_drives_resource(resource)
            if not parsed:
                log.warning("SharePoint: cannot parse resource=%r", resource)
                continue
            site_id, drive_id = parsed
            key = (site_id, drive_id)
            if key in seen:
                continue
            seen.add(key)
            yield from self._delta_pages(site_id, drive_id)

    def _cursor_key(self, site_id: str, drive_id: str) -> str:
        return f"bridge:cursor:sharepoint:{site_id}:{drive_id}"

    def _delta_pages(self, site_id: str, drive_id: str) -> Iterator[dict[str, Any]]:
        r = redis_client()
        ck = self._cursor_key(site_id, drive_id)
        stored = r.get(ck)
        headers = {"Authorization": f"Bearer {self.bearer_token()}"}
        if stored:
            url: str | None = stored.decode("utf-8")
        else:
            url = f"{GRAPH_ROOT}/sites/{site_id}/drives/{drive_id}/root/delta"
        with httpx.Client(timeout=60.0, headers=headers, follow_redirects=True) as client:
            while url:
                resp = client.get(url)
                if resp.status_code == 401:
                    raise BridgeAuthError("Microsoft Graph returned 401 — refresh or set GRAPH_BRIDGE_TOKEN")
                resp.raise_for_status()
                payload = resp.json()
                for item in payload.get("value", []):
                    yield item
                next_link = payload.get("@odata.nextLink")
                delta_link = payload.get("@odata.deltaLink")
                if delta_link:
                    r.set(ck, delta_link)
                if next_link:
                    url = next_link
                else:
                    url = None

    def download_file(self, file_ref: dict[str, Any]) -> bytes:
        site_id = file_ref["site_id"]
        drive_id = file_ref["drive_id"]
        item_id = file_ref["item_id"]
        u = f"{GRAPH_ROOT}/sites/{site_id}/drives/{drive_id}/items/{item_id}/content"
        headers = {"Authorization": f"Bearer {self.bearer_token()}"}
        with httpx.Client(timeout=120.0, headers=headers, follow_redirects=True) as client:
            resp = client.get(u)
            resp.raise_for_status()
            return resp.content


def process_sharepoint_event(payload: dict[str, Any]) -> dict[str, Any]:
    """RQ entrypoint: run delta walk for notifications in payload."""
    bridge = SharePointBridge()
    count = 0
    try:
        for item in bridge.walk_delta({"notifications": payload.get("notifications", [])}):
            count += 1
            if item.get("deleted"):
                log.info("SharePoint delta: deleted id=%s", item.get("id"))
            elif item.get("file"):
                log.info(
                    "SharePoint delta: file name=%s id=%s",
                    item.get("name"),
                    item.get("id"),
                )
    except BridgeAuthError as e:
        log.error("%s", e)
        return {"status": "error", "error": str(e)}
    return {"status": "ok", "items_seen": count}
