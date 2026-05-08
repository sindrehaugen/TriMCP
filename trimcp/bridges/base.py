"""
Abstract document-bridge provider (TriMCP Enterprise §10.3, Appendix H).

Concrete bridges implement delta enumeration and optional OAuth refresh.
RQ workers import these classes to download files after webhook enqueueing.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any

log = logging.getLogger("trimcp.bridges.base")


class BridgeAuthError(RuntimeError):
    """Raised when bridge credentials are missing or refresh fails."""


class BridgeProvider(ABC):
    """Provider abstraction: OAuth surface + delta walk + file download."""

    @property
    @abstractmethod
    def provider_key(self) -> str:
        """One of: sharepoint | gdrive | dropbox."""

    @abstractmethod
    def bearer_token(self) -> str:
        """Return a valid access token (env, cache, or refreshed)."""

    def refresh_oauth_token(self) -> str:
        """
        Exchange refresh token / MSAL silent / etc.
        Default: no-op; subclasses override when wired to MSAL / google-auth / Dropbox SDK.
        """
        raise BridgeAuthError(
            f"{self.provider_key}: refresh_oauth_token not implemented; set *_BRIDGE_TOKEN env vars"
        )

    @abstractmethod
    def walk_delta(self, context: dict[str, Any]) -> Iterator[dict[str, Any]]:
        """
        Yield change records from the provider delta API using `context`
        (webhook-derived; shape is provider-specific).
        """

    def download_file(self, file_ref: dict[str, Any]) -> bytes:
        """
        Fetch raw file bytes for indexing. `file_ref` is provider-specific metadata.
        """
        raise NotImplementedError(
            f"{self.provider_key}.download_file must be implemented for ingestion"
        )


def redis_client():
    """Shared sync Redis handle for cursors and dedupe (worker + bridges)."""
    from redis import Redis

    from trimcp.config import cfg

    return Redis.from_url(cfg.REDIS_URL)
