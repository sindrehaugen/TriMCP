"""
Shared safe HTTP client utilities.

SafeAsyncClient subclasses httpx.AsyncClient to block requests that resolve
to private, loopback, link-local, reserved, or multicast IP addresses.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse

import httpx


class UnsafeURLError(RuntimeError):
    """Raised when a request targets a private or internal IP address."""


def _check_url_host(hostname: str) -> None:
    """Synchronous check that *hostname* does not resolve to non-public IPs."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        # Unresolvable hosts will fail naturally at connection time.
        return
    for _family, _type, _proto, _canonname, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            raise UnsafeURLError(
                f"Host {hostname!r} resolves to non-public IP {ip_str}"
            )


class SafeAsyncClient(httpx.AsyncClient):
    """httpx.AsyncClient that rejects requests to private/internal networks."""

    async def request(self, method: str, url: Any, **kwargs: Any) -> httpx.Response:
        hostname: str | None = None
        if isinstance(url, str):
            hostname = urlparse(url).hostname
        elif hasattr(url, "host"):
            hostname = url.host
        if hostname:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _check_url_host, hostname)
        return await super().request(method, url, **kwargs)
