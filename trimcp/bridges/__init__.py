"""
Document bridge providers (SharePoint / Google Drive / Dropbox).

RQ worker imports `dispatch_bridge_event` from here, or the concrete
`SharePointBridge`, `GoogleDriveBridge`, `DropboxBridge` classes to download files.
"""

from __future__ import annotations

from typing import Any

from trimcp.bridges.base import BridgeAuthError, BridgeProvider, redis_client
from trimcp.bridges.dropbox import DropboxBridge, process_dropbox_event
from trimcp.bridges.gdrive import GoogleDriveBridge, process_gdrive_event
from trimcp.bridges.sharepoint import SharePointBridge, process_sharepoint_event

__all__ = [
    "BridgeAuthError",
    "BridgeProvider",
    "DropboxBridge",
    "GoogleDriveBridge",
    "SharePointBridge",
    "dispatch_bridge_event",
    "process_dropbox_event",
    "process_gdrive_event",
    "process_sharepoint_event",
    "redis_client",
]


def dispatch_bridge_event(provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Synchronous fan-in from `trimcp.tasks.process_bridge_event` (RQ worker).
    `provider` is one of: sharepoint, gdrive, dropbox.
    """
    p = provider.strip().lower()
    if p == "sharepoint":
        return process_sharepoint_event(payload)
    if p in ("gdrive", "google_drive", "drive"):
        return process_gdrive_event(payload)
    if p == "dropbox":
        return process_dropbox_event(payload)
    raise ValueError(f"Unknown bridge provider: {provider!r}")
